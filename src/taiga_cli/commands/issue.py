"""``taiga-cli issue``: issues."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import click

from taiga_cli.api import issues
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

KIND = issues.RESOURCE.status_kind


def _value_options(plural: bool) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    metavar, how = ("NAMES", "name(s), comma-separated") if plural else ("NAME", "name")

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        func = click.option("--severity", metavar=metavar, help=f"Severity {how}.")(func)
        func = click.option("--priority", metavar=metavar, help=f"Priority {how}.")(func)
        func = click.option("--type", "type_", metavar=metavar, help=f"Issue type {how}.")(func)
        return func

    return decorator


@click.group()
def issue() -> None:
    """Issues."""


@issue.command("list")
@project_option
@common_filter_options
@_value_options(plural=True)
@click.option("--sprint", metavar="NAME", help="Sprint name/slug.")
@list_options(issues.FIELDS, issues.DEFAULT_FIELDS)
@pass_app
def list_(
    app: AppContext,
    project: str | None,
    status: str | None,
    assignee: str | None,
    tags: tuple[str, ...],
    state: str,
    type_: str | None,
    priority: str | None,
    severity: str | None,
    sprint: str | None,
    fields: str | None,
    as_json: bool,
    raw: bool,
    limit: int,
) -> None:
    """List issues of a project (default: open ones)."""
    out = ListOutput.from_options(
        fields=fields,
        as_json=as_json,
        raw=raw,
        limit=limit,
        available=issues.FIELDS,
        default=issues.DEFAULT_FIELDS,
    )
    pctx = app.project_context(app.project_slug(project))
    params = common_filter_params(
        app, pctx, KIND, status=status, assignee=assignee, tags=tags, state=state
    )
    for param, names, kind in (
        ("type", type_, "issue_types"),
        ("priority", priority, "priorities"),
        ("severity", severity, "severities"),
    ):
        if names:
            params[param] = ",".join(str(i) for i in pctx.value_ids(kind, names))
    if sprint:
        milestone = pctx.milestone_id(sprint)
        if milestone is None:
            raise UsageError("issues can't be filtered by 'backlog'; use a sprint name")
        params["milestone"] = milestone

    items, truncated = issues.RESOURCE.list(app.client(), params, limit=limit)
    # Resolve id -> name only for the value columns actually printed.
    wanted = [] if out.raw else [f for f in out.fields if f in issues.VALUE_FIELDS]
    names = {issues.VALUE_FIELDS[f]: pctx.value_names(issues.VALUE_FIELDS[f]) for f in wanted}
    out.emit(items, issues.make_normalizer(names), truncated=truncated)


@issue.command("update")
@common_update_options("issue")
@_value_options(plural=False)
@click.option("--sprint", metavar="NAME", help="Sprint name/slug, or 'backlog' to remove.")
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
    type_: str | None,
    priority: str | None,
    severity: str | None,
    sprint: str | None,
) -> None:
    """Update an issue.

    Example: `taiga-cli issue update web#7 --status Closed --priority High`
    """
    change = ItemUpdate(subject, status, assignee, add_tag, remove_tag, description, comment)
    for field, name, kind in (
        ("type", type_, "issue_types"),
        ("priority", priority, "priorities"),
        ("severity", severity, "severities"),
    ):
        if name:
            change.extra[field] = lambda pctx, kind=kind, name=name: pctx.value_id(kind, name)
    if sprint:
        change.extra["milestone"] = lambda pctx: pctx.milestone_id(sprint)
    run_update(app, issues.RESOURCE, ref, project, change, raw=raw)


@issue.command("create")
@common_create_options("issue")
@_value_options(plural=False)
@click.option("--sprint", metavar="NAME", help="Sprint name/slug, or 'backlog'.")
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
    type_: str | None,
    priority: str | None,
    severity: str | None,
    sprint: str | None,
) -> None:
    """Create an issue; prints `created: SLUG#REF`.

    Example: `taiga-cli issue create --subject "Crash on login" --type Bug --priority High`
    """
    item = ItemCreate(subject, description, status, assignee, tags, custom)
    item.defaults = {"type": "issue_type", "priority": "priority", "severity": "severity"}
    for field_name, name, kind in (
        ("type", type_, "issue_types"),
        ("priority", priority, "priorities"),
        ("severity", severity, "severities"),
    ):
        if name:
            item.extra[field_name] = lambda pctx, kind=kind, name=name: pctx.value_id(kind, name)
    if sprint:
        item.extra["milestone"] = lambda pctx: pctx.milestone_id(sprint)

    def normalizer(pctx: ProjectContext) -> Callable[[dict[str, Any]], dict[str, Any]]:
        kinds = issues.VALUE_FIELDS.values()
        return issues.make_normalizer({kind: pctx.value_names(kind) for kind in kinds})

    run_create(
        app,
        issues.RESOURCE,
        project,
        item,
        if_absent=if_absent,
        as_json=as_json,
        normalizer=normalizer,
    )
