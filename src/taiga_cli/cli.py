"""Entry point: ``taiga-cli``."""

from __future__ import annotations

import click

from taiga_cli import __version__
from taiga_cli.commands import auth, epic, issue, project, skill, story, task
from taiga_cli.context import AppContext

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"], "max_content_width": 100}


@click.group(context_settings=CONTEXT_SETTINGS)
@click.version_option(__version__, "-V", "--version", prog_name="taiga-cli")
@click.option(
    "-p", "--profile", metavar="NAME", help="Config profile [default: project file, then config]."
)
@click.option(
    "--no-project-config",
    is_flag=True,
    help="Ignore .taiga-cli-config.json found in this or a parent directory.",
)
@click.pass_context
def main(ctx: click.Context, profile: str | None, no_project_config: bool) -> None:
    """Token-efficient Taiga client."""
    app = ctx.ensure_object(AppContext)
    if profile:
        app.profile_name = profile
    if no_project_config:
        app.use_project_config = False
    ctx.call_on_close(app.close)


main.add_command(auth.auth)
main.add_command(project.project)
main.add_command(story.story)
main.add_command(task.task)
main.add_command(issue.issue)
main.add_command(epic.epic)
main.add_command(skill.skill)
