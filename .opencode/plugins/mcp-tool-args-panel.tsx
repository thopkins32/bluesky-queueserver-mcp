/** @jsxImportSource @opentui/solid */
import type { ToolPart } from "@opencode-ai/sdk/v2"
import type { TuiPlugin, TuiPluginModule } from "@opencode-ai/plugin/tui"
import type { ScrollBoxRenderable } from "@opentui/core"
import { useTerminalDimensions } from "@opentui/solid"
import { createMemo, createSignal, Show } from "solid-js"

const toolPrefix = "bluesky-queueserver"

type Active = {
  requestID: string
  sessionID: string
  callID: string
  tool: string
  args: Record<string, unknown>
}

function isToolPart(value: unknown): value is ToolPart {
  return typeof value === "object" && value !== null && "type" in value && value.type === "tool"
}

function format(value: unknown) {
  try {
    return JSON.stringify(value, null, 2) ?? "{}"
  } catch {
    return String(value)
  }
}

const tui: TuiPlugin = async (api) => {
  const [active, setActive] = createSignal<Active>()
  let scroll: ScrollBoxRenderable | undefined

  api.event.on("permission.asked", (event) => {
    const request = event.properties
    if (!request.tool || !request.permission.startsWith(toolPrefix)) return

    const part = api
      .state
      .part(request.tool.messageID)
      .find((item) => isToolPart(item) && item.callID === request.tool?.callID)

    if (!part) return
    setActive({
      requestID: request.id,
      sessionID: request.sessionID,
      callID: request.tool.callID,
      tool: part.tool,
      args: part.state.input,
    })
  })

  api.event.on("permission.replied", (event) => {
    const current = active()
    if (!current) return
    if (event.properties.sessionID !== current.sessionID || event.properties.requestID !== current.requestID) return
    setActive(undefined)
  })

  api.keymap.registerLayer({
    enabled: () => active() !== undefined,
    commands: [
      { name: "mcp.args.pageUp", title: "Page MCP args up", run: () => scroll?.scrollBy(-(scroll?.height ?? 8)) },
      { name: "mcp.args.pageDown", title: "Page MCP args down", run: () => scroll?.scrollBy(scroll?.height ?? 8) },
    ],
    bindings: [
      { key: "pageup", cmd: "mcp.args.pageUp", desc: "Page MCP args up" },
      { key: "pagedown", cmd: "mcp.args.pageDown", desc: "Page MCP args down" },
    ],
  })

  api.slots.register({
    slots: {
      app_bottom() {
        const size = useTerminalDimensions()
        const height = createMemo(() => Math.max(4, Math.min(12, Math.floor(size().height / 3))))
        const args = createMemo(() => format(active()?.args ?? {}))

        return (
          <Show when={active()}>
            {(item) => (
              <box
                flexDirection="column"
                flexShrink={0}
                border={["top"]}
                borderColor={api.theme.current.warning}
                backgroundColor={api.theme.current.backgroundPanel}
                paddingLeft={1}
                paddingRight={1}
              >
                <box flexDirection="row" justifyContent="space-between" flexShrink={0}>
                  <text fg={api.theme.current.warning}>MCP tool args</text>
                  <text fg={api.theme.current.textMuted} truncate>
                    {item().tool}
                  </text>
                </box>
                <scrollbox ref={(value: ScrollBoxRenderable) => (scroll = value)} height={height()}>
                  <text fg={api.theme.current.text} wrapMode="word">
                    {args()}
                  </text>
                </scrollbox>
              </box>
            )}
          </Show>
        )
      },
    },
  })
}

const plugin: TuiPluginModule & { id: string } = {
  id: "local.mcp-tool-args-panel",
  tui,
}

export default plugin
