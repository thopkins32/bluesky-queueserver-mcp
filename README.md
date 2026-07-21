# bluesky-queueserver-mcp

A deliberately restricted local MCP server for the
[Bluesky QueueServer](https://github.com/bluesky/bluesky-queueserver) HTTP API.
It lets an agent observe QueueServer state and submit an allowed plan to the
back of the queue. It does not expose queue execution, item mutation, Run
Engine control, worker environment control, scripting, permissions, locks, or
the underlying `REManagerAPI`.

## Security model

This server is intended to run locally under OpenCode over stdio. It should be
configured with a **scoped QueueServer API key**, not the broad shared
single-user key used for normal operations.

The recommended workflow is:

1. Use the existing broad single-user key once to mint a long-lived API sub-key.
2. Give the sub-key exactly these scopes:
   `read:status`, `read:queue`, `read:resources`, `write:queue:edit`.
3. Configure OpenCode to launch this MCP server with that scoped sub-key.

The MCP server verifies the configured key with `api_scopes()` before making any
QueueServer request. It refuses keys that are missing required scopes or have
extra scopes. This prevents accidentally running the MCP server with the broad
shared key.

`write:queue:edit` is broader than this MCP server's tool surface: if someone
bypasses the MCP server and directly uses the scoped key, they may be able to
perform other queue-edit operations supported by the httpserver. They still
should not be able to start the queue, control the Run Engine, run scripts, or
manage the environment unless additional scopes are granted.

Operational safety still depends on a human-in-the-loop workflow: keep queue
autostart off and have a person review and start the queue.

## Tools

| Tool | Capability |
|------|------------|
| `status` | Read RE Manager status |
| `list_plans` | Read allowed plans and argument schemas |
| `list_devices` | Read allowed devices and properties |
| `queue_get` | Read queued and currently running items |
| `add_plan_to_queue` | Add one allowed plan to the back of the queue |

`add_plan_to_queue` accepts only `name`, `args`, and `kwargs`. The agent cannot
choose queue position, override user identity or group, supply lock keys, start
execution, reorder items, or remove items through the MCP server.

## Configuration

| Environment variable | Default | Description |
|----------------------|---------|-------------|
| `QSERVER_HTTP_SERVER_URI` | `http://localhost:60610` | Bluesky HTTP server URI |
| `QSERVER_HTTP_API_KEY` | required | Scoped QueueServer API key |
| `QSERVER_USER_GROUP` | `primary` | QueueServer permission group |
| `QSERVER_USER` | unset | QueueServer user name label |

## Minting the scoped key

Using the broad single-user key, request a derived key with the restricted scope
set. The exact command may vary by deployment, but with `httpie` it looks like:

```bash
http POST http://localhost:60610/api/auth/apikey \
  'Authorization: ApiKey <broad-single-user-key>' \
  expires_in:=31536000 \
  scopes:='["read:status","read:queue","read:resources","write:queue:edit"]' \
  note='OpenCode QueueServer MCP scoped key'
```

`31536000` seconds is about one year. If the key expires, the MCP server will
simply stop working until a new scoped key is configured.

## OpenCode

See `opencode.example.json` for a local MCP configuration. The key should come
from the shell environment rather than being committed to a file:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "bluesky-queueserver": {
      "type": "local",
      "command": ["pixi", "run", "serve"],
      "environment": {
        "QSERVER_HTTP_SERVER_URI": "http://localhost:60610",
        "QSERVER_HTTP_API_KEY": "{env:QSERVER_HTTP_API_KEY}",
        "QSERVER_USER_GROUP": "primary"
      }
    }
  }
}
```

## Development

The environment is managed by Pixi through `pyproject.toml`.

```bash
pixi install
pixi run --environment test test
pixi run serve
```
