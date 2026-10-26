"""Rules for long-term memory: which facts are always loaded, how keys are normalised, what is never stored."""
import re
from typing import Any, Optional

# Identity facts are loaded for every question, not only when the question resembles them.
# The first alias is the canonical key new facts are written under; older aliases are still read.
IDENTITY_GROUPS: dict[str, tuple[str, ...]] = {
    "name": ("name", "employee_name"),
    "location": ("location", "seat_location", "workspace_location", "employee_workspace"),
    "role": ("role", "employee_role"),
    "manager": ("manager", "manager_name", "employee_manager"),
}
IDENTITY_ALIASES: tuple[str, ...] = tuple(a for aliases in IDENTITY_GROUPS.values() for a in aliases)
SEMANTIC_LIMIT = 6

_ALIAS_TO_GROUP = {alias: group for group, aliases in IDENTITY_GROUPS.items() for alias in aliases}
# "no name is on file", "not available", "unknown"... - a missing fact is not a fact
_NEGATIVE = re.compile(
    r"\bno\b.{0,40}\b(on file|available|recorded|found|known|provided)\b"
    r"|\bnot\b.{0,20}\b(on file|available|known|provided|found|recorded|specified)\b"
    r"|\bunknown\b|\bn/a\b",
    re.IGNORECASE,
)


def canonical_memory_key(topic_key: str) -> str:
    """Identity aliases (employee_name, seat_location, ...) collapse to one key; other keys are unchanged."""
    return _ALIAS_TO_GROUP.get(topic_key, topic_key)


def is_negative_fact(content: str) -> bool:
    return bool(_NEGATIVE.search(content or ""))


def _content(item: Any) -> str:
    return ((item.value or {}).get("content") or "").strip()


def identity_lines(items: dict[str, Optional[Any]]) -> list[str]:
    """items maps alias key -> store item (or None). Per group keep the newest usable value."""
    lines = []
    for group, aliases in IDENTITY_GROUPS.items():
        usable = [items[a] for a in aliases if items.get(a) is not None and _content(items[a]) and not is_negative_fact(_content(items[a]))]
        if usable:
            newest = max(usable, key=lambda i: i.updated_at)
            lines.append(f"{group}: {_content(newest)}")
    return lines


def build_memory_text(items: dict[str, Optional[Any]], semantic: list[Any]) -> Optional[str]:
    """Identity facts first, then the semantic matches (minus identity duplicates and negative facts)."""
    lines = identity_lines(items)
    for r in semantic:
        text = _content(r)
        if r.key not in _ALIAS_TO_GROUP and text and not is_negative_fact(text) and text not in lines:
            lines.append(text)
    return "\n".join(lines) or None
