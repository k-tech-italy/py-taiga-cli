"""``--custom NAME=VALUE``: parse assignments and convert values to the field's type."""

from __future__ import annotations

import datetime
from typing import Any

from taiga_cli.errors import UsageError

_TRUE = {"true", "yes", "y", "1", "on"}
_FALSE = {"false", "no", "n", "0", "off"}


def parse_assignments(values: tuple[str, ...]) -> dict[str, str]:
    """``("Priority=2", "Customer=ACME")`` -> ``{"Priority": "2", "Customer": "ACME"}``."""
    parsed: dict[str, str] = {}
    seen: set[str] = set()
    for value in values:
        name, sep, raw = value.partition("=")
        name = name.strip()
        if not sep or not name:
            raise UsageError(f"--custom: expected NAME=VALUE, got '{value}'")
        key = name.casefold()
        if key in seen:
            raise UsageError(f"--custom: '{name}' given more than once")
        seen.add(key)
        parsed[name] = raw
    return parsed


def convert(field: dict[str, Any], value: str) -> Any:
    """Convert a command-line string to what Taiga expects for this custom field."""
    name = field.get("name")
    kind = field.get("type") or "text"
    if kind == "checkbox":
        lowered = value.strip().casefold()
        if lowered in _TRUE:
            return True
        if lowered in _FALSE:
            return False
        raise UsageError(f"custom field '{name}': expected true/false, got '{value}'")
    if kind == "number":
        try:
            number = float(value)
        except ValueError:
            raise UsageError(f"custom field '{name}': expected a number, got '{value}'") from None
        return int(number) if number.is_integer() and "." not in value else number
    if kind == "date":
        try:
            return datetime.date.fromisoformat(value.strip()).isoformat()
        except ValueError:
            raise UsageError(
                f"custom field '{name}': expected a date YYYY-MM-DD, got '{value}'"
            ) from None
    if kind == "dropdown":
        options = [str(o) for o in field.get("extra") or []]
        for option in options:
            if option.casefold() == value.strip().casefold():
                return option
        raise UsageError(
            f"custom field '{name}': unknown option '{value}'; available: {','.join(options)}"
        )
    return value  # text, multiline, richtext, url
