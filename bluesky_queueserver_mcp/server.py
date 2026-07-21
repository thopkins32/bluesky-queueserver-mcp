"""Restricted MCP server for the Bluesky QueueServer HTTP API."""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from typing import Any

from fastmcp import FastMCP
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier


def create_server(get_api: Callable[[], Any], *, auth: Any = None) -> FastMCP:
    """Create an MCP server exposing only observation and plan submission."""
    mcp = FastMCP(
        name="bluesky-queueserver",
        instructions=(
            "Observe the plans, devices, status, and queue of a Bluesky "
            "QueueServer. Plans may be submitted to the back of the queue, "
            "but the queue and Run Engine cannot otherwise be controlled."
        ),
        auth=auth,
    )
    api_lock = threading.Lock()

    @mcp.tool()
    def status() -> dict:
        """Return the current RE Manager status."""
        with api_lock:
            return get_api().status(reload=True)

    @mcp.tool()
    def list_plans() -> dict:
        """Return allowed plans, including their argument schemas."""
        with api_lock:
            return get_api().plans_allowed(reload=True)

    @mcp.tool()
    def list_devices() -> dict:
        """Return allowed devices and their properties."""
        with api_lock:
            return get_api().devices_allowed(reload=True)

    @mcp.tool()
    def queue_get() -> dict:
        """Return queued items and the currently running item."""
        with api_lock:
            return get_api().queue_get(reload=True)

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

        with api_lock:
            return get_api().item_add(item)

    return mcp


def _build_get_api() -> Callable[[], Any]:
    """Build a lazy, cached HTTP RE Manager API factory from the environment."""
    api_cache: list[Any] = []
    cache_lock = threading.Lock()

    def get_api() -> Any:
        with cache_lock:
            if api_cache:
                return api_cache[0]

            from bluesky_queueserver_api.http import REManagerAPI

            api = REManagerAPI(
                http_server_uri=os.environ.get(
                    "QSERVER_HTTP_SERVER_URI", "http://localhost:60610"
                )
            )
            api_key = os.environ.get("QSERVER_HTTP_API_KEY")
            if api_key:
                api.set_authorization_key(api_key=api_key)

            user = os.environ.get("QSERVER_USER")
            if user:
                api.user = user
            api.user_group = os.environ.get("QSERVER_USER_GROUP", "primary_users")

            api_cache.append(api)
            return api

    return get_api


def _build_remote_auth() -> StaticTokenVerifier:
    """Create the required bearer-token verifier for remote transport."""
    token = os.environ.get("QSERVER_MCP_TOKEN")
    if not token:
        raise RuntimeError(
            "QSERVER_MCP_TOKEN is required when QSERVER_MCP_TRANSPORT=http"
        )
    return StaticTokenVerifier(
        tokens={
            token: {
                "client_id": "opencode",
                "scopes": ["queueserver:access"],
            }
        },
        required_scopes=["queueserver:access"],
    )


def main() -> None:
    """Run the server over stdio or authenticated Streamable HTTP."""
    transport = os.environ.get("QSERVER_MCP_TRANSPORT", "stdio").lower()
    if transport not in {"stdio", "http"}:
        raise RuntimeError("QSERVER_MCP_TRANSPORT must be 'stdio' or 'http'")

    auth = _build_remote_auth() if transport == "http" else None
    mcp = create_server(_build_get_api(), auth=auth)

    if transport == "http":
        mcp.run(
            transport="http",
            host=os.environ.get("QSERVER_MCP_HOST", "127.0.0.1"),
            port=int(os.environ.get("QSERVER_MCP_PORT", "8000")),
        )
    else:
        mcp.run(transport="stdio")
