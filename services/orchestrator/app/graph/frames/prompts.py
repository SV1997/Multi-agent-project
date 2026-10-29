"""The scope prompt: tells the answering model which part of the policies the question is about."""


def scope_prompt(taxonomy, frame) -> str:
    """A model told its topic, and told to say it does not know, is less likely to answer from the wrong rule."""
    areas = []
    for name in frame.categories:
        areas.append(f"{name}: {taxonomy.categories[frame.domain][name].description}")
    return (f"This question is about {frame.description}. The relevant policy areas are: " + "; ".join(areas) + ". "
            "Answer only from the provided context about these areas. If the context does not answer the question, "
            "say you do not know.")
