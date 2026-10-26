"""Policy taxonomy: the categories of each domain and which documents belong to them.

One file is the single source of truth for four users:
  ingestion        tags every new chunk with its categories
  backfill script  tags the chunks already in Pinecone and in the BM25 index
  retrieval        filters a search to the categories a query frame names
  evaluation       decides whether a retrieved chunk was in the right category

policy_taxonomy.yaml format (one block per domain):

    hr:
      categories:
        leave_and_attendance: {description: "...", parents: []}
        parental_leave:       {description: "...", parents: [leave_and_attendance, benefits_and_insurance]}
      documents:                          # doc id (preferred) or file name -> categories
        3f2a9c1d4e5b6a7c: {title: "Leave Policy 2025", categories: [leave_and_attendance]}
        benefits.md: [benefits_and_insurance]
      mixed: [3f2a9c1d4e5b6a7c]           # documents classified chunk by chunk (scripts/taxonomy/classify_mixed.py)

Key documents by doc id. Files fetched from SeaweedFS are loaded through a temporary file, so the "source"
stored on their chunks is a name like /tmp/tmpevoy1z0r.md; the doc id (the prefix of every chunk id) is stable.
A title, when given, is written to the chunk metadata so citations show a readable name.

A category's parents make the taxonomy a DAG. Use a second parent only for a policy that really belongs to two
categories, and cite that document in the report.
"""
from __future__ import annotations

import json
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
    mixed: dict[str, frozenset[str]]                    
    overrides: dict[str, tuple[str, ...]]               

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

    def document_key(self, domain: str, source: str, chunk_id: str | None = None,
                     file_name: str | None = None) -> str | None:
        """The taxonomy entry a chunk belongs to: its doc id if listed, else the name the file was uploaded
        under, else the last part of its source. The uploaded name wins over the source because a stored
        source is often a temp or signed name (tmpabc.pdf, <uuid>-handbook.pdf) that never matches the yaml."""
        docs = self.documents.get(domain, {})
        doc_id = chunk_id.split("#", 1)[0] if chunk_id else None
        if doc_id and doc_id in docs:
            return doc_id
        if file_name and file_name in docs:
            return file_name
        name = source_key(source)
        return name if name in docs else None

    def for_chunk(self, domain: str, source: str, chunk_id: str | None = None,
                  file_name: str | None = None) -> tuple[str, ...]:
        """Categories of one chunk: a chunk-level override first, then its document's categories."""
        if chunk_id and chunk_id in self.overrides:
            return self.overrides[chunk_id]
        key = self.document_key(domain, source, chunk_id, file_name)
        return self.documents[domain][key] if key else (UNCATEGORIZED,)

    def title_for(self, domain: str, source: str, chunk_id: str | None = None,
                  file_name: str | None = None) -> str | None:
        key = self.document_key(domain, source, chunk_id, file_name)
        return self.titles.get(domain, {}).get(key) if key else None

    def is_mixed(self, domain: str, source: str, chunk_id: str | None = None,
                 file_name: str | None = None) -> bool:
        key = self.document_key(domain, source, chunk_id, file_name)
        return key is not None and key in self.mixed.get(domain, frozenset())


def source_key(source: str) -> str:
    """File name of a chunk's source. Signed SeaweedFS URLs and local paths of the same file give the same key."""
    path = urlparse(source).path if "://" in (source or "") else (source or "")
    return unquote(path.rstrip("/").split("/")[-1])


def parse_taxonomy(data: dict, overrides: dict | None = None) -> Taxonomy:
    errors: list[str] = []
    categories: dict[str, dict[str, Category]] = {}
    documents: dict[str, dict[str, tuple[str, ...]]] = {}
    titles: dict[str, dict[str, str]] = {}
    mixed: dict[str, frozenset[str]] = {}

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

        mixed_files = frozenset(str(m) for m in (block.get("mixed") or ()))
        for file_name in mixed_files:
            if file_name not in docs:
                errors.append(f"{domain}: mixed file '{file_name}' must also be listed under documents")
        mixed[domain] = mixed_files

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

    tax = Taxonomy(categories, documents, titles, mixed, {})
    for domain, cats in categories.items():
        _check_acyclic(domain, cats, errors)

    all_names = {(d, n) for d, cats in categories.items() for n in cats}
    for chunk_id, entry in (overrides or {}).items():
        domain, names = entry.get("domain"), tuple(entry.get("categories") or ())
        if not names or any((domain, n) not in all_names for n in names):
            errors.append(f"override for chunk {chunk_id} names an unknown category: {entry}")
        tax.overrides[chunk_id] = names

    if errors:
        raise TaxonomyError("policy taxonomy is invalid:\n  " + "\n  ".join(errors))
    return tax


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
def load_taxonomy(path: str | None = None, overrides_path: str | None = None) -> Taxonomy:
    path = path or os.getenv("POLICY_TAXONOMY_PATH") or str(HERE / "policy_taxonomy.yaml")
    overrides_path = overrides_path or os.getenv("CHUNK_OVERRIDES_PATH") or str(HERE / "chunk_overrides.json")
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    overrides = {}
    if os.path.exists(overrides_path):
        with open(overrides_path, encoding="utf-8") as f:
            overrides = json.load(f)
    return parse_taxonomy(data, overrides)

if __name__ == "__main__":
    t = load_taxonomy()
    print({d: len(t.names(d)) for d in ['hr','finance','legal','support','engineering'] })