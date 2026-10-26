"""Builds and checks the set of frames for every domain.

Why this file exists: frames come from two places. A few are written by hand in frames.yaml (the ones that need
slots, like "which leave type?"). The rest are generated, one per leaf category of the taxonomy, so every part
of the policy documents has a frame without anyone writing it. Both have to be combined into one menu per
domain, and checked against the taxonomy, because a typo in a category name would make a search silently look
in the wrong place.

Problem it solves: a closed, validated menu. The model can only choose a number from this menu, so it can
never invent a frame or point a search at a category that does not exist. Every mistake in frames.yaml is
reported at startup, all at once, instead of showing up later as a strange answer.

Menu order per domain: hand-written frames (in file order), then generated ones (taxonomy order), then
"<domain>.other", which stands for "none of the above" and searches the whole domain.
"""
import os
import re
from dataclasses import dataclass

import yaml

from .models import Frame

HERE = os.path.dirname(__file__)
OTHER = "other"
NON_CONTENT = "non_content"                      # marks menus and reference lists; never a frame of its own
SLOT_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


class FrameError(ValueError):
    pass


@dataclass
class FrameRegistry:
    menus: dict[str, list[Frame]]                # domain -> ordered menu

    def menu(self, domain: str) -> list[Frame]:
        return self.menus.get(domain, [])

    def get(self, domain: str, frame_id: str) -> Frame | None:
        return next((f for f in self.menu(domain) if f.frame_id == frame_id), None)

    def other(self, domain: str) -> Frame:
        return self.menu(domain)[-1]


def leaf_categories(taxonomy, domain: str) -> list[str]:
    """Categories nothing else lists as a parent. Chunks carry leaf labels, so leaves are what a search matches."""
    categories = taxonomy.categories[domain]
    parents = {p for category in categories.values() for p in category.parents}
    return [name for name in categories if name not in parents and name != NON_CONTENT]


def auto_frames(taxonomy, domain: str) -> list[Frame]:
    return [
        Frame(
            frame_id=f"{domain}.{name}",
            domain=domain,
            description=taxonomy.categories[domain][name].description,
            categories=(name,),
            origin="auto",
        )
        for name in leaf_categories(taxonomy, domain)
    ]


def other_frame(domain: str) -> Frame:
    return Frame(
        frame_id=f"{domain}.{OTHER}",
        domain=domain,
        description="None of the other frames fits; the whole domain is searched",
        categories=(),
        origin="other",
    )


def _hand_frames(data: dict, taxonomy, auto_ids: dict[str, set[str]], errors: list[str]) -> dict[str, list[Frame]]:
    frames: dict[str, list[Frame]] = {}
    for domain, block in (data or {}).items():
        if domain == "version":
            continue
        if domain not in taxonomy.categories:
            errors.append(f"frames.yaml: unknown domain '{domain}'")
            continue
        seen: set[str] = set()
        for frame_id, spec in (block or {}).items():
            where = f"{domain}: frame '{frame_id}'"
            spec = spec or {}
            if not str(frame_id).startswith(f"{domain}."):
                errors.append(f"{where}: the id must start with '{domain}.'")
            if frame_id == f"{domain}.{OTHER}":
                errors.append(f"{where}: '{domain}.{OTHER}' is generated and reserved")
            elif frame_id in auto_ids[domain]:
                errors.append(f"{where}: this id is already generated for a category; choose another id")
            if frame_id in seen:
                errors.append(f"{where}: defined twice")
            seen.add(frame_id)

            description = str(spec.get("description") or "").strip()
            if not description:
                errors.append(f"{where}: needs a description (the model reads it in the menu)")

            categories = tuple(spec.get("categories") or ())
            if not categories:
                errors.append(f"{where}: needs at least one category")
            for name in categories:
                if name not in taxonomy.categories[domain]:
                    errors.append(f"{where}: unknown category '{name}'")
                elif name == NON_CONTENT:
                    errors.append(f"{where}: '{NON_CONTENT}' cannot be searched by a frame")
            if len(set(categories)) != len(categories):
                errors.append(f"{where}: a category is listed twice")

            required = dict(spec.get("required_slots") or {})
            optional = tuple(spec.get("optional_slots") or ())
            for name, question in required.items():
                if not SLOT_NAME.match(str(name)):
                    errors.append(f"{where}: slot name '{name}' must be lowercase letters, digits and _")
                if not str(question or "").strip():
                    errors.append(f"{where}: required slot '{name}' needs the question to ask when it is missing")
            for name in optional:
                if not SLOT_NAME.match(str(name)):
                    errors.append(f"{where}: slot name '{name}' must be lowercase letters, digits and _")
            overlap = set(required) & set(optional)
            if overlap:
                errors.append(f"{where}: slot(s) {sorted(overlap)} are both required and optional")

            frames.setdefault(domain, []).append(Frame(
                frame_id=str(frame_id), domain=domain, description=description, categories=categories,
                required_slots={str(k): str(v).strip() for k, v in required.items()},
                optional_slots=optional, origin="hand",
            ))
    return frames


def build_registry(taxonomy, hand_data: dict | None = None) -> FrameRegistry:
    """The menu for every domain of the taxonomy. Raises FrameError listing every problem found."""
    errors: list[str] = []
    generated = {domain: auto_frames(taxonomy, domain) for domain in taxonomy.categories}
    auto_ids = {domain: {f.frame_id for f in frames} for domain, frames in generated.items()}
    hand = _hand_frames(hand_data or {}, taxonomy, auto_ids, errors)
    if errors:
        raise FrameError("frames are invalid:\n  " + "\n  ".join(errors))
    return FrameRegistry({
        domain: hand.get(domain, []) + generated[domain] + [other_frame(domain)]
        for domain in taxonomy.categories
    })


def load_registry(taxonomy, path: str | None = None) -> FrameRegistry:
    """Read frames.yaml (or POLICY_FRAMES_PATH, or `path`) and build the registry. A missing file means no hand-written frames."""
    path = path or os.getenv("POLICY_FRAMES_PATH") or os.path.join(HERE, "frames.yaml")
    data = None
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    return build_registry(taxonomy, data)
