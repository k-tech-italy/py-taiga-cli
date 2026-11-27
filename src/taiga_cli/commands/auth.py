"""``taiga-cli auth``: login / logout / status."""

from __future__ import annotations

import sys

import click

from taiga_cli import config, credentials
from taiga_cli.context import AppContext, pass_app


@click.group()
def auth() -> None:
    """Manage credentials (stored in the OS keyring)."""


@auth.command()
@click.option("--url", help="Taiga base URL, e.g. https://api.taiga.io")
@click.option("--username", help="Username or email.")
@click.option(
    "--password-stdin", is_flag=True, help="Read the password from stdin (non-interactive)."
)
@pass_app
def login(app: AppContext, url: str | None, username: str | None, password_stdin: bool) -> None:
    """Log in and store tokens for the profile. The password itself is never stored."""
    cfg = app.config
    name = app.resolved_profile_name
    existing = cfg.profiles.get(name)
    pc = app.project_config()
    url = (
        url
        or (existing.url if existing else None)
        or (pc.url if pc and pc.profile == name else None)
        or click.prompt("Taiga URL")
    )
    username = username or (existing.username if existing else None) or click.prompt("Username")
    if password_stdin:
        password = sys.stdin.readline().rstrip("\r\n")
    else:
        password = click.prompt("Password", hide_input=True)

    with app.new_client(url) as client:
        user = client.login(username, password)
        assert client.tokens is not None
        credentials.save_tokens(name, client.tokens)
        base_url = client.base_url

    cfg.profiles[name] = config.Profile(
        name=name, url=base_url, username=username, user_id=user.get("id")
    )
    if len(cfg.profiles) == 1:
        cfg.default_profile = name
    config.save(cfg)
    click.echo(f"ok: {username}@{base_url} profile={name}")


@auth.command()
@pass_app
def logout(app: AppContext) -> None:
    """Remove stored tokens for the profile."""
    name = app.resolved_profile_name
    removed = credentials.delete_tokens(name)
    click.echo(f"ok: logged out profile={name}" if removed else f"ok: no tokens profile={name}")


@auth.command()
@pass_app
def status(app: AppContext) -> None:
    """Verify the stored session against the server."""
    profile = app.profile()
    me = app.client().get("/users/me")
    click.echo(f"ok: {me.get('username')}@{profile.url} profile={profile.name}")
