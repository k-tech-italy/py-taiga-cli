"""Renderers implementing the output contract.

- compact (default): one line per item, tab-separated fields, nothing else on stdout.
- ``--json``: a compact JSON array with only the selected fields.
- ``--raw``: the unmodified Taiga API payload as compact JSON (escape hatch, costly).
- truncation notice goes to stderr so stdout stays machine-parseable.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any

import click

from taiga_cli.errors import UsageError

DEFAULT_LIMIT = 20
MAX_LIMIT = 1000


def parse_fields(
    value: str | None, available: Sequence[str], default: Sequence[str]
) -> tuple[str, ...]:
    if not value:
        return tuple(default)
    fields = tuple(f.strip() for f in value.split(",") if f.strip())
    unknown = [f for f in fields if f not in available]
    if unknown:
        raise UsageError(
            f"--fields: unknown field(s) {','.join(unknown)}; available: {','.join(available)}"
        )
    return fields


def dump_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _cell(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return " ".join(str(value).split())


def _truncation_note(truncated: bool, limit: int | None) -> None:
    if truncated:
        click.echo(f"truncated at {limit}; raise --limit for more", err=True)


def render(
    items: Iterable[dict[str, Any]],
    fields: Sequence[str],
    *,
    as_json: bool,
    truncated: bool = False,
    limit: int | None = None,
) -> None:
    rows = [{f: item.get(f) for f in fields} for item in items]
    if as_json:
        click.echo(dump_json(rows))
    else:
        for row in rows:
            click.echo("\t".join(_cell(row[f]) for f in fields))
    _truncation_note(truncated, limit)


@dataclass(frozen=True)
class ListOutput:
    """Resolved output options of a list command; validate before calling the API."""

    fields: tuple[str, ...]
    as_json: bool
    raw: bool
    limit: int

    @classmethod
    def from_options(
        cls,
        *,
        fields: str | None,
        as_json: bool,
        raw: bool,
        limit: int,
        available: Sequence[str],
        default: Sequence[str],
    ) -> ListOutput:
        if raw and fields:
            raise UsageError("--raw returns every field; drop --fields")
        return cls(parse_fields(fields, available, default), as_json, raw, limit)

    def emit(
        self,
        raw_items: list[dict[str, Any]],
        normalize: Callable[[dict[str, Any]], dict[str, Any]],
        *,
        truncated: bool,
    ) -> None:
        if self.raw:
            click.echo(dump_json(raw_items))
            _truncation_note(truncated, self.limit)
        else:
            render(
                [normalize(r) for r in raw_items],
                self.fields,
                as_json=self.as_json,
                truncated=truncated,
                limit=self.limit,
            )


def list_options(
    available: Sequence[str], default: Sequence[str]
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Add ``--fields``, ``--json``, ``--raw`` and ``--limit`` to a list command."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        func = click.option(
            "--limit",
            type=click.IntRange(1, MAX_LIMIT),
            default=DEFAULT_LIMIT,
            show_default=True,
            help="Max items.",
        )(func)
        func = click.option(
            "--raw", is_flag=True, help="Full Taiga API payload as JSON (large; use sparingly)."
        )(func)
        func = click.option("--json", "as_json", is_flag=True, help="JSON output.")(func)
        func = click.option(
            "--fields",
            metavar="F1,F2",
            help=f"Fields: {','.join(available)} [default: {','.join(default)}]",
        )(func)
        return func

    return decorator
