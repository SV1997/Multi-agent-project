"""Category instructions for the answering agent, and how they become prompt text.

Why this file exists: the examiner's second note was "use the categorization to create appropriate prompts".
Once a question has been sorted into a frame, the answering agent can be told what that part of the policy
covers, what to check in the evidence before answering, and what to ask the user when something is unclear.
Those instructions are written once per category in category_prompts.yaml; this file loads and checks them and
turns the ones for a question's frame into a block of text for the system prompt.

Problem it solves: an agent that only sees "answer from this context" will happily answer a leave question with a
rule about a different kind of leave. The block names the category, tells the agent to stay inside it, and tells
it to say so when the evidence does not answer the question - while the facts still come only from the retrieved
documents (the instructions carry no policy facts and no numbers).

Three versions of the block are prepared for every question, because the right closing rule depends on where the
evidence came from, which is only known after the search:
    base      the instructions only (no search was made, e.g. a database lookup answered the question)
    strict    + "answer only from evidence in these categories; do not borrow a rule from another category"
    widened   used when the first search found nothing and the search was widened: the evidence may legitimately
              come from a neighbouring category, so the closing rule says to use it only if it really fits the
              situation and to say where it comes from. (The strict rule would contradict the evidence it was given.)
"""
import os

import yaml

HERE = os.path.dirname(__file__)
NON_CONTENT = "non_content"          # never searched, so it needs no instructions

MAX_SCOPE = 240                      # characters; the instructions are meant to be short
MAX_ITEM = 220
MAX_CHECKS = 3
MAX_ASKS = 2


class PromptError(ValueError):
    pass


def _check_entry(where: str, entry, errors: list[str]) -> dict | None:
    if not isinstance(entry, dict):
        errors.append(f"{where}: must have scope, check and ask")
        return None
    scope = str(entry.get("scope") or "").strip()
    if not scope:
        errors.append(f"{where}: needs a scope")
    elif len(scope) > MAX_SCOPE:
        errors.append(f"{where}: scope is {len(scope)} characters; keep it under {MAX_SCOPE}")

    lists = {}
    for field, low, high in (("check", 1, MAX_CHECKS), ("ask", 0, MAX_ASKS)):
        items = entry.get(field)
        items = [] if items is None else items
        if not isinstance(items, list) or not all(isinstance(i, str) and i.strip() for i in items):
            errors.append(f"{where}: {field} must be a list of non-empty strings")
            items = []
        if not low <= len(items) <= high:
            errors.append(f"{where}: {field} needs {low} to {high} items, found {len(items)}")
        for item in items:
            if len(item) > MAX_ITEM:
                errors.append(f"{where}: a {field} item is {len(item)} characters; keep it under {MAX_ITEM}")
        lists[field] = [i.strip() for i in items]
    return {"scope": scope, "check": lists["check"], "ask": lists["ask"]}


def parse_category_prompts(taxonomy, data: dict | None) -> dict[str, dict[str, dict]]:
    """Check the prompts against the taxonomy and return {domain: {category: {scope, check, ask}}}.

    Every category must have an entry (except non_content), no entry may name an unknown category, and every
    problem is reported at once.
    """
    errors: list[str] = []
    result: dict[str, dict[str, dict]] = {}
    data = data or {}
    for domain in data:
        if domain != "version" and domain not in taxonomy.categories:
            errors.append(f"category_prompts: unknown domain '{domain}'")

    for domain, categories in taxonomy.categories.items():
        block = data.get(domain) or {}
        result[domain] = {}
        for name in block:
            if name not in categories:
                errors.append(f"{domain}: unknown category '{name}'")
            elif name == NON_CONTENT:
                errors.append(f"{domain}: '{NON_CONTENT}' is never searched, so it needs no prompt")
        for name in categories:
            if name == NON_CONTENT:
                continue
            if name not in block:
                errors.append(f"{domain}: category '{name}' has no prompt")
                continue
            entry = _check_entry(f"{domain}.{name}", block[name], errors)
            if entry:
                result[domain][name] = entry
    if errors:
        raise PromptError("category prompts are invalid:\n  " + "\n  ".join(errors))
    return result


def load_category_prompts(taxonomy, path: str | None = None) -> dict[str, dict[str, dict]]:
    """Read category_prompts.yaml (or CATEGORY_PROMPTS_PATH, or `path`). The file must exist when prompts are in use."""
    path = path or os.getenv("CATEGORY_PROMPTS_PATH") or os.path.join(HERE, "category_prompts.yaml")
    if not os.path.exists(path):
        raise PromptError(f"category prompts file not found: {path}")
    with open(path, encoding="utf-8") as f:
        return parse_category_prompts(taxonomy, yaml.safe_load(f))


def build_prompt_texts(frame, prompts: dict, slots: dict, missing: list[str], searched: list[str] | None) -> dict | None:
    """The three versions of the prompt block for a frame, or None when there is nothing to say.

    frame     the chosen Frame (its categories are the topic of the question)
    prompts   the checked prompts from load_category_prompts
    slots     slot values the user gave; missing: required slots still unknown
    searched  the categories the first search covers, named in the strict rule
    """
    if not frame.categories:
        return None
    domain_prompts = prompts.get(frame.domain, {})
    entries = [(name, domain_prompts[name]) for name in frame.categories if name in domain_prompts]
    if not entries:
        return None

    lines = [f"Localized answer rules for this question (frame {frame.frame_id}). Follow them together with your other instructions.",
             "", "The question belongs to these parts of the policy documents:"]
    for name, entry in entries:
        lines.append(f"- {name}: {entry['scope']}")
        lines.extend(f"    Check: {item}" for item in entry["check"])
        lines.extend(f"    What to find out from the user if it is not clear: {item}" for item in entry["ask"])
    if slots:
        lines += ["", "What the user has told us: " + "; ".join(f"{name} = {value}" for name, value in slots.items())]
    if missing:
        lines += ["", f"Not yet known: {', '.join(missing)}. If the answer depends on it, say what it depends on and "
                      "ask the user for it instead of guessing."]
    base = "\n".join(lines)

    names = ", ".join(searched or frame.categories)
    strict = base + (
        f"\n\nAnswer only from evidence in these categories: {names}. Do not borrow a rule from another category. "
        "If the evidence does not answer the question, say so plainly."
    )
    widened = base + (
        "\n\nThe search of these categories found nothing useful, so it was widened to related parts of the documents. "
        "The evidence below may come from outside the categories above: use a passage only if it really concerns the "
        "situation asked about, say which part of the policy it comes from, and do not borrow a rule that belongs to a "
        "different situation. If nothing answers the question, say so plainly."
    )
    return {"base": base, "strict": strict, "widened": widened}


def choose_prompt_block(state) -> str:
    """The block for the answering prompt, picked by where the evidence came from; "" when there is none to add.

    No vector search made (level None): the instructions alone. Evidence from the frame's own categories
    (level 0): with the strict rule. Evidence from a wider level: with the widened rule.
    """
    texts = state.get("category_prompts_text")
    if not texts:
        return ""
    level = state.get("fallback_level")
    key = "base" if level is None else ("strict" if level == 0 else "widened")
    return texts[key] + "\n\n"
