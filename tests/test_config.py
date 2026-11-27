from pathlib import Path

import pytest

from taiga_cli import config
from taiga_cli.errors import ConfigError


def test_missing_file_gives_empty_config(tmp_path: Path) -> None:
    cfg = config.load(tmp_path / "nope.toml")
    assert cfg.profiles == {}
    assert cfg.default_profile == "default"


def test_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "c.toml"
    cfg = config.Config(
        default_profile="work",
        profiles={
            "work": config.Profile("work", "https://t.example", 'bob "b"', user_id=3),
            "my home": config.Profile("my home", "https://h.example", "bob"),
        },
    )
    config.save(cfg, path)
    assert config.load(path) == cfg


def test_unknown_profile_hints_login() -> None:
    with pytest.raises(ConfigError, match="taiga-cli -p x auth login"):
        config.Config().get_profile("x")


def test_invalid_toml(tmp_path: Path) -> None:
    path = tmp_path / "c.toml"
    path.write_text("not = = toml")
    with pytest.raises(ConfigError, match="invalid config"):
        config.load(path)
