"""Epics resource."""

from __future__ import annotations

import re
from typing import Any

from taiga_cli.api.client import TaigaClient
from taiga_cli.api.items import Resource, extra_name, tags_cell
from taiga_cli.errors import UsageError

RESOURCE = Resource(name="epic", endpoint="/epics", status_kind="epic")

FIELDS = (
    "ref",
    "subject",
    "status",
    "assignee",
    "stories",
    "color",
    "tags",
    "closed",
    "blocked",
    "modified",
    "description",
    "id",
)
DEFAULT_FIELDS = ("ref", "status", "subject", "assignee", "stories")

_COLOR = re.compile(r"^#?([0-9a-f]{6})$", re.IGNORECASE)


def parse_color(value: str) -> str:
    """``ff8800`` or ``#FF8800`` -> ``#ff8800``."""
    m = _COLOR.match(value.strip())
    if not m:
        raise UsageError(f"invalid color '{value}'; use a hex value like #ff8800")
    return f"#{m[1].lower()}"


def normalize(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "ref": f"#{raw.get('ref')}",
        "subject": raw.get("subject"),
        "status": extra_name(raw, "status_extra_info"),
        "assignee": extra_name(raw, "assigned_to_extra_info", "username"),
        # Number of user stories linked to the epic (list endpoint only).
        "stories": (raw.get("user_stories_counts") or {}).get("total"),
        "color": raw.get("color"),
        "tags": tags_cell(raw),
        "closed": raw.get("is_closed"),
        "blocked": raw.get("is_blocked"),
        "modified": raw.get("modified_date"),
        "description": raw.get("description"),
        "id": raw.get("id"),
    }


# -- epic <-> user story links ------------------------------------------------
def related_story_ids(client: TaigaClient, epic_id: int) -> set[int]:
    links = client.get(
        f"/epics/{epic_id}/related_userstories", headers={"x-disable-pagination": "True"}
    )
    return {link["user_story"] for link in links}


def link_story(client: TaigaClient, epic_id: int, story_id: int) -> None:
    client.request(
        "POST",
        f"/epics/{epic_id}/related_userstories",
        json={"epic": epic_id, "user_story": story_id},
    )


def unlink_story(client: TaigaClient, epic_id: int, story_id: int) -> None:
    client.request("DELETE", f"/epics/{epic_id}/related_userstories/{story_id}")
