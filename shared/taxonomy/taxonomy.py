"""Policy taxonomy: the categories of each domain and which documents belong to them.

One file is the single source of truth for four users:
  ingestion        tags every new chunk with its categories
  labelling script tags the chunks already in Pinecone (scripts/label_documents.py)
  retrieval        filters a search to the categories a query frame names
  evaluation       decides whether a retrieved chunk was in the right category

How it works, in two steps:
  1. parse_taxonomy() reads policy_taxonomy.yaml ONCE (load_taxonomy() caches the result), checks the file for
     mistakes and builds a Taxonomy object. It never sees a document or a chunk.
  2. For every chunk, the Taxonomy object is asked "which categories?" (for_chunk). The answer is looked up by
     the chunk's file name in the table that step 1 built.

policy_taxonomy.yaml format (one block per domain):

    hr:
      categories:
        leave_and_attendance: {description: "...", parents: []}
        parental_leave:       {description: "...", parents: [leave_and_attendance, benefits_and_insurance]}
      documents:                          # source file name -> categories
        leave_policy_2025.pdf: {title: "Leave Policy 2025", categories: [leave_and_attendance]}
        benefits.md: [benefits_and_insurance]

Key documents by the source file name, the name a chunk's "source" ends with (or the name the file was uploaded
under, which ingestion passes as file_name). A file name that is not listed gets the category "uncategorized".
Files fetched from SeaweedFS are loaded through a temporary file, so a stored "source" can be a name like
/tmp/tmpevoy1z0r.md; that is why ingestion tags new uploads with the uploaded file name.
A title, when given, is written to the chunk metadata so citations show a readable name.

A category's parents make the taxonomy a DAG. Use a second parent only for a policy that really belongs to two
categories, and cite that document in the report. descendants() and expand_with_descendants() walk the DAG
downwards: a frame that names a parent category also searches everything below it. parents_family() is the
step upwards, used when a narrow search finds nothing.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import unquote, urlparse

import yaml

HERE = Path(__file__).parent
DOMAINS = ("legal", "hr", "engineering", "finance", "support")
UNCATEGORIZED = "uncategorized"


class TaxonomyError(ValueError):
    pass


@dataclass(frozen=True)
class Category:
    domain: str
    name: str
    description: str
    parents: tuple[str, ...]


@dataclass
class Taxonomy:
    categories: dict[str, dict[str, Category]]          
    documents: dict[str, dict[str, tuple[str, ...]]]    
    titles: dict[str, dict[str, str]]

    def names(self, domain: str) -> list[str]:
        return list(self.categories.get(domain, {}))

    def ancestors(self, domain: str, name: str) -> list[str]:
        """Every category above `name`, nearest first, each once."""
        seen: list[str] = []
        frontier = list(self.categories[domain][name].parents)
        while frontier:
            parent = frontier.pop(0)
            if parent not in seen:
                seen.append(parent)
                frontier.extend(self.categories[domain][parent].parents)
        return seen

    def document_key(self, domain: str, source: str, file_name: str | None = None) -> str | None:
        """The yaml entry a chunk belongs to. Entries are keyed by source file name: the name the file was
        uploaded under, else the last part of the chunk's source. The uploaded name wins over the source because
        a stored source is often a temp or signed name (tmpabc.pdf, <uuid>-handbook.pdf) that never matches the
        yaml. None when the file is not listed."""
        docs = self.documents.get(domain, {})
        if file_name and file_name in docs:
            return file_name
        name = source_key(source)
        return name if name in docs else None

    def for_chunk(self, domain: str, source: str, file_name: str | None = None) -> tuple[str, ...]:
        """Categories of a chunk: the ones listed for its document, or ("uncategorized",) if the file is not listed."""
        key = self.document_key(domain, source, file_name)
        return self.documents[domain][key] if key else (UNCATEGORIZED,)

    def title_for(self, domain: str, source: str, file_name: str | None = None) -> str | None:
        key = self.document_key(domain, source, file_name)
        return self.titles.get(domain, {}).get(key) if key else None


def source_key(source: str) -> str:
    """File name of a chunk's source. Signed SeaweedFS URLs and local paths of the same file give the same key."""
    path = urlparse(source).path if "://" in (source or "") else (source or "")
    return unquote(path.rstrip("/").split("/")[-1])


def descendants(taxonomy: Taxonomy, domain: str, names) -> set[str]:
    """Searching a parent category must also search its children, because chunks carry the child labels."""
    categories = taxonomy.categories.get(domain, {})
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


def expand_with_descendants(taxonomy: Taxonomy, domain: str, names) -> list[str]:
    """A frame names a few categories; the search needs those plus everything below them, in a stable order."""
    categories = taxonomy.categories.get(domain, {})
    given = [name for name in names if name in categories]
    below = descendants(taxonomy, domain, given)
    ordered = []
    for name in categories:                      # the order the yaml lists them in
        if name in below:
            ordered.append(name)
    return given + ordered


def parents_family(taxonomy: Taxonomy, domain: str, names) -> list[str]:
    """When a narrow search finds nothing, the next try is the parents' whole family: the parents and all under them."""
    categories = taxonomy.categories.get(domain, {})
    own = expand_with_descendants(taxonomy, domain, names)
    parents = []
    for name in own:
        for parent in categories[name].parents:
            if parent not in own and parent not in parents:
                parents.append(parent)
    if not parents:
        return []                                # no wider family, so this level would only repeat the first search
    family = set(own) | set(parents) | descendants(taxonomy, domain, parents)
    ordered = []
    for name in categories:                      # the order the yaml lists them in
        if name in family:
            ordered.append(name)
    return ordered


def parse_taxonomy(data: dict) -> Taxonomy:
    """Check the yaml data against itself and build the Taxonomy. Raises TaxonomyError listing every problem."""
    errors: list[str] = []
    categories: dict[str, dict[str, Category]] = {}
    documents: dict[str, dict[str, tuple[str, ...]]] = {}
    titles: dict[str, dict[str, str]] = {}

    for domain, block in (data or {}).items():
        if domain == "version":
            continue
        if domain not in DOMAINS:
            errors.append(f"unknown domain '{domain}'")
            continue
        block = block or {}
        cats = {}
        for name, spec in (block.get("categories") or {}).items():
            spec = spec or {}
            if name == UNCATEGORIZED:
                errors.append(f"{domain}: '{UNCATEGORIZED}' is reserved")
            if not str(spec.get("description", "")).strip():
                errors.append(f"{domain}.{name}: needs a description (the frame prompt shows it)")
            cats[name] = Category(domain, name, str(spec.get("description", "")).strip(),
                                  tuple(spec.get("parents") or ()))
        categories[domain] = cats

        docs, doc_titles = {}, {}
        for file_name, entry in (block.get("documents") or {}).items():
            file_name = str(file_name)
            if isinstance(entry, dict):
                names = tuple(entry.get("categories") or ())
                if entry.get("title"):
                    doc_titles[file_name] = str(entry["title"]).strip()
            else:
                names = tuple(entry or ())
            if not names:
                errors.append(f"{domain}: document '{file_name}' has no category")
            for n in names:
                if n not in cats:
                    errors.append(f"{domain}: document '{file_name}' uses unknown category '{n}'")
            docs[file_name] = names
        documents[domain] = docs
        titles[domain] = doc_titles

        for cat in cats.values():
            for p in cat.parents:
                if p not in cats:
                    errors.append(f"{domain}.{cat.name}: unknown parent '{p}'")
                if p == cat.name:
                    errors.append(f"{domain}.{cat.name}: is its own parent")
        used = {n for names in docs.values() for n in names}
        for cat in cats:
            is_parent = any(cat in c.parents for c in cats.values())
            if cat not in used and not is_parent:
                errors.append(f"{domain}.{cat}: no document belongs to it")

    for domain, cats in categories.items():
        _check_acyclic(domain, cats, errors)

    if errors:
        raise TaxonomyError("policy taxonomy is invalid:\n  " + "\n  ".join(errors))
    return Taxonomy(categories, documents, titles)


def _check_acyclic(domain: str, cats: dict[str, Category], errors: list[str]) -> None:
    state: dict[str, int] = {}         

    def visit(name: str, path: list[str]) -> None:
        if state.get(name) == 2 or name not in cats:
            return
        if state.get(name) == 1:
            errors.append(f"{domain}: parent cycle {' -> '.join(path + [name])}")
            return
        state[name] = 1
        for p in cats[name].parents:
            visit(p, path + [name])
        state[name] = 2

    for name in cats:
        visit(name, [])


@lru_cache(maxsize=1)
def load_taxonomy(path: str | None = None) -> Taxonomy:
    """Read policy_taxonomy.yaml (or POLICY_TAXONOMY_PATH, or `path`) and build the Taxonomy. Cached per process:
    after editing the yaml, restart the service."""
    path = path or os.getenv("POLICY_TAXONOMY_PATH") or str(HERE / "policy_taxonomy.yaml")
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return parse_taxonomy(data)


if __name__ == "__main__":
    t = load_taxonomy()
    print({d: len(t.names(d)) for d in ['hr','finance','legal','support','engineering'] })