"""``taiga-cli project``."""

from __future__ import annotations

import json
from pathlib import Path

import click

from taiga_cli.api import projects
from taiga_cli.api.client import normalize_base_url
from taiga_cli.api.project_config import CONFIG_FILENAME, build_config, parse_taiga_url
from taiga_cli.api.project_context import ProjectContext
from taiga_cli.context import AppContext, pass_app
from taiga_cli.errors import AuthError, UsageError
from taiga_cli.output import ListOutput, list_options


@click.group()
def project() -> None:
    """Projects."""


@project.command("list")
@click.option("--all", "all_", is_flag=True, help="Include projects you are not a member of.")
@list_options(projects.FIELDS, projects.DEFAULT_FIELDS)
@pass_app
def list_(
    app: AppContext, all_: bool, fields: str | None, as_json: bool, raw: bool, limit: int
) -> None:
    """List projects (default: those you are a member of)."""
    out = ListOutput.from_options(
        fields=fields,
        as_json=as_json,
        raw=raw,
        limit=limit,
        available=projects.FIELDS,
        default=projects.DEFAULT_FIELDS,
    )
    member_id = None if all_ else app.profile().user_id
    items, truncated = projects.list_projects(app.client(), member_id=member_id, limit=limit)
    out.emit(items, projects.normalize, truncated=truncated)


@project.group()
def configure() -> None:
    """Per-repository .taiga-cli-config.json."""


def _profile_for(app: AppContext, api_url: str) -> str:
    """Pick the profile whose URL matches: -p if given, else default, else the only match."""
    cfg = app.config
    if app.profile_name:
        chosen = cfg.get_profile(app.profile_name)
        if normalize_base_url(chosen.url) != api_url:
            raise UsageError(f"profile '{chosen.name}' is for {chosen.url}, not {api_url}")
        return chosen.name
    matches = [p.name for p in cfg.profiles.values() if normalize_base_url(p.url) == api_url]
    if not matches:
        raise AuthError(
            f"no profile for {api_url}; run `taiga-cli -p NAME auth login --url {api_url}`"
        )
    if cfg.default_profile in matches:
        return cfg.default_profile
    if len(matches) == 1:
        return matches[0]
    raise UsageError(f"several profiles for {api_url} ({','.join(matches)}); choose with -p")


@configure.command("export")
@click.argument("url")
@click.option("-P", "--project", metavar="SLUG", help="Project slug, if not in URL.")
@click.option(
    "-o",
    "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    help=f"Output file, '-' for stdout [default: ./{CONFIG_FILENAME}].",
)
@click.option("--force", is_flag=True, help="Overwrite an existing file.")
@pass_app
def export(
    app: AppContext, url: str, project: str | None, output: Path | None, force: bool
) -> None:
    """Export a project's admin settings to .taiga-cli-config.json.

    URL is a Taiga page of the project (e.g. https://tree.taiga.io/project/web) or the
    instance URL together with -P SLUG. Meant for project administrators; the file holds
    credential references (keyring profile), never secrets, and can be committed.
    """
    api_url, web_url, slug = parse_taiga_url(url, project)
    api_url = normalize_base_url(api_url)
    to_stdout = output is not None and str(output) == "-"
    path = output or Path.cwd() / CONFIG_FILENAME
    if not to_stdout and path.exists() and not force:
        raise UsageError(f"{path} exists; use --force to overwrite")

    app.profile_name = _profile_for(app, api_url)
    client = app.client()
    raw = ProjectContext.load(client, slug).raw
    if raw.get("i_am_admin") is False:
        click.echo(f"warning: you are not an admin of '{slug}'; export may be incomplete", err=True)

    data = build_config(
        client, raw, api_url=api_url, web_url=web_url, profile=app.resolved_profile_name
    )
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if to_stdout:
        click.echo(text, nl=False)
    else:
        path.write_text(text, encoding="utf-8")
        click.echo(f"ok: {path}")
