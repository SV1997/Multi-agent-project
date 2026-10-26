"""The plain rules that sit around the model's choice of a frame.

Why this file exists: the model proposes a frame number, slot values and a rewritten query, but a model can be
wrong or can make things up. Everything it returns is checked by ordinary code before anything depends on it.
These checks are small pure functions so each rule can be tested on its own, without a model.

Problems it solves:
  - a number that is not on the menu must not select anything (it falls back to "<domain>.other");
  - a slot value (say, leave_type = "maternity") is only trusted if the user actually said it, or it is in
    their stored memories - a guessed value would send the search to the wrong category;
  - a rewritten query must not contain a number or ID that appears nowhere in the context.

"Said by the user" means the user's own messages plus the memories about them. The assistant's earlier replies
do not count: otherwise the assistant could supply a slot value by mentioning it first.
"""
import re

from .models import Frame

WORD = re.compile(r"[^\W_]+")


def words(text) -> set[str]:
    """Lowercase words and numbers of a text: 'EMP-10492, B-14' -> {'emp', '10492', 'b', '14'}."""
    return set(WORD.findall(str(text).casefold()))


def number_words(text) -> set[str]:
    """The words that contain a digit (numbers, IDs, dates)."""
    return {w for w in words(text) if any(ch.isdigit() for ch in w)}


def menu_text(frames: list[Frame]) -> str:
    """The numbered menu the model chooses from, one line per frame, with the slots each frame can fill."""
    lines = []
    for number, frame in enumerate(frames):
        slots = [f"{name} (required)" for name in frame.required_slots] + list(frame.optional_slots)
        note = f"  [slots: {', '.join(slots)}]" if slots else ""
        lines.append(f"{number}. {frame.frame_id}: {frame.description}{note}")
    return "\n".join(lines)


def frame_by_number(frames: list[Frame], number) -> tuple[Frame, bool]:
    """(frame, True) for a valid menu number; (the "other" frame, False) for anything else.

    The last frame of every menu is "<domain>.other". bool is excluded because True would count as 1.
    """
    if isinstance(number, int) and not isinstance(number, bool) and 0 <= number < len(frames):
        return frames[number], True
    return frames[-1], False


def ground_slots(frame: Frame, proposed: list[tuple[str, str]], sources: list[str]):
    """Keep the proposed slot values that are allowed and really said.

    Returns (kept {slot: value}, dropped [(slot, value, reason)]). A value is kept when the slot belongs to the
    frame and every word of the value appears somewhere in `sources`. The first value for a slot wins.
    """
    allowed = set(frame.slot_names)
    available = set().union(*(words(s) for s in sources)) if sources else set()
    kept: dict[str, str] = {}
    dropped: list[tuple[str, str, str]] = []
    for name, value in proposed:
        name, value = str(name).strip(), str(value).strip()
        if name not in allowed:
            dropped.append((name, value, "not a slot of this frame"))
        elif not words(value) or not words(value) <= available:
            dropped.append((name, value, "not in the user's words or memories"))
        else:
            kept.setdefault(name, value)
    return kept, dropped


def missing_required(frame: Frame, kept: dict[str, str]) -> list[str]:
    """Required slots the user has not given, in the order the frame lists them."""
    return [name for name in frame.required_slots if name not in kept]


def guard_rewrite(rewrite, message: str, sources: list[str]) -> tuple[str, str | None]:
    """The query to search with: the model's rewrite if it is safe, otherwise the user's own message.

    Returns (query, reason it was not used or None). A rewrite is not used when it is empty or when it
    contains a number or ID that appears in neither the message nor the other context.
    """
    rewrite = " ".join(str(rewrite or "").split())
    if not rewrite:
        return message, "empty"
    known = number_words(message).union(*(number_words(s) for s in sources)) if sources else number_words(message)
    if not number_words(rewrite) <= known:
        return message, "contains a number that was never said"
    return rewrite, None
