"""Issues resource."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from taiga_cli.api.items import Resource, extra_name, tags_cell

RESOURCE = Resource(name="issue", endpoint="/issues", status_kind="issue")

FIELDS = (
    "ref",
    "subject",
    "status",
    "type",
    "priority",
    "severity",
    "assignee",
    "tags",
    "closed",
    "blocked",
    "due",
    "modified",
    "description",
    "id",
)
DEFAULT_FIELDS = ("ref", "status", "type", "priority", "subject", "assignee")

# Output field -> project value list. Taiga's issue list only returns the ids of these, so
# names come from the project (config file or one /projects/by_slug call).
VALUE_FIELDS = {"type": "issue_types", "priority": "priorities", "severity": "severities"}

ValueNames = Mapping[str, Mapping[int, str]]


def make_normalizer(names: ValueNames) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """``names`` maps a VALUE_FIELDS kind to ``{id: name}``; missing kinds render as None."""

    def value(raw: dict[str, Any], field: str) -> str | None:
        value_id = raw.get(field)
        return None if value_id is None else names.get(VALUE_FIELDS[field], {}).get(value_id)

    def normalize(raw: dict[str, Any]) -> dict[str, Any]:
        return {
            "ref": f"#{raw.get('ref')}",
            "subject": raw.get("subject"),
            "status": extra_name(raw, "status_extra_info"),
            "type": value(raw, "type"),
            "priority": value(raw, "priority"),
            "severity": value(raw, "severity"),
            "assignee": extra_name(raw, "assigned_to_extra_info", "username"),
            "tags": tags_cell(raw),
            "closed": raw.get("is_closed"),
            "blocked": raw.get("is_blocked"),
            "due": raw.get("due_date"),
            "modified": raw.get("modified_date"),
            "description": raw.get("description"),
            "id": raw.get("id"),
        }

    return normalize
