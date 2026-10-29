"""The query-frame step: decide what kind of question this is, before any search happens.

A frame is a named kind of question tied to the policy categories that can answer it (frames.yaml). One model call
picks a frame number from a numbered menu. The frame's categories are then expanded down the DAG, so a frame that
names a parent category also searches its children. The result goes into the state: the categories the search is
narrowed to, and the scope sentence the answering model is given.
"""
import logging

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from shared.taxonomy.taxonomy import expand_with_descendants, load_taxonomy, parents_family
from ...core import config
from .prompts import scope_prompt
from .registry import load_registry
from .selection import frame_by_number, menu_text

logger = logging.getLogger(__name__)


class FrameChoice(BaseModel):
    number: int


def build_chooser():
    """Built when a question arrives, not at import, so nothing needs an API key while LOCALIZE is off."""
    return (
        init_chat_model(model="groq:openai/gpt-oss-120b", temperature=0, streaming=False, reasoning_effort="low")
        .with_structured_output(FrameChoice, method="json_schema", strict=True)
        .with_config(tags=["frame-choice"])
        .with_retry(stop_after_attempt=2)
    )


def latest_message(state) -> str:
    """The newest user message is the question the frame is chosen for."""
    humans = [message for message in state.get("messages", []) if isinstance(message, HumanMessage)]
    return str(humans[-1].content) if humans else ""


def choose_frame(frames: list, domain: str, question: str):
    """Searching without a filter is safe, so a failed call or a bad number must mean "no frame", not a guess."""
    system = (
        f"You sort a user's question about {domain} policies into one frame: a kind of question.\n\n"
        f"Frames (answer with the NUMBER):\n{menu_text(frames)}\n\n"
        "Choose the frame that best fits the question. If no frame fits, answer -1."
    )
    try:
        choice = build_chooser().invoke([("system", system), ("human", question)])
    except Exception:
        logger.exception("Frame choice failed; the question will be searched without a filter")
        return None
    return frame_by_number(frames, choice.number)


def frame_query_node(state) -> dict:
    """Runs once per question before the domain agent, so the search and the answer both stay inside one frame."""
    if config.LOCALIZE == "off" or state.get("authorization_denied"):
        return {}
    domain, question = state["domain"], latest_message(state)
    taxonomy = load_taxonomy()
    frames = load_registry(taxonomy).get(domain, [])
    frame = choose_frame(frames, domain, question) if frames and question else None
    categories, wider, scope = [], [], None
    if frame is not None:
        categories = expand_with_descendants(taxonomy, domain, frame.categories)
        wider = parents_family(taxonomy, domain, categories)          # level 1, tried only if level 0 finds nothing
        scope = scope_prompt(taxonomy, frame)
    logger.info("frame %s | categories %s | question %r", frame.frame_id if frame else None, categories, question[:100])
    return {
        "localize_frame_id": frame.frame_id if frame else None,
        "localize_categories": categories or None,          # level 0; None = no filter
        "localize_wider_categories": wider or None,         # level 1; level 2 is the whole domain
        "localize_scope": scope,
        "localize_fallback_used": None,
        "localize_fallback_level": None,
    }


def debug_payload(values: dict):
    """Shows the frame decision next to the answer, so the demo can point at the frame, the categories and how far the search had to widen."""
    if not values or not values.get("localize_frame_id"):
        return None
    return {
        "frame_id": values["localize_frame_id"],
        "categories": values.get("localize_categories"),
        "wider_categories": values.get("localize_wider_categories"),
        "fallback_used": values.get("localize_fallback_used"),
        "fallback_level": values.get("localize_fallback_level"),
    }
