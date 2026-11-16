"""The policy taxonomy and the query frames, stored in Postgres as one versioned content set.

policy_taxonomy.yaml and frames.yaml stay in the repo as the seed (scripts/seed_policy_content.py). At runtime
load_taxonomy() and load_registry() read the ACTIVE version from the database instead. This module only moves data
between the tables and the same dict shape the YAML files produce, so parse_taxonomy() and build_registry() still
do all the checking, unchanged.

    to_rows(...)      YAML-shaped dicts  -> table rows    (the seed script)
    from_rows(...)    table rows         -> YAML-shaped dicts (the loaders)
    active_content()  the active version, read ONCE per process; None when there is none or the database is
                      unreachable, and the loaders then fall back to the YAML files.

One version covers taxonomy AND frames, because frames name taxonomy categories. `position` columns keep the order
the YAML listed things in: the frame menu numbers and the category order both depend on it.
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache

logger = logging.getLogger(__name__)

CONNECT_TIMEOUT_SECONDS = 5


def to_rows(taxonomy_data: dict, frames_data: dict) -> dict[str, list[tuple]]:
    """Flattens the two YAML dicts into rows per table (without version_id). Each tuple ends with its position."""
    rows = {name: [] for name in
            ("category", "category_parent", "frame", "frame_category", "document", "document_category")}
    count = {name: 0 for name in rows}

    def add(table: str, *values):
        rows[table].append((*values, count[table]))
        count[table] += 1

    for domain, block in (taxonomy_data or {}).items():
        if domain == "version":
            continue
        block = block or {}
        for name, spec in (block.get("categories") or {}).items():
            spec = spec or {}
            add("category", domain, name, str(spec.get("description", "")))
            for parent in spec.get("parents") or ():
                add("category_parent", domain, name, parent)
        for file_name, entry in (block.get("documents") or {}).items():
            if isinstance(entry, dict):
                names, title = entry.get("categories") or (), entry.get("title")
            else:
                names, title = entry or (), None
            add("document", domain, str(file_name), str(title).strip() if title else None)
            for category in names:
                add("document_category", domain, str(file_name), category)

    for domain, block in (frames_data or {}).items():
        if domain == "version":
            continue
        for frame_id, spec in (block or {}).items():
            spec = spec or {}
            add("frame", str(frame_id), domain, str(spec.get("description") or ""))
            for category in spec.get("categories") or ():
                add("frame_category", str(frame_id), category)
    return rows


def from_rows(rows: dict[str, list[tuple]]) -> tuple[dict, dict]:
    """The reverse of to_rows: rows (already in position order, without the position) back into the two YAML dicts."""
    taxonomy: dict = {}

    def block(domain):
        return taxonomy.setdefault(domain, {"categories": {}, "documents": {}})

    for domain, name, description in rows["category"]:
        block(domain)["categories"][name] = {"description": description, "parents": []}
    for domain, name, parent in rows["category_parent"]:
        block(domain)["categories"][name]["parents"].append(parent)
    for domain, file_name, title in rows["document"]:
        entry = {"categories": []}
        if title:
            entry["title"] = title
        block(domain)["documents"][file_name] = entry
    for domain, file_name, category in rows["document_category"]:
        block(domain)["documents"][file_name]["categories"].append(category)

    frames: dict = {}
    domain_of = {}
    for frame_id, domain, description in rows["frame"]:
        frames.setdefault(domain, {})[frame_id] = {"description": description, "categories": []}
        domain_of[frame_id] = domain
    for frame_id, category in rows["frame_category"]:
        frames[domain_of[frame_id]][frame_id]["categories"].append(category)
    return taxonomy, frames



_TABLES = {
    "category": "domain, name, description",
    "category_parent": "domain, name, parent_name",
    "frame": "frame_id, domain, description",
    "frame_category": "frame_id, category_name",
    "document": "domain, file_name, title",
    "document_category": "domain, file_name, category_name",
}


def connect(url: str):
    """The only place a connection is opened, so a test can replace it. Never log `url`: it holds the password."""
    import psycopg
    # prepare_threshold=None: the Neon pooler can drop server-side prepared statements between calls.
    return psycopg.connect(url, connect_timeout=CONNECT_TIMEOUT_SECONDS, prepare_threshold=None)


def read_active(conn):
    """(version_number, taxonomy_data, frames_data) of the active version, or None when no version is active."""
    with conn.cursor() as cur:
        cur.execute("SELECT id, version_number FROM content_version WHERE is_active")
        found = cur.fetchone()
        if found is None:
            return None
        version_id, version_number = found
        rows = {}
        for table, columns in _TABLES.items():
            cur.execute(f"SELECT {columns} FROM {table} WHERE version_id = %s ORDER BY position", (version_id,))
            rows[table] = [tuple(row) for row in cur.fetchall()]
    taxonomy, frames = from_rows(rows)
    return version_number, taxonomy, frames


def write_version(conn, taxonomy_data: dict, frames_data: dict) -> int:
    """Stores both dicts as a new content_version and makes it the active one, in one transaction. Returns its number."""
    rows = to_rows(taxonomy_data, frames_data)
    with conn.transaction(), conn.cursor() as cur:
        cur.execute("SELECT COALESCE(MAX(version_number), 0) + 1 FROM content_version")
        version_number = cur.fetchone()[0]
        cur.execute("INSERT INTO content_version (version_number, is_active) VALUES (%s, false) RETURNING id",
                    (version_number,))
        version_id = cur.fetchone()[0]
        for table, columns in _TABLES.items():
            marks = ", ".join(["%s"] * (columns.count(",") + 3))         
            cur.executemany(f"INSERT INTO {table} (version_id, {columns}, position) VALUES ({marks})",
                            [(version_id, *row) for row in rows[table]])
 
        cur.execute("UPDATE content_version SET is_active = false WHERE is_active")
        cur.execute("UPDATE content_version SET is_active = true WHERE id = %s", (version_id,))
    return version_number




@lru_cache(maxsize=1)
def active_content():
    """(version_number, taxonomy_data, frames_data) of the active version, or None.

    Tried ONCE per process, so the per-question path never touches the database; a restart picks up a new version.
    None means "use the YAML files": no DATABASE_URL, the database cannot be reached, or no version is active.
    The log line carries the error class only, never the message, because a connection error can hold the URL.
    """
    url = os.getenv("DATABASE_URL")
    if not url:
        return None
    try:
        with connect(url) as conn:
            found = read_active(conn)
    except Exception as error:
        logger.warning("Policy content database not usable (%s); using the YAML files", type(error).__name__)
        return None
    if found is None:
        logger.warning("No active policy content version in the database; using the YAML files")
    else:
        logger.info("Policy content: using database version %s", found[0])
    return found


def active_version():
    """The version number in use, or "yaml" when the YAML files are. For the per-question log line."""
    if os.getenv("POLICY_TAXONOMY_PATH") or os.getenv("POLICY_FRAMES_PATH"):
        return "yaml"                                  
    found = active_content()
    return found[0] if found else "yaml"
