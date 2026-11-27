"""``taiga-cli task``: tasks."""

from __future__ import annotations

import click

from taiga_cli.api import stories, tasks
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

KIND = tasks.RESOURCE.status_kind


@click.group()
def task() -> None:
    """Tasks."""


@task.command("list")
@project_option
@common_filter_options
@click.option(
    "--story", "story_ref", metavar="REF", help="Tasks of this user story (42 or SLUG#42)."
)
@click.option("--sprint", metavar="NAME", help="Sprint name/slug.")
@list_options(tasks.FIELDS, tasks.DEFAULT_FIELDS)
@pass_app
def list_(
    app: AppContext,
    project: str | None,
    status: str | None,
    assignee: str | None,
    tags: tuple[str, ...],
    state: str,
    story_ref: str | None,
    sprint: str | None,
    fields: str | None,
    as_json: bool,
    raw: bool,
    limit: int,
) -> None:
    """List tasks of a project (default: open ones)."""
    out = ListOutput.from_options(
        fields=fields,
        as_json=as_json,
        raw=raw,
        limit=limit,
        available=tasks.FIELDS,
        default=tasks.DEFAULT_FIELDS,
    )
    story_slug, story_number = parse_ref(story_ref, project) if story_ref else (None, None)
    # parse_ref already merged -P into story_slug and rejected conflicts
    slug = app.project_slug(story_slug or project)

    client = app.client()
    pctx = app.project_context(slug)
    params = common_filter_params(
        app, pctx, KIND, status=status, assignee=assignee, tags=tags, state=state
    )
    if sprint:
        milestone = pctx.milestone_id(sprint)
        if milestone is None:
            raise UsageError("tasks can't be filtered by 'backlog'; use --story or a sprint name")
        params["milestone"] = milestone
    if story_number is not None:
        params["user_story"] = stories.RESOURCE.get_by_ref(client, pctx.id, story_number, slug)[
            "id"
        ]

    items, truncated = tasks.RESOURCE.list(client, params, limit=limit)
    out.emit(items, tasks.normalize, truncated=truncated)


@task.command("update")
@common_update_options("task")
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
) -> None:
    """Update a task.

    Example: `taiga-cli task update web#43 --status Closed`
    """
    change = ItemUpdate(subject, status, assignee, add_tag, remove_tag, description, comment)
    run_update(app, tasks.RESOURCE, ref, project, change, raw=raw)


@task.command("create")
@common_create_options("task")
@click.option("--story", "story_ref", metavar="REF", help="Attach to a user story (42 or SLUG#42).")
@click.option("--sprint", metavar="NAME", help="Sprint name/slug [default: the story's sprint].")
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
    story_ref: str | None,
    sprint: str | None,
) -> None:
    """Create a task; prints `created: SLUG#REF`.

    Example: `taiga-cli task create --subject "Write tests" --story 42`
    """
    item = ItemCreate(subject, description, status, assignee, tags, custom)
    if story_ref:
        story_slug, story_number = parse_ref(story_ref, project)  # rejects a conflicting -P
        project = story_slug or project
        parent: dict[str, dict] = {}

        def story(pctx: ProjectContext) -> dict:
            if "item" not in parent:  # one lookup shared by user_story and milestone
                parent["item"] = stories.RESOURCE.get_by_ref(
                    app.client(), pctx.id, story_number, pctx.slug
                )
            return parent["item"]

        item.extra["user_story"] = lambda pctx: story(pctx)["id"]
        if not sprint:
            item.extra["milestone"] = lambda pctx: story(pctx).get("milestone")
    if sprint:
        item.extra["milestone"] = lambda pctx: pctx.milestone_id(sprint)
    run_create(
        app,
        tasks.RESOURCE,
        project,
        item,
        if_absent=if_absent,
        as_json=as_json,
        normalizer=lambda _pctx: tasks.normalize,
    )
