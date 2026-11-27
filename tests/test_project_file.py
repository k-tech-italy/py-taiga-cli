"""Discovery of .taiga-cli-config.json and its use as defaults by the commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from taiga_cli import config, project_file
from taiga_cli.errors import ConfigError
from tests.conftest import BASE_URL
from tests.fakes import FakeTaiga

OTHER_URL = "https://other.test"


def write_project_config(directory: Path, **overrides: Any) -> Path:
    data: dict[str, Any] = {
        "version": 1,
        "url": BASE_URL,
        "web_url": BASE_URL,
        "credentials": {"store": "keyring", "service": "taiga-cli", "profile": "default"},
        "project": {"id": 5, "slug": "web", "name": "Web"},
        "statuses": {
            "userstory": [
                {"id": 10, "name": "New", "slug": "new"},
                {"id": 11, "name": "In progress", "slug": "in-progress"},
                {"id": 12, "name": "Done", "slug": "done"},
            ]
        },
    }
    data.update(overrides)
    path = directory / project_file.CONFIG_FILENAME
    path.write_text(json.dumps(data))
    return path


def api_paths(taiga: FakeTaiga) -> list[str]:
    return [f"{r.method} {r.url.path.removeprefix('/api/v1')}" for r in taiga.requests]


# -- discovery & parsing -----------------------------------------------------


def test_find_walks_up(tmp_path: Path) -> None:
    path = write_project_config(tmp_path)
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    assert project_file.find(nested) == path


def test_find_none(tmp_path: Path) -> None:
    assert project_file.find(tmp_path) is None


def test_closest_file_wins(tmp_path: Path) -> None:
    write_project_config(tmp_path)
    (tmp_path / "sub").mkdir()
    inner = write_project_config(tmp_path / "sub", project={"id": 6, "slug": "api"})
    pc = project_file.discover(tmp_path / "sub")
    assert pc is not None
    assert (pc.path, pc.slug, pc.project_id) == (inner, "api", 6)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("{not json", "invalid"),
        ("[]", "expected a JSON object"),
        ('{"version": 99}', "unsupported version 99"),
        ('{"version": 1, "url": "x"}', "missing or bad"),
    ],
)
def test_load_errors(tmp_path: Path, content: str, message: str) -> None:
    path = tmp_path / project_file.CONFIG_FILENAME
    path.write_text(content)
    with pytest.raises(ConfigError, match=message):
        project_file.load(path)


# -- story commands use the file ---------------------------------------------


def test_list_without_project_uses_file_offline(invoke, logged_in, isolated_cwd: Path) -> None:
    write_project_config(isolated_cwd)
    taiga = FakeTaiga()
    result = invoke(taiga, "story", "list", "--status", "in progress,done")
    assert result.exit_code == 0, result.output
    # statuses and project id come from the file: a single API call
    assert api_paths(taiga) == ["GET /userstories"]
    params = taiga.requests[0].url.params
    assert params["project"] == "5"
    assert params["status"] == "11,12"


def test_file_found_from_subdirectory(invoke, logged_in, isolated_cwd: Path, monkeypatch) -> None:
    write_project_config(isolated_cwd)
    sub = isolated_cwd / "src" / "pkg"
    sub.mkdir(parents=True)
    monkeypatch.chdir(sub)
    taiga = FakeTaiga()
    result = invoke(taiga, "story", "list")
    assert result.exit_code == 0, result.output
    assert api_paths(taiga) == ["GET /userstories"]


def test_stale_status_falls_back_to_server(invoke, logged_in, isolated_cwd: Path) -> None:
    write_project_config(isolated_cwd, statuses={"userstory": [{"id": 10, "name": "New"}]})
    taiga = FakeTaiga()
    result = invoke(taiga, "story", "list", "--status", "Done")
    assert result.exit_code == 0, result.output
    assert api_paths(taiga) == ["GET /projects/by_slug", "GET /userstories"]
    assert taiga.requests[-1].url.params["status"] == "12"


def test_unknown_status_still_lists_server_choices(invoke, logged_in, isolated_cwd: Path) -> None:
    write_project_config(isolated_cwd)
    result = invoke(FakeTaiga(), "story", "list", "--status", "Doing")
    assert result.exit_code == 2
    assert result.output == "error: unknown status 'Doing'; available: New,In progress,Done\n"


def test_explicit_project_overrides_file(invoke, logged_in, isolated_cwd: Path) -> None:
    write_project_config(isolated_cwd, project={"id": 6, "slug": "other"})
    taiga = FakeTaiga()
    result = invoke(taiga, "story", "list", "-P", "web", "--status", "Done")
    assert result.exit_code == 0, result.output
    assert api_paths(taiga) == ["GET /projects/by_slug", "GET /userstories"]
    assert taiga.requests[-1].url.params["project"] == "5"


def test_update_bare_ref_uses_file(invoke, logged_in, isolated_cwd: Path) -> None:
    write_project_config(isolated_cwd)
    taiga = FakeTaiga()
    result = invoke(taiga, "story", "update", "1", "--status", "Done")
    assert result.exit_code == 0, result.output
    assert result.output == "ok: web#1\n"
    assert api_paths(taiga) == ["GET /userstories/by_ref", "PATCH /userstories/101"]


def test_no_project_config_flag(invoke, logged_in, isolated_cwd: Path) -> None:
    write_project_config(isolated_cwd)
    result = invoke(FakeTaiga(), "--no-project-config", "story", "list")
    assert result.exit_code == 2
    assert "project required" in result.output


def test_missing_project_hints_export(invoke, logged_in) -> None:
    result = invoke(FakeTaiga(), "story", "list")
    assert result.exit_code == 2
    assert "taiga-cli project configure export" in result.output


def test_invalid_file_is_reported(invoke, logged_in, isolated_cwd: Path) -> None:
    (isolated_cwd / project_file.CONFIG_FILENAME).write_text("{oops")
    result = invoke(FakeTaiga(), "story", "list")
    assert result.exit_code == 2
    assert result.output.startswith("error: invalid ")


# -- profile selection -------------------------------------------------------


@pytest.fixture
def work_profile(config_file: Path, memory_keyring, logged_in) -> None:
    cfg = config.load(config_file)
    cfg.profiles["work"] = config.Profile("work", OTHER_URL, "bob", user_id=8)
    config.save(cfg, config_file)
    memory_keyring.set_password("taiga-cli", "work", json.dumps({"auth_token": "work-tok"}))


def test_file_selects_profile(invoke, work_profile, isolated_cwd: Path) -> None:
    write_project_config(
        isolated_cwd,
        url=OTHER_URL,
        credentials={"store": "keyring", "service": "taiga-cli", "profile": "work"},
    )
    taiga = FakeTaiga()
    result = invoke(taiga, "story", "list")
    assert result.exit_code == 0, result.output
    req = taiga.requests[0]
    assert req.url.host == "other.test"
    assert req.headers["authorization"] == "Bearer work-tok"


def test_profile_url_mismatch_is_an_error(invoke, work_profile, isolated_cwd: Path) -> None:
    # file references "work" (other.test) but claims to be for BASE_URL
    write_project_config(
        isolated_cwd, credentials={"store": "keyring", "service": "taiga-cli", "profile": "work"}
    )
    taiga = FakeTaiga()
    result = invoke(taiga, "story", "list")
    assert result.exit_code == 2
    assert f"is for {BASE_URL} but profile 'work' is for {OTHER_URL}" in result.output
    assert taiga.requests == []


def test_explicit_profile_on_other_instance_ignores_file_project(
    invoke, work_profile, isolated_cwd: Path
) -> None:
    write_project_config(isolated_cwd)  # for BASE_URL / profile default
    result = invoke(FakeTaiga(), "-p", "work", "story", "list")
    assert result.exit_code == 2
    assert "is for https://taiga.example.test" in result.output


def test_unknown_file_profile_hints_login(invoke, logged_in, isolated_cwd: Path) -> None:
    write_project_config(
        isolated_cwd, credentials={"store": "keyring", "service": "taiga-cli", "profile": "ghost"}
    )
    result = invoke(FakeTaiga(), "story", "list")
    assert result.exit_code == 2
    assert "taiga-cli -p ghost auth login" in result.output


def test_login_defaults_to_file_url_and_profile(invoke, config_file: Path, isolated_cwd) -> None:
    write_project_config(
        isolated_cwd,
        url=OTHER_URL,
        credentials={"store": "keyring", "service": "taiga-cli", "profile": "work"},
    )

    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.host == "other.test"
        return httpx.Response(200, json={"id": 8, "auth_token": "a"})

    result = invoke(handler, "auth", "login", "--username", "bob", "--password-stdin", input="pw\n")
    assert result.exit_code == 0, result.output
    assert result.output == f"ok: bob@{OTHER_URL} profile=work\n"
    assert config.load(config_file).profiles["work"].url == OTHER_URL
