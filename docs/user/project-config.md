# Project config file

A repository can carry a `.taiga-cli-config.json` at its root describing the Taiga project it
belongs to: the instance URL, a **reference** to the credentials to use, and the project's
admin settings (statuses, points, priorities, custom fields, …).

The file contains **no secrets** and is meant to be committed, so every contributor — human or
AI agent — shares the same view of the project.

## How the CLI uses it

`taiga-cli` looks for the file in the current directory and then in each parent directory,
so it works from anywhere inside the repository. The closest file wins.

- **Project:** `-P SLUG` becomes optional: `taiga-cli story list`, `taiga-cli story update 42`.
- **Profile:** the profile named in `credentials.profile` is used instead of your default one.
  If you don't have it yet, run `taiga-cli auth login` from inside the repository: the profile
  name and the URL are taken from the file, you only type username and password.
- **Fewer requests:** the project id and story statuses are read from the file, so for
  example `story list --status "In progress"` needs a single API call. If a status isn't in
  the file (it may be out of date), the CLI asks the server before failing.

Command-line options always win: `-P` picks another project, `-p` another profile, and
`--no-project-config` (before the subcommand) ignores the file entirely.

As a safety check, the CLI stops with exit code 2 if the profile it would use points at a
different Taiga instance than the file's `url`, so commands never run against the wrong server.

## Creating it (project administrators)

```bash
taiga-cli project configure export https://tree.taiga.io/project/web
```

`URL` can be any page of the project in the Taiga web UI (for example the admin page you are
looking at), or the instance URL together with `-P SLUG`:

```bash
taiga-cli project configure export https://taiga.example.com -P web
```

| Option         | Effect                                                   |
|----------------|----------------------------------------------------------|
| `-P SLUG`      | project slug, when the URL doesn't contain `/project/SLUG` |
| `-o PATH`      | write elsewhere; `-o -` prints to stdout                 |
| `--force`      | overwrite an existing file                               |

You must be logged in to the instance first (`taiga-cli auth login --url …`). The profile
used is `-p NAME` if given (it must point at the same instance), otherwise the default profile
if it matches the URL, otherwise the only profile that does. Taiga Cloud URLs
(`tree.taiga.io`) are mapped to the API host (`api.taiga.io`) automatically.

Non-administrators can run the export too, but get a warning: some settings may be missing.

Re-run the command with `--force` after changing the project's settings in Taiga.

## Contents

| Key             | Source (Taiga admin page)                        |
|-----------------|--------------------------------------------------|
| `url`, `web_url`| API base URL and web UI URL of the instance       |
| `credentials`   | `{"store": "keyring", "service": "taiga-cli", "profile": NAME}` — log in with `taiga-cli -p NAME auth login` |
| `project`       | Project profile › Details: id, slug, name, description, privacy |
| `defaults`      | Project profile › Default values (`{"id", "name"}` per entry) |
| `modules`       | Project profile › Modules (epics, backlog, kanban, issues, wiki, videoconferences) |
| `statuses`      | Project values › Status (`epic`, `userstory`, `task`, `issue`) |
| `points`        | Project values › Points                          |
| `priorities`    | Project values › Priorities                      |
| `severities`    | Project values › Severities                      |
| `issue_types`   | Project values › Types                           |
| `custom_fields` | Project values › Custom fields (`epic`, `userstory`, `task`, `issue`) |
| `tags`          | Project values › Tags (`{"tag": "#color"}`)      |
| `due_dates`     | Project values › Due dates (`userstory`, `task`, `issue`) |

Lists are sorted by their order in Taiga and keep the item `id`, so tools can map names to
IDs without asking the server. Example (abridged):

```json
{
  "version": 1,
  "url": "https://api.taiga.io",
  "web_url": "https://tree.taiga.io",
  "credentials": {"store": "keyring", "service": "taiga-cli", "profile": "default"},
  "project": {"id": 5, "slug": "web", "name": "Web", "description": "The website", "is_private": true},
  "defaults": {"userstory_status": {"id": 10, "name": "New"}, "...": "..."},
  "statuses": {
    "userstory": [
      {"id": 10, "name": "New", "slug": "new", "color": "#999", "is_closed": false, "order": 1}
    ]
  },
  "tags": {"api": null, "ui": "#ffffff"}
}
```
