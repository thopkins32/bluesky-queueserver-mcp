# bluesky-queueserver-mcp

A deliberately restricted local MCP server for the
[Bluesky QueueServer](https://github.com/bluesky/bluesky-queueserver) HTTP API.
It exposes only write operations that add Bluesky plans to the back of the
queue. Read-only inspection is intentionally handled outside MCP by an OpenCode
Skill that uses a separate read-only QueueServer API key and the Python
`REManagerAPI`.

## Security model

Use two QueueServer API sub-keys for the shared beamline account:

| Key | Intended use | Scopes |
|-----|--------------|--------|
| `QSERVER_READ_API_KEY` | OpenCode Skill + Python `REManagerAPI` reads | `read:status`, `read:queue`, `read:resources` |
| `QSERVER_WRITE_API_KEY` | This MCP server only | `write:queue:edit` |

Do not give OpenCode the broad shared single-user key. The MCP server verifies
`QSERVER_WRITE_API_KEY` with `api_scopes()` before making any QueueServer
request and refuses keys that are missing `write:queue:edit` or have extra
scopes.

`write:queue:edit` is broader than this MCP server's tool surface: if someone
bypasses the MCP server and directly uses the write key, they may be able to
perform other queue-edit operations supported by the httpserver. They still
should not be able to start the queue, control the Run Engine, run scripts, or
manage the environment unless additional scopes are granted.

Operational safety still depends on a human-in-the-loop workflow: keep queue
autostart off and have a person review and start the queue.

## MCP tools

The MCP server exposes exactly two tools:

| Tool | Capability |
|------|------------|
| `add_plan_to_queue` | Add one allowed plan to the back of the queue |
| `add_plan_batch_to_queue` | Add multiple allowed plans to the back of the queue |

Both tools accept only plan-shaped input. The server constructs QueueServer
items itself with `item_type: "plan"`; raw QueueServer item dictionaries and
instruction items such as `queue_stop` are not accepted.

There are no MCP read tools and no queue start/stop, remove, move, update,
clear, environment, Run Engine, scripting, permission, lock, or manager-control
tools.

## Configuration

| Environment variable | Default | Description |
|----------------------|---------|-------------|
| `QSERVER_HTTP_SERVER_URI` | `http://localhost:60610` | Bluesky HTTP server URI |
| `QSERVER_WRITE_API_KEY` | required | Scoped QueueServer write key for MCP |
| `QSERVER_READ_API_KEY` | required for read Skill | Scoped QueueServer read key for Python reads |
| `QSERVER_USER_GROUP` | `primary` | QueueServer permission group |
| `QSERVER_USER` | unset | QueueServer user name label |

`QSERVER_READ_API_KEY` should be exported in the shell that launches OpenCode so
the read Skill can use it. `QSERVER_WRITE_API_KEY` is passed to the MCP server in
the OpenCode MCP configuration.

## Minting scoped keys

Using the broad single-user key, request derived keys with restricted scopes.
The exact command may vary by deployment, but with `httpie` it looks like:

```bash
http POST http://localhost:60610/api/auth/apikey \
  'Authorization: ApiKey <broad-single-user-key>' \
  expires_in:=31536000 \
  scopes:='["read:status","read:queue","read:resources"]' \
  note='OpenCode QueueServer read key'
```

```bash
http POST http://localhost:60610/api/auth/apikey \
  'Authorization: ApiKey <broad-single-user-key>' \
  expires_in:=31536000 \
  scopes:='["write:queue:edit"]' \
  note='OpenCode QueueServer MCP write key'
```

`31536000` seconds is about one year. If a key expires, the respective read or
write operation simply stops working until a new scoped key is configured.

## OpenCode

See `opencode.example.json` for a local MCP configuration. The write key should
come from the shell environment rather than being committed to a file:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "bluesky-queueserver": {
      "type": "local",
      "command": ["pixi", "run", "serve"],
      "environment": {
        "QSERVER_HTTP_SERVER_URI": "http://localhost:60610",
        "QSERVER_WRITE_API_KEY": "{env:QSERVER_WRITE_API_KEY}",
        "QSERVER_USER_GROUP": "primary"
      }
    }
  }
}
```

The project includes `.opencode/skills/bluesky-queueserver-read/SKILL.md` for
read-only QueueServer inspection using `QSERVER_READ_API_KEY` and the Python
`REManagerAPI`. Restart OpenCode after adding or changing Skills or MCP config.

## OpenCode plugin

The project includes `.opencode/plugins/mcp-tool-args-panel.tsx`, an OpenCode
TUI plugin that displays the arguments of any pending `bluesky-queueserver` MCP
tool call at the bottom of the terminal while OpenCode is waiting for permission
to proceed. The panel shows the tool name and the full JSON argument payload,
scrollable with Page Up / Page Down, and disappears once the permission request
is answered.

The plugin is auto-loaded from `.opencode/plugins/` — no extra config entry is
needed.

## Development

The environment is managed by Pixi through `pyproject.toml`.

```bash
pixi install
pixi run --environment test test
pixi run serve
```
