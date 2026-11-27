"""Bundled agent skill and installers."""

from __future__ import annotations

import re
from importlib.resources import files
from pathlib import Path

SKILL_NAME = "taiga-cli"
BEGIN = "<!-- taiga-cli:begin -->"
END = "<!-- taiga-cli:end -->"
_FRONTMATTER = re.compile(r"\A---\n.*?\n---\n+", re.DOTALL)


def read_skill() -> str:
    return files(__package__).joinpath(SKILL_NAME, "SKILL.md").read_text(encoding="utf-8")


def skill_body() -> str:
    """Skill content without the YAML frontmatter."""
    return _FRONTMATTER.sub("", read_skill(), count=1)


def install_claude(skills_dir: Path) -> Path:
    target = skills_dir / SKILL_NAME / "SKILL.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(read_skill(), encoding="utf-8")
    return target


def install_agents_md(path: Path) -> Path:
    """Insert or replace a managed block in an AGENTS.md-style file."""
    block = f"{BEGIN}\n{skill_body().strip()}\n{END}\n"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    pattern = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?", re.DOTALL)
    if pattern.search(text):
        text = pattern.sub(lambda _: block, text, count=1)
    else:
        sep = "" if not text or text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
        text = f"{text}{sep}{block}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path
