# bluesky-queueserver-mcp

A deliberately restricted MCP server for the
[Bluesky QueueServer](https://github.com/bluesky/bluesky-queueserver) HTTP API.
It lets an agent observe QueueServer state and submit an allowed plan to the
back of the queue. It does not expose queue execution, item mutation, Run
Engine control, worker environment control, scripting, permissions, locks, or
the underlying `REManagerAPI`.

## Security model

Production use should run this MCP server on a trusted host using Streamable
HTTP. The QueueServer API key exists only in that host's environment. OpenCode
receives a separate MCP bearer token, which can invoke only the tools below.

The QueueServer user group remains an important second boundary. Configure
`QSERVER_USER_GROUP` so that only plans appropriate for agent submission are
allowed. This server prevents access to destructive QueueServer API methods,
but it cannot make an inherently destructive allowed plan safe.

Local stdio mode is provided for development only. It requires placing the
QueueServer API key in the local process environment and therefore does not
provide the production trust boundary.

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
execution, reorder items, or remove items.

## Configuration

| Environment variable | Default | Description |
|----------------------|---------|-------------|
| `QSERVER_HTTP_SERVER_URI` | `http://localhost:60610` | Bluesky HTTP server URI |
| `QSERVER_HTTP_API_KEY` | unset | QueueServer API key; keep on the MCP host |
| `QSERVER_USER_GROUP` | `primary_users` | QueueServer permission group |
| `QSERVER_USER` | unset | QueueServer user name |
| `QSERVER_MCP_TRANSPORT` | `stdio` | `stdio` or `http` |
| `QSERVER_MCP_HOST` | `127.0.0.1` | HTTP bind address |
| `QSERVER_MCP_PORT` | `8000` | HTTP bind port |
| `QSERVER_MCP_TOKEN` | unset | Required bearer token for HTTP transport |

HTTP mode fails to start if `QSERVER_MCP_TOKEN` is unset.

## Development

The environment is managed by Pixi through `pyproject.toml`.

```bash
pixi install
pixi run --environment test test
pixi run serve
```

`pixi run serve` starts local stdio mode. To start the remote transport:

```bash
QSERVER_HTTP_SERVER_URI=http://queueserver:60610 \
QSERVER_HTTP_API_KEY=queueserver-secret \
QSERVER_MCP_TOKEN=agent-specific-secret \
QSERVER_MCP_HOST=0.0.0.0 \
pixi run serve-http
```

The MCP endpoint is `http://HOST:8000/mcp`. Put TLS termination in front of
the service for any connection outside a trusted private network.

## OpenCode

`opencode.example.json` contains remote production and local development
configurations. The production configuration is equivalent to:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "bluesky-queueserver": {
      "type": "remote",
      "url": "https://queueserver-mcp.example.org/mcp",
      "oauth": false,
      "headers": {
        "Authorization": "Bearer {env:QSERVER_MCP_TOKEN}"
      }
    }
  }
}
```

The token in OpenCode is the restricted MCP token, never the QueueServer API
key.
