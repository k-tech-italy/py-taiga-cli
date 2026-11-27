"""Build the per-repository ``.taiga-cli-config.json`` from a project's admin settings.

The file is meant to be committed: it holds **references** to credentials (keyring service
+ profile name), never secrets.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from taiga_cli import APP_NAME
from taiga_cli.api.client import API_PREFIX, TaigaClient
from taiga_cli.errors import UsageError
from taiga_cli.project_file import CONFIG_FILENAME, FORMAT_VERSION

__all__ = ["CONFIG_FILENAME", "build_config", "parse_taiga_url"]

# Taiga Cloud serves the web UI and the API on different hosts.
_CLOUD_WEB_TO_API = {"tree.taiga.io": "api.taiga.io"}
_CLOUD_API_TO_WEB = {v: k for k, v in _CLOUD_WEB_TO_API.items()}

# Keys kept for every configurable value (only those present in the payload are exported).
_ITEM_KEYS = (
    "id",
    "name",
    "slug",
    "color",
    "value",
    "is_closed",
    "is_archived",
    "wip_limit",
    "days_to_due",
    "by_default",
    "description",
    "type",
    "extra",
    "order",
)

# config path -> (project-detail key, fallback endpoint)
_SECTIONS: dict[tuple[str, ...], tuple[str, str]] = {
    ("statuses", "epic"): ("epic_statuses", "/epic-statuses"),
    ("statuses", "userstory"): ("us_statuses", "/userstory-statuses"),
    ("statuses", "task"): ("task_statuses", "/task-statuses"),
    ("statuses", "issue"): ("issue_statuses", "/issue-statuses"),
    ("points",): ("points", "/points"),
    ("priorities",): ("priorities", "/priorities"),
    ("severities",): ("severities", "/severities"),
    ("issue_types",): ("issue_types", "/issue-types"),
    ("custom_fields", "epic"): ("epic_custom_attributes", "/epic-custom-attributes"),
    ("custom_fields", "userstory"): (
        "userstory_custom_attributes",
        "/userstory-custom-attributes",
    ),
    ("custom_fields", "task"): ("task_custom_attributes", "/task-custom-attributes"),
    ("custom_fields", "issue"): ("issue_custom_attributes", "/issue-custom-attributes"),
    ("due_dates", "userstory"): ("us_duedates", "/userstory-due-dates"),
    ("due_dates", "task"): ("task_duedates", "/task-due-dates"),
    ("due_dates", "issue"): ("issue_duedates", "/issue-due-dates"),
}

# defaults key -> (project-detail key, config path of the list it points into)
_DEFAULTS: dict[str, tuple[str, tuple[str, ...]]] = {
    "epic_status": ("default_epic_status", ("statuses", "epic")),
    "userstory_status": ("default_us_status", ("statuses", "userstory")),
    "points": ("default_points", ("points",)),
    "task_status": ("default_task_status", ("statuses", "task")),
    "issue_status": ("default_issue_status", ("statuses", "issue")),
    "issue_type": ("default_issue_type", ("issue_types",)),
    "priority": ("default_priority", ("priorities",)),
    "severity": ("default_severity", ("severities",)),
}

_MODULES = {
    "epics": "is_epics_activated",
    "backlog": "is_backlog_activated",
    "kanban": "is_kanban_activated",
    "issues": "is_issues_activated",
    "wiki": "is_wiki_activated",
    "videoconferences": "videoconferences",
    "videoconferences_extra_data": "videoconferences_extra_data",
}


def parse_taiga_url(url: str, project: str | None) -> tuple[str, str, str]:
    """Return ``(api_url, web_url, slug)`` from a Taiga web/API URL and optional ``-P``.

    Accepts e.g. ``https://tree.taiga.io/project/web/admin/project-profile/details``,
    ``https://taiga.example.com`` (with ``-P``) or ``https://host/api/v1``.
    """
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise UsageError(f"invalid url '{url}': expected https://host[/project/SLUG]")
    path = parts.path.rstrip("/")
    slug: str | None = None
    if "/project/" in f"{path}/":
        prefix, _, rest = path.partition("/project/")
        slug = rest.split("/")[0] or None
        path = prefix
    if path.endswith(API_PREFIX):
        path = path[: -len(API_PREFIX)]

    if slug and project and slug != project:
        raise UsageError(f"url project '{slug}' conflicts with -P {project}")
    slug = slug or project
    if not slug:
        raise UsageError("project required: pass a .../project/SLUG url or -P SLUG")

    host = parts.netloc
    api_host = _CLOUD_WEB_TO_API.get(host, host)
    web_host = _CLOUD_API_TO_WEB.get(host, host)
    return f"{parts.scheme}://{api_host}{path}", f"{parts.scheme}://{web_host}{path}", slug


def _pick(item: dict[str, Any]) -> dict[str, Any]:
    return {k: item[k] for k in _ITEM_KEYS if k in item}


def _sorted(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted((_pick(i) for i in items), key=lambda i: (i.get("order") or 0, i.get("id") or 0))


def _tags(raw: dict[str, Any]) -> dict[str, str | None]:
    colors = raw.get("tags_colors") or {}
    if isinstance(colors, list):  # some versions: [["tag", "#color"], ...]
        colors = {t[0]: (t[1] if len(t) > 1 else None) for t in colors}
    return dict(sorted(colors.items()))


def _set(target: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    for key in path[:-1]:
        target = target.setdefault(key, {})
    target[path[-1]] = value


def _get(source: dict[str, Any], path: tuple[str, ...]) -> Any:
    for key in path:
        source = source[key]
    return source


def build_config(
    client: TaigaClient,
    raw: dict[str, Any],
    *,
    api_url: str,
    web_url: str,
    profile: str,
) -> dict[str, Any]:
    """Assemble the config dict from a ``/projects/by_slug`` payload (+ fallbacks)."""
    config: dict[str, Any] = {
        "version": FORMAT_VERSION,
        "url": api_url,
        "web_url": web_url,
        "credentials": {"store": "keyring", "service": APP_NAME, "profile": profile},
        "project": {
            "id": raw["id"],
            "slug": raw["slug"],
            "name": raw.get("name"),
            "description": raw.get("description"),
            "is_private": raw.get("is_private"),
        },
        "defaults": {},
        "modules": {name: raw.get(key) for name, key in _MODULES.items()},
    }

    for path, (detail_key, endpoint) in _SECTIONS.items():
        items = raw.get(detail_key)
        if items is None:
            items = client.get(
                endpoint,
                params={"project": raw["id"]},
                headers={"x-disable-pagination": "True"},
            )
        _set(config, path, _sorted(items))

    for name, (detail_key, path) in _DEFAULTS.items():
        default_id = raw.get(detail_key)
        names = {i["id"]: i.get("name") for i in _get(config, path)}
        config["defaults"][name] = (
            None if default_id is None else {"id": default_id, "name": names.get(default_id)}
        )

    config["tags"] = _tags(raw)

    # Keep a stable, readable key order in the file.
    order = (
        "version",
        "url",
        "web_url",
        "credentials",
        "project",
        "defaults",
        "modules",
        "statuses",
        "points",
        "priorities",
        "severities",
        "issue_types",
        "custom_fields",
        "tags",
        "due_dates",
    )
    return {k: config[k] for k in order}
