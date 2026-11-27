"""``taiga-cli story``: user stories."""

from __future__ import annotations

from typing import Any

import click

from taiga_cli.api import epics, stories
from taiga_cli.api.client import TaigaClient
from taiga_cli.api.items import parse_ref
from taiga_cli.api.project_context import ProjectContext
from taiga_cli.commands._items import (
    ItemCreate,
    ItemUpdate,
    common_create_options,
    common_filter_options,
    common_filter_params,
    common_update_options,
    project_option,
    run_create,
    run_update,
    step_failed,
)
from taiga_cli.context import AppContext, pass_app
from taiga_cli.errors import TaigaCliError
from taiga_cli.output import ListOutput, list_options

KIND = stories.RESOURCE.status_kind


@click.group()
def story() -> None:
    """User stories."""


@story.command("list")
@project_option
@common_filter_options
@click.option("--sprint", metavar="NAME", help="Sprint name/slug, or 'backlog'.")
@list_options(stories.FIELDS, stories.DEFAULT_FIELDS)
@pass_app
def list_(
    app: AppContext,
    project: str | None,
    status: str | None,
    assignee: str | None,
    tags: tuple[str, ...],
    state: str,
    sprint: str | None,
    fields: str | None,
    as_json: bool,
    raw: bool,
    limit: int,
) -> None:
    """List user stories of a project (default: open ones)."""
    out = ListOutput.from_options(
        fields=fields,
        as_json=as_json,
        raw=raw,
        limit=limit,
        available=stories.FIELDS,
        default=stories.DEFAULT_FIELDS,
    )
    pctx = app.project_context(app.project_slug(project))
    params = common_filter_params(
        app, pctx, KIND, status=status, assignee=assignee, tags=tags, state=state
    )
    if sprint:
        milestone = pctx.milestone_id(sprint)
        if milestone is None:
            params["milestone__isnull"] = "true"
        else:
            params["milestone"] = milestone

    items, truncated = stories.RESOURCE.list(app.client(), params, limit=limit)
    out.emit(items, stories.normalize, truncated=truncated)


@story.command("update")
@common_update_options("story")
@click.option("--sprint", metavar="NAME", help="Sprint name/slug, or 'backlog'.")
@pass_app
def update(
    app: AppContext,
    ref: str,
    project: str | None,
    subject: str | None,
    status: str | None,
    assignee: str | None,
    add_tag: tuple[str, ...],
    remove_tag: tuple[str, ...],
    description: str | None,
    comment: str | None,
    raw: bool,
    sprint: str | None,
) -> None:
    """Update a user story.

    Example: `taiga-cli story update web#42 --status Done`
    """
    change = ItemUpdate(subject, status, assignee, add_tag, remove_tag, description, comment)
    if sprint:
        change.extra["milestone"] = lambda pctx: pctx.milestone_id(sprint)
    run_update(app, stories.RESOURCE, ref, project, change, raw=raw)


class EpicLinks:
    """``story create --epic REF``: epics resolved before the story exists, linked after."""

    def __init__(self, refs: tuple[str, ...]) -> None:
        self._refs = [parse_ref(r, None) for r in refs]  # syntax errors before any request
        self._epics: dict[int, str] = {}  # epic id -> "slug#ref" for messages

    def prepare(self, app: AppContext, pctx: ProjectContext) -> None:
        client = app.client()
        for slug, number in self._refs:
            target = pctx if slug in (None, pctx.slug) else app.project_context(slug)
            found = epics.RESOURCE.get_by_ref(client, target.id, number, target.slug)
            self._epics.setdefault(found["id"], f"{target.slug}#{number}")

    def apply(self, client: TaigaClient, item: dict[str, Any]) -> None:
        for epic_id, label in self._epics.items():
            try:
                epics.link_story(client, epic_id, item["id"])
            except TaigaCliError as exc:
                raise step_failed(f"linking to epic {label}", exc) from exc


@story.command("create")
@common_create_options("story")
@click.option("--sprint", metavar="NAME", help="Sprint name/slug, or 'backlog'.")
@click.option(
    "--epic", "epic_refs", multiple=True, metavar="REF", help="Link to an epic (repeatable)."
)
@pass_app
def create(
    app: AppContext,
    subject: str,
    project: str | None,
    description: str | None,
    status: str | None,
    assignee: str | None,
    tags: tuple[str, ...],
    custom: tuple[str, ...],
    if_absent: bool,
    as_json: bool,
    sprint: str | None,
    epic_refs: tuple[str, ...],
) -> None:
    """Create a user story; prints `created: SLUG#REF`.

    Example: `taiga-cli story create --subject "Login page" --epic 3`
    """
    item = ItemCreate(subject, description, status, assignee, tags, custom)
    if sprint:
        item.extra["milestone"] = lambda pctx: pctx.milestone_id(sprint)
    if epic_refs:
        item.side_effects.append(EpicLinks(epic_refs))
    run_create(
        app,
        stories.RESOURCE,
        project,
        item,
        if_absent=if_absent,
        as_json=as_json,
        normalizer=lambda _pctx: stories.normalize,
    )
