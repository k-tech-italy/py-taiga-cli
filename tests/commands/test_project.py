import json

import httpx

PROJECTS = [
    {"id": 1, "slug": "alpha", "name": "Alpha", "description": "first\nline", "is_private": True},
    {"id": 2, "slug": "beta", "name": "Beta", "description": "", "is_private": False},
]


def _handler(seen: list[httpx.Request], headers: dict[str, str] | None = None):
    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json=PROJECTS, headers=headers or {})

    return handler


def test_list_compact_default(invoke, logged_in) -> None:
    seen: list[httpx.Request] = []
    result = invoke(_handler(seen), "project", "list")
    assert result.exit_code == 0, result.output
    assert result.output == "alpha\tAlpha\nbeta\tBeta\n"
    assert seen[0].url.params["member"] == "7"
    assert seen[0].headers["authorization"] == "Bearer tok"


def test_list_all_drops_member_filter(invoke, logged_in) -> None:
    seen: list[httpx.Request] = []
    invoke(_handler(seen), "project", "list", "--all")
    assert "member" not in seen[0].url.params


def test_list_json_fields(invoke, logged_in) -> None:
    result = invoke(_handler([]), "project", "list", "--json", "--fields", "id,is_private")
    assert json.loads(result.output) == [
        {"id": 1, "is_private": True},
        {"id": 2, "is_private": False},
    ]


def test_list_compact_flattens_whitespace(invoke, logged_in) -> None:
    result = invoke(_handler([]), "project", "list", "--fields", "slug,description,is_private")
    assert result.output == "alpha\tfirst line\tyes\nbeta\t\tno\n"


def test_unknown_field_lists_available(invoke, logged_in) -> None:
    result = invoke(_handler([]), "project", "list", "--fields", "nope")
    assert result.exit_code == 2
    assert "available: id,slug,name" in result.output


def test_truncation_note_on_stderr(invoke, logged_in) -> None:
    result = invoke(_handler([], {"x-pagination-next": "x"}), "project", "list", "--limit", "2")
    assert result.stdout == "alpha\tAlpha\nbeta\tBeta\n"
    assert "truncated at 2" in result.stderr
