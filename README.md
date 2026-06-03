# 2FAuth-TUI

Terminal UI for 2FAuth.

## Features

- Onboarding flow for server URL, PAT, and local password
- Server availability check during setup
- PAT stored in its own file
- Local password protected unlock screen
- Optional launcher install to your `~/.local/bin/2fauth`
- Password hash stored with salted PBKDF2 and base64 encoding for the hash blob
- Live list of 2FA accounts and OTP codes

## Install

```bash
uv sync
```

## Run

```bash
uv run 2FAuth-TUI
```

If you want direct module run:

```bash
uv run python -m twofauth_tui
```

If you install the launcher during onboarding, run:

```bash
2fauth
```

You can also install or reinstall the launcher later from dashboard with `i`
or the `Install launcher` button.

## Storage

Data lives in your platform config dir, usually:

`~/.config/2FAuth-TUI/`

Files:

- `config.json` - server URL
- `pat.token` - 2FAuth Personal Access Token
- `password.json` - local password hash record

## Security note

Base64 is used only to safely store binary hash/salt bytes in JSON. It is not password protection by itself.
