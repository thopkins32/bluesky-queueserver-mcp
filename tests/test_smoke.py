"""Tests for the restricted QueueServer MCP surface."""

from __future__ import annotations

import asyncio

from fastmcp import Client

from bluesky_queueserver_mcp.server import REQUIRED_SCOPES, _validate_api_scopes, create_server


EXPECTED_TOOLS = {
    "status",
    "list_plans",
    "list_devices",
    "queue_get",
    "add_plan_to_queue",
}


class FakeAPI:
    def __init__(self, *, scopes: set[str] | None = None) -> None:
        self.added_item = None
        self.scopes = scopes if scopes is not None else set(REQUIRED_SCOPES)

    def api_scopes(self) -> dict:
        return {"success": True, "scopes": sorted(self.scopes)}

    def status(self, *, reload: bool) -> dict:
        return {"success": True, "reload": reload}

    def plans_allowed(self, *, reload: bool) -> dict:
        return {"success": True, "plans_allowed": {}, "reload": reload}

    def devices_allowed(self, *, reload: bool) -> dict:
        return {"success": True, "devices_allowed": {}, "reload": reload}

    def queue_get(self, *, reload: bool) -> dict:
        return {"success": True, "items": [], "reload": reload}

    def item_add(self, item: dict) -> dict:
        self.added_item = item
        return {"success": True, "item": item}


def test_server_registers_exactly_the_restricted_tools() -> None:
    mcp = create_server(FakeAPI)
    tools = asyncio.run(mcp.list_tools())
    assert {tool.name for tool in tools} == EXPECTED_TOOLS


async def test_add_plan_only_builds_a_plan_item() -> None:
    api = FakeAPI()
    mcp = create_server(lambda: api)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "add_plan_to_queue",
            {
                "name": "count",
                "args": [["det"]],
                "kwargs": {"num": 5},
            },
        )

    assert not result.is_error
    assert api.added_item == {
        "item_type": "plan",
        "name": "count",
        "args": [["det"]],
        "kwargs": {"num": 5},
    }


def test_scope_validation_accepts_exact_scopes() -> None:
    _validate_api_scopes(FakeAPI())


def test_scope_validation_rejects_missing_scopes() -> None:
    api = FakeAPI(scopes=set(REQUIRED_SCOPES) - {"write:queue:edit"})
    try:
        _validate_api_scopes(api)
    except RuntimeError as exc:
        assert "missing required scopes" in str(exc)
    else:
        raise AssertionError("scope validation should reject missing scopes")


def test_scope_validation_rejects_extra_scopes() -> None:
    api = FakeAPI(scopes=set(REQUIRED_SCOPES) | {"write:queue:control"})
    try:
        _validate_api_scopes(api)
    except RuntimeError as exc:
        assert "unexpected extra scopes" in str(exc)
    else:
        raise AssertionError("scope validation should reject extra scopes")
