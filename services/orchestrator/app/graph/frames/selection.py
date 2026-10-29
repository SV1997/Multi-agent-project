"""The menu the model chooses a frame from, and how its answer is read."""


def menu_text(frames: list) -> str:
    """The model can only answer with a number, so it needs a numbered menu of every frame."""
    lines = []
    for number, frame in enumerate(frames):
        lines.append(f"{number}. {frame.frame_id}: {frame.description}")
    return "\n".join(lines)


def frame_by_number(frames: list, number):
    """A model can answer with a number that is not on the menu; that must mean "no frame", never a guess.

    bool is excluded because True would count as 1.
    """
    if isinstance(number, int) and not isinstance(number, bool) and 0 <= number < len(frames):
        return frames[number]
    return None
