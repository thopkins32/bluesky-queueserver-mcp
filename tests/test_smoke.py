"""Tests for the write-only QueueServer MCP surface."""

from __future__ import annotations

import asyncio

from fastmcp import Client

from bluesky_queueserver_mcp.server import (
    REQUIRED_SCOPES,
    _build_plan_batch,
    _validate_api_scopes,
    create_server,
)


EXPECTED_TOOLS = {
    "add_plan_to_queue",
    "add_plan_batch_to_queue",
}


class FakeAPI:
    def __init__(self, *, scopes: set[str] | None = None) -> None:
        self.added_item = None
        self.added_batch = None
        self.scopes = scopes if scopes is not None else set(REQUIRED_SCOPES)

    def api_scopes(self) -> dict:
        return {"success": True, "scopes": sorted(self.scopes)}

    def item_add(self, item: dict) -> dict:
        self.added_item = item
        return {"success": True, "item": item}

    def item_add_batch(self, items: list[dict]) -> dict:
        self.added_batch = items
        return {"success": True, "items": items}


def test_server_registers_exactly_the_write_tools() -> None:
    mcp = create_server(FakeAPI)
    tools = asyncio.run(mcp.list_tools())
    assert {tool.name for tool in tools} == EXPECTED_TOOLS


def test_tools_publish_rich_argument_metadata() -> None:
    mcp = create_server(FakeAPI)
    tools = {
        tool.name: tool.to_mcp_tool().model_dump(mode="json", exclude_none=True)
        for tool in asyncio.run(mcp.list_tools())
    }

    add_plan = tools["add_plan_to_queue"]
    assert add_plan["title"] == "Add one Bluesky plan to the QueueServer queue"
    assert add_plan["annotations"] == {
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    }
    assert add_plan["inputSchema"]["properties"]["name"] == {
        "description": (
            "QueueServer allowed plan name, for example 'count' or 'sleep'. "
            "This must be a plan from the active QueueServer allowed plans list."
        ),
        "minLength": 1,
        "type": "string",
    }
    assert "description" in add_plan["inputSchema"]["properties"]["args"]
    assert "description" in add_plan["inputSchema"]["properties"]["kwargs"]

    batch_plans = tools["add_plan_batch_to_queue"]["inputSchema"]["properties"][
        "plans"
    ]
    assert batch_plans["minItems"] == 1
    assert "raw QueueServer item dictionaries" in batch_plans["description"]
    assert batch_plans["items"]["additionalProperties"] is False
    assert batch_plans["items"]["required"] == ["name"]
    assert "description" in batch_plans["items"]["properties"]["name"]


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


async def test_add_plan_batch_only_builds_plan_items() -> None:
    api = FakeAPI()
    mcp = create_server(lambda: api)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "add_plan_batch_to_queue",
            {
                "plans": [
                    {"name": "count", "args": [["det"]], "kwargs": {"num": 5}},
                    {"name": "sleep", "args": [1]},
                ]
            },
        )

    assert not result.is_error
    assert api.added_batch == [
        {
            "item_type": "plan",
            "name": "count",
            "args": [["det"]],
            "kwargs": {"num": 5},
        },
        {"item_type": "plan", "name": "sleep", "args": [1]},
    ]


def test_batch_builder_rejects_raw_queue_items() -> None:
    try:
        _build_plan_batch(
            [{"item_type": "instruction", "name": "queue_stop"}]
        )
    except ValueError as exc:
        assert "unsupported keys" in str(exc)
    else:
        raise AssertionError("batch builder should reject raw QueueServer items")


def test_scope_validation_accepts_exact_write_scope() -> None:
    _validate_api_scopes(FakeAPI())


def test_scope_validation_rejects_missing_write_scope() -> None:
    api = FakeAPI(scopes=set())
    try:
        _validate_api_scopes(api)
    except RuntimeError as exc:
        assert "missing required scopes" in str(exc)
    else:
        raise AssertionError("scope validation should reject missing scopes")


def test_scope_validation_rejects_extra_scopes() -> None:
    api = FakeAPI(scopes=set(REQUIRED_SCOPES) | {"read:queue"})
    try:
        _validate_api_scopes(api)
    except RuntimeError as exc:
        assert "unexpected extra scopes" in str(exc)
    else:
        raise AssertionError("scope validation should reject extra scopes")
