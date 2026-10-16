"""Feature 4 (orchestrator side): new SQL functions are on the planner menu and the right agents.
Run from services/orchestrator: python -m pytest tests/test_sql_menu.py"""
import os
import sys
from typing import get_args

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))
from app.graph.agents.base.agent_factory import SQL_FUNCTION_DESCRIPTIONS  # noqa: E402
from shared.contracts.schema import SQLQuerySelection  # noqa: E402

AGENTS = os.path.join(os.path.dirname(__file__), "../app/graph/agents")
NEW = {"claims_by_status_for_team": "finance_agent", "leave_taken_by_month": "hr_agent"}


def test_menu_matches_selection_schema():
    literal = set(get_args(SQLQuerySelection.model_fields["query_name"].annotation))
    assert literal == set(SQL_FUNCTION_DESCRIPTIONS)


def test_new_functions_assigned_to_one_agent_each():
    for fn, agent in NEW.items():
        for name in os.listdir(AGENTS):
            graph = os.path.join(AGENTS, name, "graph.py")
            if os.path.isfile(graph):
                assert (f'"{fn}"' in open(graph, encoding="utf-8").read()) == (name == agent), (fn, name)
