# Architecture

```
src/taiga_cli/
  cli.py            root click group `main`, global options (-p/--profile, --version)
  context.py        AppContext (ctx.obj): lazy config, profile and authenticated client
  config.py         profiles in config.toml (no secrets)
  credentials.py    tokens in the OS keyring, one entry per profile
  errors.py         exceptions -> single-line stderr message + exit code
  output.py         ListOutput + renderers, --fields/--json/--raw/--limit options
  api/client.py     httpx wrapper: auth header, token refresh, error mapping, pagination
  api/project_context.py  resolve status/user/sprint names to IDs (config file, else one API call)
  api/project_config.py   build .taiga-cli-config.json (`project configure export`)
  project_file.py   discover/load .taiga-cli-config.json from the cwd upwards
  api/items.py      Resource (list / get_by_ref / update) for ref-addressed items, parse_ref, tags
  api/<resource>.py one module per Taiga resource: RESOURCE, FIELDS, DEFAULT_FIELDS, normalize()
  commands/_items.py  shared filter/update options, ItemUpdate, run_update (optimistic locking)
  commands/<area>.py click groups
  skills/taiga-cli/SKILL.md   bundled agent skill
```

## Request flow

`command` → validates output options (`ListOutput.from_options`) before any request →
`AppContext.client()` loads the profile and keyring tokens → `AppContext.project_slug()` /
`project_context()` fill in the project from `.taiga-cli-config.json` when `-P` is absent and
resolve names to IDs → `api/<resource>.py` calls `TaigaClient` and returns raw API items →
`ListOutput.emit()` prints them raw (`--raw`) or passes them through the resource's
`normalize()` and prints only the selected fields.

On a 401 the client uses the refresh token once, saves the new tokens to the keyring and
retries. HTTP errors become `AuthError` (exit 3), `NotFoundError` (4) or `TaigaCliError` (1).

## Adding a command

1. Add or extend `api/<resource>.py` with `FIELDS`, `DEFAULT_FIELDS`, a `normalize(raw)`
   function and API calls returning raw items. Ref-addressed items (stories, tasks, issues,
   epics) just declare a `RESOURCE = Resource(...)`.
2. Add a click command in `commands/<area>.py`; list commands use `@list_options(...)` and
   `ListOutput`; item commands reuse `commands/_items.py` (see `story.py` / `task.py`).
   Accept names, not IDs, via `ProjectContext`. Write commands print only
   `ok: SLUG#REF` (full object with `--raw`). Register new groups in `cli.py`.
3. Add tests with a mocked transport (see [Testing](testing.md)).
4. Document it in `docs/user/commands.md` **and** in `skills/taiga-cli/SKILL.md`
   (a test fails if the skill names a command that doesn't exist).
