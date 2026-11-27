# Using with AI agents

`taiga-cli` ships a short skill file that tells an agent which commands exist and how to read
their output, so it doesn't need to explore `--help`.

```bash
taiga-cli skill show                       # print it
taiga-cli skill install                    # ./.claude/skills/taiga-cli/SKILL.md (Claude Code, this project)
taiga-cli skill install --global           # ~/.claude/skills/taiga-cli/SKILL.md (all projects)
taiga-cli skill install --target agents-md # managed block in ./AGENTS.md (Codex, Cursor, ...)
taiga-cli skill install --dest PATH        # custom location
```

Re-run `install` after upgrading `taiga-cli` to refresh the skill. The `agents-md` target
only rewrites the block between `<!-- taiga-cli:begin -->` and `<!-- taiga-cli:end -->`.

## Tips

- Log in once interactively (`taiga-cli auth login`); the agent then reuses the keyring tokens.
- Ask for only the fields you need: `--fields slug`.
- Prefer compact output over `--json` unless you need to parse nested values.
