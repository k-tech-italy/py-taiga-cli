"""Shared plumbing for ref-addressed Taiga items (user stories, tasks, ...)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from taiga_cli.api.client import TaigaClient
from taiga_cli.errors import NotFoundError, UsageError

_REF = re.compile(r"^(?:(?P<slug>[a-z0-9][a-z0-9_-]*)?#)?(?P<ref>\d+)$", re.IGNORECASE)


def parse_ref(value: str, project: str | None) -> tuple[str | None, int]:
    """``slug#42``, ``#42`` or ``42`` (+ ``-P slug``) -> ``(slug, 42)``.

    The slug is None when neither the ref nor ``-P`` names a project; the caller then falls
    back to the project config file.
    """
    m = _REF.match(value.strip())
    if not m:
        raise UsageError(f"invalid ref '{value}'; use SLUG#N or N with -P SLUG")
    slug = m["slug"]
    if slug and project and slug != project:
        raise UsageError(f"ref '{value}' conflicts with -P {project}")
    return slug or project, int(m["ref"])


def tag_names(raw: dict[str, Any]) -> list[str]:
    # Taiga returns tags either as ["name", ...] or [["name", "#color"], ...].
    return [t[0] if isinstance(t, list | tuple) else t for t in raw.get("tags") or []]


def tags_cell(raw: dict[str, Any]) -> str | None:
    return ",".join(tag_names(raw)) or None


def extra_name(raw: dict[str, Any], key: str, attr: str = "name") -> Any:
    """Value from Taiga's ``*_extra_info`` sub-objects, tolerating null."""
    return (raw.get(key) or {}).get(attr)


@dataclass(frozen=True)
class Resource:
    """A Taiga resource whose items have a project-scoped ``ref``."""

    name: str  # human name used in messages: "story", "task"
    endpoint: str  # "/userstories", "/tasks"
    status_kind: str  # key in ProjectContext/ProjectConfig statuses: "userstory", "task"

    def list(
        self, client: TaigaClient, params: dict[str, Any], *, limit: int
    ) -> tuple[list[dict[str, Any]], bool]:
        return client.list_page(self.endpoint, limit=limit, params=params)

    def get_by_ref(
        self, client: TaigaClient, project_id: int, ref: int, slug: str
    ) -> dict[str, Any]:
        try:
            return client.get(f"{self.endpoint}/by_ref", params={"project": project_id, "ref": ref})
        except NotFoundError:
            raise NotFoundError(f"{self.name} {slug}#{ref} not found") from None

    def update(self, client: TaigaClient, item_id: int, data: dict[str, Any]) -> dict[str, Any]:
        return client.patch(f"{self.endpoint}/{item_id}", data)
