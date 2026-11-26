import contextlib
import os

import pytest

# Read before any test imports the app, whose load_dotenv() would fill this in from the service's .env.
# Database tests run only against a database named in the shell, never against the .env one by accident.
EXPLICIT_DATABASE_URL = os.environ.get("DATABASE_URL")


def pytest_configure(config):
    config.addinivalue_line("markers", "real_bm25_lock: keep the real keyword-index lock instead of the no-op")


@pytest.fixture(autouse=True)
def no_bm25_lock(request, monkeypatch):
    """The real lock opens a database connection; tests that fake load/save must not need one."""
    if request.node.get_closest_marker("real_bm25_lock"):
        return
    from app.api import route   # imported here so that test modules can stub shared modules first

    @contextlib.asynccontextmanager
    async def no_lock(namespace: str):
        yield

    monkeypatch.setattr(route, "bm25_lock", no_lock)
