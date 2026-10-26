"""How a localized search widens when it finds nothing useful: the taxonomy's DAG doing real work.

Why this file exists: searching only the frame's categories keeps answers focused, but if the right passage is
filed under a neighbouring category the search finds nothing and the user gets no answer at all. Instead of
giving up (or dropping every restriction at once), the search widens one step at a time:

    level 0   the frame's own categories
    level 1   everything under the PARENTS of those categories (their siblings and cousins)
    level 2   the whole domain (no category restriction; only the "is it real content" rule still applies)

Problem it solves: a narrow search that is wrong should cost one retry, not a wrong or missing answer, and the
widening should follow the structure of the policy (leave -> earned leave, sick leave ...) rather than a guess.

Chunks carry LEAF labels, so a search for a parent category has to name its descendants too: a filter on
"leave" alone would match almost nothing. That is why the levels below are expanded to include descendants.
A step that would not widen anything is skipped (a category with no parent has no level 1), so a retry is
never spent repeating the same search.

The result is a short list of {"level", "categories"} in plain JSON (None = the whole domain), computed once
per question by the frame step and stored in the state.
"""


def _category_map(taxonomy, domain: str) -> dict:
    return taxonomy.categories.get(domain, {})


def descendants(taxonomy, domain: str, names) -> set[str]:
    """Every category below the given ones (children, grandchildren, ...), not including the given ones."""
    categories = _category_map(taxonomy, domain)
    children: dict[str, list[str]] = {}
    for name, category in categories.items():
        for parent in category.parents:
            children.setdefault(parent, []).append(name)
    found: set[str] = set()
    queue = list(names)
    while queue:
        for child in children.get(queue.pop(), ()):
            if child not in found:
                found.add(child)
                queue.append(child)
    return found - set(names)


def _in_taxonomy_order(taxonomy, domain: str, names) -> list[str]:
    wanted = set(names)
    return [name for name in _category_map(taxonomy, domain) if name in wanted]


def expand_with_descendants(taxonomy, domain: str, names) -> list[str]:
    """The given categories plus everything below them. The given ones keep their order and come first."""
    given = [n for n in names if n in _category_map(taxonomy, domain)]
    below = _in_taxonomy_order(taxonomy, domain, descendants(taxonomy, domain, given))
    return given + [n for n in below if n not in given]


def widen_levels(taxonomy, domain: str, categories) -> list[dict]:
    """The search plan for a frame: [{"level": 0, "categories": [...]}, {"level": 1, ...}, {"level": 2, "categories": None}].

    categories: the frame's own categories. An empty list (the "other" frame) is already the whole domain,
    so the plan is a single level 0 with categories None.
    """
    if not categories:
        return [{"level": 0, "categories": None}]

    own = expand_with_descendants(taxonomy, domain, categories)
    parents = [p for name in own for p in _category_map(taxonomy, domain)[name].parents if p not in own]
    levels = [{"level": 0, "categories": own}]
    if parents:
        wider = set(own) | set(parents) | descendants(taxonomy, domain, parents)
        levels.append({"level": 1, "categories": _in_taxonomy_order(taxonomy, domain, wider)})
    levels.append({"level": 2, "categories": None})
    return levels
