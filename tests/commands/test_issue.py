from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from tests.fakes import FakeTaiga
from tests.test_project_file import api_paths, write_project_config


@pytest.fixture
def taiga() -> FakeTaiga:
    return FakeTaiga()


def _params(taiga: FakeTaiga) -> httpx.QueryParams:
    return taiga.last("GET", "/api/v1/issues").url.params


# -- list ------------------------------------------------------------------


def test_list_default_shows_value_names(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(taiga, "issue", "list", "-P", "web")
    assert result.exit_code == 0, result.output
    assert result.output == (
        "#7\tOpen\tBug\tHigh\tIssue 7\t-\n"
        "#8\tOpen\tEnhancement\t-\tIssue 8\t-\n"
    )  # fmt: skip
    assert _params(taiga)["status__is_closed"] == "false"


def test_list_filters_by_values(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(
        taiga, "issue", "list", "-P", "web",
        "--type", "bug", "--priority", "High,low", "--severity", "critical",
        "--status", "Closed", "--state", "all",
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    params = _params(taiga)
    assert (params["type"], params["priority"], params["severity"]) == ("50", "61,60", "71")
    assert params["status"] == "41"


def test_list_unknown_value_lists_choices(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(taiga, "issue", "list", "-P", "web", "--severity", "Blocker")
    assert result.exit_code == 2
    assert result.output == "error: unknown severity 'Blocker'; available: Minor,Critical\n"


def test_list_fields_without_value_columns_need_no_names(
    invoke, logged_in, taiga: FakeTaiga, isolated_cwd: Path
) -> None:
    write_project_config(isolated_cwd)  # has no issue_types/priorities/severities
    result = invoke(taiga, "issue", "list", "--fields", "ref,subject")
    assert result.exit_code == 0, result.output
    assert api_paths(taiga) == ["GET /issues"]


def test_list_value_names_from_project_file(
    invoke, logged_in, taiga: FakeTaiga, isolated_cwd: Path
) -> None:
    write_project_config(
        isolated_cwd,
        issue_types=[{"id": 50, "name": "Bug"}, {"id": 51, "name": "Enhancement"}],
        severities=[{"id": 70, "name": "Minor"}, {"id": 71, "name": "Critical"}],
    )
    result = invoke(taiga, "issue", "list", "--fields", "ref,type,severity", "--json")
    assert result.exit_code == 0, result.output
    assert api_paths(taiga) == ["GET /issues"]  # names resolved offline
    assert json.loads(result.output) == [
        {"ref": "#7", "type": "Bug", "severity": "Critical"},
        {"ref": "#8", "type": "Enhancement", "severity": "Minor"},
    ]


def test_list_value_names_fall_back_to_server(
    invoke, logged_in, taiga: FakeTaiga, isolated_cwd: Path
) -> None:
    write_project_config(isolated_cwd)  # file lacks priorities
    result = invoke(taiga, "issue", "list", "--fields", "ref,priority")
    assert result.exit_code == 0, result.output
    assert api_paths(taiga) == ["GET /issues", "GET /projects/by_slug"]
    assert result.output == "#7\tHigh\n#8\t-\n"


def test_list_raw_needs_no_names(invoke, logged_in, taiga: FakeTaiga, isolated_cwd: Path) -> None:
    write_project_config(isolated_cwd)
    result = invoke(taiga, "issue", "list", "--raw")
    assert json.loads(result.output) == taiga.issues
    assert api_paths(taiga) == ["GET /issues"]


def test_list_sprint(invoke, logged_in, taiga: FakeTaiga) -> None:
    invoke(taiga, "issue", "list", "-P", "web", "--sprint", "sprint-12")
    assert _params(taiga)["milestone"] == "30"
    result = invoke(taiga, "issue", "list", "-P", "web", "--sprint", "backlog")
    assert result.exit_code == 2


# -- update ----------------------------------------------------------------


def _patch_body(taiga: FakeTaiga, issue_id: int = 307) -> dict[str, Any]:
    return json.loads(taiga.last("PATCH", f"/api/v1/issues/{issue_id}").content)


def test_update_values(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(
        taiga, "issue", "update", "web#7",
        "--status", "closed", "--type", "Enhancement", "--priority", "low",
        "--severity", "Minor", "--assignee", "bob", "--sprint", "backlog",
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    assert result.output == "ok: web#7\n"
    assert _patch_body(taiga) == {
        "status": 41,
        "type": 51,
        "priority": 60,
        "severity": 70,
        "assigned_to": 8,
        "milestone": None,
        "version": 2,
    }


def test_update_unknown_priority(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(taiga, "issue", "update", "web#7", "--priority", "Urgent")
    assert result.exit_code == 2
    assert result.output == "error: unknown priority 'Urgent'; available: Low,High\n"
    assert not [r for r in taiga.requests if r.method == "PATCH"]


def test_update_comment_and_tags(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(
        taiga, "issue", "update", "8", "-P", "web", "--comment", "repro'd", "--add-tag", "ui"
    )
    assert result.exit_code == 0, result.output
    assert _patch_body(taiga, 308) == {"comment": "repro'd", "tags": ["ui"], "version": 2}


def test_update_missing_issue(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(taiga, "issue", "update", "web#99", "--status", "Open")
    assert result.exit_code == 4
    assert result.output == "error: issue web#99 not found\n"
