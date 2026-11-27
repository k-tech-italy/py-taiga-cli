"""Token storage in the OS keyring, one entry per profile."""

from __future__ import annotations

import json

import keyring
from keyring.errors import KeyringError, PasswordDeleteError

from taiga_cli import APP_NAME
from taiga_cli.api.client import Tokens
from taiga_cli.errors import AuthError


def _keyring_error(exc: Exception) -> AuthError:
    return AuthError(f"keyring unavailable ({type(exc).__name__}: {exc})")


def load_tokens(profile: str) -> Tokens | None:
    try:
        raw = keyring.get_password(APP_NAME, profile)
    except KeyringError as exc:
        raise _keyring_error(exc) from exc
    if not raw:
        return None
    data = json.loads(raw)
    return Tokens(auth_token=data["auth_token"], refresh=data.get("refresh"))


def save_tokens(profile: str, tokens: Tokens) -> None:
    payload = json.dumps({"auth_token": tokens.auth_token, "refresh": tokens.refresh})
    try:
        keyring.set_password(APP_NAME, profile, payload)
    except KeyringError as exc:
        raise _keyring_error(exc) from exc


def delete_tokens(profile: str) -> bool:
    try:
        keyring.delete_password(APP_NAME, profile)
    except PasswordDeleteError:
        return False
    except KeyringError as exc:
        raise _keyring_error(exc) from exc
    return True
