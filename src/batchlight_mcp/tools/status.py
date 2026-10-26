from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.types import ToolAnnotations

from ..bridge.connection import Bridge
from ..contract import PROTOCOL, BridgeError, message
from ..policy import Policy, Tagged, register_tool, safe


async def lightroom_status(ctx: Context) -> Tagged:
    """Check the connection to Lightroom Classic.

    Reports whether the BatchLight plugin is connected, the Lightroom version, the
    current module and how many photos are selected, plus what to fix if anything is
    wrong. Call this first, and whenever another tool says Lightroom isn't connected.
    """
    bridge: Bridge = ctx.request_context.lifespan_context
    problems: list[str] = []
    notes: list[str] = []
    report: dict[str, Any] = {"connected": False}

    try:
        hub = await bridge.hub_status()
    except BridgeError as e:
        return safe({**report, "problems": [str(e)]})

    report["server"] = {"version": hub["server_version"], "protocol": hub["server_protocol"], "role": hub["role"]}
    if hub["plugin_version"] is not None:
        report["plugin"] = {"version": hub["plugin_version"], "protocol": hub["plugin_protocol"]}

    if not hub["plugin_connected"]:
        problems.append(message("plugin_not_connected"))
    elif hub["plugin_protocol"] != PROTOCOL:
        problems.append(message("protocol_mismatch", plugin_protocol=hub["plugin_protocol"], server_protocol=PROTOCOL))
    else:
        try:
            live = await bridge.request("status")
        except BridgeError as e:
            problems.append(str(e))
        else:
            report["connected"] = True
            report["lightroom"] = {
                "version": live.get("lightroom_version"),
                "module": live.get("module"),
                "selected_photos": live.get("selected_photos"),
            }
        if hub["plugin_version"] != hub["server_version"]:
            notes.append(
                f"The plugin ({hub['plugin_version']}) and server ({hub['server_version']}) versions differ. "
                "Reinstall the plugin from this server version when convenient."
            )

    report["problems"] = problems
    if notes:
        report["notes"] = notes
    return safe(report)


def register(server: MCPServer, policy: Policy) -> None:
    register_tool(
        server,
        lightroom_status,
        policy=policy,
        annotations=ToolAnnotations(title="Lightroom status", read_only_hint=True, open_world_hint=False),
    )
