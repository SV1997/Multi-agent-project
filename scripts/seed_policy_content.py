"""Seed the policy content tables from the two YAML files, as one new version, and make it the active one.

    uv run python scripts/seed_policy_content.py [--dry-run]

Reads shared/taxonomy/policy_taxonomy.yaml and services/orchestrator/app/graph/frames/frames.yaml, runs the SAME
checks the services run (parse_taxonomy: no cycles; build_registry: every frame category exists), and only then
writes. Nothing is written when a check fails. Uses DATABASE_URL (from the environment or .env); it is never printed.
The YAML files stay in the repo as this seed and as the fallback for a service with no database.
Each run adds a new version (the old ones stay in the tables), so running it twice is safe. Restart the services
afterwards: they read the active version once, at startup.
"""
import argparse
import os
import sys

import yaml

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "services", "orchestrator"))      # so `app.graph.frames` imports as in the service

from dotenv import load_dotenv                                           # noqa: E402
from shared.taxonomy.content_store import connect, to_rows, write_version  # noqa: E402
from shared.taxonomy.taxonomy import HERE as TAXONOMY_DIR, parse_taxonomy  # noqa: E402
from app.graph.frames.registry import HERE as FRAMES_DIR, build_registry   # noqa: E402


def read_yaml(path) -> dict:
    with open(path, encoding="utf-8") as file:
        return yaml.safe_load(file)


def checked_data() -> tuple[dict, dict]:
    """Both files, validated together. Raises TaxonomyError / ValueError listing every problem."""
    taxonomy_data = read_yaml(os.path.join(TAXONOMY_DIR, "policy_taxonomy.yaml"))
    frames_data = read_yaml(os.path.join(FRAMES_DIR, "frames.yaml"))
    build_registry(parse_taxonomy(taxonomy_data), frames_data)
    return taxonomy_data, frames_data


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dry-run", action="store_true", help="check the files and show the row counts; write nothing")
    args = parser.parse_args(argv)

    taxonomy_data, frames_data = checked_data()
    counts = {table: len(rows) for table, rows in to_rows(taxonomy_data, frames_data).items()}
    print("checked ok; rows:", counts)
    if args.dry_run:
        return 0

    load_dotenv(os.path.join(ROOT, "services", "orchestrator", ".env"))
    url = os.getenv("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set")
        return 1
    with connect(url) as conn:
        number = write_version(conn, taxonomy_data, frames_data)
    print(f"wrote content version {number} and made it active")
    return 0


if __name__ == "__main__":
    sys.exit(main())
