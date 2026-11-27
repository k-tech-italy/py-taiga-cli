"""Resolve human names (status, user, sprint) to Taiga IDs for one project.

Two sources, both lazy:

- the repository's ``.taiga-cli-config.json`` (no API call) for the project id and statuses;
- one ``/projects/by_slug`` call for everything else (members, or statuses missing from a
  stale config file), so agents never need to look up numeric IDs themselves.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from taiga_cli.api.client import TaigaClient
from taiga_cli.errors import NotFoundError, UsageError
from taiga_cli.project_file import ProjectConfig

BACKLOG = "backlog"

# project value lists (same key in the config file and the API payload) -> label for messages
VALUE_KINDS = {"issue_types": "type", "priorities": "priority", "severities": "severity"}

# status kind -> key in the /projects/by_slug payload
_STATUS_KEYS = {
    "userstory": "us_statuses",
    "task": "task_statuses",
    "issue": "issue_statuses",
    "epic": "epic_statuses",
}


def _norm(value: str) -> str:
    return " ".join(value.casefold().split())


def _split(names: str) -> list[str]:
    return [n for n in names.split(",") if n.strip()]


def _find(value: str, options: Iterable[dict[str, Any]], keys: tuple[str, ...]) -> Any:
    wanted = _norm(value)
    for option in options:
        if any(option.get(k) and _norm(str(option[k])) == wanted for k in keys):
            return option
    return None


def _unknown(kind: str, value: str, options: Iterable[dict[str, Any]], key: str) -> UsageError:
    names = ",".join(str(o.get(key)) for o in options)
    return UsageError(f"unknown {kind} '{value}'; available: {names}")


def _match(kind: str, value: str, options: Iterable[dict[str, Any]], *keys: str) -> dict[str, Any]:
    options = list(options)
    found = _find(value, options, keys)
    if found is None:
        raise _unknown(kind, value, options, keys[0])
    return found


class ProjectContext:
    def __init__(
        self,
        client: TaigaClient,
        slug: str,
        *,
        raw: dict[str, Any] | None = None,
        project_config: ProjectConfig | None = None,
    ) -> None:
        self._client = client
        self.slug = slug
        self._raw = raw
        self._file = project_config
        self._milestones: list[dict[str, Any]] | None = None

    @classmethod
    def load(cls, client: TaigaClient, slug: str) -> ProjectContext:
        """Eagerly fetch the project (fails fast on an unknown slug)."""
        ctx = cls(client, slug)
        ctx.raw  # noqa: B018 - property access performs the fetch
        return ctx

    @classmethod
    def from_project_config(cls, client: TaigaClient, pc: ProjectConfig) -> ProjectContext:
        return cls(client, pc.slug, project_config=pc)

    @property
    def raw(self) -> dict[str, Any]:
        if self._raw is None:
            try:
                self._raw = self._client.get("/projects/by_slug", params={"slug": self.slug})
            except NotFoundError:
                raise NotFoundError(f"project '{self.slug}' not found") from None
        return self._raw

    @property
    def id(self) -> int:
        if self._raw is None and self._file is not None:
            return self._file.project_id
        return self.raw["id"]

    # -- statuses & project values -------------------------------------------
    def _values(self, label: str, file_items: list[dict[str, Any]], raw_key: str, name: str) -> int:
        """Name/slug -> id: config file first, then the server (the file may be stale)."""
        keys = ("name", "slug")
        if self._raw is None and self._file is not None:
            found = _find(name, file_items, keys)
            if found is not None:
                return found["id"]
        return _match(label, name, self.raw.get(raw_key, []), *keys)["id"]

    def status_id(self, kind: str, name: str) -> int:
        """Status name/slug of an item ``kind`` ("userstory", "task", ...) -> id."""
        file_items = self._file.statuses(kind) if self._file else []
        return self._values("status", file_items, _STATUS_KEYS[kind], name)

    def status_ids(self, kind: str, names: str) -> list[int]:
        """Comma-separated status names -> ids."""
        return [self.status_id(kind, n) for n in _split(names)]

    def value_id(self, kind: str, name: str) -> int:
        """Issue type / priority / severity name -> id (``kind`` from VALUE_KINDS)."""
        file_items = self._file.values(kind) if self._file else []
        return self._values(VALUE_KINDS[kind], file_items, kind, name)

    def value_ids(self, kind: str, names: str) -> list[int]:
        return [self.value_id(kind, n) for n in _split(names)]

    def value_names(self, kind: str) -> dict[int, str]:
        """id -> name for a VALUE_KINDS list (config file if it has them, else the server)."""
        items = self._file.values(kind) if self._file and self._raw is None else []
        if not items:
            items = self.raw.get(kind, [])
        return {i["id"]: i.get("name") for i in items}

    # -- users ---------------------------------------------------------------
    def user_id(self, name: str, me: Callable[[], int]) -> int:
        if _norm(name) == "me":
            return me()
        member = _match(
            "user", name, self.raw.get("members", []), "username", "full_name", "full_name_display"
        )
        return member["id"]

    # -- sprints -------------------------------------------------------------
    @property
    def milestones(self) -> list[dict[str, Any]]:
        if self._milestones is None:
            embedded = self._raw.get("milestones") if self._raw is not None else None
            self._milestones = (
                embedded
                if embedded is not None
                else self._client.get(
                    "/milestones",
                    params={"project": self.id},
                    headers={"x-disable-pagination": "True"},
                )
            )
        return self._milestones

    def milestone_id(self, name: str) -> int | None:
        """Sprint name/slug -> id; ``backlog`` -> None."""
        if _norm(name) == BACKLOG:
            return None
        return _match("sprint", name, self.milestones, "name", "slug")["id"]
