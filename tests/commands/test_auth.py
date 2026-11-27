import json

import httpx

from taiga_cli import config
from tests.conftest import BASE_URL


def test_login_saves_profile_and_tokens(invoke, memory_keyring, config_file) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        assert json.loads(req.content)["password"] == "s3cret"
        return httpx.Response(200, json={"id": 42, "auth_token": "a", "refresh": "r"})

    result = invoke(
        handler,
        "auth", "login", "--url", BASE_URL + "/api/v1/", "--username", "alice", "--password-stdin",
        input="s3cret\n",
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    assert result.output == f"ok: alice@{BASE_URL} profile=default\n"

    cfg = config.load(config_file)
    assert cfg.profiles["default"] == config.Profile("default", BASE_URL, "alice", 42)
    assert "s3cret" not in config_file.read_text()
    stored = json.loads(memory_keyring.store[("taiga-cli", "default")])
    assert stored == {"auth_token": "a", "refresh": "r"}


def test_login_named_profile_prompts(invoke, config_file) -> None:
    handler = lambda r: httpx.Response(200, json={"id": 1, "auth_token": "a"})  # noqa: E731 - tiny stub
    result = invoke(handler, "-p", "work", "auth", "login", input=f"{BASE_URL}\nbob\npw\n")
    assert result.exit_code == 0, result.output
    cfg = config.load(config_file)
    assert cfg.default_profile == "work"
    assert cfg.profiles["work"].username == "bob"


def test_status_not_logged_in(invoke) -> None:
    result = invoke(None, "auth", "status")
    assert result.exit_code == 2
    assert "auth login" in result.output


def test_status_ok(invoke, logged_in) -> None:
    result = invoke(lambda r: httpx.Response(200, json={"username": "alice"}), "auth", "status")
    assert result.exit_code == 0, result.output
    assert result.output == f"ok: alice@{BASE_URL} profile=default\n"


def test_status_missing_tokens_exit_3(invoke, logged_in, memory_keyring) -> None:
    memory_keyring.store.clear()
    result = invoke(None, "auth", "status")
    assert result.exit_code == 3
    assert result.output.startswith("error: not logged in")


def test_logout(invoke, logged_in, memory_keyring) -> None:
    result = invoke(None, "auth", "logout")
    assert result.exit_code == 0
    assert memory_keyring.store == {}
    assert invoke(None, "auth", "logout").output == "ok: no tokens profile=default\n"
