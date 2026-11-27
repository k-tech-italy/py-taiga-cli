"""User stories resource."""

from __future__ import annotations

from typing import Any

from taiga_cli.api.items import Resource, extra_name, tags_cell

RESOURCE = Resource(name="story", endpoint="/userstories", status_kind="userstory")

FIELDS = (
    "ref",
    "subject",
    "status",
    "assignee",
    "sprint",
    "points",
    "tags",
    "closed",
    "blocked",
    "due",
    "modified",
    "epics",
    "description",
    "id",
)
DEFAULT_FIELDS = ("ref", "status", "subject", "assignee")


def normalize(raw: dict[str, Any]) -> dict[str, Any]:
    epics = raw.get("epics") or []
    return {
        "ref": f"#{raw.get('ref')}",
        "subject": raw.get("subject"),
        "status": extra_name(raw, "status_extra_info"),
        "assignee": extra_name(raw, "assigned_to_extra_info", "username"),
        "sprint": raw.get("milestone_name"),
        "points": raw.get("total_points"),
        "tags": tags_cell(raw),
        "closed": raw.get("is_closed"),
        "blocked": raw.get("is_blocked"),
        "due": raw.get("due_date"),
        "modified": raw.get("modified_date"),
        "epics": ",".join(f"#{e.get('ref')}" for e in epics) or None,
        "description": raw.get("description"),
        "id": raw.get("id"),
    }
