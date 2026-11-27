"""Options and update logic shared by ref-addressed item commands (story, task, ...)."""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

import click

from taiga_cli.api.client import TaigaClient
from taiga_cli.api.items import Resource, parse_ref, tag_names
from taiga_cli.api.project_context import ProjectContext
from taiga_cli.context import AppContext
from taiga_cli.errors import UsageError, VersionConflictError
from taiga_cli.output import dump_json

project_option = click.option(
    "-P", "--project", metavar="SLUG", help="Project slug [default: from project config file]."
)

STATE_OPTION = click.option(
    "--state",
    type=click.Choice(["open", "closed", "all"]),
    default="open",
    show_default=True,
    help="Filter by closed status.",
)


def common_filter_options(func: Callable[..., Any]) -> Callable[..., Any]:
    """--status/--assignee/--tag/--state for list commands."""
    func = STATE_OPTION(func)
    func = click.option(
        "--tag", "tags", multiple=True, metavar="TAG", help="Has tag (repeatable)."
    )(func)
    func = click.option("--assignee", metavar="USER", help="Username, full name or 'me'.")(func)
    func = click.option("--status", metavar="NAMES", help="Status name(s), comma-separated.")(func)
    return func


def common_filter_params(
    app: AppContext,
    pctx: ProjectContext,
    kind: str,
    *,
    status: str | None,
    assignee: str | None,
    tags: tuple[str, ...],
    state: str,
) -> dict[str, Any]:
    params: dict[str, Any] = {"project": pctx.id}
    if status:
        params["status"] = ",".join(str(i) for i in pctx.status_ids(kind, status))
    if assignee:
        params["assigned_to"] = pctx.user_id(assignee, app.me_id)
    if tags:
        params["tags"] = ",".join(tags)
    if state != "all":
        params["status__is_closed"] = "true" if state == "closed" else "false"
    return params


def common_update_options(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """REF argument, -P and the change options every item supports."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        options = [
            click.option("--raw", is_flag=True, help=f"Print the full updated {name} as JSON."),
            click.option("--comment", metavar="TEXT", help="Add a comment; '-' reads stdin."),
            click.option(
                "--description", metavar="TEXT", help="Replace description; '-' reads stdin."
            ),
            click.option(
                "--remove-tag", multiple=True, metavar="TAG", help="Remove tag (repeatable)."
            ),
            click.option("--add-tag", multiple=True, metavar="TAG", help="Add tag (repeatable)."),
            click.option("--assignee", metavar="USER", help="Username, full name, 'me' or 'none'."),
            click.option("--status", metavar="NAME", help="Status name."),
            click.option("--subject", help="New title."),
            project_option,
            click.argument("ref"),
        ]
        for option in options:
            func = option(func)
        return func

    return decorator


class SideEffect(Protocol):
    """Work beyond the item's own fields (e.g. epic <-> story links).

    ``prepare`` runs before anything is modified (resolve and validate, may fail);
    ``apply`` runs after the item's fields were saved.
    """

    def prepare(self, app: AppContext, pctx: ProjectContext) -> None: ...

    def apply(self, client: TaigaClient, item: dict[str, Any]) -> None: ...


@dataclass
class ItemUpdate:
    """Changes requested on the command line, before name resolution."""

    subject: str | None = None
    status: str | None = None
    assignee: str | None = None
    add_tag: tuple[str, ...] = ()
    remove_tag: tuple[str, ...] = ()
    description: str | None = None
    comment: str | None = None
    # Extra already-resolvable changes contributed by a specific command (e.g. story --sprint).
    extra: dict[str, Callable[[ProjectContext], Any]] = field(default_factory=dict)
    side_effects: list[SideEffect] = field(default_factory=list)

    def read_stdin(self) -> None:
        if self.description == "-" and self.comment == "-":
            raise UsageError("only one of --description/--comment can read stdin")
        if self.description == "-":
            self.description = sys.stdin.read()
        if self.comment == "-":
            self.comment = sys.stdin.read()

    def is_empty(self) -> bool:
        flags = [self.subject, self.status, self.assignee, self.add_tag, self.remove_tag]
        flags += [self.comment, self.extra, self.side_effects]
        return not any(flags) and self.description is None

    def resolve(self, app: AppContext, pctx: ProjectContext, kind: str) -> dict[str, Any]:
        changes: dict[str, Any] = {}
        if self.subject:
            changes["subject"] = self.subject
        if self.status:
            changes["status"] = pctx.status_id(kind, self.status)
        if self.assignee:
            none = self.assignee.strip().casefold() == "none"
            changes["assigned_to"] = None if none else pctx.user_id(self.assignee, app.me_id)
        for key, resolve in self.extra.items():
            changes[key] = resolve(pctx)
        if self.description is not None:
            changes["description"] = self.description
        if self.comment:
            changes["comment"] = self.comment
        return changes


def run_update(
    app: AppContext,
    resource: Resource,
    ref: str,
    project: str | None,
    update: ItemUpdate,
    *,
    raw: bool,
) -> None:
    """Resolve names, PATCH with Taiga's optimistic locking, print ``ok: SLUG#REF``."""
    ref_slug, number = parse_ref(ref, project)
    update.read_stdin()
    if update.is_empty():
        raise UsageError("nothing to update; pass at least one change option")

    slug = app.project_slug(ref_slug)
    client = app.client()
    pctx = app.project_context(slug)
    changes = update.resolve(app, pctx, resource.status_kind)
    for effect in update.side_effects:
        effect.prepare(app, pctx)

    if changes or update.add_tag or update.remove_tag:
        updated = _patch_with_retry(client, resource, pctx, number, slug, changes, update)
    else:  # only side effects: no PATCH, but they need the item
        updated = resource.get_by_ref(client, pctx.id, number, slug)
    for effect in update.side_effects:
        effect.apply(client, updated)

    click.echo(dump_json(updated) if raw else f"ok: {slug}#{number}")


def _patch_with_retry(
    client: TaigaClient,
    resource: Resource,
    pctx: ProjectContext,
    number: int,
    slug: str,
    changes: dict[str, Any],
    update: ItemUpdate,
) -> dict[str, Any]:
    """PATCH sending the version we read; if someone changed the item meanwhile, retry once."""
    for attempt in (1, 2):
        current = resource.get_by_ref(client, pctx.id, number, slug)
        body = dict(changes, version=current["version"])
        if update.add_tag or update.remove_tag:
            names = [t for t in tag_names(current) if t not in update.remove_tag]
            body["tags"] = names + [t for t in update.add_tag if t not in names]
        try:
            return resource.update(client, current["id"], body)
        except VersionConflictError:
            if attempt == 2:
                raise
    raise AssertionError("unreachable")  # pragma: no cover
