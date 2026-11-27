"""A tiny in-memory Taiga API used by command tests."""

from __future__ import annotations

import json
from typing import Any

import httpx

PROJECT = {
    "id": 5,
    "slug": "web",
    "us_statuses": [
        {"id": 10, "name": "New", "slug": "new", "is_closed": False},
        {"id": 11, "name": "In progress", "slug": "in-progress", "is_closed": False},
        {"id": 12, "name": "Done", "slug": "done", "is_closed": True},
    ],
    "task_statuses": [
        {"id": 20, "name": "New", "slug": "new", "is_closed": False},
        {"id": 21, "name": "In progress", "slug": "in-progress", "is_closed": False},
        {"id": 22, "name": "Closed", "slug": "closed", "is_closed": True},
    ],
    "issue_statuses": [
        {"id": 40, "name": "Open", "slug": "open", "is_closed": False},
        {"id": 41, "name": "Closed", "slug": "closed", "is_closed": True},
    ],
    "epic_statuses": [
        {"id": 80, "name": "New", "slug": "new", "is_closed": False},
        {"id": 81, "name": "Ready", "slug": "ready", "is_closed": False},
        {"id": 82, "name": "Done", "slug": "done", "is_closed": True},
    ],
    "issue_types": [{"id": 50, "name": "Bug"}, {"id": 51, "name": "Enhancement"}],
    "priorities": [{"id": 60, "name": "Low"}, {"id": 61, "name": "High"}],
    "severities": [{"id": 70, "name": "Minor"}, {"id": 71, "name": "Critical"}],
    "userstory_custom_attributes": [
        {"id": 90, "name": "Priority", "type": "number"},
        {"id": 91, "name": "Customer", "type": "dropdown", "extra": ["ACME", "Globex"]},
        {"id": 92, "name": "Billable", "type": "checkbox"},
        {"id": 93, "name": "Due", "type": "date"},
    ],
    "task_custom_attributes": [{"id": 95, "name": "Estimate", "type": "number"}],
    "issue_custom_attributes": [{"id": 96, "name": "Browser", "type": "text"}],
    "epic_custom_attributes": [
        {"id": 97, "name": "Quarter", "type": "dropdown", "extra": ["Q1", "Q2", "Q3", "Q4"]}
    ],
    "members": [
        {"id": 7, "username": "alice", "full_name": "Alice A", "full_name_display": "Alice A"},
        {"id": 8, "username": "bob", "full_name": "Bob B", "full_name_display": "Bob B"},
    ],
    "milestones": [
        {"id": 30, "name": "Sprint 12", "slug": "sprint-12", "closed": False},
    ],
}


def story(ref: int, **extra: Any) -> dict[str, Any]:
    base = {
        "id": 100 + ref,
        "ref": ref,
        "version": 3,
        "subject": f"Story {ref}",
        "status_extra_info": {"name": "In progress", "is_closed": False},
        "assigned_to_extra_info": {"username": "alice", "photo": "https://x/y.png"},
        "milestone_name": "Sprint 12",
        "tags": [["api", None], ["ui", "#fff"]],
        "total_points": 3.0,
        "is_closed": False,
        "is_blocked": False,
        "epics": [{"ref": 2, "subject": "Epic"}],
        "owner_extra_info": {"big_photo": "https://x/z.png"},
    }
    base.update(extra)
    return base


def task(ref: int, **extra: Any) -> dict[str, Any]:
    base = {
        "id": 200 + ref,
        "ref": ref,
        "version": 5,
        "subject": f"Task {ref}",
        "status_extra_info": {"name": "In progress", "is_closed": False},
        "assigned_to_extra_info": {"username": "bob"},
        "user_story": 101,
        "user_story_extra_info": {"id": 101, "ref": 1, "subject": "Story 1"},
        "milestone_slug": "sprint-12",
        "tags": ["backend"],
        "is_closed": False,
        "is_blocked": False,
    }
    base.update(extra)
    return base


def issue(ref: int, **extra: Any) -> dict[str, Any]:
    base = {
        "id": 300 + ref,
        "ref": ref,
        "version": 2,
        "subject": f"Issue {ref}",
        "status": 40,
        "status_extra_info": {"name": "Open", "is_closed": False},
        "type": 50,
        "priority": 61,
        "severity": 71,
        "assigned_to_extra_info": None,
        "tags": [],
        "is_closed": False,
        "is_blocked": False,
    }
    base.update(extra)
    return base


def epic(ref: int, **extra: Any) -> dict[str, Any]:
    base = {
        "id": 400 + ref,
        "ref": ref,
        "version": 4,
        "subject": f"Epic {ref}",
        "status_extra_info": {"name": "Ready", "is_closed": False},
        "assigned_to_extra_info": {"username": "alice"},
        "color": "#aabbcc",
        "user_stories_counts": {"total": 5, "progress": 2},
        "tags": [],
        "is_closed": False,
        "is_blocked": False,
    }
    base.update(extra)
    return base


class FakeTaiga:
    """Minimal routing fake recording every request."""

    def __init__(self, project: dict[str, Any] | None = None) -> None:
        self.project = project or PROJECT
        self.requests: list[httpx.Request] = []
        self.other_projects: dict[str, dict[str, Any]] = {}  # slug -> project payload
        self.stories = [story(1), story(2, assigned_to_extra_info=None, tags=[])]
        self.tasks = [task(11), task(12, user_story=None, user_story_extra_info=None)]
        self.issues = [issue(7), issue(8, type=51, priority=None, severity=70)]
        self.epics = [epic(3), epic(4, user_stories_counts=None, assigned_to_extra_info=None)]
        # epic id -> linked user story ids
        self.epic_links: dict[int, list[int]] = {403: [102]}
        self.patch_responses: list[httpx.Response] = []
        # (method, path without /api/v1) -> canned response, to simulate failures
        self.failures: dict[tuple[str, str], httpx.Response] = {}
        self.next_ref = 100  # refs are shared by every item type of a project, as in Taiga
        # ".../custom-attributes-values/<id>" -> {"attributes_values": {...}, "version": n}
        self.custom_values: dict[str, dict[str, Any]] = {}

    def last(self, method: str, path: str) -> httpx.Request:
        return [r for r in self.requests if r.method == method and r.url.path == path][-1]

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.requests.append(req)
        path = req.url.path.removeprefix("/api/v1")
        if (req.method, path) in self.failures:
            return self.failures[(req.method, path)]
        if "/custom-attributes-values/" in path:
            return self._custom_values(req, path)
        if path == "/projects/by_slug":
            projects = {self.project["slug"]: self.project, **self.other_projects}
            found = projects.get(req.url.params["slug"])
            if found is None:
                return httpx.Response(404, json={"_error_message": "No Project matches"})
            return httpx.Response(200, json=found)
        if path == "/projects" and req.method == "GET":
            return httpx.Response(200, json=[self.project])
        statuses = {
            "/userstory-statuses": "us_statuses",
            "/task-statuses": "task_statuses",
            "/issue-statuses": "issue_statuses",
            "/epic-statuses": "epic_statuses",
        }
        if path in statuses:
            return httpx.Response(200, json=self.project.get(statuses[path], []))
        if path == "/milestones":
            return httpx.Response(200, json=[{"id": 31, "name": "Sprint 13", "slug": "sprint-13"}])
        if path == "/users/me":
            return httpx.Response(200, json={"id": 7, "username": "alice"})
        if path.startswith("/epics/") and "/related_userstories" in path:
            return self._epic_links(req, path)
        for prefix, items, make in (
            ("/userstories", self.stories, story),
            ("/tasks", self.tasks, task),
            ("/issues", self.issues, issue),
            ("/epics", self.epics, epic),
        ):
            if path == prefix and req.method == "GET":
                return httpx.Response(200, json=items)
            if path == prefix and req.method == "POST":
                return self._create(json.loads(req.content), items, make, prefix)
            if path == f"{prefix}/by_ref":
                ref = int(req.url.params["ref"])
                found = [i for i in items if i["ref"] == ref]
                if not found:
                    return httpx.Response(404, json={"detail": "Not found."})
                return httpx.Response(200, json=found[0])
            if path.startswith(f"{prefix}/") and req.method == "PATCH":
                if self.patch_responses:
                    return self.patch_responses.pop(0)
                item_id = int(path.rsplit("/", 1)[1])
                current = next(i for i in items if i["id"] == item_id)
                return httpx.Response(200, json=make(current["ref"], **json.loads(req.content)))
        return httpx.Response(500, json={"detail": f"unexpected {req.method} {path}"})

    def _epic_links(self, req: httpx.Request, path: str) -> httpx.Response:
        parts = path.strip("/").split("/")  # epics/<id>/related_userstories[/<us id>]
        links = self.epic_links.setdefault(int(parts[1]), [])
        if req.method == "GET":
            return httpx.Response(
                200, json=[{"epic": int(parts[1]), "user_story": us} for us in links]
            )
        if req.method == "POST":
            body = json.loads(req.content)
            assert body["epic"] == int(parts[1])
            if body["user_story"] in links:
                return httpx.Response(400, json={"_error_message": "already related"})
            links.append(body["user_story"])
            return httpx.Response(201, json=body)
        if req.method == "DELETE":
            links.remove(int(parts[3]))
            return httpx.Response(204)
        return httpx.Response(405)

    def _create(self, body: dict[str, Any], items: list, make: Any, prefix: str) -> httpx.Response:
        assert body.pop("project") == self.project["id"]
        ref, self.next_ref = self.next_ref, self.next_ref + 1
        statuses = {
            "/userstories": "us_statuses",
            "/tasks": "task_statuses",
            "/issues": "issue_statuses",
            "/epics": "epic_statuses",
        }[prefix]
        status = next((s for s in self.project[statuses] if s["id"] == body.get("status")), None)
        member = next(
            (m for m in self.project["members"] if m["id"] == body.get("assigned_to")), None
        )
        extra: dict[str, Any] = {
            "status_extra_info": {"name": status["name"]} if status else None,
            "assigned_to_extra_info": {"username": member["username"]} if member else None,
            "tags": body.get("tags", []),
            "version": 1,
        }
        if prefix == "/tasks":
            parent = next((s for s in self.stories if s["id"] == body.get("user_story")), None)
            extra["user_story_extra_info"] = {"ref": parent["ref"]} if parent else None
        if prefix == "/userstories":
            extra["epics"] = []
        item = make(ref, **{**extra, **body})
        items.append(item)
        return httpx.Response(201, json=item)

    def _custom_values(self, req: httpx.Request, path: str) -> httpx.Response:
        current = self.custom_values.setdefault(path, {"attributes_values": {}, "version": 1})
        if req.method == "GET":
            return httpx.Response(200, json=current)
        if req.method == "PATCH":
            body = json.loads(req.content)
            if body["version"] != current["version"]:
                return httpx.Response(400, json={"version": "doesn't match"})
            current["attributes_values"] = body["attributes_values"]
            current["version"] += 1
            return httpx.Response(200, json=current)
        return httpx.Response(405)
