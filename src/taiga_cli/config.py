"""Profiles stored as TOML in the per-user config directory.

Secrets never live here: tokens are kept in the keyring (see credentials.py).
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import platformdirs

from taiga_cli import APP_NAME
from taiga_cli.errors import ConfigError

DEFAULT_PROFILE = "default"


def config_path() -> Path:
    return Path(platformdirs.user_config_dir(APP_NAME, appauthor=False)) / "config.toml"


@dataclass
class Profile:
    name: str
    url: str
    username: str
    user_id: int | None = None


@dataclass
class Config:
    default_profile: str = DEFAULT_PROFILE
    profiles: dict[str, Profile] = field(default_factory=dict)

    def get_profile(self, name: str | None = None) -> Profile:
        name = name or self.default_profile
        try:
            return self.profiles[name]
        except KeyError:
            raise ConfigError(
                f"profile '{name}' not configured; run `taiga-cli -p {name} auth login`"
            ) from None


def load(path: Path | None = None) -> Config:
    path = path or config_path()
    if not path.exists():
        return Config()
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid config file {path}: {exc}") from exc
    profiles = {
        name: Profile(
            name=name,
            url=raw["url"],
            username=raw["username"],
            user_id=raw.get("user_id"),
        )
        for name, raw in data.get("profiles", {}).items()
    }
    return Config(default_profile=data.get("default_profile", DEFAULT_PROFILE), profiles=profiles)


def _q(value: str) -> str:
    # JSON string escaping is a valid TOML basic string for our (plain text) values.
    return json.dumps(value, ensure_ascii=False)


def dumps(cfg: Config) -> str:
    lines = [f"default_profile = {_q(cfg.default_profile)}", ""]
    for p in cfg.profiles.values():
        lines.append(f"[profiles.{_q(p.name)}]")
        lines.append(f"url = {_q(p.url)}")
        lines.append(f"username = {_q(p.username)}")
        if p.user_id is not None:
            lines.append(f"user_id = {int(p.user_id)}")
        lines.append("")
    return "\n".join(lines)


def save(cfg: Config, path: Path | None = None) -> Path:
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(cfg), encoding="utf-8")
    return path
