#!/usr/bin/env python3
"""Compare the tokens an AI agent reads when using taiga-mcp vs taiga-cli.

For each scenario the script:

- **taiga-mcp side**: calls the Taiga REST API directly and renders each response exactly the
  way taiga-mcp does (https://github.com/illodev/taiga-mcp: the raw payload passed through
  ``JSON.stringify(data, null, 2)``), plus the tool-call input (tool name + arguments).
  The MCP server itself is not needed.
- **taiga-cli side**: runs the real ``taiga-cli`` command in-process and counts the command
  line plus everything it prints (stdout + stderr).

Nothing is written to Taiga: the "update" scenario is simulated by reading the data an
update would return (taiga-mcp echoes the full updated item; taiga-cli prints ``ok: REF``).

Usage (logged in with ``taiga-cli auth login``)::

    uv run python scripts/benchmark_tokens.py -P my-project
    uv run python scripts/benchmark_tokens.py              # project from .taiga-cli-config.json

    # exact Claude token counts (sends the Taiga data to the Anthropic token-counting API):
    uv run --group bench python scripts/benchmark_tokens.py -P my-project --tokenizer anthropic

    # include taiga-mcp's fixed per-session cost (its tool definitions), from a tools/list dump:
    npx @modelcontextprotocol/inspector --cli node /path/to/taiga-mcp/dist/index.js \\
        --method tools/list > mcp-tools.json
    uv run python scripts/benchmark_tokens.py -P my-project --mcp-tools-json mcp-tools.json
"""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from click.testing import CliRunner

from taiga_cli.cli import main as cli_main
from taiga_cli.context import AppContext
from taiga_cli.errors import TaigaCliError
from taiga_cli.skills import read_skill, skill_body

DEFAULT_MODEL = "claude-opus-5-5"


# -- token counting ------------------------------------------------------------


class Tokenizer:
    """Approximate tokenizer: ~4 characters per token (offline, no dependency)."""

    name = "approx (chars/4)"

    def count(self, text: str) -> int:
        return (len(text) + 3) // 4

    def count_tools(self, tools: list[dict[str, Any]]) -> int:
        return self.count(json.dumps(tools))


class AnthropicTokenizer(Tokenizer):
    """Exact counts from the Anthropic token-counting API (sends the text to Anthropic)."""

    def __init__(self, model: str) -> None:
        import anthropic  # optional dependency: `uv run --group bench ...`

        self._client = anthropic.Anthropic()
        self._model = model
        self.name = f"anthropic count_tokens ({model})"
        # Fixed per-request overhead, measured once and subtracted from every count.
        self._base = self._raw(messages=[{"role": "user", "content": "a"}]) - 1

    def _raw(self, **kwargs: Any) -> int:
        return self._client.messages.count_tokens(model=self._model, **kwargs).input_tokens

    def count(self, text: str) -> int:
        if not text:
            return 0
        return max(0, self._raw(messages=[{"role": "user", "content": text}]) - self._base)

    def count_tools(self, tools: list[dict[str, Any]]) -> int:
        api_tools = [
            {
                "name": t["name"],
                "description": t.get("description", ""),
                "input_schema": t.get("inputSchema") or {"type": "object"},
            }
            for t in tools
        ]
        with_tools = self._raw(messages=[{"role": "user", "content": "a"}], tools=api_tools)
        return max(0, with_tools - self._base - 1)


# -- scenarios -----------------------------------------------------------------


def mcp_render(data: Any) -> str:
    """taiga-mcp's tool result text: ``JSON.stringify(data, null, 2)``."""
    return json.dumps(data, indent=2, ensure_ascii=False)


@dataclass
class Result:
    scenario: str
    items: int | None = None
    mcp_calls: int = 0
    mcp_tokens: int = 0
    cli_calls: int = 0
    cli_tokens: int = 0
    note: str = ""

    @property
    def ratio(self) -> float | None:
        return self.mcp_tokens / self.cli_tokens if self.cli_tokens else None


@dataclass
class FixedCost:
    """Tokens loaded once per session, before any call."""

    mcp_tools: int | None = None  # taiga-mcp tool definitions (from a tools/list dump)
    mcp_tool_count: int | None = None
    cli_skill_description: int = 0  # always in context (skill frontmatter)
    cli_skill_full: int = 0  # loaded when the agent uses the skill


@dataclass
class Report:
    tokenizer: str
    project: str
    results: list[Result] = field(default_factory=list)
    fixed: FixedCost = field(default_factory=FixedCost)


class Bench:
    def __init__(self, app: AppContext, tokenizer: Tokenizer, project: str | None) -> None:
        self.app = app
        self.tok = tokenizer
        self.client = app.client()
        self.slug = app.project_slug(project)
        # Setup only (not counted): ids the MCP calls need, and status names to filter on.
        self.project = self.client.get("/projects/by_slug", params={"slug": self.slug})
        self.runner = CliRunner()

    # -- one MCP tool call: input + pretty-printed raw API payload
    def mcp(self, tool: str, args: dict[str, Any], path: str) -> tuple[int, Any]:
        data = self.client.get(path, params={k: _param(v) for k, v in args.items()})
        text = json.dumps({"tool": tool, "input": args}) + "\n" + mcp_render(data)
        return self.tok.count(text), data

    # -- one taiga-cli invocation: command line + everything printed
    def cli(self, *argv: str) -> int:
        app = AppContext(
            profile_name=self.app.profile_name,
            transport=self.app.transport,
            use_project_config=self.app.use_project_config,
        )
        result = self.runner.invoke(cli_main, list(argv), obj=app)
        if result.exit_code != 0:
            raise TaigaCliError(f"taiga-cli {shlex.join(argv)}: {result.output.strip()}")
        return self.tok.count(f"taiga-cli {shlex.join(argv)}\n{result.stdout}{result.stderr}")

    def _list(
        self, name: str, tool: str, path: str, args: dict[str, Any], cli_argv: list[str]
    ) -> Result:
        mcp_tokens, data = self.mcp(tool, args, path)
        items = len(data) if isinstance(data, list) else 0
        # Same number of items on both sides: taiga-mcp has no page-size option, so the CLI
        # is asked for exactly what the MCP call returned.
        cli_tokens = self.cli(*cli_argv, "--limit", str(max(1, min(items, 1000))))
        return Result(name, items, 1, mcp_tokens, 1, cli_tokens)

    # -- scenarios
    def projects(self) -> Result:
        me = self.app.me_id()
        return self._list(
            "List my projects", "taiga_projects_list", "/projects", {"member": me},
            ["project", "list"],
        )  # fmt: skip

    def open_items(self, label: str, tool: str, path: str, group: str) -> Result:
        return self._list(
            f"List open {label}", tool, path,
            {"project": self.project["id"], "status__is_closed": False},
            [group, "list", "-P", self.slug],
        )  # fmt: skip

    def stories_by_status(self) -> Result:
        status = _first_open(self.project.get("us_statuses", []))
        if status is None:
            return Result("Stories in a status (by name)", note="skipped: no open status")
        pid = self.project["id"]
        # taiga-mcp needs the numeric status id: list statuses first, then filter.
        lookup, _ = self.mcp(
            "taiga_userstory_statuses_list", {"project": pid}, "/userstory-statuses"
        )
        listed = self._list(
            "Stories in a status (by name)", "taiga_userstories_list", "/userstories",
            {"project": pid, "status": status["id"]},
            ["story", "list", "-P", self.slug, "--status", status["name"], "--state", "all"],
        )  # fmt: skip
        listed.mcp_calls += 1
        listed.mcp_tokens += lookup
        return listed

    def update_story_status(self) -> Result:
        name = "Update a story's status (simulated)"
        pid = self.project["id"]
        stories = self.client.get(
            "/userstories", params={"project": pid, "page": 1, "page_size": 1}
        )
        status = _first_open(self.project.get("us_statuses", []))
        if not stories or status is None:
            return Result(name, note="skipped: no story or status")
        ref = stories[0]["ref"]
        # taiga-mcp: status id lookup, get_by_ref (for id + version), update (echoes the item).
        lookup, _ = self.mcp(
            "taiga_userstory_statuses_list", {"project": pid}, "/userstory-statuses"
        )
        get, item = self.mcp(
            "taiga_userstories_get_by_ref", {"project": pid, "ref": ref}, "/userstories/by_ref"
        )
        update_input = {"id": item["id"], "status": status["id"], "version": item["version"]}
        update = self.tok.count(
            json.dumps({"tool": "taiga_userstories_update", "input": update_input})
            + "\n"
            + mcp_render(item)  # the PATCH response is the full updated story
        )
        # taiga-cli: one command, resolves names and version internally.
        cli_text = (
            f"taiga-cli story update {self.slug}#{ref} --status {shlex.quote(status['name'])}\n"
            f"ok: {self.slug}#{ref}\n"
        )
        return Result(
            name, 1, 3, lookup + get + update, 1, self.tok.count(cli_text), "nothing written"
        )


def _param(value: Any) -> Any:
    return str(value).lower() if isinstance(value, bool) else value


def _first_open(statuses: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next((s for s in statuses if not s.get("is_closed")), None)


def run(
    app: AppContext,
    tokenizer: Tokenizer,
    project: str | None,
    mcp_tools: list[dict[str, Any]] | None = None,
) -> Report:
    bench = Bench(app, tokenizer, project)
    report = Report(tokenizer=tokenizer.name, project=bench.slug)
    scenarios: list[tuple[str, Callable[[], Result]]] = [
        ("List my projects", bench.projects),
        (
            "List open user stories",
            lambda: bench.open_items(
                "user stories", "taiga_userstories_list", "/userstories", "story"
            ),
        ),
        ("Stories in a status (by name)", bench.stories_by_status),
        (
            "List open tasks",
            lambda: bench.open_items("tasks", "taiga_tasks_list", "/tasks", "task"),
        ),
        (
            "List open issues",
            lambda: bench.open_items("issues", "taiga_issues_list", "/issues", "issue"),
        ),
        (
            "List open epics",
            lambda: bench.open_items("epics", "taiga_epics_list", "/epics", "epic"),
        ),
        ("Update a story's status (simulated)", bench.update_story_status),
    ]
    for label, scenario in scenarios:
        try:
            report.results.append(scenario())
        except TaigaCliError as exc:  # e.g. a module disabled in the project
            report.results.append(Result(label, note=f"skipped: {exc.format_message()}"))

    description = read_skill().split("\n---", 1)[0]  # frontmatter: what is always loaded
    report.fixed = FixedCost(
        mcp_tools=tokenizer.count_tools(mcp_tools) if mcp_tools is not None else None,
        mcp_tool_count=len(mcp_tools) if mcp_tools is not None else None,
        cli_skill_description=tokenizer.count(description),
        cli_skill_full=tokenizer.count(skill_body()),
    )
    return report


# -- output --------------------------------------------------------------------


def _fmt(n: int | None) -> str:
    return "-" if n is None else f"{n:,}"


def render_markdown(report: Report) -> str:
    lines = [
        f"Project `{report.project}` · tokenizer: {report.tokenizer}",
        "",
        "| Scenario | Items | MCP calls | MCP tokens | CLI calls | CLI tokens | Ratio |",
        "|---|--:|--:|--:|--:|--:|--:|",
    ]
    done = [r for r in report.results if not r.note.startswith("skipped")]
    for r in report.results:
        ratio = f"{r.ratio:.0f}x" if r.ratio else "-"
        label = f"{r.scenario} ({r.note})" if r.note else r.scenario
        lines.append(
            f"| {label} | {_fmt(r.items)} | {r.mcp_calls} | {_fmt(r.mcp_tokens)} "
            f"| {r.cli_calls} | {_fmt(r.cli_tokens)} | {ratio} |"
        )
    mcp_total = sum(r.mcp_tokens for r in done)
    cli_total = sum(r.cli_tokens for r in done)
    total_ratio = f"{mcp_total / cli_total:.0f}x" if cli_total else "-"
    lines.append(
        f"| **Total** | | {sum(r.mcp_calls for r in done)} | **{_fmt(mcp_total)}** "
        f"| {sum(r.cli_calls for r in done)} | **{_fmt(cli_total)}** | **{total_ratio}** |"
    )
    f = report.fixed
    mcp_fixed = (
        f"{_fmt(f.mcp_tools)} tokens ({f.mcp_tool_count} tool definitions)"
        if f.mcp_tools is not None
        else "not measured (pass --mcp-tools-json)"
    )
    lines += [
        "",
        "Fixed cost per session (loaded before any call):",
        f"- taiga-mcp: {mcp_fixed}",
        f"- taiga-cli: {_fmt(f.cli_skill_description)} tokens (skill description), "
        f"{_fmt(f.cli_skill_full)} more when the skill is used",
    ]
    return "\n".join(lines) + "\n"


def render_json(report: Report) -> str:
    data = asdict(report)
    for r, raw in zip(report.results, data["results"], strict=True):
        raw["ratio"] = r.ratio
    return json.dumps(data, indent=2) + "\n"


# -- entry point ---------------------------------------------------------------


def main(argv: list[str] | None = None, *, transport: Any = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("-p", "--profile", help="taiga-cli profile")
    parser.add_argument("-P", "--project", help="project slug [default: project config file]")
    parser.add_argument(
        "--tokenizer",
        choices=["approx", "anthropic"],
        default="approx",
        help="approx: chars/4, offline (default). anthropic: exact counts via the Anthropic "
        "token-counting API; sends the Taiga data to Anthropic (needs the `bench` group).",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="model for --tokenizer anthropic")
    parser.add_argument(
        "--mcp-tools-json",
        type=Path,
        help="taiga-mcp tools/list output, to include its tool-definition cost",
    )
    parser.add_argument("--json", action="store_true", help="JSON instead of a Markdown table")
    args = parser.parse_args(argv)

    mcp_tools = None
    if args.mcp_tools_json:
        dump = json.loads(args.mcp_tools_json.read_text(encoding="utf-8"))
        mcp_tools = dump["tools"] if isinstance(dump, dict) else dump

    tokenizer = AnthropicTokenizer(args.model) if args.tokenizer == "anthropic" else Tokenizer()
    app = AppContext(profile_name=args.profile, transport=transport)
    try:
        report = run(app, tokenizer, args.project, mcp_tools)
    except TaigaCliError as exc:
        print(f"error: {exc.format_message()}", file=sys.stderr)
        return int(exc.exit_code)
    finally:
        app.close()
    sys.stdout.write(render_json(report) if args.json else render_markdown(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
