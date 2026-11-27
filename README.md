# taiga-cli

Token-efficient command-line client for [Taiga](https://taiga.io), designed primarily to be
driven by AI agents. Works on Linux, macOS and Windows; credentials live in the OS keyring.

```bash
uv tool install taiga-cli        # or: pipx install taiga-cli
taiga-cli auth login --url https://api.taiga.io
taiga-cli project list
taiga-cli skill install          # teach your agent (Claude Code) how to use it
```

## Why a CLI instead of an MCP server?

An agent pays for every token it reads. Compared with an MCP server such as
[taiga-mcp](https://github.com/illodev/taiga-mcp), which returns Taiga's raw API payloads
pretty-printed and exposes ~236 tools, `taiga-cli` is designed to keep that bill small:

- **Compact output:** one tab-separated line per item with only the fields you ask for,
  instead of the full JSON object (avatars, nested `*_extra_info`, dates, ...).
- **Names, not IDs:** statuses, users, sprints, types and priorities are resolved by name
  inside the CLI, so the agent makes no lookup calls (none at all with a
  [`.taiga-cli-config.json`](docs/user/project-config.md)).
- **Quiet writes:** updates print `ok: web#42`; Taiga's optimistic locking is handled for you.
- **No tool catalogue in context:** the agent runs `taiga-cli` through its shell and loads a
  short [skill](docs/user/agents.md) only when needed.

Estimated tokens the agent reads (typical Taiga payloads; your numbers will vary):

| Scenario | taiga-mcp | taiga-cli |
|---|--:|--:|
| Loaded every session (tool definitions / skill) | ~20–35k ¹ | ~65, +~700 when the skill is used |
| List 15 user stories | ~20–30k | ~300–400 |
| Filter stories by status name | +1–2k (status lookup call) | +0 |
| Change a story's status | ~4k (3 calls) | ~25 (1 call) |
| *"What's in progress in Sprint 12? Mark #42 done."* | ~35–45k (≈6 calls) | ~0.5k (2 calls) |

¹ When the harness loads all MCP tool definitions upfront; harnesses that defer them (e.g.
Claude Code's tool search) pay ~3k for the tool names plus each schema they fetch.

These are estimates. Measure them on your own project with the read-only benchmark script,
which replays the same requests the way taiga-mcp renders them and runs the real CLI:

```bash
uv run python scripts/benchmark_tokens.py -P my-project
# exact Claude token counts (sends the data to Anthropic's token-counting API):
uv run --group bench python scripts/benchmark_tokens.py -P my-project --tokenizer anthropic
```

## Documentation

- User guide: [`docs/user/`](docs/user/index.md)
- Developer guide: [`docs/dev/`](docs/dev/index.md)
- Agent/contributor rules: [`AGENTS.md`](AGENTS.md)

License: PolyForm Noncommercial 1.0.0 — see [LICENSE.md](LICENSE.md).
