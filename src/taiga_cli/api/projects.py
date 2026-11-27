"""Projects resource."""

from __future__ import annotations

from typing import Any

from taiga_cli.api.client import TaigaClient

FIELDS = ("id", "slug", "name", "description", "is_private")
DEFAULT_FIELDS = ("slug", "name")


def normalize(raw: dict[str, Any]) -> dict[str, Any]:
    return {f: raw.get(f) for f in FIELDS}


def list_projects(
    client: TaigaClient, *, member_id: int | None, limit: int
) -> tuple[list[dict[str, Any]], bool]:
    params: dict[str, Any] = {"order_by": "name"}
    if member_id is not None:
        params["member"] = member_id
    return client.list_page("/projects", limit=limit, params=params)
