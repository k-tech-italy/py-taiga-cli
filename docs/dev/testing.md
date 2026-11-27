# Testing

- Unit tests never touch the network or the real keyring. `tests/conftest.py` provides:
    - an in-memory keyring backend (autouse),
    - a temporary `config.toml` (autouse),
    - `invoke(handler, *args, input=...)`: runs the CLI with an `httpx.MockTransport`,
    - `logged_in`: a default profile with stored tokens.
- Tests that hit a real Taiga instance must be marked `@pytest.mark.live`; they are skipped by
  tox and CI (`-m "not live"`).

```bash
pytest                 # fast loop
tox                    # full matrix: lint, 3.11–3.14, docs
tox -e 3.13 -- -k auth # one env, extra pytest args after --
```

## Token benchmark

`scripts/benchmark_tokens.py` compares the tokens an agent reads with taiga-mcp and with
taiga-cli on a real project. It is **read-only**: the MCP side replays the same API requests
and renders them as taiga-mcp does (`JSON.stringify(data, null, 2)`); the CLI side runs the
real commands in-process.

```bash
uv run python scripts/benchmark_tokens.py -P my-project           # Markdown table
uv run python scripts/benchmark_tokens.py -P my-project --json    # machine-readable
uv run --group bench python scripts/benchmark_tokens.py -P my-project --tokenizer anthropic
```

- `--tokenizer approx` (default) estimates 4 characters per token, offline.
- `--tokenizer anthropic` uses the Anthropic token-counting API for exact Claude counts
  (`--model`, default `claude-opus-5-5`). It sends the Taiga data to Anthropic and needs
  credentials (`ANTHROPIC_API_KEY` or `ant auth login`).
- `--mcp-tools-json FILE` adds taiga-mcp's per-session tool-definition cost, from a
  `tools/list` dump, e.g.
  `npx @modelcontextprotocol/inspector --cli node taiga-mcp/dist/index.js --method tools/list`.

It is covered by `tests/test_benchmark_script.py` against the fake Taiga.

CI (`.github/workflows/ci.yml`) runs tox on Linux, macOS and Windows. Docs are deployed to
GitHub Pages by `.github/workflows/docs.yml` on pushes to `main`.
