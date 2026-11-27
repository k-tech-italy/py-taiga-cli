import re
from pathlib import Path

import click

from taiga_cli import skills
from taiga_cli.cli import main


def _command_exists(words: list[str]) -> bool:
    """Walk groups; words after a leaf command are its arguments."""
    cmd: click.Command = main
    for word in words:
        if not isinstance(cmd, click.Group):
            return True
        if word not in cmd.commands:
            return False
        cmd = cmd.commands[word]
    return not isinstance(cmd, click.Group)


def test_skill_commands_exist() -> None:
    """Every `taiga-cli ...` command documented in the skill must exist."""
    documented = re.findall(r"`taiga-cli ((?:[a-z][a-z-]* ?)+)", skills.read_skill())
    assert documented, "skill documents no commands"
    for cmd in documented:
        words = cmd.split()
        assert _command_exists(words), f"skill documents missing command: {cmd}"


def test_show(invoke) -> None:
    result = invoke(None, "skill", "show")
    assert result.output == skills.read_skill()


def test_install_claude(invoke, tmp_path: Path) -> None:
    result = invoke(None, "skill", "install", "--dest", str(tmp_path))
    target = tmp_path / "taiga-cli" / "SKILL.md"
    assert result.output == f"ok: {target}\n"
    assert target.read_text() == skills.read_skill()


def test_install_agents_md_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "AGENTS.md"
    path.write_text("# Mine\n\nkeep me\n")
    skills.install_agents_md(path)
    once = path.read_text()
    skills.install_agents_md(path)
    assert path.read_text() == once
    assert once.startswith("# Mine\n\nkeep me\n\n<!-- taiga-cli:begin -->\n")
    assert "name: taiga-cli" not in once  # frontmatter stripped
    assert once.count(skills.BEGIN) == 1
