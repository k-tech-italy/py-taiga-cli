# Development setup

Prerequisites: [uv](https://docs.astral.sh/uv/) and [direnv](https://direnv.net/)
(on Windows, use direnv from Git Bash).

```bash
uv venv && uv sync          # .venv with runtime + dev dependencies
cp .envrc.example .envrc    # git-ignored, customise freely
touch .env                  # required by .envrc (or set ENVFILE)
direnv allow
```

`.env` holds local development settings only. Never put Taiga passwords or tokens there:
they belong in the keyring via `taiga-cli auth login`.

Without direnv, prefix commands with `uv run`.

## Everyday commands

```bash
taiga-cli --help            # run the CLI from source
pytest                      # tests
ruff check --fix .          # lint
ruff format .               # format
tox                         # everything CI runs: lint, tests on 3.11-3.14, docs build
make docs-serve              # build + serve docs on localhost:$DOCS_PORT (default 8001)
```
