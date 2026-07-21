"""Tests for the restricted QueueServer MCP surface."""

from __future__ import annotations

import asyncio

import pytest
from fastmcp import Client

from bluesky_queueserver_mcp.server import _build_remote_auth, create_server


EXPECTED_TOOLS = {
    "status",
    "list_plans",
    "list_devices",
    "queue_get",
    "add_plan_to_queue",
}


class FakeAPI:
    def __init__(self) -> None:
        self.added_item = None

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


def test_remote_auth_requires_a_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QSERVER_MCP_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="QSERVER_MCP_TOKEN is required"):
        _build_remote_auth()


async def test_remote_auth_accepts_only_the_configured_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QSERVER_MCP_TOKEN", "test-token")
    auth = _build_remote_auth()

    assert await auth.verify_token("test-token") is not None
    assert await auth.verify_token("wrong-token") is None
