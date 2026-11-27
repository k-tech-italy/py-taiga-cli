"""HTTP client for the Taiga REST API (``<base-url>/api/v1``)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

from taiga_cli.errors import (
    AuthError,
    ConfigError,
    NotFoundError,
    TaigaCliError,
    VersionConflictError,
)

API_PREFIX = "/api/v1"
DEFAULT_TIMEOUT = 30.0
_MAX_DETAIL = 200


@dataclass
class Tokens:
    auth_token: str
    refresh: str | None = None


def normalize_base_url(url: str) -> str:
    """Accept ``https://host``, ``https://host/`` or ``https://host/api/v1``."""
    url = url.strip().rstrip("/")
    if url.endswith(API_PREFIX):
        url = url[: -len(API_PREFIX)]
    if not url.startswith(("http://", "https://")):
        raise ConfigError(f"invalid url '{url}': must start with http:// or https://")
    return url


def _detail(resp: httpx.Response) -> str:
    try:
        body = resp.json()
    except ValueError:
        text = resp.text
    else:
        if isinstance(body, dict):
            text = str(body.get("_error_message") or body.get("detail") or body)
        else:
            text = str(body)
    text = " ".join(text.split())
    return text[:_MAX_DETAIL]


def _is_version_conflict(resp: httpx.Response) -> bool:
    """Taiga rejects stale optimistic-concurrency updates with a 400 keyed on `version`."""
    try:
        body = resp.json()
    except ValueError:
        return False
    return isinstance(body, dict) and "version" in body


def raise_for_status(resp: httpx.Response) -> None:
    code = resp.status_code
    if code < 400:
        return
    if code in (401, 403):
        raise AuthError(f"not authorised ({code}): {_detail(resp)}")
    if code == 404:
        raise NotFoundError(f"not found: {resp.request.url.path}")
    if code == 400 and _is_version_conflict(resp):
        raise VersionConflictError(f"version conflict: {_detail(resp)}")
    raise TaigaCliError(f"HTTP {code}: {_detail(resp)}")


class TaigaClient:
    def __init__(
        self,
        base_url: str,
        tokens: Tokens | None = None,
        *,
        on_refresh: Callable[[Tokens], None] | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = normalize_base_url(base_url)
        self.tokens = tokens
        self._on_refresh = on_refresh
        self._http = httpx.Client(
            base_url=self.base_url + API_PREFIX,
            timeout=timeout,
            transport=transport,
            headers={"Accept": "application/json"},
        )

    # -- lifecycle -----------------------------------------------------------
    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> TaigaClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- low level -----------------------------------------------------------
    def _send(self, method: str, path: str, *, auth: bool = True, **kwargs: Any) -> httpx.Response:
        headers = kwargs.pop("headers", {})
        if auth and self.tokens:
            headers["Authorization"] = f"Bearer {self.tokens.auth_token}"
        try:
            return self._http.request(method, path, headers=headers, **kwargs)
        except httpx.TransportError as exc:
            raise TaigaCliError(f"cannot reach {self.base_url}: {exc}") from exc

    def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        resp = self._send(method, path, **kwargs)
        if resp.status_code == 401 and self.tokens and self.tokens.refresh:
            self._refresh()
            resp = self._send(method, path, **kwargs)
        raise_for_status(resp)
        return resp

    def get(self, path: str, **kwargs: Any) -> Any:
        return self.request("GET", path, **kwargs).json()

    def patch(self, path: str, data: dict[str, Any]) -> Any:
        return self.request("PATCH", path, json=data).json()

    def list_page(
        self, path: str, *, limit: int, params: dict[str, Any] | None = None
    ) -> tuple[list[dict[str, Any]], bool]:
        """Fetch at most ``limit`` items; return ``(items, truncated)``."""
        query = {**(params or {}), "page": 1, "page_size": limit}
        resp = self.request("GET", path, params=query)
        items = resp.json()
        truncated = bool(resp.headers.get("x-pagination-next")) or len(items) > limit
        return items[:limit], truncated

    # -- auth ----------------------------------------------------------------
    def login(self, username: str, password: str) -> dict[str, Any]:
        """Authenticate with username/password; returns the user payload."""
        resp = self._send(
            "POST",
            "/auth",
            auth=False,
            json={"type": "normal", "username": username, "password": password},
        )
        if resp.status_code == 400:
            raise AuthError(f"login failed: {_detail(resp)}")
        raise_for_status(resp)
        data = resp.json()
        self.tokens = Tokens(auth_token=data["auth_token"], refresh=data.get("refresh"))
        return data

    def _refresh(self) -> None:
        if not (self.tokens and self.tokens.refresh):
            raise AuthError("session expired; run `taiga-cli auth login`")
        resp = self._send(
            "POST", "/auth/refresh", auth=False, json={"refresh": self.tokens.refresh}
        )
        if resp.status_code >= 400:
            raise AuthError("session expired; run `taiga-cli auth login`")
        data = resp.json()
        self.tokens = Tokens(
            auth_token=data["auth_token"], refresh=data.get("refresh", self.tokens.refresh)
        )
        if self._on_refresh:
            self._on_refresh(self.tokens)
