---
name: taiga-cli
description: Read and update Taiga projects, epics, user stories, tasks and issues from the shell with the token-efficient `taiga-cli` command. Use when the user mentions Taiga, user stories, tasks, issues, epics or sprints in Taiga.
---

# taiga-cli

Output is compact: one item per line, tab-separated, no headers. Errors are one `error:` line
on stderr. Do not run `--help` unless a command below fails. Use names, not numeric IDs:
statuses, users and sprints are resolved by name (case-insensitive); an unknown name returns
the valid ones.

## Commands

- `taiga-cli auth status` — check the session (exit 3 = ask the user to run `taiga-cli auth login`).
- `taiga-cli project list` — your projects: `slug<TAB>name`.
- `taiga-cli story list -P SLUG` — open stories: `#ref<TAB>status<TAB>subject<TAB>assignee`.
  Filters: `--status "In progress,Ready"`, `--sprint NAME|backlog`, `--assignee USER|me`,
  `--tag T` (repeatable), `--state open|closed|all`.
- `taiga-cli story update SLUG#REF ...` — prints `ok: SLUG#REF`. Options: `--status NAME`,
  `--subject TEXT`, `--assignee USER|me|none`, `--sprint NAME|backlog`, `--add-tag T`,
  `--remove-tag T`, `--description TEXT|-`, `--comment TEXT|-` (`-` reads stdin).
- `taiga-cli task list -P SLUG` — open tasks: `#ref<TAB>status<TAB>subject<TAB>assignee<TAB>#story`.
  Filters: `--story REF`, `--status`, `--sprint NAME`, `--assignee`, `--tag`, `--state`.
- `taiga-cli task update SLUG#REF ...` — same options as story update except `--sprint`.
  Task statuses differ from story statuses (e.g. `Closed` vs `Done`).
- `taiga-cli issue list -P SLUG` — open issues: `#ref<TAB>status<TAB>type<TAB>priority<TAB>subject<TAB>assignee`.
  Filters: `--type`, `--priority`, `--severity`, `--status` (names, comma-separated),
  `--sprint NAME`, `--assignee`, `--tag`, `--state`.
- `taiga-cli issue update SLUG#REF ...` — story update options plus `--type`, `--priority`,
  `--severity`.
- `taiga-cli epic list -P SLUG` — open epics: `#ref<TAB>status<TAB>subject<TAB>assignee<TAB>stories`.
  Filters: `--status`, `--assignee`, `--tag`, `--state`.
- `taiga-cli epic update SLUG#REF ...` — task update options plus `--color HEX`,
  `--add-story REF` / `--remove-story REF` (repeatable, idempotent; link/unlink user stories).

Refs: write `web#42` or `42 -P web`. Never a bare `#42`: the shell treats it as a comment.

Inside a repository with `.taiga-cli-config.json` (in the cwd or a parent), `-P` is optional and
a bare `42` works; don't read the file just to find status names, an unknown name returns the
valid ones.

## Options on list commands

- `--fields a,b` choose columns (an invalid name lists the valid ones).
- `--json` JSON array with only the selected fields.
- `--raw` full Taiga API payload (large: only when a needed field is not in `--fields`).
- `--limit N` (default 20); a `truncated` note on stderr means more exist.
- `-p NAME` before the subcommand selects a config profile.

## Exit codes

0 ok · 1 error · 2 usage/unknown name · 3 auth · 4 not found
