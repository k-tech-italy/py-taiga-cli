# Commands

Global options go **before** the subcommand:
`taiga-cli [-p PROFILE] [--no-project-config] <group> <command>`.

Inside a repository with a [project config file](project-config.md), `-P SLUG` is optional
and the profile comes from the file.

Every list command also accepts `--fields`, `--json`, `--raw` and `--limit`; see
[Output & exit codes](output.md).

## auth

See [Authentication](authentication.md).

## project

| Command                  | Description                                          |
|--------------------------|------------------------------------------------------|
| `taiga-cli project list` | projects you are a member of (`--all` for every visible project) |

Fields: `id`, `slug`, `name`, `description`, `is_private` (default `slug,name`).

| Command                                       | Description                              |
|-----------------------------------------------|------------------------------------------|
| `taiga-cli project configure export URL`      | write `.taiga-cli-config.json` from the project's admin settings; see [Project config file](project-config.md) |

## story

### Referring to stories

Stories are identified by their project-scoped ref, as shown in the Taiga UI:
`web#42`, or `42` together with `-P web`, or just `42` inside a repository with a
[project config file](project-config.md).

!!! warning
    Don't pass a bare `#42`: in most shells `#` starts a comment and the argument is lost.
    `web#42` is safe because `#` is not at the start of a word.

Statuses, users and sprints are given **by name** (case-insensitive; slugs also work) and
resolved with a single request per command. An unknown name fails with exit code 2 and lists
the valid names.

### `taiga-cli story list [-P SLUG]`

| Option                     | Effect                                                    |
|----------------------------|-----------------------------------------------------------|
| `--status "A,B"`           | stories in any of these statuses                          |
| `--sprint NAME`            | stories in a sprint; `backlog` = not in any sprint        |
| `--assignee USER`          | username or full name; `me` = you                         |
| `--tag T`                  | has tag `T` (repeatable)                                  |
| `--state open\|closed\|all`| default `open`                                            |

Fields: `ref`, `subject`, `status`, `assignee`, `sprint`, `points`, `tags`, `closed`,
`blocked`, `due`, `modified`, `epics`, `description`, `id`
(default `ref,status,subject,assignee`). `description` is usually empty in lists because
Taiga's list endpoint doesn't return it.

```console
$ taiga-cli story list -P web --sprint "Sprint 12" --status "In progress"
#42	In progress	Login page	alice
#57	In progress	Password reset	-
```

### `taiga-cli story update REF`

| Option                        | Effect                                           |
|-------------------------------|--------------------------------------------------|
| `--status NAME`               | change status                                    |
| `--subject TEXT`              | change title                                     |
| `--assignee USER`             | username, full name, `me`, or `none` to unassign |
| `--sprint NAME`               | move to a sprint; `backlog` removes it from its sprint |
| `--add-tag T` / `--remove-tag T` | edit tags (repeatable)                        |
| `--description TEXT`          | replace the description; `-` reads stdin         |
| `--comment TEXT`              | add a comment; `-` reads stdin                   |
| `--raw`                       | print the full updated story as JSON             |

Prints `ok: web#42`. Taiga's optimistic locking is handled for you: the story is re-read and
the update retried once if someone changed it in the meantime.

## task

Tasks use the same refs, name resolution and output options as stories. Statuses are the
project's **task** statuses (e.g. `Closed` rather than `Done`).

### `taiga-cli task list [-P SLUG]`

| Option                     | Effect                                                    |
|----------------------------|-----------------------------------------------------------|
| `--story REF`              | tasks of a user story (`42` or `web#42`)                   |
| `--status "A,B"`           | tasks in any of these statuses                            |
| `--sprint NAME`            | tasks in a sprint                                         |
| `--assignee USER`          | username or full name; `me` = you                         |
| `--tag T`                  | has tag `T` (repeatable)                                  |
| `--state open\|closed\|all`| default `open`                                            |

Fields: `ref`, `subject`, `status`, `assignee`, `story`, `sprint`, `tags`, `closed`,
`blocked`, `due`, `modified`, `description`, `id` (default `ref,status,subject,assignee,story`).

```console
$ taiga-cli task list --story web#42
#43	In progress	Build the form	bob	#42
#44	New	Write tests	-	#42
```

### `taiga-cli task update REF`

Same options as `story update` except `--sprint` (a task follows its story's sprint):
`--status`, `--subject`, `--assignee`, `--add-tag`, `--remove-tag`, `--description`,
`--comment`, `--raw`. Prints `ok: web#43`.

## issue

Issues use the same refs, name resolution and output options as stories, with their own
statuses plus **type**, **priority** and **severity**, all given by name.

### `taiga-cli issue list [-P SLUG]`

| Option                       | Effect                                                  |
|------------------------------|---------------------------------------------------------|
| `--status "A,B"`             | issues in any of these statuses                         |
| `--type "A,B"`               | issue type(s), e.g. `Bug`                               |
| `--priority "A,B"`           | priority(ies)                                           |
| `--severity "A,B"`           | severity(ies)                                           |
| `--sprint NAME`              | issues attached to a sprint                             |
| `--assignee USER`            | username or full name; `me` = you                       |
| `--tag T`                    | has tag `T` (repeatable)                                |
| `--state open\|closed\|all`  | default `open`                                          |

Fields: `ref`, `subject`, `status`, `type`, `priority`, `severity`, `assignee`, `tags`,
`closed`, `blocked`, `due`, `modified`, `description`, `id`
(default `ref,status,type,priority,subject,assignee`).

Taiga returns only the ids of type, priority and severity; the CLI shows their names, taken
from the [project config file](project-config.md) when it has them, otherwise with one
extra request. Leave these columns out with `--fields` and no extra request is made.

```console
$ taiga-cli issue list --type Bug --priority High
#7	Open	Bug	High	Crash on login	alice
```

### `taiga-cli issue update REF`

Same options as `story update` (including `--sprint NAME|backlog`) plus `--type`,
`--priority` and `--severity`. Prints `ok: web#7`.

## epic

Epics use the same refs, name resolution and output options as stories, with the project's
**epic** statuses. They have no sprint.

### `taiga-cli epic list [-P SLUG]`

Filters: `--status "A,B"`, `--assignee USER|me`, `--tag T`, `--state open|closed|all`
(default `open`).

Fields: `ref`, `subject`, `status`, `assignee`, `stories` (number of linked user stories),
`color`, `tags`, `closed`, `blocked`, `modified`, `description`, `id`
(default `ref,status,subject,assignee,stories`).

```console
$ taiga-cli epic list
#3	Ready	Self-service onboarding	alice	5
```

### `taiga-cli epic update REF`

Same options as `task update` plus:

| Option               | Effect                                                         |
|----------------------|----------------------------------------------------------------|
| `--color HEX`        | epic color, e.g. `#ff8800`                                     |
| `--add-story REF`    | link a user story (repeatable); `42`, `web#42`, or `api#7` for a story in another project |
| `--remove-story REF` | unlink a user story (repeatable)                               |

Prints `ok: web#3`.

Linking is idempotent: stories already linked (or already unlinked) are skipped, so the
command can be safely re-run. All story refs are checked before anything is changed, so a
typo never leaves a half-applied update. With only `--add-story`/`--remove-story`, the epic
itself is not modified.

```console
$ taiga-cli epic update web#3 --add-story 42 --add-story 43 --remove-story 17
ok: web#3
```

## skill

| Command                    | Description                                              |
|----------------------------|----------------------------------------------------------|
| `taiga-cli skill show`     | print the bundled agent skill                            |
| `taiga-cli skill install`  | install it for an agent; see [Using with AI agents](agents.md) |
