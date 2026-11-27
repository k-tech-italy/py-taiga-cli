# Authentication

```bash
taiga-cli auth login --url https://api.taiga.io --username alice
```

- For Taiga Cloud use `https://api.taiga.io`; for self-hosted use your instance URL
  (a trailing `/api/v1` is accepted and stripped).
- You are prompted for the password. For non-interactive use pipe it in:
  `printf '%s\n' "$PW" | taiga-cli auth login --password-stdin`.
- The **password is never stored**. The auth and refresh tokens Taiga returns are saved in the
  OS keyring; expired tokens are refreshed automatically.

| Command                 | Effect                                              |
|-------------------------|-----------------------------------------------------|
| `taiga-cli auth login`  | log in, save profile and tokens                     |
| `taiga-cli auth status` | verify the session against the server               |
| `taiga-cli auth logout` | delete tokens from the keyring (profile is kept)    |

## Profiles

Use `-p NAME` (before the subcommand) to work with several instances or accounts:

```bash
taiga-cli -p work auth login --url https://taiga.example.com
taiga-cli -p work project list
```

Which profile is used: `-p NAME` if given, otherwise the one named in the repository's
[project config file](project-config.md), otherwise the default profile. The first profile
you log in with becomes the default. Profiles (URL, username, user id — no
secrets) are stored in `config.toml` in the per-user config directory:

| OS      | Location                                          |
|---------|---------------------------------------------------|
| Linux   | `~/.config/taiga-cli/config.toml`                 |
| macOS   | `~/Library/Application Support/taiga-cli/config.toml` |
| Windows | `%LOCALAPPDATA%\taiga-cli\config.toml`            |

## Keyring backends

| OS      | Backend                                             |
|---------|-----------------------------------------------------|
| Linux   | Secret Service (GNOME Keyring, KWallet)             |
| macOS   | Keychain                                            |
| Windows | Windows Credential Manager                          |

On a headless Linux machine without a Secret Service, the CLI exits with code 3 and a
`keyring unavailable` message. See the [keyring documentation](https://pypi.org/project/keyring/)
for alternative backends.
