from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from taiga_cli import config
from taiga_cli.api.project_config import CONFIG_FILENAME, parse_taiga_url
from taiga_cli.errors import UsageError
from tests.conftest import BASE_URL


def _status(id_: int, name: str, order: int, **kw: Any) -> dict[str, Any]:
    return {"id": id_, "name": name, "slug": name.lower(), "color": "#999", "order": order,
            "is_closed": False, "project_id": 5, **kw}  # fmt: skip


DETAIL: dict[str, Any] = {
    "id": 5,
    "slug": "web",
    "name": "Web",
    "description": "The website",
    "is_private": True,
    "i_am_admin": True,
    "members": [{"id": 7, "username": "alice"}],  # not exported
    "is_epics_activated": False,
    "is_backlog_activated": True,
    "is_kanban_activated": True,
    "is_issues_activated": True,
    "is_wiki_activated": False,
    "videoconferences": None,
    "videoconferences_extra_data": None,
    "epic_statuses": [_status(1, "New", 1)],
    # out of order on purpose: export sorts by `order`
    "us_statuses": [
        _status(12, "Done", 3, is_closed=True, is_archived=False, wip_limit=None),
        _status(10, "New", 1, is_archived=False, wip_limit=None),
        _status(11, "In progress", 2, is_archived=False, wip_limit=5),
    ],
    "task_statuses": [_status(20, "New", 1)],
    "issue_statuses": [_status(30, "Open", 1)],
    "points": [
        {"id": 40, "name": "?", "value": None, "order": 1},
        {"id": 41, "name": "1", "value": 1.0, "order": 2},
    ],
    "priorities": [{"id": 50, "name": "Normal", "color": "#0f0", "order": 2}],
    "severities": [{"id": 60, "name": "Minor", "color": "#ff0", "order": 1}],
    "issue_types": [{"id": 70, "name": "Bug", "color": "#f00", "order": 1}],
    "epic_custom_attributes": [],
    "userstory_custom_attributes": [
        {
            "id": 80,
            "name": "Customer",
            "description": "Who asked",
            "type": "dropdown",
            "extra": ["ACME", "Globex"],
            "order": 1,
            "created_date": "2026-01-01",
        },
    ],
    "task_custom_attributes": [],
    "issue_custom_attributes": [],
    "tags_colors": {"ui": "#fff", "api": None},
    "us_duedates": [
        {
            "id": 90,
            "name": "Due soon",
            "color": "#f80",
            "days_to_due": 7,
            "by_default": False,
            "order": 1,
        }
    ],
    "task_duedates": [],
    "issue_duedates": [],
    "default_epic_status": 1,
    "default_us_status": 10,
    "default_points": 40,
    "default_task_status": 20,
    "default_issue_status": 30,
    "default_issue_type": 70,
    "default_priority": 50,
    "default_severity": None,
}


class FakeTaiga:
    def __init__(self, detail: dict[str, Any]) -> None:
        self.detail = detail
        self.paths: list[str] = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        path = req.url.path.removeprefix("/api/v1")
        self.paths.append(path)
        if path == "/projects/by_slug":
            return httpx.Response(200, json=self.detail)
        if path == "/task-due-dates":
            assert req.url.params["project"] == "5"
            assert req.headers["x-disable-pagination"] == "True"
            return httpx.Response(200, json=[{"id": 95, "name": "Late", "order": 1}])
        return httpx.Response(500, json={"detail": f"unexpected {path}"})


@pytest.fixture
def chdir_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


# -- URL parsing -------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "project", "expected"),
    [
        (
            "https://tree.taiga.io/project/web/admin/project-profile/details",
            None,
            ("https://api.taiga.io", "https://tree.taiga.io", "web"),
        ),
        (
            "https://api.taiga.io/api/v1/",
            "web",
            ("https://api.taiga.io", "https://tree.taiga.io", "web"),
        ),
        (
            "https://taiga.example.com/taiga/project/web/",
            None,
            ("https://taiga.example.com/taiga", "https://taiga.example.com/taiga", "web"),
        ),
        (
            "http://localhost:9000",
            "web",
            ("http://localhost:9000", "http://localhost:9000", "web"),
        ),
    ],
)
def test_parse_taiga_url(url: str, project: str | None, expected: tuple[str, str, str]) -> None:
    assert parse_taiga_url(url, project) == expected


@pytest.mark.parametrize(
    ("url", "project", "message"),
    [
        ("https://t.example", None, "project required"),
        ("https://t.example/project/web", "api", "conflicts"),
        ("t.example/project/web", None, "invalid url"),
    ],
)
def test_parse_taiga_url_errors(url: str, project: str | None, message: str) -> None:
    with pytest.raises(UsageError, match=message):
        parse_taiga_url(url, project)


# -- export ------------------------------------------------------------------


def test_export_writes_file(invoke, logged_in, chdir_tmp: Path) -> None:
    detail = {k: v for k, v in DETAIL.items() if k != "task_duedates"}  # force fallback
    taiga = FakeTaiga(detail)
    result = invoke(taiga, "project", "configure", "export", f"{BASE_URL}/project/web")
    assert result.exit_code == 0, result.output
    path = chdir_tmp / CONFIG_FILENAME
    assert result.output == f"ok: {path}\n"
    assert taiga.paths == ["/projects/by_slug", "/task-due-dates"]

    data = json.loads(path.read_text())
    assert list(data) == [
        "version", "url", "web_url", "credentials", "project", "defaults", "modules",
        "statuses", "points", "priorities", "severities", "issue_types", "custom_fields",
        "tags", "due_dates",
    ]  # fmt: skip
    assert data["version"] == 1
    assert data["url"] == data["web_url"] == BASE_URL
    assert data["credentials"] == {"store": "keyring", "service": "taiga-cli", "profile": "default"}
    assert data["project"] == {
        "id": 5, "slug": "web", "name": "Web", "description": "The website", "is_private": True,
    }  # fmt: skip
    assert data["modules"]["backlog"] is True
    assert data["modules"]["wiki"] is False
    assert [s["name"] for s in data["statuses"]["userstory"]] == ["New", "In progress", "Done"]
    assert data["statuses"]["userstory"][1] == {
        "id": 11, "name": "In progress", "slug": "in progress", "color": "#999",
        "is_closed": False, "is_archived": False, "wip_limit": 5, "order": 2,
    }  # fmt: skip
    assert data["defaults"]["userstory_status"] == {"id": 10, "name": "New"}
    assert data["defaults"]["points"] == {"id": 40, "name": "?"}
    assert data["defaults"]["severity"] is None
    assert data["custom_fields"]["userstory"] == [
        {"id": 80, "name": "Customer", "description": "Who asked", "type": "dropdown",
         "extra": ["ACME", "Globex"], "order": 1},
    ]  # fmt: skip
    assert data["tags"] == {"api": None, "ui": "#fff"}
    assert data["due_dates"]["userstory"][0]["days_to_due"] == 7
    assert data["due_dates"]["task"] == [{"id": 95, "name": "Late", "order": 1}]
    assert "members" not in json.dumps(data)


def test_export_contains_no_secrets(invoke, logged_in, chdir_tmp: Path) -> None:
    invoke(FakeTaiga(DETAIL), "project", "configure", "export", f"{BASE_URL}/project/web")
    text = (chdir_tmp / CONFIG_FILENAME).read_text()
    assert "tok" not in text  # auth token from the `logged_in` fixture
    assert "ref" not in text.replace("refer", "")  # refresh token


def test_export_to_stdout(invoke, logged_in, chdir_tmp: Path) -> None:
    result = invoke(FakeTaiga(DETAIL), "project", "configure", "export", BASE_URL,
                    "-P", "web", "-o", "-")  # fmt: skip
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["project"]["slug"] == "web"
    assert not (chdir_tmp / CONFIG_FILENAME).exists()


def test_export_refuses_to_overwrite(invoke, logged_in, chdir_tmp: Path) -> None:
    (chdir_tmp / CONFIG_FILENAME).write_text("{}")
    taiga = FakeTaiga(DETAIL)
    result = invoke(taiga, "project", "configure", "export", f"{BASE_URL}/project/web")
    assert result.exit_code == 2
    assert "--force" in result.output
    assert taiga.paths == []
    result = invoke(taiga, "project", "configure", "export", f"{BASE_URL}/project/web", "--force")
    assert result.exit_code == 0, result.output
    assert json.loads((chdir_tmp / CONFIG_FILENAME).read_text())["version"] == 1


def test_export_warns_non_admin(invoke, logged_in, chdir_tmp: Path) -> None:
    taiga = FakeTaiga({**DETAIL, "i_am_admin": False})
    result = invoke(taiga, "project", "configure", "export", f"{BASE_URL}/project/web")
    assert result.exit_code == 0
    assert "not an admin" in result.stderr


def test_export_without_matching_profile(invoke, logged_in, chdir_tmp: Path) -> None:
    result = invoke(None, "project", "configure", "export", "https://other.test/project/web")
    assert result.exit_code == 3
    assert "auth login --url https://other.test" in result.output


def test_export_picks_matching_non_default_profile(
    invoke, logged_in, chdir_tmp: Path, config_file: Path, memory_keyring
) -> None:
    cfg = config.load(config_file)
    cfg.profiles["other"] = config.Profile("other", "https://other.test", "bob")
    config.save(cfg, config_file)
    memory_keyring.set_password("taiga-cli", "other", json.dumps({"auth_token": "t2"}))
    taiga = FakeTaiga(DETAIL)
    result = invoke(taiga, "project", "configure", "export", "https://other.test/project/web")
    assert result.exit_code == 0, result.output
    data = json.loads((chdir_tmp / CONFIG_FILENAME).read_text())
    assert data["credentials"]["profile"] == "other"
    assert data["url"] == "https://other.test"


def test_export_explicit_profile_must_match_url(invoke, logged_in, chdir_tmp: Path) -> None:
    result = invoke(
        None, "-p", "default", "project", "configure", "export", "https://other.test/project/web"
    )
    assert result.exit_code == 2
    assert "is for https://taiga.example.test" in result.output
