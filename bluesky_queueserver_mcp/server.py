"""Write-only local MCP server for the Bluesky QueueServer HTTP API."""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from typing import Any

from fastmcp import FastMCP


REQUIRED_SCOPES = frozenset({"write:queue:edit"})


def create_server(get_api: Callable[[], Any]) -> FastMCP:
    """Create a local MCP server exposing only plan submission tools."""
    mcp = FastMCP(
        name="bluesky-queueserver",
        instructions=(
            "Submit Bluesky plans to the back of a QueueServer queue. "
            "Only plan items can be submitted. Queue execution, queue editing, "
            "Run Engine control, environment control, scripting, and read-only "
            "inspection are intentionally not exposed as MCP tools."
        ),
    )
    api_lock = threading.Lock()
    scopes_checked = False

    def get_validated_api() -> Any:
        nonlocal scopes_checked
        api = get_api()
        if not scopes_checked:
            _validate_api_scopes(api)
            scopes_checked = True
        return api

    def call_api(operation: Callable[[Any], dict]) -> dict:
        with api_lock:
            try:
                return operation(get_validated_api())
            except Exception as exc:
                return {"success": False, "msg": str(exc)}

    @mcp.tool()
    def add_plan_to_queue(
        name: str,
        args: list[Any] | None = None,
        kwargs: dict[str, Any] | None = None,
    ) -> dict:
        """Add one allowed plan to the back of the queue without starting it.

        Args:
            name: Name of an allowed plan.
            args: Positional plan arguments.
            kwargs: Keyword plan arguments.
        """
        try:
            item = _build_plan_item(name=name, args=args, kwargs=kwargs)
        except ValueError as exc:
            return {"success": False, "msg": str(exc)}

        return call_api(lambda api: api.item_add(item))

    @mcp.tool()
    def add_plan_batch_to_queue(plans: list[dict[str, Any]]) -> dict:
        """Add multiple allowed plans to the back of the queue without starting it.

        Each plan must be a dict with only these keys: ``name``, ``args``, and
        ``kwargs``. The server constructs QueueServer plan items and never accepts
        raw item dictionaries or instruction items.
        """
        try:
            items = _build_plan_batch(plans)
        except ValueError as exc:
            return {"success": False, "msg": str(exc)}

        return call_api(lambda api: api.item_add_batch(items))

    return mcp


def _build_plan_item(
    *,
    name: str,
    args: list[Any] | None = None,
    kwargs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a QueueServer plan item from restricted user input."""
    if not isinstance(name, str) or not name:
        raise ValueError("plan name must be a non-empty string")
    if args is not None and not isinstance(args, list):
        raise ValueError("args must be a list when provided")
    if kwargs is not None and not isinstance(kwargs, dict):
        raise ValueError("kwargs must be a dict when provided")

    item: dict[str, Any] = {"item_type": "plan", "name": name}
    if args is not None:
        item["args"] = args
    if kwargs is not None:
        item["kwargs"] = kwargs
    return item


def _build_plan_batch(plans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build QueueServer plan items from a restricted batch input."""
    if not isinstance(plans, list) or not plans:
        raise ValueError("plans must be a non-empty list")

    allowed_keys = {"name", "args", "kwargs"}
    items = []
    for index, plan in enumerate(plans):
        if not isinstance(plan, dict):
            raise ValueError(f"plans[{index}] must be a dict")
        unexpected = set(plan) - allowed_keys
        if unexpected:
            raise ValueError(
                f"plans[{index}] contains unsupported keys: {sorted(unexpected)}"
            )
        items.append(
            _build_plan_item(
                name=plan.get("name"),
                args=plan.get("args"),
                kwargs=plan.get("kwargs"),
            )
        )
    return items


def _validate_api_scopes(api: Any) -> None:
    """Refuse QueueServer credentials that are missing or over-scoped."""
    response = api.api_scopes()
    if response.get("success") is False:
        raise RuntimeError(response.get("msg") or "Failed to verify API scopes")

    scopes = response.get("scopes")
    if scopes is None:
        raise RuntimeError(f"Could not determine API scopes from response: {response!r}")

    scopes = set(scopes)
    missing = REQUIRED_SCOPES - scopes
    extra = scopes - REQUIRED_SCOPES
    if missing or extra:
        details = []
        if missing:
            details.append(f"missing required scopes: {sorted(missing)}")
        if extra:
            details.append(f"unexpected extra scopes: {sorted(extra)}")
        raise RuntimeError(
            "QSERVER_WRITE_API_KEY must be scoped exactly for MCP write access ("
            + "; ".join(details)
            + ")"
        )


def _build_get_api() -> Callable[[], Any]:
    """Build a lazy, cached HTTP RE Manager API factory from the environment."""
    api_cache: list[Any] = []
    cache_lock = threading.Lock()

    def get_api() -> Any:
        with cache_lock:
            if api_cache:
                return api_cache[0]

            api_key = os.environ.get("QSERVER_WRITE_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "QSERVER_WRITE_API_KEY is required. Use a QueueServer API key "
                    "with exactly this scope: " + ", ".join(sorted(REQUIRED_SCOPES))
                )

            from bluesky_queueserver_api.http import REManagerAPI

            api = REManagerAPI(
                http_server_uri=os.environ.get(
                    "QSERVER_HTTP_SERVER_URI", "http://localhost:60610"
                )
            )
            api.set_authorization_key(api_key=api_key)

            user = os.environ.get("QSERVER_USER")
            if user:
                api.user = user
            api.user_group = os.environ.get("QSERVER_USER_GROUP", "primary")

            api_cache.append(api)
            return api

    return get_api


def main() -> None:
    """Run the local MCP server over stdio."""
    mcp = create_server(_build_get_api())
    mcp.run(transport="stdio")
