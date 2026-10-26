import argparse
import asyncio
import json
import logging
import os
import sys

from . import __version__
from .bridge.connection import Bridge
from .contract import ACTIONS, BridgeError


def configure_logging() -> None:
    # Before MCPServer exists: it calls basicConfig too. Everything goes to stderr,
    # because stdout carries MCP.
    logging.basicConfig(
        level=os.environ.get("BATCHLIGHT_LOG_LEVEL", "INFO").upper(),
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    for noisy in ("uvicorn", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


async def probe(action: str, params_json: str) -> int:
    """Send one raw command to the plugin, bypassing MCP (and the privacy policy: output stays local)."""
    try:
        params = json.loads(params_json)
    except ValueError as e:
        print(f"error: params must be a JSON object: {e}", file=sys.stderr)
        return 2
    if not isinstance(params, dict):
        print("error: params must be a JSON object", file=sys.stderr)
        return 2
    async with Bridge(server_version=__version__) as bridge:
        role = bridge.role
        try:
            if action == "hub-status":
                result = await bridge.hub_status()
            else:
                result = await bridge.request(action, params)
        except BridgeError as e:
            print(f"error ({e.code}): {e}", file=sys.stderr)
            return 1
    print(json.dumps({"role": role, "result": result}, indent=2))
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="batchlight-mcp", description="BatchLight: an MCP server for Lightroom Classic.")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("serve", help="run the MCP server on stdio (the default)")
    probe_cmd = commands.add_parser(
        "probe", help="send one raw command to the Lightroom plugin, bypassing MCP (output stays on this machine)"
    )
    probe_cmd.add_argument("action", choices=[*ACTIONS, "hub-status"])
    probe_cmd.add_argument("params", nargs="?", default="{}", help="JSON object of parameters (default: {})")
    args = parser.parse_args(argv)

    configure_logging()
    if args.command == "probe":
        raise SystemExit(asyncio.run(probe(args.action, args.params)))

    from .server import build_server

    build_server().run()
