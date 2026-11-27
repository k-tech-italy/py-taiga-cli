# Output & exit codes

The output format is a stable contract.

## List commands

| Option        | Effect                                                         |
|---------------|----------------------------------------------------------------|
| *(default)*   | one item per line, fields separated by a TAB, no header        |
| `--json`      | compact JSON array of objects with only the selected fields    |
| `--fields a,b`| choose and order fields; an unknown name lists the valid ones  |
| `--raw`       | the full, unmodified Taiga API payload as compact JSON          |
| `--limit N`   | max items (default 20, max 1000)                               |

In compact output, missing values print as `-`, booleans as `yes`/`no`, and newlines inside a
value are collapsed to spaces.

When more items exist than `--limit`, a `truncated at N; …` line is printed on **stderr**, so
stdout stays parseable.

`--raw` is an escape hatch for the rare case where you need a field that `--fields` doesn't
offer. It can be tens of times larger than the default output, so agents should avoid it. It
cannot be combined with `--fields`.

## Errors and exit codes

Errors are a single `error: …` line on stderr.

| Code | Meaning                                            |
|------|----------------------------------------------------|
| 0    | success                                            |
| 1    | generic error (network, server error)              |
| 2    | usage or configuration error (bad option, unknown profile, unknown status/user/sprint name) |
| 3    | authentication (not logged in, expired, forbidden, no keyring) |
| 4    | not found                                          |
