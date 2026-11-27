"""Token-efficient command-line client for Taiga."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("taiga-cli")
except PackageNotFoundError:  # pragma: no cover - running from a source tree without install
    __version__ = "0.0.0"

APP_NAME = "taiga-cli"
