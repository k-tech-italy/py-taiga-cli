from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import httpx
import keyring
import pytest
from click.testing import CliRunner
from keyring.backend import KeyringBackend
from keyring.errors import PasswordDeleteError

from taiga_cli import config
from taiga_cli.cli import main
from taiga_cli.context import AppContext

BASE_URL = "https://taiga.example.test"


class MemoryKeyring(KeyringBackend):
    priority = 1  # type: ignore[assignment]

    def __init__(self) -> None:
        super().__init__()
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        if self.store.pop((service, username), None) is None:
            raise PasswordDeleteError(username)


@pytest.fixture(autouse=True)
def memory_keyring() -> MemoryKeyring:
    previous = keyring.get_keyring()
    backend = MemoryKeyring()
    keyring.set_keyring(backend)
    yield backend
    keyring.set_keyring(previous)


@pytest.fixture(autouse=True)
def config_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "config" / "config.toml"
    monkeypatch.setattr(config, "config_path", lambda: path)
    return path


@pytest.fixture(autouse=True)
def isolated_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Run every test in an empty directory so no real .taiga-cli-config.json is found."""
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    return cwd


Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture
def invoke() -> Callable[..., object]:
    """Run the CLI with a mocked HTTP handler: ``invoke(handler, "project", "list")``."""

    def _invoke(handler: Handler | None, *args: str, input: str | None = None):
        transport = httpx.MockTransport(handler) if handler else None
        runner = CliRunner()
        return runner.invoke(main, list(args), obj=AppContext(transport=transport), input=input)

    return _invoke


@pytest.fixture
def logged_in(memory_keyring: MemoryKeyring, config_file: Path) -> None:
    cfg = config.Config(
        profiles={"default": config.Profile("default", BASE_URL, "alice", user_id=7)}
    )
    config.save(cfg, config_file)
    memory_keyring.set_password(
        "taiga-cli", "default", json.dumps({"auth_token": "tok", "refresh": "ref"})
    )
