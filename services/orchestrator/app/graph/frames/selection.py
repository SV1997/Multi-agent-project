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


def frames_by_numbers(frames: list, numbers) -> list:
    """The frames the model chose, each once, in the order given. Bad numbers are dropped silently - the same rule
    as frame_by_number - so a wrong answer still means "no frame", never a wrong frame. Duplicates are removed because
    the model may repeat itself when a question only fits one frame."""
    chosen, seen = [], set()
    for number in numbers or ():
        frame = frame_by_number(frames, number)
        if frame is not None and frame.frame_id not in seen:
            seen.add(frame.frame_id)
            chosen.append(frame)
    return chosen
