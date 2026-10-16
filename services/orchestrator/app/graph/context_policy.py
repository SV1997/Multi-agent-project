from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

SUMMARIZE_THRESHOLD = 12
KEEP_RAW_TURNS = 5
LEDGER_LABEL="[Conversation notes]"
SUMMARY_PROMPT = (
    """You maintain a running notes ledger for a conversation.

You get EXISTING NOTES (may be empty) and NEW MESSAGES.
Return the updated notes.

Rules:
1. Copy every line of EXISTING NOTES forward unchanged, unless a new message
   explicitly corrects or replaces it. Never shorten or merge existing lines.
2. Add one line per new item from NEW MESSAGES.
3. Keep identifiers exactly as written: names, numbers, ticket or claim IDs,
   dates, amounts, seat and office locations. Do not paraphrase them.
4. Record what the user asked, what the assistant answered, and what is unresolved.
5. No commentary. Use exactly these sections:

FACTS:
DECISIONS:
IDENTIFIERS AND DATES:
OPEN QUESTIONS:"""
)

def is_ledger(message)-> bool:
       return isinstance(message, SystemMessage) and str(message.content).startswith(LEDGER_LABEL)

def ledger_text(message)->str:
       return str(message.content[len(LEDGER_LABEL):]).strip()

def render(message)->str:
       lines= []
       for m in message:
              if isinstance(m,HumanMessage):
                     lines.append(f"User: {m.content}")
              elif isinstance(m,AIMessage) and m.content and not getattr(m,"tool_calls",None):
                    lines.append(f"Assisstant: {m.content}") 
       return "\n".join(lines)

import re

IDENTIFIER_PATTERN = re.compile(r"\b[\w-]*\d[\w-]*\b")


def missing_identifiers(old_notes: str, new_notes: str) -> list[str]:
    old_ids = set(IDENTIFIER_PATTERN.findall(old_notes))
    return sorted(i for i in old_ids if i not in new_notes)


def guard_notes(old_notes: str, new_notes: str) -> tuple[str, list[str]]:
    missing = missing_identifiers(old_notes, new_notes)
    if not missing:
        return new_notes, []
    recovered = [line for line in old_notes.splitlines() if any(i in line for i in missing)]
    return new_notes + "\n\nRECOVERED:\n" + "\n".join(recovered), missing

def split_for_summary(messages):
    human_turns = [m for m in messages if isinstance(m, HumanMessage)]
    if len(human_turns) <= SUMMARIZE_THRESHOLD:
        return None
    cut = messages.index(human_turns[-KEEP_RAW_TURNS])
    ledger = next((m for m in messages if is_ledger(m)), None)
    to_compress = [m for m in messages[:cut] if not is_ledger(m)]
    to_remove = to_compress + ([ledger] if ledger else [])
    return ledger, to_compress, to_remove

async def summarize(llm,old_ledger, new_messages, prompt=SUMMARY_PROMPT) -> str:
    human = HumanMessage(content=f"EXISTING NOTES: \n{old_ledger or '(empty)'}\n\n New Messages:\n{render(new_messages)}")
    result = await llm.ainvoke([SystemMessage(content=prompt), human])
    return result.content