"""Loads the hand-written frames from frames.yaml and checks them against the taxonomy."""
import os

import yaml

from .models import Frame

HERE = os.path.dirname(__file__)


def check_frame(taxonomy, domain: str, frame_id: str, spec: dict) -> list[str]:
    """A frame naming a category that does not exist would search the wrong place silently, so it must stop startup."""
    problems = []
    if not str(frame_id).startswith(domain + "."):
        problems.append(f"{frame_id}: the id must start with '{domain}.'")
    if not str(spec.get("description") or "").strip():
        problems.append(f"{frame_id}: needs a description (the model reads it in the menu)")
    categories = spec.get("categories") or []
    if not categories:
        problems.append(f"{frame_id}: needs at least one category")
    for name in categories:
        if name not in taxonomy.categories[domain]:
            problems.append(f"{frame_id}: unknown category '{name}'")
    return problems


def build_registry(taxonomy, data: dict) -> dict[str, list[Frame]]:
    """Turns the yaml data into {domain: [frames]}; every mistake is reported at once."""
    registry, problems = {}, []
    for domain, block in (data or {}).items():
        if domain == "version":
            continue
        if domain not in taxonomy.categories:
            problems.append(f"unknown domain '{domain}'")
            continue
        registry[domain] = []
        for frame_id, spec in (block or {}).items():
            problems.extend(check_frame(taxonomy, domain, frame_id, spec or {}))
            registry[domain].append(Frame(str(frame_id), domain, str((spec or {}).get("description") or "").strip(),
                                          tuple((spec or {}).get("categories") or ())))
    if problems:
        raise ValueError("frames.yaml is invalid:\n  " + "\n  ".join(problems))
    return registry


def load_registry(taxonomy, path=None) -> dict[str, list[Frame]]:
    """Reads frames.yaml (or POLICY_FRAMES_PATH, or `path`) once per call."""
    path = path or os.getenv("POLICY_FRAMES_PATH") or os.path.join(HERE, "frames.yaml")
    with open(path, encoding="utf-8") as file:
        return build_registry(taxonomy, yaml.safe_load(file))
