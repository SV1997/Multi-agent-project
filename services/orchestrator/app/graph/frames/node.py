"""The query-frame step of the graph: decide what kind of question this is, before any search happens.

Why this file exists: this is where the examiner's three notes meet. The taxonomy says which part of the
policy documents each category covers; a frame says which categories a kind of question needs; this step picks
the frame for the user's actual question. After it, retrieval can be told to look only in those categories, the
answering prompt can say "stay inside this part", and a question that lacks a needed fact (which leave type?)
can be answered with a clarifying question instead of a guess.

Problem it solves: hallucination from searching, and borrowing a rule from, the wrong part of the policy.

How it works: the model sees a closed, numbered menu of this domain's frames and returns a NUMBER, the slot
values the user gave, and a standalone version of the question. Ordinary code then checks all of it
(selection.py): a bad number becomes "<domain>.other", an unsaid slot value is dropped, an invented number in
the rewrite is refused. If the model fails, there is no frame and the question is answered exactly as it would
be with LOCALIZE=off. With LOCALIZE=off the step does nothing at all.

Counters (FRAME_STATS) are kept for calls, successes, model failures, invalid choices, dropped slots, refused
rewrites and questions asked, and a one-line summary is logged for every question.
"""
import logging
from collections import defaultdict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel

from .selection import menu_text, frame_by_number, ground_slots, missing_required, guard_rewrite

logger = logging.getLogger(__name__)

FRAME_STATS = defaultdict(int)
CONVERSATION_WINDOW = 6          # how many earlier messages the model gets to see

# What this step leaves in the state. It is returned on EVERY run, so a frame can never leak from one turn into the next.
NO_FRAME = {
    "frame_id": None,
    "frame_slots": None,
    "missing_slots": None,
    "clarifying_question": None,
    "rewritten_query": None,
    "localize_categories": None,
    "query_dag": None,
    "asked_frame_id": None,            # the frame that asked the user a question; kept for exactly one turn (see frame_query)
}


class SlotValue(BaseModel):
    name: str
    value: str


class FrameChoice(BaseModel):
    number: int
    slots: list[SlotValue]
    standalone_query: str


def system_prompt(domain: str, menu: str) -> str:
    return (
        f"You sort a user's question about {domain} policies into one \"frame\": a kind of question.\n\n"
        f"Frames (choose by NUMBER):\n{menu}\n\n"
        "Rules:\n"
        "1. Choose the frame that best fits the user's LATEST message. Earlier messages only help with follow-ups. "
        f"If no frame fits, choose the number of {domain}.other.\n"
        "2. Fill slots only for the frame you chose. Copy each slot value in the user's own words. "
        "If the user did not say it, leave that slot out. Never guess.\n"
        "3. standalone_query: rewrite the latest message so it makes sense without the conversation "
        "(resolve words like \"it\" or \"that\"). Keep every name, number and date exactly as said. "
        "Do not answer the question and do not add anything that was not said."
    )


def _is_plain_turn(message) -> bool:
    if isinstance(message, HumanMessage):
        return True
    return isinstance(message, AIMessage) and bool(message.content) and not getattr(message, "tool_calls", None)


def latest_message(state) -> str:
    humans = [m for m in state.get("messages", []) if isinstance(m, HumanMessage)]
    return str(humans[-1].content) if humans else ""


def _earlier_turns(state) -> list:
    """The few messages before the newest user message, user and assistant turns only."""
    messages = list(state.get("messages", []))
    last_human = max((i for i, m in enumerate(messages) if isinstance(m, HumanMessage)), default=len(messages))
    return [m for m in messages[:last_human] if _is_plain_turn(m)][-CONVERSATION_WINDOW:]


def _memory_texts(state) -> list[str]:
    texts = []
    for key in ("conversation_memories", "long_term_memory", "thread_facts"):
        value = state.get(key)
        if isinstance(value, (list, tuple)):
            texts.extend(str(v) for v in value if v)
        elif value and value != "none":
            texts.append(str(value))
    return texts


def grounding_sources(state, message: str) -> list[str]:
    """What the user is known to have said: their recent messages, this one, and the memories about them.
    The assistant's own replies are left out on purpose (see selection.py)."""
    earlier_user = [str(m.content) for m in _earlier_turns(state) if isinstance(m, HumanMessage)]
    return earlier_user + [message] + _memory_texts(state)


def _render(turns) -> str:
    lines = [f"{'User' if isinstance(m, HumanMessage) else 'Assistant'}: {m.content}" for m in turns]
    return "\n".join(lines) or "(none)"


def make_frame_query_node(registry, choosers, level=lambda: "off"):
    """The graph node.

    registry  FrameRegistry (may be None while LOCALIZE is off)
    choosers  [(label, runnable)] tried in order; each runnable's ainvoke(messages) returns a FrameChoice
    level     function returning the current LOCALIZE level, so it can be changed in tests
    """
    async def frame_query(state) -> dict:
        current = level()
        if current == "off" or registry is None:
            return dict(NO_FRAME)

        domain = state.get("domain")
        frames = registry.menu(domain)
        message = latest_message(state)
        if not frames or not message:
            return dict(NO_FRAME)

        FRAME_STATS["calls"] += 1
        memories = _memory_texts(state)
        # If the previous reply asked the user a question on behalf of a frame, say so: a short answer like "I am
        # still on probation" says nothing about the topic by itself, and the model should stay with that frame.
        asked = state.get("asked_frame_id")
        follow_up = ""
        if asked and any(f.frame_id == asked for f in frames):
            follow_up = (f"Note: your previous reply asked the user for a missing detail needed by frame {asked}. "
                         f"If the latest message answers that question, choose that same frame.\n\n")
        prompt = [
            SystemMessage(content=system_prompt(domain, menu_text(frames))),
            HumanMessage(content=(
                "Memories about this user:\n" + ("\n".join(memories) or "(none)") + "\n\n"
                "Conversation so far:\n" + _render(_earlier_turns(state)) + "\n\n"
                + follow_up +
                "Latest message: " + message
            )),
        ]

        choice = None
        for label, chooser in choosers:
            try:
                choice = await chooser.ainvoke(prompt)
                break
            except Exception as e:
                logger.warning("Frame choice failed (%s): %s: %s", label, type(e).__name__, str(e)[:150])
        if choice is None:
            FRAME_STATS["llm_failures"] += 1
            logger.warning("No frame for %r: the model could not choose; answering as if localization were off", message[:80])
            return dict(NO_FRAME)

        frame, valid = frame_by_number(frames, choice.number)
        if not valid:
            FRAME_STATS["invalid_choices"] += 1
        sources = grounding_sources(state, message)
        kept, dropped = ground_slots(frame, [(s.name, s.value) for s in choice.slots], sources)
        FRAME_STATS["slots_dropped"] += len(dropped)
        missing = missing_required(frame, kept)
        query, rewrite_problem = guard_rewrite(choice.standalone_query, message, sources)
        if rewrite_problem and rewrite_problem != "empty":
            FRAME_STATS["rewrites_rejected"] += 1

        question = None
        if missing and current == "full":
            question = frame.required_slots[missing[0]]
            FRAME_STATS["asked"] += 1
        FRAME_STATS["ok"] += 1
        logger.info("Frame %s (number %r%s) | slots kept %s, dropped %s | missing %s | rewrite %s | asking %s",
                    frame.frame_id, choice.number, "" if valid else ", INVALID -> other", kept,
                    [(n, r) for n, _, r in dropped], missing, rewrite_problem or "used", bool(question))

        return {
            "frame_id": frame.frame_id,
            "frame_slots": kept,
            "missing_slots": missing,
            "clarifying_question": question,
            "rewritten_query": query if query != message else None,
            "localize_categories": list(frame.categories) or None,
            "query_dag": None,                 # cleared here; the trace step fills it in once the answer is known
            "asked_frame_id": frame.frame_id if question else None,
        }

    return frame_query


def route_after_authorization(state) -> str:
    """Denied users stop here; everyone else goes to the frame step."""
    return "denied" if state.get("authorization_denied") else "frame"


def route_after_frame(state) -> str:
    """Ask the clarifying question if the frame step produced one, otherwise on to the domain's agent."""
    return "ask" if state.get("clarifying_question") else state["domain"]


def ask_for_slot(state) -> dict:
    """Answer with the clarifying question and stop: no search is done for a question that cannot be answered yet.
    The user's reply comes in as the next message, and the frame step runs again with it in the conversation."""
    question = state["clarifying_question"]
    return {
        "messages": [AIMessage(content=question)],
        "final_answer": {
            "domain": state.get("domain"),
            "answer": question,
            "sources": [],
            "context": [],
            "confidence": 1.0,
            "requires_human_review": False,
        },
        "requires_human_review": False,
    }
