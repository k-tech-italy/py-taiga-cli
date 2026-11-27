# AGENTS.md — taiga-cli

Instructions for AI agents (and humans) working in this repository.
This file is loaded into every agent session: keep it short, factual and current.

## Project goal

`taiga-cli` is a Python command-line client for [Taiga](https://taiga.io) (cloud and self-hosted).
Its **primary consumer is an AI agent or subagent**, so every design choice should minimise
tokens in and out while staying usable by humans.

- Runs on Linux, macOS and Windows (no POSIX-only APIs, use `pathlib`, no shell-outs).
- Talks to the Taiga REST API (`<base-url>/api/v1/`).

## Tech stack

| Concern             | Choice                                                        |
|---------------------|---------------------------------------------------------------|
| Python              | >= 3.11                                                       |
| CLI framework       | `click`                                                       |
| HTTP client         | `httpx` (sync API, shared `Client` with timeouts)             |
| Credentials         | `keyring` (OS keychain / Credential Manager / Secret Service) |
| Config location     | per-user config dir (e.g. `platformdirs`), TOML               |
| Packaging / envs    | `uv` (`pyproject.toml`, `uv.lock` committed)                  |
| Tests               | `pytest`; `tox` as the single entry point for CI              |
| Lint / format       | `ruff` (`ruff check` + `ruff format`), configured in `pyproject.toml` |
| Dev shell           | `direnv` with `.envrc` (from `.envrc.example`)                |
| Docs                | Markdown in `docs/`, published to GitHub Pages by a workflow  |

Keep runtime dependencies minimal; adding one requires a short justification in the PR.

## Repository layout

```
src/taiga_cli/        # package (src layout; .envrc adds ./src to PYTHONPATH)
  cli.py              # click entry point: `taiga-cli`
  context.py          # AppContext (ctx.obj): config, profile, authenticated client
  config.py           # profiles in config.toml (no secrets)
  credentials.py      # tokens in the keyring
  errors.py           # exceptions + exit codes
  output.py           # compact / json renderers, --fields/--json/--limit
  api/                # httpx client + one module per Taiga resource
  commands/           # one click group per area
  skills/             # bundled agent skill files (see "Agent skills")
scripts/              # dev tools, e.g. benchmark_tokens.py (taiga-mcp vs taiga-cli tokens)
tests/                # pytest; mirrors src/ structure
docs/user/            # user guide
docs/dev/             # developer guide
.github/workflows/    # CI (tox) + docs publishing
```

## Development environment

Contributors are expected to use **direnv** so the venv, `PYTHONPATH` and dev env vars are
loaded automatically on `cd`:

```bash
uv venv && uv sync          # create .venv and install dev deps
cp .envrc.example .envrc    # .envrc is git-ignored; customise locally
touch .env                  # required by .envrc (or set ENVFILE to another file)
direnv allow
```

- `.env` is for local dev settings only — never Taiga passwords or tokens (those go in the
  keyring). It is git-ignored; don't commit it.
- On Windows, use direnv from Git Bash (`.envrc` handles `.venv/Scripts`).
- Without direnv, prefix commands with `uv run`; agents should assume the env may not be
  loaded and use `uv run` explicitly.

## Common commands

```bash
uv run taiga-cli --help     # run the CLI from source
uv run pytest               # quick test run
uv run ruff check --fix .   # lint (and autofix)
uv run ruff format .        # format
uv run tox                  # full matrix: tests, lint, docs build
```

Before declaring a task done, `uv run tox` must pass.

## Configuration & credentials

- Base URL and username live in a config file in the user config dir, organised as named
  **profiles** (`--profile` / default profile).
- Secrets (password or auth/refresh token) are stored **only in the keyring**, never in the
  config file, never printed, never logged.
- `taiga-cli auth login` stores credentials; `taiga-cli auth logout` removes them;
  `taiga-cli auth status` reports without revealing secrets.
- Environment variables are **not** the primary mechanism. They may exist only as an explicit
  override for headless/CI use where no keyring backend is available, and must be documented
  as such.
- Handle expired tokens transparently via the refresh token.
- A repository may carry `.taiga-cli-config.json` (created by
  `taiga-cli project configure export`): instance URL, a credential **reference**
  (keyring service + profile name) and the project's admin settings. It is committed, so it
  must never contain secrets. Format documented in `docs/user/project-config.md`.
  It is discovered from the cwd upwards (`project_file.py`) and supplies defaults:
  precedence is always explicit option > config file > user config. Use it to resolve
  names offline, falling back to the API when a name is missing (the file may be stale).

## Output contract (token efficiency)

This is the core requirement — treat it as a public API and cover it with tests.

- Default output is **compact plain text**: one line per item, minimal fields
  (e.g. `#123 [In progress] Title @assignee`). No banners, colours, spinners or
  decorative tables when stdout is not a TTY.
- `--json` emits machine-readable JSON with **only the requested/default fields**, not the
  raw API payload. `--fields a,b,c` selects fields.
- `--raw` is the escape hatch: the unmodified API payload as compact JSON. Every list
  command supports it; it is never the default and never combined with `--fields`.
- Accept **names** (status, user, sprint) and resolve them to IDs inside the CLI
  (`api/project_context.py`); on an unknown name, fail listing the valid ones.
- List commands paginate with `--limit` (sensible default, e.g. 20) and say when results
  were truncated.
- Refer to items by project-scoped **ref** (`#123`) as in the Taiga UI, not internal IDs.
- Errors go to stderr as a single line; use distinct, documented exit codes
  (e.g. 0 ok, 1 generic, 2 usage, 3 auth, 4 not found).
- `--help` text is concise; put long explanations in `docs/`, not in help strings.
- Write commands (create/update/delete) print only the ref and a short confirmation.
  Handle Taiga's `version` (optimistic locking) internally.
  Destructive commands require `--yes` when not interactive.

## Agent skills

Ship the knowledge an agent needs to use this CLI as installable skill files, so agents
don't have to read `--help` repeatedly:

- Bundle skill sources in `src/taiga_cli/skills/` (e.g. a `SKILL.md` for Claude Code).
- `taiga-cli skill install [--target claude|agents-md|path]` writes/updates them in the chosen
  location; `taiga-cli skill show` prints them to stdout.
- Keep skills in sync with the CLI: a test should fail if a documented command no longer exists.

## Documentation

- `docs/user/`: installation, auth setup per OS, command reference, agent usage examples.
- `docs/dev/`: architecture, dev setup, testing, release process.
- A GitHub Actions workflow builds and publishes `docs/` to GitHub Pages on push to the
  default branch (static site generator: Zensical, configured in `zensical.toml`).
- Update the relevant doc in the same change that alters behaviour.

## Coding conventions

- Type hints everywhere; small, single-purpose modules.
- Code must be clean under `ruff check` and formatted with `ruff format`; don't add
  `# noqa` without a reason in the same line.
- Never hit the real Taiga API in unit tests — mock HTTP with `httpx.MockTransport`
  (no extra dependency). Optional live tests must be opt-in (marker) and skipped by default.
- No secrets, tokens or real instance URLs in tests, fixtures or docs.

## Prior art

Look at these for ideas (in order of relevance). Do **not** copy code without checking that
its license is compatible with this project's PolyForm Noncommercial 1.0.0 license.

1. https://github.com/KoukeNeko/taiga-cli
2. https://github.com/BasisTI/taiga-cli
3. https://github.com/teksimx/taiga-cli
4. https://github.com/ilhamdean/taiga-cli
5. https://github.com/paulchambaz/taiga-cli
