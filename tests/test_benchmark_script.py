"""Smoke-test scripts/benchmark_tokens.py against the fake Taiga."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import httpx
import pytest

from tests.fakes import FakeTaiga

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "benchmark_tokens.py"


@pytest.fixture(scope="module")
def bench() -> ModuleType:
    spec = importlib.util.spec_from_file_location("benchmark_tokens", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(module)
    return module


def test_markdown_report(bench, logged_in, capsys) -> None:
    taiga = FakeTaiga()
    assert bench.main(["-P", "web"], transport=httpx.MockTransport(taiga)) == 0
    out = capsys.readouterr().out
    assert out.startswith("Project `web` · tokenizer: approx (chars/4)")
    for scenario in (
        "List my projects",
        "List open user stories",
        "Stories in a status (by name)",
        "List open tasks",
        "List open issues",
        "List open epics",
        "Update a story's status (simulated)",
    ):
        assert f"| {scenario}" in out
    assert "| **Total** |" in out
    assert "taiga-mcp: not measured (pass --mcp-tools-json)" in out
    # read-only: the benchmark never writes to Taiga
    assert {r.method for r in taiga.requests} == {"GET"}


def test_json_report_and_savings(bench, logged_in, capsys, tmp_path: Path) -> None:
    tools = tmp_path / "tools.json"
    tools.write_text(json.dumps({"tools": [{"name": "taiga_x", "description": "d" * 400}]}))
    code = bench.main(
        ["-P", "web", "--json", "--mcp-tools-json", str(tools)],
        transport=httpx.MockTransport(FakeTaiga()),
    )
    assert code == 0
    report = json.loads(capsys.readouterr().out)
    results = {r["scenario"]: r for r in report["results"]}
    assert len(results) == 7
    assert all(not r["note"].startswith("skipped") for r in results.values())
    # the compact CLI output must be smaller than the pretty-printed raw payload everywhere
    for r in results.values():
        assert r["cli_tokens"] < r["mcp_tokens"], r
    # the status-filtered list costs taiga-mcp an extra lookup call; the update needs three
    assert results["Stories in a status (by name)"]["mcp_calls"] == 2
    assert results["Update a story's status (simulated)"]["mcp_calls"] == 3
    assert report["fixed"]["mcp_tool_count"] == 1
    assert report["fixed"]["mcp_tools"] > 100


def test_same_item_count_both_sides(bench, logged_in) -> None:
    taiga = FakeTaiga()
    from taiga_cli.context import AppContext

    app = AppContext(transport=httpx.MockTransport(taiga))
    report = bench.run(app, bench.Tokenizer(), "web")
    stories = next(r for r in report.results if r.scenario == "List open user stories")
    assert stories.items == len(taiga.stories)
    cli_list = [
        r
        for r in taiga.requests
        if r.url.path == "/api/v1/userstories" and "page_size" in r.url.params
    ]
    assert cli_list[0].url.params["page_size"] == str(len(taiga.stories))


def test_missing_project_is_a_clean_error(bench, logged_in, capsys) -> None:
    code = bench.main([], transport=httpx.MockTransport(FakeTaiga()))
    assert code == 2
    assert "project required" in capsys.readouterr().err
