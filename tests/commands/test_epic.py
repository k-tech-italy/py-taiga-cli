from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from taiga_cli.api.epics import parse_color
from taiga_cli.errors import UsageError
from tests.fakes import FakeTaiga
from tests.test_project_file import api_paths, write_project_config


@pytest.fixture
def taiga() -> FakeTaiga:
    return FakeTaiga()


@pytest.mark.parametrize(("value", "expected"), [("ff8800", "#ff8800"), (" #AABBCC ", "#aabbcc")])
def test_parse_color(value: str, expected: str) -> None:
    assert parse_color(value) == expected


@pytest.mark.parametrize("value", ["red", "#fff", "#gggggg"])
def test_parse_color_invalid(value: str) -> None:
    with pytest.raises(UsageError, match="invalid color"):
        parse_color(value)


# -- list ------------------------------------------------------------------


def test_list_default_compact(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(taiga, "epic", "list", "-P", "web")
    assert result.exit_code == 0, result.output
    assert result.output == "#3\tReady\tEpic 3\talice\t5\n#4\tReady\tEpic 4\t-\t-\n"
    params = taiga.last("GET", "/api/v1/epics").url.params
    assert params["project"] == "5"
    assert params["status__is_closed"] == "false"


def test_list_epic_statuses(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(taiga, "epic", "list", "-P", "web", "--status", "ready,done", "--state", "all")
    assert result.exit_code == 0, result.output
    assert taiga.last("GET", "/api/v1/epics").url.params["status"] == "81,82"
    result = invoke(taiga, "epic", "list", "-P", "web", "--status", "In progress")
    assert result.exit_code == 2
    assert result.output == "error: unknown status 'In progress'; available: New,Ready,Done\n"


def test_list_offline_with_project_file(
    invoke, logged_in, taiga: FakeTaiga, isolated_cwd: Path
) -> None:
    write_project_config(isolated_cwd, statuses={"epic": [{"id": 82, "name": "Done"}]})
    result = invoke(taiga, "epic", "list", "--status", "Done", "--json", "--fields", "ref,color")
    assert result.exit_code == 0, result.output
    assert api_paths(taiga) == ["GET /epics"]
    assert json.loads(result.output) == [
        {"ref": "#3", "color": "#aabbcc"},
        {"ref": "#4", "color": "#aabbcc"},
    ]


def test_list_raw(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(taiga, "epic", "list", "-P", "web", "--raw")
    assert json.loads(result.output) == taiga.epics


# -- update ----------------------------------------------------------------


def _patch_body(taiga: FakeTaiga, epic_id: int = 403) -> dict[str, Any]:
    return json.loads(taiga.last("PATCH", f"/api/v1/epics/{epic_id}").content)


def test_update(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(
        taiga, "epic", "update", "web#3",
        "--status", "Done", "--color", "FF8800", "--assignee", "none", "--add-tag", "q3",
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    assert result.output == "ok: web#3\n"
    assert _patch_body(taiga) == {
        "status": 82,
        "assigned_to": None,
        "color": "#ff8800",
        "tags": ["q3"],
        "version": 4,
    }


def test_update_invalid_color_before_any_request(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(taiga, "epic", "update", "web#3", "--color", "orange")
    assert result.exit_code == 2
    assert taiga.requests == []


def test_update_color_only_counts_as_change(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(taiga, "epic", "update", "web#4", "--color", "#000000")
    assert result.exit_code == 0, result.output
    assert _patch_body(taiga, 404) == {"color": "#000000", "version": 4}


def test_update_missing_epic(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(taiga, "epic", "update", "web#99", "--status", "Done")
    assert result.exit_code == 4
    assert result.output == "error: epic web#99 not found\n"


# -- story links -----------------------------------------------------------
# Fake state: epic #3 (id 403) is linked to story #2 (id 102); story #1 has id 101.


def _mutations(taiga: FakeTaiga) -> list[str]:
    return [p for p in api_paths(taiga) if not p.startswith("GET")]


def test_add_story_only_links_without_patch(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(taiga, "epic", "update", "web#3", "--add-story", "1")
    assert result.exit_code == 0, result.output
    assert result.output == "ok: web#3\n"
    assert taiga.epic_links[403] == [102, 101]
    assert _mutations(taiga) == ["POST /epics/403/related_userstories"]


def test_links_are_idempotent(invoke, logged_in, taiga: FakeTaiga) -> None:
    # #2 is already linked, #1 is not linked: nothing to do for either
    result = invoke(taiga, "epic", "update", "web#3", "--add-story", "web#2", "--remove-story", "1")
    assert result.exit_code == 0, result.output
    assert taiga.epic_links[403] == [102]
    assert _mutations(taiga) == []


def test_remove_story(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(taiga, "epic", "update", "web#3", "--remove-story", "2")
    assert result.exit_code == 0, result.output
    assert taiga.epic_links[403] == []
    assert _mutations(taiga) == ["DELETE /epics/403/related_userstories/102"]


def test_fields_and_links_together(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(
        taiga, "epic", "update", "web#3",
        "--status", "Done", "--add-story", "1", "--add-story", "1", "--remove-story", "2",
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    assert _mutations(taiga) == [
        "PATCH /epics/403",
        "POST /epics/403/related_userstories",
        "DELETE /epics/403/related_userstories/102",
    ]
    assert taiga.epic_links[403] == [101]


def test_unknown_story_fails_before_any_change(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(
        taiga, "epic", "update", "web#3", "--status", "Done", "--add-story", "1",
        "--add-story", "99",
    )  # fmt: skip
    assert result.exit_code == 4
    assert result.output == "error: story web#99 not found\n"
    assert _mutations(taiga) == []


def test_invalid_story_ref_fails_before_any_request(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(taiga, "epic", "update", "web#3", "--add-story", "#x")
    assert result.exit_code == 2
    assert taiga.requests == []


def test_same_story_added_and_removed(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(taiga, "epic", "update", "web#3", "--add-story", "1", "--remove-story", "web#1")
    assert result.exit_code == 2
    assert "both --add-story and --remove-story" in result.output
    assert _mutations(taiga) == []


def test_link_story_from_other_project(invoke, logged_in, taiga: FakeTaiga) -> None:
    taiga.other_projects["api"] = {**taiga.project, "id": 6, "slug": "api"}
    result = invoke(taiga, "epic", "update", "web#3", "--add-story", "api#1")
    assert result.exit_code == 0, result.output
    by_ref = taiga.last("GET", "/api/v1/userstories/by_ref").url.params
    assert (by_ref["project"], by_ref["ref"]) == ("6", "1")
    assert taiga.epic_links[403] == [102, 101]


def test_link_story_from_unknown_project(invoke, logged_in, taiga: FakeTaiga) -> None:
    result = invoke(taiga, "epic", "update", "web#3", "--add-story", "nope#1")
    assert result.exit_code == 4
    assert result.output == "error: project 'nope' not found\n"
    assert _mutations(taiga) == []
