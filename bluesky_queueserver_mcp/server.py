"""Restricted local MCP server for the Bluesky QueueServer HTTP API."""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from typing import Any

from fastmcp import FastMCP


REQUIRED_SCOPES = frozenset(
    {
        "read:status",
        "read:queue",
        "read:resources",
        "write:queue:edit",
    }
)


def create_server(get_api: Callable[[], Any]) -> FastMCP:
    """Create a local MCP server exposing only observation and plan submission."""
    mcp = FastMCP(
        name="bluesky-queueserver",
        instructions=(
            "Observe the plans, devices, status, and queue of a Bluesky "
            "QueueServer. Plans may be submitted to the back of the queue, "
            "but the queue and Run Engine cannot otherwise be controlled."
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
    def status() -> dict:
        """Return the current RE Manager status."""
        return call_api(lambda api: api.status(reload=True))

    @mcp.tool()
    def list_plans() -> dict:
        """Return allowed plans, including their argument schemas."""
        return call_api(lambda api: api.plans_allowed(reload=True))

    @mcp.tool()
    def list_devices() -> dict:
        """Return allowed devices and their properties."""
        return call_api(lambda api: api.devices_allowed(reload=True))

    @mcp.tool()
    def queue_get() -> dict:
        """Return queued items and the currently running item."""
        return call_api(lambda api: api.queue_get(reload=True))

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
        item: dict[str, Any] = {"item_type": "plan", "name": name}
        if args is not None:
            item["args"] = args
        if kwargs is not None:
            item["kwargs"] = kwargs

        return call_api(lambda api: api.item_add(item))

    return mcp


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
            "QSERVER_HTTP_API_KEY must be scoped exactly for MCP access ("
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

            api_key = os.environ.get("QSERVER_HTTP_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "QSERVER_HTTP_API_KEY is required. Use a QueueServer API key "
                    "with exactly these scopes: "
                    + ", ".join(sorted(REQUIRED_SCOPES))
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
