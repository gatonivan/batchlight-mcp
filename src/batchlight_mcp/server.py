from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server import MCPServer

from . import __version__
from .bridge.connection import Bridge
from .policy import Policy
from .tools import status

INSTRUCTIONS = (
    "BatchLight connects you to Lightroom Classic running on this computer. "
    "Call lightroom_status first to check the connection; if it reports a problem, "
    "pass its fix on to the user in plain words."
)


def build_server(policy: Policy | None = None) -> MCPServer[Bridge]:
    policy = policy or Policy.from_env()

    @asynccontextmanager
    async def lifespan(server: MCPServer[Bridge]) -> AsyncIterator[Bridge]:
        async with Bridge(server_version=__version__) as bridge:
            yield bridge

    server = MCPServer("batchlight", instructions=INSTRUCTIONS, version=__version__, lifespan=lifespan)
    status.register(server, policy)
    return server
