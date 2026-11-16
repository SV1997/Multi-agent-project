"""The taxonomy and frames stored in the database: same result as the YAML, same checks, YAML fallback.

Run from services/orchestrator:  python -m pytest tests/test_content_store.py
No real Postgres is needed: FakePostgres is an in-memory sqlite database behind the small part of the psycopg
interface that content_store.py uses, so the real read_active / write_version SQL runs against real tables.
"""
import copy
import logging
import os
import sqlite3
import sys
from contextlib import contextmanager

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))
from shared.taxonomy import content_store, taxonomy as taxonomy_module  # noqa: E402
from shared.taxonomy.taxonomy import TaxonomyError, load_taxonomy  # noqa: E402
from app.graph.frames import registry as registry_module  # noqa: E402
from app.graph.frames.registry import load_registry  # noqa: E402

TAXONOMY_YAML = os.path.join(os.path.dirname(taxonomy_module.__file__), "policy_taxonomy.yaml")
FRAMES_YAML = os.path.join(registry_module.HERE, "frames.yaml")
SECRET_URL = "postgresql://someone:hunter2@db.example.com/neondb"

SCHEMA = """
CREATE TABLE content_version (id INTEGER PRIMARY KEY AUTOINCREMENT, version_number INTEGER NOT NULL UNIQUE,
                              is_active BOOLEAN NOT NULL DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE UNIQUE INDEX one_active ON content_version(is_active) WHERE is_active;
CREATE TABLE category (version_id INT, domain TEXT, name TEXT, description TEXT, position INT);
CREATE TABLE category_parent (version_id INT, domain TEXT, name TEXT, parent_name TEXT, position INT);
CREATE TABLE frame (version_id INT, frame_id TEXT, domain TEXT, description TEXT, position INT);
CREATE TABLE frame_category (version_id INT, frame_id TEXT, category_name TEXT, position INT);
CREATE TABLE document (version_id INT, domain TEXT, file_name TEXT, title TEXT, position INT);
CREATE TABLE document_category (version_id INT, domain TEXT, file_name TEXT, category_name TEXT, position INT);
"""


class FakeCursor:
    def __init__(self, cursor):
        self.cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=()):
        self.cursor.execute(sql.replace("%s", "?"), params)

    def executemany(self, sql, rows):
        self.cursor.executemany(sql.replace("%s", "?"), rows)

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()


class FakePostgres:
    def __init__(self):
        self.db = sqlite3.connect(":memory:", isolation_level=None)
        self.db.executescript(SCHEMA)

    def cursor(self):
        return FakeCursor(self.db.cursor())

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN")
        try:
            yield
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        self.db.execute("COMMIT")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def yaml_data():
    with open(TAXONOMY_YAML, encoding="utf-8") as f1, open(FRAMES_YAML, encoding="utf-8") as f2:
        return yaml.safe_load(f1), yaml.safe_load(f2)


def snapshot(taxonomy):
    """Everything in a Taxonomy, in order: dict equality alone would ignore the order the yaml listed things in."""
    return {
        "categories": [(d, [(c.name, c.description, c.parents) for c in cats.values()])
                       for d, cats in taxonomy.categories.items()],
        "documents": [(d, list(docs.items())) for d, docs in taxonomy.documents.items()],
        "titles": [(d, list(titles.items())) for d, titles in taxonomy.titles.items()],
    }


def registry_snapshot(registry):
    return [(d, list(frames)) for d, frames in registry.items()]


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    for name in ("DATABASE_URL", "POLICY_TAXONOMY_PATH", "POLICY_FRAMES_PATH"):
        monkeypatch.delenv(name, raising=False)
    for cached in (content_store.active_content, load_taxonomy):
        cached.cache_clear()
    registry_module._built.clear()
    yield
    for cached in (content_store.active_content, load_taxonomy):
        cached.cache_clear()
    registry_module._built.clear()


@pytest.fixture
def database(monkeypatch):
    """A fake database that load_taxonomy / load_registry will find through DATABASE_URL. Counts the connections."""
    fake = FakePostgres()
    fake.connections = 0

    def connect(url):
        fake.connections += 1
        return fake

    monkeypatch.setenv("DATABASE_URL", SECRET_URL)
    monkeypatch.setattr(content_store, "connect", connect)
    return fake


def yaml_result():
    taxonomy = load_taxonomy(TAXONOMY_YAML)
    return taxonomy, load_registry(taxonomy, FRAMES_YAML)


def reset_caches():
    for cached in (content_store.active_content, load_taxonomy):
        cached.cache_clear()
    registry_module._built.clear()


# ---------------------------------------------------------------- the database gives the same result as the YAML

def test_database_gives_the_same_taxonomy_and_frames_as_the_yaml(database):
    expected_taxonomy, expected_registry = yaml_result()
    reset_caches()
    content_store.write_version(database, *yaml_data())

    taxonomy = load_taxonomy()
    registry = load_registry(taxonomy)

    assert snapshot(taxonomy) == snapshot(expected_taxonomy)
    assert registry_snapshot(registry) == registry_snapshot(expected_registry)


def test_the_database_is_read_once_and_the_same_objects_come_back(database):
    content_store.write_version(database, *yaml_data())

    first = load_taxonomy()
    registry = load_registry(first)
    for _ in range(5):                                   # what five more questions do
        assert load_taxonomy() is first
        assert load_registry(first) is registry
        content_store.active_version()

    assert database.connections == 1


def test_the_log_version_is_the_database_version(database):
    content_store.write_version(database, *yaml_data())
    assert content_store.active_version() == 1


def test_a_new_version_replaces_the_old_one_and_only_one_is_active(database):
    taxonomy_data, frames_data = yaml_data()
    content_store.write_version(database, taxonomy_data, frames_data)
    changed = copy.deepcopy(frames_data)
    changed["hr"]["hr.notice_period"]["description"] = "a new description"
    assert content_store.write_version(database, taxonomy_data, changed) == 2

    active = database.db.execute("SELECT version_number FROM content_version WHERE is_active").fetchall()
    assert active == [(2,)]
    registry = load_registry(load_taxonomy())
    assert {f.frame_id: f.description for f in registry["hr"]}["hr.notice_period"] == "a new description"
    with pytest.raises(sqlite3.IntegrityError):          # the partial unique index: two active rows are impossible
        database.db.execute("UPDATE content_version SET is_active = 1")


# ---------------------------------------------------------------- the existing checks still run on database data

def test_a_cycle_in_the_database_is_rejected(database):
    taxonomy_data, frames_data = yaml_data()
    taxonomy_data["hr"]["categories"]["leave"]["parents"] = ["earned_leave"]      # leave -> earned_leave -> leave
    content_store.write_version(database, taxonomy_data, frames_data)

    with pytest.raises(TaxonomyError, match="parent cycle"):
        load_taxonomy()


def test_a_frame_naming_a_missing_category_in_the_database_is_rejected(database):
    taxonomy_data, frames_data = yaml_data()
    frames_data["hr"]["hr.provident_fund"]["categories"] = ["no_such_category"]
    content_store.write_version(database, taxonomy_data, frames_data)

    taxonomy = load_taxonomy()
    with pytest.raises(ValueError, match="hr.provident_fund: unknown category 'no_such_category'"):
        load_registry(taxonomy)


# ---------------------------------------------------------------- the YAML fallback

def test_no_active_version_falls_back_to_the_yaml(database):
    expected_taxonomy, expected_registry = yaml_result()
    reset_caches()                                       # the database exists but holds no version

    taxonomy = load_taxonomy()
    assert snapshot(taxonomy) == snapshot(expected_taxonomy)
    assert registry_snapshot(load_registry(taxonomy)) == registry_snapshot(expected_registry)
    assert content_store.active_version() == "yaml"


def test_an_unreachable_database_falls_back_to_the_yaml_without_leaking_the_url(monkeypatch, caplog):
    expected_taxonomy, expected_registry = yaml_result()
    reset_caches()
    monkeypatch.setenv("DATABASE_URL", SECRET_URL)

    def unreachable(url):
        raise RuntimeError(f"could not connect to {url}")        # a connection error can carry the whole URL

    monkeypatch.setattr(content_store, "connect", unreachable)
    with caplog.at_level(logging.INFO):
        taxonomy = load_taxonomy()
        registry = load_registry(taxonomy)

    assert snapshot(taxonomy) == snapshot(expected_taxonomy)
    assert registry_snapshot(registry) == registry_snapshot(expected_registry)
    assert "hunter2" not in caplog.text and SECRET_URL not in caplog.text
    assert "RuntimeError" in caplog.text


def test_no_database_url_never_connects(monkeypatch):
    def must_not_connect(url):
        raise AssertionError("connected without a DATABASE_URL")

    monkeypatch.setattr(content_store, "connect", must_not_connect)
    assert content_store.active_content() is None
    assert load_taxonomy().names("hr")


def test_an_explicit_file_path_wins_over_the_database(database):
    taxonomy_data, frames_data = yaml_data()
    del taxonomy_data["hr"]["categories"]["comp_off_and_lwp"]                    # make the database differ
    taxonomy_data["hr"]["documents"]["tmp5jdxnb7a.pdf"]["categories"].remove("comp_off_and_lwp")
    content_store.write_version(database, taxonomy_data, frames_data)

    from_file = load_taxonomy(TAXONOMY_YAML)
    assert "comp_off_and_lwp" in from_file.names("hr")
    assert database.connections == 0


# ---------------------------------------------------------------- the row conversion on its own

def test_rows_round_trip_the_yaml_dicts_including_the_short_document_form():
    taxonomy_data = {
        "hr": {"categories": {"leave": {"description": "leave", "parents": []},
                              "earned": {"description": "earned", "parents": ["leave"]}},
               "documents": {"a.pdf": {"title": "Handbook", "categories": ["earned"]}, "b.md": ["leave"]}},
    }
    frames_data = {"version": 2, "hr": {"hr.leave": {"description": "leave", "categories": ["leave", "earned"]}}}

    rows = content_store.to_rows(taxonomy_data, frames_data)
    back_taxonomy, back_frames = content_store.from_rows({t: [r[:-1] for r in rs] for t, rs in rows.items()})

    assert back_taxonomy["hr"]["categories"] == taxonomy_data["hr"]["categories"]
    assert back_taxonomy["hr"]["documents"] == {"a.pdf": {"title": "Handbook", "categories": ["earned"]},
                                                "b.md": {"categories": ["leave"]}}
    assert back_frames == {"hr": {"hr.leave": {"description": "leave", "categories": ["leave", "earned"]}}}
