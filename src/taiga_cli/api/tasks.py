"""Tasks resource."""

from __future__ import annotations

from typing import Any

from taiga_cli.api.items import Resource, extra_name, tags_cell

RESOURCE = Resource(name="task", endpoint="/tasks", status_kind="task")

FIELDS = (
    "ref",
    "subject",
    "status",
    "assignee",
    "story",
    "sprint",
    "tags",
    "closed",
    "blocked",
    "due",
    "modified",
    "description",
    "id",
)
DEFAULT_FIELDS = ("ref", "status", "subject", "assignee", "story")


def normalize(raw: dict[str, Any]) -> dict[str, Any]:
    story_ref = extra_name(raw, "user_story_extra_info", "ref")
    return {
        "ref": f"#{raw.get('ref')}",
        "subject": raw.get("subject"),
        "status": extra_name(raw, "status_extra_info"),
        "assignee": extra_name(raw, "assigned_to_extra_info", "username"),
        "story": None if story_ref is None else f"#{story_ref}",
        "sprint": raw.get("milestone_slug"),
        "tags": tags_cell(raw),
        "closed": raw.get("is_closed"),
        "blocked": raw.get("is_blocked"),
        "due": raw.get("due_date"),
        "modified": raw.get("modified_date"),
        "description": raw.get("description"),
        "id": raw.get("id"),
    }
