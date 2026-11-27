"""``taiga-cli story``: user stories."""

from __future__ import annotations

import click

from taiga_cli.api import stories
from taiga_cli.commands._items import (
    ItemUpdate,
    common_filter_options,
    common_filter_params,
    common_update_options,
    project_option,
    run_update,
)
from taiga_cli.context import AppContext, pass_app
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
