"""The scope prompt: tells the answering model which part of the policies the question is about.

There are three sentences, one per search level, because the sentence must match the context the model really receives:
    level 0  the frame's own categories             scope_prompt
    level 1  the parents' whole family              wider_scope_prompt   (used when the first search found nothing)
    level 2  the whole domain, no category filter   domain_scope_prompt  (used when the second search found nothing too)
All three are built together by the frame step (before any search); scope_for_level picks the right one afterwards,
once the retrieval service has reported how far it had to widen.
"""


def _topics(frames) -> str:
    return " and ".join(frame.description for frame in frames) or "this policy area"


def _areas(taxonomy, domain: str, names) -> str:
    """'name: description' for each category, each once, in the order given."""
    known = taxonomy.categories.get(domain, {})
    seen, areas = set(), []
    for name in names:
        if name not in seen and name in known:
            seen.add(name)
            areas.append(f"{name}: {known[name].description}")
    return "; ".join(areas)


def scope_prompt(taxonomy, frames) -> str:
    """Level 0. A model told its topic, and told to say it does not know, is less likely to answer from the wrong rule.

    `frames` is a list, because a question may straddle two frames (multi-frame selection). Each category is
    described once, even when two frames name the same one.
    """
    if hasattr(frames, "frame_id"):                            # one Frame, as the old call site passed
        frames = [frames]
    areas = _areas(taxonomy, frames[0].domain, [name for frame in frames for name in frame.categories])
    return (f"This question is about {_topics(frames)}. The relevant policy areas are: {areas}. "
            "Answer only from the provided context about these areas. If the context does not answer the question, "
            "say you do not know.")


def wider_scope_prompt(taxonomy, frames, wider_categories) -> str:
    """Level 1: the narrow search found nothing, so the context may come from the parents' whole family."""
    areas = _areas(taxonomy, frames[0].domain, wider_categories)
    return (f"This question is about {_topics(frames)}. The search of that narrow area found nothing, so the context "
            f"may come from the wider policy family: {areas}. "
            "Answer only from the provided context about these areas. If the context does not answer the question, "
            "say you do not know.")


def domain_scope_prompt(frames) -> str:
    """Level 2: no category filter was applied, so the context can be about anything in the domain."""
    return (f"This question is about {_topics(frames)}. The search of that area found nothing, so the context below "
            f"comes from the whole {frames[0].domain} policy set and may not match the topic. "
            "Answer only if the provided context actually answers the question; otherwise say you do not know.")


def scope_for_level(state) -> str | None:
    """The sentence that matches how far the search really widened. The level is written by the retrieval step;
    until a search has run (or when no filter was used) it is None, which means level 0."""
    level = state.get("localize_fallback_level") or 0
    if level >= 2:
        return state.get("localize_scope_domain")
    if level == 1:
        return state.get("localize_scope_wider") or state.get("localize_scope_domain")
    return state.get("localize_scope")
