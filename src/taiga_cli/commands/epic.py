"""``taiga-cli epic``: epics."""

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
)
from taiga_cli.context import AppContext, pass_app
from taiga_cli.errors import UsageError
from taiga_cli.output import ListOutput, list_options

KIND = epics.RESOURCE.status_kind


class StoryLinks:
    """Add/remove epic <-> user story links (a SideEffect of `epic update`).

    Idempotent: links already in the desired state are skipped.
    """

    def __init__(self, add: tuple[str, ...], remove: tuple[str, ...]) -> None:
        # Validate ref syntax before any request.
        self._add = [parse_ref(r, None) for r in add]
        self._remove = [parse_ref(r, None) for r in remove]
        self._add_ids: list[int] = []
        self._remove_ids: list[int] = []

    def prepare(self, app: AppContext, pctx: ProjectContext) -> None:
        client = app.client()

        def story_id(slug: str | None, number: int) -> int:
            target = pctx if slug in (None, pctx.slug) else app.project_context(slug)
            return stories.RESOURCE.get_by_ref(client, target.id, number, target.slug)["id"]

        # Resolving every story first means a typo fails before anything is modified.
        self._add_ids = [story_id(*r) for r in self._add]
        self._remove_ids = [story_id(*r) for r in self._remove]
        if set(self._add_ids) & set(self._remove_ids):
            raise UsageError("the same story is in both --add-story and --remove-story")

    def apply(self, client: TaigaClient, item: dict[str, Any]) -> None:
        linked = epics.related_story_ids(client, item["id"])
        for sid in dict.fromkeys(self._add_ids):
            if sid not in linked:
                epics.link_story(client, item["id"], sid)
        for sid in dict.fromkeys(self._remove_ids):
            if sid in linked:
                epics.unlink_story(client, item["id"], sid)


@click.group()
def epic() -> None:
    """Epics."""


@epic.command("list")
@project_option
@common_filter_options
@list_options(epics.FIELDS, epics.DEFAULT_FIELDS)
@pass_app
def list_(
    app: AppContext,
    project: str | None,
    status: str | None,
    assignee: str | None,
    tags: tuple[str, ...],
    state: str,
    fields: str | None,
    as_json: bool,
    raw: bool,
    limit: int,
) -> None:
    """List epics of a project (default: open ones)."""
    out = ListOutput.from_options(
        fields=fields,
        as_json=as_json,
        raw=raw,
        limit=limit,
        available=epics.FIELDS,
        default=epics.DEFAULT_FIELDS,
    )
    pctx = app.project_context(app.project_slug(project))
    params = common_filter_params(
        app, pctx, KIND, status=status, assignee=assignee, tags=tags, state=state
    )
    items, truncated = epics.RESOURCE.list(app.client(), params, limit=limit)
    out.emit(items, epics.normalize, truncated=truncated)


@epic.command("update")
@common_update_options("epic")
@click.option("--color", metavar="HEX", help="Epic color, e.g. #ff8800.")
@click.option(
    "--add-story",
    multiple=True,
    metavar="REF",
    help="Link a user story: 42 or SLUG#42 (repeatable).",
)
@click.option(
    "--remove-story", multiple=True, metavar="REF", help="Unlink a user story (repeatable)."
)
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
    color: str | None,
    add_story: tuple[str, ...],
    remove_story: tuple[str, ...],
) -> None:
    """Update an epic.

    Example: `taiga-cli epic update web#3 --status Done --add-story 42`
    """
    change = ItemUpdate(subject, status, assignee, add_tag, remove_tag, description, comment)
    if color:
        parsed = epics.parse_color(color)  # validate before any request
        change.extra["color"] = lambda _pctx: parsed
    if add_story or remove_story:
        change.side_effects.append(StoryLinks(add_story, remove_story))
    run_update(app, epics.RESOURCE, ref, project, change, raw=raw)


@epic.command("create")
@common_create_options("epic")
@click.option("--color", metavar="HEX", help="Epic color, e.g. #ff8800.")
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
    color: str | None,
) -> None:
    """Create an epic; prints `created: SLUG#REF`.

    Example: `taiga-cli epic create --subject "Self-service onboarding" --color "#ff8800"`
    """
    item = ItemCreate(subject, description, status, assignee, tags, custom)
    if color:
        parsed = epics.parse_color(color)  # validate before any request
        item.extra["color"] = lambda _pctx: parsed
    run_create(
        app,
        epics.RESOURCE,
        project,
        item,
        if_absent=if_absent,
        as_json=as_json,
        normalizer=lambda _pctx: epics.normalize,
    )
