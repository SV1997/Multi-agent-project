"""LOCALIZE is exactly "on" or "off" (default off). Run from services/orchestrator: python -m pytest tests/test_config_localize.py"""
import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))
from app.core import config  # noqa: E402


@pytest.mark.parametrize("value, expected", [
    (None, "off"), ("on", "on"), (" ON ", "on"), ("off", "off"),
    ("filter", "off"), ("prompt", "off"), ("full", "off"), ("yes", "off"), ("", "off"),
])
def test_localize_is_on_or_off_and_anything_else_is_off(monkeypatch, value, expected):
    try:
        if value is None:
            monkeypatch.delenv("LOCALIZE", raising=False)
        else:
            monkeypatch.setenv("LOCALIZE", value)
        assert importlib.reload(config).LOCALIZE == expected
    finally:
        monkeypatch.undo()
        importlib.reload(config)          # leave the module as the other tests expect it
