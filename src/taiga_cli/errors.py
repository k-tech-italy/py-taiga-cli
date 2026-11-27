"""Exceptions and exit codes.

Exit codes are part of the public contract (see docs/user/output.md).
"""

from enum import IntEnum

import click


class ExitCode(IntEnum):
    OK = 0
    GENERIC = 1
    USAGE = 2  # click's own usage errors already use 2
    AUTH = 3
    NOT_FOUND = 4


class TaigaCliError(click.ClickException):
    """Base error: printed as a single `error: ...` line on stderr."""

    exit_code = ExitCode.GENERIC

    def show(self, file=None) -> None:
        click.echo(f"error: {self.format_message()}", err=True)


class UsageError(TaigaCliError):
    """Bad option value (single-line, unlike click's multi-line usage errors)."""

    exit_code = ExitCode.USAGE


class ConfigError(UsageError):
    pass


class AuthError(TaigaCliError):
    exit_code = ExitCode.AUTH


class NotFoundError(TaigaCliError):
    exit_code = ExitCode.NOT_FOUND


class VersionConflictError(TaigaCliError):
    """The item changed on the server since it was read."""
