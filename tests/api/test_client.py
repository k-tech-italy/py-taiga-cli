import httpx
import pytest

from taiga_cli.api.client import TaigaClient, Tokens, normalize_base_url
from taiga_cli.errors import AuthError, ConfigError, NotFoundError, TaigaCliError


@pytest.mark.parametrize(
    "url",
    [
        "https://t.example",
        "https://t.example/",
        "https://t.example/api/v1",
        " https://t.example/api/v1/ ",
    ],
)
def test_normalize_base_url(url: str) -> None:
    assert normalize_base_url(url) == "https://t.example"


def test_normalize_rejects_missing_scheme() -> None:
    with pytest.raises(ConfigError):
        normalize_base_url("t.example")


def test_login_stores_tokens() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/api/v1/auth"
        assert "authorization" not in req.headers
        return httpx.Response(200, json={"id": 1, "auth_token": "a", "refresh": "r"})

    client = TaigaClient("https://t.example", transport=httpx.MockTransport(handler))
    user = client.login("u", "p")
    assert user["id"] == 1
    assert client.tokens == Tokens("a", "r")


def test_login_bad_credentials() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"_error_message": "No active account"})

    client = TaigaClient("https://t.example", transport=httpx.MockTransport(handler))
    with pytest.raises(AuthError, match="No active account"):
        client.login("u", "p")


def test_refresh_on_401_and_persist() -> None:
    calls: list[str] = []
    saved: list[Tokens] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(f"{req.url.path} {req.headers.get('authorization')}")
        if req.url.path == "/api/v1/auth/refresh":
            return httpx.Response(200, json={"auth_token": "new", "refresh": "r2"})
        if req.headers["authorization"] == "Bearer old":
            return httpx.Response(401, json={"detail": "expired"})
        return httpx.Response(200, json={"username": "u"})

    client = TaigaClient(
        "https://t.example",
        Tokens("old", "r1"),
        on_refresh=saved.append,
        transport=httpx.MockTransport(handler),
    )
    assert client.get("/users/me") == {"username": "u"}
    assert saved == [Tokens("new", "r2")]
    assert calls == [
        "/api/v1/users/me Bearer old",
        "/api/v1/auth/refresh None",
        "/api/v1/users/me Bearer new",
    ]


def test_failed_refresh_is_auth_error() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    client = TaigaClient(
        "https://t.example", Tokens("a", "r"), transport=httpx.MockTransport(handler)
    )
    with pytest.raises(AuthError, match="session expired"):
        client.get("/users/me")


@pytest.mark.parametrize(
    ("status", "exc"), [(403, AuthError), (404, NotFoundError), (500, TaigaCliError)]
)
def test_error_mapping(status: int, exc: type[Exception]) -> None:
    client = TaigaClient(
        "https://t.example",
        Tokens("a"),
        transport=httpx.MockTransport(lambda r: httpx.Response(status, text="boom")),
    )
    with pytest.raises(exc):
        client.get("/x")


def test_transport_error() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=req)

    client = TaigaClient("https://t.example", transport=httpx.MockTransport(handler))
    with pytest.raises(TaigaCliError, match="cannot reach"):
        client.get("/x")


def test_list_page_truncation() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.params["page_size"] == "2"
        return httpx.Response(
            200, json=[{"n": 1}, {"n": 2}], headers={"x-pagination-next": "http://next"}
        )

    client = TaigaClient("https://t.example", Tokens("a"), transport=httpx.MockTransport(handler))
    items, truncated = client.list_page("/things", limit=2)
    assert items == [{"n": 1}, {"n": 2}]
    assert truncated is True
