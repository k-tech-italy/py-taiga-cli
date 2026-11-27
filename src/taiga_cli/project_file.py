"""Discover and read the per-repository ``.taiga-cli-config.json``.

The file is searched for from the current directory upwards. It supplies defaults
(profile, project slug) and lets names be resolved to IDs without an API call.
Explicit command-line options always win.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from taiga_cli.errors import ConfigError

CONFIG_FILENAME = ".taiga-cli-config.json"
FORMAT_VERSION = 1


@dataclass(frozen=True)
class ProjectConfig:
    path: Path
    url: str
    profile: str | None
    project_id: int
    slug: str
    data: dict[str, Any]

    def values(self, kind: str) -> list[dict[str, Any]]:
        """A top-level value list: "issue_types", "priorities", "severities", "points"."""
        return self.data.get(kind) or []

    def custom_fields(self, kind: str) -> list[dict[str, Any]]:
        """Custom-field definitions of ``kind`` ("userstory", "task", "issue", "epic")."""
        return (self.data.get("custom_fields") or {}).get(kind) or []

    def default_id(self, key: str) -> int | None:
        """Id of a project default, e.g. "userstory_status", "priority" (None if unset)."""
        entry = (self.data.get("defaults") or {}).get(key)
        return entry.get("id") if isinstance(entry, dict) else None

    def statuses(self, kind: str) -> list[dict[str, Any]]:
        """Statuses of ``kind`` ("userstory", "task", "issue", "epic")."""
        return (self.data.get("statuses") or {}).get(kind) or []


def find(start: Path | None = None) -> Path | None:
    """Closest ``.taiga-cli-config.json`` in ``start`` or any parent directory."""
    here = (start or Path.cwd()).resolve()
    for directory in (here, *here.parents):
        candidate = directory / CONFIG_FILENAME
        if candidate.is_file():
            return candidate
    return None


def load(path: Path) -> ProjectConfig:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ConfigError(f"invalid {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"invalid {path}: expected a JSON object")
    version = data.get("version")
    if version != FORMAT_VERSION:
        raise ConfigError(
            f"{path}: unsupported version {version!r} (expected {FORMAT_VERSION}); "
            "re-export it with `taiga-cli project configure export`"
        )
    try:
        return ProjectConfig(
            path=path,
            url=data["url"],
            profile=(data.get("credentials") or {}).get("profile"),
            project_id=int(data["project"]["id"]),
            slug=data["project"]["slug"],
            data=data,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ConfigError(f"invalid {path}: missing or bad {exc}") from exc


def discover(start: Path | None = None) -> ProjectConfig | None:
    path = find(start)
    return load(path) if path else None
