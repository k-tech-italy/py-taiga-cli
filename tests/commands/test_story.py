from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from taiga_cli.api.items import parse_ref
from taiga_cli.errors import UsageError
from tests.fakes import PROJECT, FakeTaiga


@pytest.fixture
def taiga() -> FakeTaiga:
    return FakeTaiga()


# -- parse_ref -------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "project", "expected"),
    [
        ("web#42", None, ("web", 42)),
        ("42", "web", ("web", 42)),
        ("#42", "web", ("web", 42)),
        ("web#42", "web", ("web", 42)),
        ("42", None, (None, 42)),  # project then comes from .taiga-cli-config.json
    ],
)
def test_parse_ref(value: str, project: str | None, expected: tuple[str, int]) -> None:
    assert parse_ref(value, project) == expected


@pytest.mark.parametrize(
    ("value", "project", "message"),
    [
        ("web#42", "api", "conflicts"),
        ("web#x", None, "invalid ref"),
    ],
)
def test_parse_ref_errors(value: str, project: str | None, message: str) -> None:
    with pytest.raises(UsageError, match=message):
        parse_ref(value, project)


# -- list ------------------------------------------------------------------


def test_list_default_compact(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(taiga, "story", "list", "-P", "web")
    assert result.exit_code == 0, result.output
    assert result.output == "#1\tIn progress\tStory 1\talice\n#2\tIn progress\tStory 2\t-\n"
    params = taiga.last("GET", "/api/v1/userstories").url.params
    assert params["project"] == "5"
    assert params["status__is_closed"] == "false"
    assert params["page_size"] == "20"


def test_list_resolves_filters(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(
        taiga, "story", "list", "-P", "web",
        "--status", "in progress,NEW", "--sprint", "sprint-12", "--assignee", "Bob B",
        "--tag", "api", "--tag", "ui", "--state", "all",
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    params = taiga.last("GET", "/api/v1/userstories").url.params
    assert params["status"] == "11,10"
    assert params["milestone"] == "30"
    assert params["assigned_to"] == "8"
    assert params["tags"] == "api,ui"
    assert "status__is_closed" not in params


def test_list_backlog_and_me(invoke, logged_in, taiga: FakeTaiga) -> None:
    invoke(taiga, "story", "list", "-P", "web", "--sprint", "backlog", "--assignee", "me")
    params = taiga.last("GET", "/api/v1/userstories").url.params
    assert params["milestone__isnull"] == "true"
    assert "milestone" not in params
    assert params["assigned_to"] == "7"  # from the profile, no /users/me call
    assert not [r for r in taiga.requests if r.url.path.endswith("/users/me")]


def test_list_sprint_falls_back_to_milestones_endpoint(invoke, logged_in) -> None:
    taiga = FakeTaiga({k: v for k, v in PROJECT.items() if k != "milestones"})
    result = invoke(taiga, "story", "list", "-P", "web", "--sprint", "Sprint 13")
    assert result.exit_code == 0, result.output
    assert taiga.last("GET", "/api/v1/userstories").url.params["milestone"] == "31"


def test_list_unknown_status_lists_choices(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(taiga, "story", "list", "-P", "web", "--status", "Doing")
    assert result.exit_code == 2
    assert result.output == "error: unknown status 'Doing'; available: New,In progress,Done\n"


def test_list_unknown_project(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(taiga, "story", "list", "-P", "nope")
    assert result.exit_code == 4
    assert result.output == "error: project 'nope' not found\n"


def test_list_fields_and_json(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(
        taiga, "story", "list", "-P", "web", "--json", "--fields", "ref,tags,epics,points"
    )
    assert json.loads(result.output) == [
        {"ref": "#1", "tags": "api,ui", "epics": "#2", "points": 3.0},
        {"ref": "#2", "tags": None, "epics": "#2", "points": 3.0},
    ]


def test_list_raw_is_full_payload(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(taiga, "story", "list", "-P", "web", "--raw")
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == taiga.stories
    assert "\n" not in result.output.rstrip("\n")  # compact JSON, not pretty-printed


def test_list_raw_rejects_fields(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(taiga, "story", "list", "-P", "web", "--raw", "--fields", "ref")
    assert result.exit_code == 2
    assert "--raw" in result.output
    assert taiga.requests == []  # validated before any API call


# -- update ----------------------------------------------------------------


def _patch_body(taiga: FakeTaiga) -> dict[str, Any]:
    return json.loads(taiga.last("PATCH", "/api/v1/userstories/101").content)


def test_update_status_sends_version(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(taiga, "story", "update", "web#1", "--status", "done")
    assert result.exit_code == 0, result.output
    assert result.output == "ok: web#1\n"
    assert _patch_body(taiga) == {"status": 12, "version": 3}


def test_update_many_fields(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(
        taiga, "story", "update", "1", "-P", "web",
        "--subject", "New title", "--assignee", "none", "--sprint", "backlog",
        "--add-tag", "db", "--add-tag", "api", "--remove-tag", "ui", "--comment", "moved",
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    assert _patch_body(taiga) == {
        "subject": "New title",
        "assigned_to": None,
        "milestone": None,
        "comment": "moved",
        "tags": ["api", "db"],
        "version": 3,
    }


def test_update_description_from_stdin(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(
        taiga, "story", "update", "web#1", "--description", "-", input="line 1\nline 2\n"
    )
    assert result.exit_code == 0, result.output
    assert _patch_body(taiga)["description"] == "line 1\nline 2\n"


def test_update_retries_once_on_version_conflict(invoke, logged_in, taiga: FakeTaiga) -> None:
    conflict = httpx.Response(400, json={"version": "The version doesn't match"})
    taiga.patch_responses = [conflict]
    result = invoke(taiga, "story", "update", "web#1", "--status", "New")
    assert result.exit_code == 0, result.output
    assert len([r for r in taiga.requests if r.method == "PATCH"]) == 2
    assert len([r for r in taiga.requests if r.url.path.endswith("/by_ref")]) == 2


def test_update_gives_up_after_second_conflict(invoke, logged_in, taiga: FakeTaiga) -> None:
    conflict = httpx.Response(400, json={"version": "The version doesn't match"})
    taiga.patch_responses = [conflict, conflict]
    result = invoke(taiga, "story", "update", "web#1", "--status", "New")
    assert result.exit_code == 1
    assert result.output.startswith("error: version conflict")


def test_update_raw_prints_updated_story(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(taiga, "story", "update", "web#1", "--subject", "X", "--raw")
    assert json.loads(result.output)["subject"] == "X"


def test_update_nothing_to_do(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(taiga, "story", "update", "web#1")
    assert result.exit_code == 2
    assert "nothing to update" in result.output
    assert taiga.requests == []


def test_update_missing_story(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(taiga, "story", "update", "web#99", "--status", "Done")
    assert result.exit_code == 4
    assert result.output == "error: story web#99 not found\n"
