"""`<item> create` for stories, tasks, issues and epics."""

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


def _posted(taiga: FakeTaiga, path: str) -> dict[str, Any]:
    return json.loads(taiga.last("POST", f"/api/v1{path}").content)


def _writes(taiga: FakeTaiga) -> list[str]:
    return [p for p in api_paths(taiga) if not p.startswith("GET")]


# -- common behaviour (on stories) ---------------------------------------------


def test_minimal_create(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(taiga, "story", "create", "-P", "web", "--subject", "Login page")
    assert result.exit_code == 0, result.output
    assert result.output == "created: web#100\n"
    assert _posted(taiga, "/userstories") == {"project": 5, "subject": "Login page"}


def test_names_resolved_like_update(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(
        taiga, "story", "create", "-P", "web", "--subject", "Login page",
        "--description", "As a user...", "--status", "in progress", "--assignee", "Bob B",
        "--tag", "ui", "--tag", "auth", "--tag", "ui", "--sprint", "Sprint 12",
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    assert _posted(taiga, "/userstories") == {
        "project": 5,
        "subject": "Login page",
        "description": "As a user...",
        "status": 11,
        "assigned_to": 8,
        "tags": ["ui", "auth"],
        "milestone": 30,
    }


def test_description_from_stdin_and_backlog(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(
        taiga, "story", "create", "-P", "web", "--subject", "X", "--description", "-",
        "--sprint", "backlog", "--assignee", "me",
        input="line 1\nline 2\n",
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    body = _posted(taiga, "/userstories")
    assert body["description"] == "line 1\nline 2\n"
    assert body["assigned_to"] == 7
    assert "milestone" not in body


def test_unknown_name_lists_valid_ones_and_creates_nothing(
    invoke, logged_in, taiga: FakeTaiga
) -> None:
    result = invoke(taiga, "story", "create", "-P", "web", "--subject", "X", "--status", "Doing")
    assert result.exit_code == 2
    assert result.output == "error: unknown status 'Doing'; available: New,In progress,Done\n"
    assert _writes(taiga) == []


@pytest.mark.parametrize("args", [[], ["--subject", "   "]])
def test_subject_required(invoke, logged_in, taiga: FakeTaiga, args: list[str]) -> None:
    result = invoke(taiga, "story", "create", "-P", "web", *args)
    assert result.exit_code == 2
    assert taiga.requests == []


def test_not_logged_in_is_exit_3(invoke, logged_in, taiga: FakeTaiga, memory_keyring) -> None:
    memory_keyring.store.clear()
    result = invoke(taiga, "story", "create", "-P", "web", "--subject", "X")
    assert result.exit_code == 3


def test_api_error_is_exit_1_and_prints_no_ref(invoke, logged_in, taiga: FakeTaiga) -> None:
    taiga.failures[("POST", "/userstories")] = httpx.Response(500, json={"detail": "boom"})
    result = invoke(taiga, "story", "create", "-P", "web", "--subject", "X")
    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr == "error: HTTP 500: boom\n"


def test_json_prints_normalised_fields(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(
        taiga, "story", "create", "-P", "web", "--subject", "Login", "--status", "New",
        "--tag", "ui", "--json",
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["created"] is True
    assert (data["ref"], data["subject"], data["status"], data["tags"]) == (
        "#100",
        "Login",
        "New",
        "ui",
    )


# -- project defaults from .taiga-cli-config.json --------------------------------


def test_defaults_from_project_config(invoke, logged_in, taiga: FakeTaiga, isolated_cwd) -> None:
    write_project_config(
        isolated_cwd,
        defaults={
            "userstory_status": {"id": 10, "name": "New"},
            "issue_type": {"id": 51, "name": "Enhancement"},
            "priority": {"id": 60, "name": "Low"},
            "severity": None,
        },
    )
    assert invoke(taiga, "story", "create", "--subject", "A").exit_code == 0
    assert _posted(taiga, "/userstories")["status"] == 10
    # an explicit option wins over the default
    assert invoke(taiga, "story", "create", "--subject", "B", "--status", "Done").exit_code == 0
    assert _posted(taiga, "/userstories")["status"] == 12

    result = invoke(taiga, "issue", "create", "--subject", "C", "--priority", "High")
    assert result.exit_code == 0, result.output
    body = _posted(taiga, "/issues")
    assert (body["type"], body["priority"]) == (51, 61)
    assert "severity" not in body  # no default in the file: Taiga applies its own
    assert "status" not in body


# -- --custom NAME=VALUE ---------------------------------------------------------


def _custom(taiga: FakeTaiga, path: str) -> dict[str, Any]:
    return taiga.custom_values[path]["attributes_values"]


def test_custom_fields_typed(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(
        taiga, "story", "create", "-P", "web", "--subject", "X",
        "--custom", "priority=2", "--custom", "Customer=acme",
        "--custom", "Billable=yes", "--custom", "Due=2026-12-01",
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    assert result.output == "created: web#100\n"
    assert _custom(taiga, "/userstories/custom-attributes-values/200") == {
        "90": 2,
        "91": "ACME",
        "92": True,
        "93": "2026-12-01",
    }


def test_custom_fields_from_project_config_offline(
    invoke, logged_in, taiga: FakeTaiga, isolated_cwd
) -> None:
    write_project_config(
        isolated_cwd, custom_fields={"task": [{"id": 95, "name": "Estimate", "type": "number"}]}
    )
    result = invoke(taiga, "task", "create", "--subject", "T", "--custom", "Estimate=1.5")
    assert result.exit_code == 0, result.output
    assert "GET /projects/by_slug" not in api_paths(taiga)
    assert _custom(taiga, "/tasks/custom-attributes-values/300") == {"95": 1.5}


@pytest.mark.parametrize(
    ("custom", "message"),
    [
        ("Prio=1", "unknown custom field 'Prio'; available: Priority,Customer,Billable,Due"),
        ("Customer=Initech", "unknown option 'Initech'; available: ACME,Globex"),
        ("Priority=high", "expected a number"),
        ("Billable=maybe", "expected true/false"),
        ("Due=next week", "expected a date"),
    ],
)
def test_bad_custom_field_creates_nothing(
    invoke, logged_in, taiga: FakeTaiga, custom: str, message: str
) -> None:
    result = invoke(taiga, "story", "create", "-P", "web", "--subject", "X", "--custom", custom)
    assert result.exit_code == 2
    assert message in result.output
    assert _writes(taiga) == []


@pytest.mark.parametrize("custom", [["noequals"], ["=1"], ["A=1", "a=2"]])
def test_custom_syntax_checked_before_any_request(
    invoke, logged_in, taiga: FakeTaiga, custom: list[str]
) -> None:
    args = [a for c in custom for a in ("--custom", c)]
    result = invoke(taiga, "story", "create", "-P", "web", "--subject", "X", *args)
    assert result.exit_code == 2
    assert taiga.requests == []


def test_custom_field_failure_reports_created_ref(invoke, logged_in, taiga: FakeTaiga) -> None:
    path = "/userstories/custom-attributes-values/200"
    taiga.failures[("PATCH", path)] = httpx.Response(500, json={"detail": "nope"})
    result = invoke(
        taiga, "story", "create", "-P", "web", "--subject", "X", "--custom", "Due=2026-01-02"
    )
    assert result.exit_code == 1
    assert result.stdout == "created: web#100\n"
    assert result.stderr == (
        "error: web#100 was created, but setting custom fields failed: HTTP 500: nope\n"
    )


# -- --if-absent -------------------------------------------------------------------


def test_if_absent_finds_existing_open_item(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(taiga, "story", "create", "-P", "web", "--subject", " Story 2 ", "--if-absent")
    assert result.exit_code == 0, result.output
    assert result.output == "exists: web#2\n"
    assert _writes(taiga) == []
    params = taiga.last("GET", "/api/v1/userstories").url.params
    assert (params["status__is_closed"], params["q"]) == ("false", " Story 2 ")


def test_if_absent_ignores_closed_and_partial_matches(invoke, logged_in, taiga: FakeTaiga) -> None:
    taiga.stories[0]["is_closed"] = True  # "Story 1" is closed
    for subject in ("Story 1", "Story"):
        result = invoke(taiga, "story", "create", "-P", "web", "--subject", subject, "--if-absent")
        assert result.output.startswith("created: "), result.output
    assert len(_writes(taiga)) == 2


def test_if_absent_json(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(
        taiga, "epic", "create", "-P", "web", "--subject", "Epic 3", "--if-absent", "--json"
    )
    data = json.loads(result.output)
    assert (data["ref"], data["created"]) == ("#3", False)


def test_if_absent_then_create_is_idempotent(invoke, logged_in, taiga: FakeTaiga) -> None:
    args = ["issue", "create", "-P", "web", "--subject", "Crash", "--if-absent"]
    assert invoke(taiga, *args).output == "created: web#100\n"
    assert invoke(taiga, *args).output == "exists: web#100\n"
    assert len(taiga.issues) == 3


# -- story create --epic -------------------------------------------------------------


def test_story_epic_links(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(
        taiga, "story", "create", "-P", "web", "--subject", "X",
        "--epic", "3", "--epic", "web#4", "--epic", "#3",
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    assert taiga.epic_links[403] == [102, 200]
    assert taiga.epic_links[404] == [200]
    assert _writes(taiga).count("POST /epics/403/related_userstories") == 1


def test_story_json_reflects_links(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(
        taiga, "story", "create", "-P", "web", "--subject", "X", "--epic", "3", "--json"
    )
    assert result.exit_code == 0, result.output
    assert taiga.last("GET", "/api/v1/userstories/by_ref").url.params["ref"] == "100"


def test_unknown_epic_creates_nothing(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(taiga, "story", "create", "-P", "web", "--subject", "X", "--epic", "99")
    assert result.exit_code == 4
    assert result.output == "error: epic web#99 not found\n"
    assert _writes(taiga) == []


def test_epic_link_failure_reports_created_ref(invoke, logged_in, taiga: FakeTaiga) -> None:
    taiga.failures[("POST", "/epics/404/related_userstories")] = httpx.Response(
        403, json={"_error_message": "no permission"}
    )
    result = invoke(
        taiga, "story", "create", "-P", "web", "--subject", "X", "--epic", "3", "--epic", "4"
    )
    assert result.exit_code == 3  # the failing step's exit code (auth)
    assert result.stdout == "created: web#100\n"
    assert result.stderr == (
        "error: web#100 was created, but linking to epic web#4 failed: "
        "not authorised (403): no permission\n"
    )
    assert taiga.epic_links[403] == [102, 200]  # the first link was made


# -- task create --story -------------------------------------------------------------


def test_task_story_and_its_sprint(invoke, logged_in, taiga: FakeTaiga) -> None:
    taiga.stories[0]["milestone"] = 30
    result = invoke(taiga, "task", "create", "--subject", "Write tests", "--story", "web#1")
    assert result.exit_code == 0, result.output
    assert result.output == "created: web#100\n"
    body = _posted(taiga, "/tasks")
    assert (body["user_story"], body["milestone"]) == (101, 30)
    assert len([p for p in api_paths(taiga) if p == "GET /userstories/by_ref"]) == 1


def test_task_sprint_overrides_story_sprint(invoke, logged_in, taiga: FakeTaiga) -> None:
    taiga.stories[0]["milestone"] = 31
    result = invoke(
        taiga,
        "task",
        "create",
        "-P",
        "web",
        "--subject",
        "T",
        "--story",
        "1",
        "--sprint",
        "Sprint 12",
    )
    assert result.exit_code == 0, result.output
    assert _posted(taiga, "/tasks")["milestone"] == 30


def test_task_json_shows_story(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(
        taiga, "task", "create", "-P", "web", "--subject", "T", "--story", "2", "--json"
    )
    assert json.loads(result.output)["story"] == "#2"


@pytest.mark.parametrize(
    ("args", "code"),
    [(["-P", "api", "--story", "web#1"], 2), (["-P", "web", "--story", "99"], 4)],
)
def test_task_bad_story_creates_nothing(
    invoke, logged_in, taiga: FakeTaiga, args: list[str], code: int
) -> None:
    result = invoke(taiga, "task", "create", "--subject", "T", *args)
    assert result.exit_code == code
    assert _writes(taiga) == []


# -- issue / epic specifics -------------------------------------------------------------


def test_issue_values_and_json_names(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(
        taiga, "issue", "create", "-P", "web", "--subject", "Crash",
        "--type", "bug", "--priority", "high", "--severity", "critical", "--status", "Open",
        "--custom", "Browser=Firefox 140", "--json",
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    body = _posted(taiga, "/issues")
    assert (body["type"], body["priority"], body["severity"], body["status"]) == (50, 61, 71, 40)
    data = json.loads(result.output)
    assert (data["type"], data["priority"], data["severity"]) == ("Bug", "High", "Critical")
    assert _custom(taiga, "/issues/custom-attributes-values/400") == {"96": "Firefox 140"}


def test_issue_unknown_severity(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(
        taiga, "issue", "create", "-P", "web", "--subject", "C", "--severity", "Blocker"
    )
    assert result.exit_code == 2
    assert result.output == "error: unknown severity 'Blocker'; available: Minor,Critical\n"


def test_epic_color_and_custom(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(
        taiga, "epic", "create", "-P", "web", "--subject", "Onboarding",
        "--color", "FF8800", "--custom", "Quarter=q3",
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    assert _posted(taiga, "/epics")["color"] == "#ff8800"
    assert _custom(taiga, "/epics/custom-attributes-values/500") == {"97": "Q3"}


def test_epic_bad_color_before_any_request(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(taiga, "epic", "create", "-P", "web", "--subject", "E", "--color", "orange")
    assert result.exit_code == 2
    assert taiga.requests == []


def test_project_from_config_file(invoke, logged_in, taiga: FakeTaiga, isolated_cwd: Path) -> None:
    write_project_config(isolated_cwd)
    result = invoke(taiga, "epic", "create", "--subject", "E")
    assert result.output == "created: web#100\n"
