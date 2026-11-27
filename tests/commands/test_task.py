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
    return taiga.last("GET", "/api/v1/tasks").url.params


# -- list ------------------------------------------------------------------


def test_list_default_compact(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(taiga, "task", "list", "-P", "web")
    assert result.exit_code == 0, result.output
    assert result.output == (
        "#11\tIn progress\tTask 11\tbob\t#1\n"
        "#12\tIn progress\tTask 12\tbob\t-\n"
    )  # fmt: skip
    params = _params(taiga)
    assert params["project"] == "5"
    assert params["status__is_closed"] == "false"


def test_list_resolves_task_statuses(invoke, logged_in, taiga: FakeTaiga) -> None:
    # "Closed" exists only among task statuses, "Done" only among story statuses
    result = invoke(taiga, "task", "list", "-P", "web", "--status", "closed,new", "--state", "all")
    assert result.exit_code == 0, result.output
    assert _params(taiga)["status"] == "22,20"
    result = invoke(taiga, "task", "list", "-P", "web", "--status", "Done")
    assert result.exit_code == 2
    assert result.output == "error: unknown status 'Done'; available: New,In progress,Closed\n"


def test_list_by_story(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(taiga, "task", "list", "--story", "web#1", "--assignee", "bob")
    assert result.exit_code == 0, result.output
    params = _params(taiga)
    assert params["user_story"] == "101"
    assert params["assigned_to"] == "8"
    assert taiga.last("GET", "/api/v1/userstories/by_ref").url.params["ref"] == "1"


def test_list_story_conflicting_project(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(taiga, "task", "list", "-P", "api", "--story", "web#1")
    assert result.exit_code == 2
    assert "conflicts with -P api" in result.output


def test_list_unknown_story(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(taiga, "task", "list", "-P", "web", "--story", "99")
    assert result.exit_code == 4
    assert result.output == "error: story web#99 not found\n"


def test_list_sprint(invoke, logged_in, taiga: FakeTaiga) -> None:
    invoke(taiga, "task", "list", "-P", "web", "--sprint", "Sprint 12", "--tag", "backend")
    params = _params(taiga)
    assert params["milestone"] == "30"
    assert params["tags"] == "backend"


def test_list_backlog_sprint_rejected(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(taiga, "task", "list", "-P", "web", "--sprint", "backlog")
    assert result.exit_code == 2
    assert "backlog" in result.output


def test_list_fields_json_and_raw(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(taiga, "task", "list", "-P", "web", "--json", "--fields", "ref,story,sprint")
    assert json.loads(result.output) == [
        {"ref": "#11", "story": "#1", "sprint": "sprint-12"},
        {"ref": "#12", "story": None, "sprint": "sprint-12"},
    ]
    result = invoke(taiga, "task", "list", "-P", "web", "--raw")
    assert json.loads(result.output) == taiga.tasks


def test_list_offline_statuses_from_project_file(
    invoke, logged_in, taiga: FakeTaiga, isolated_cwd: Path
) -> None:
    write_project_config(
        isolated_cwd, statuses={"task": [{"id": 22, "name": "Closed", "slug": "closed"}]}
    )
    result = invoke(taiga, "task", "list", "--status", "Closed")
    assert result.exit_code == 0, result.output
    assert api_paths(taiga) == ["GET /tasks"]
    assert _params(taiga)["status"] == "22"


# -- update ----------------------------------------------------------------


def _patch_body(taiga: FakeTaiga, task_id: int = 211) -> dict[str, Any]:
    return json.loads(taiga.last("PATCH", f"/api/v1/tasks/{task_id}").content)


def test_update_status(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(taiga, "task", "update", "web#11", "--status", "Closed")
    assert result.exit_code == 0, result.output
    assert result.output == "ok: web#11\n"
    assert _patch_body(taiga) == {"status": 22, "version": 5}
    assert taiga.last("GET", "/api/v1/tasks/by_ref").url.params["ref"] == "11"


def test_update_many_fields(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(
        taiga, "task", "update", "11", "-P", "web",
        "--subject", "Renamed", "--assignee", "me", "--add-tag", "urgent",
        "--remove-tag", "backend", "--comment", "-",
        input="done in PR 7\n",
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    assert _patch_body(taiga) == {
        "subject": "Renamed",
        "assigned_to": 7,
        "comment": "done in PR 7\n",
        "tags": ["urgent"],
        "version": 5,
    }


def test_update_has_no_sprint_option(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(taiga, "task", "update", "web#11", "--sprint", "backlog")
    assert result.exit_code == 2
    assert "No such option" in result.output


def test_update_retries_on_conflict(invoke, logged_in, taiga: FakeTaiga) -> None:
    taiga.patch_responses = [httpx.Response(400, json={"version": "doesn't match"})]
    result = invoke(taiga, "task", "update", "web#11", "--status", "New")
    assert result.exit_code == 0, result.output
    assert len([r for r in taiga.requests if r.method == "PATCH"]) == 2


def test_update_missing_task(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(taiga, "task", "update", "web#99", "--status", "New")
    assert result.exit_code == 4
    assert result.output == "error: task web#99 not found\n"


def test_update_raw(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(taiga, "task", "update", "web#12", "--subject", "X", "--raw")
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert (data["ref"], data["subject"]) == (12, "X")
