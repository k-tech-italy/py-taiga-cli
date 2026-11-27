"""``taiga-cli skill``: print or install the bundled agent skill."""

from __future__ import annotations

from pathlib import Path

import click

from taiga_cli import skills


@click.group()
def skill() -> None:
    """Agent skill describing how to use this CLI."""


@skill.command()
def show() -> None:
    """Print the skill (SKILL.md) to stdout."""
    click.echo(skills.read_skill(), nl=False)


@skill.command()
@click.option(
    "--target",
    type=click.Choice(["claude", "agents-md"]),
    default="claude",
    show_default=True,
    help="claude: .claude/skills/taiga-cli/SKILL.md; agents-md: managed block in AGENTS.md.",
)
@click.option(
    "--dest",
    type=click.Path(path_type=Path),
    help="Override the destination (directory for claude, file for agents-md).",
)
@click.option(
    "--global", "global_", is_flag=True, help="claude target only: install in ~/.claude/skills."
)
def install(target: str, dest: Path | None, global_: bool) -> None:
    """Install or update the skill for an agent."""
    if target == "claude":
        if dest is None:
            base = Path.home() if global_ else Path.cwd()
            dest = base / ".claude" / "skills"
        path = skills.install_claude(dest)
    else:
        path = skills.install_agents_md(dest or Path.cwd() / "AGENTS.md")
    click.echo(f"ok: {path}")
