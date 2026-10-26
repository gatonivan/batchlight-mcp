"""A stand-in for the Lightroom plugin that speaks the real bridge protocol over HTTP."""

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import httpx

from batchlight_mcp.bridge.discovery import read_info
from batchlight_mcp.contract import PROTOCOL

Handler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


async def _status(params: dict[str, Any]) -> dict[str, Any]:
    return {"lightroom_version": "15.6", "module": "library", "selected_photos": 3}


async def _ping(params: dict[str, Any]) -> dict[str, Any]:
    return {"pong": True}


class FakePlugin:
    def __init__(
        self,
        state_dir: Path,
        *,
        generation: int = 1,
        protocol: int = PROTOCOL,
        handlers: dict[str, Handler] | None = None,
    ) -> None:
        self.state_dir = state_dir
        self.generation = generation
        self.protocol = protocol
        self.handlers: dict[str, Handler] = {"status": _status, "ping": _ping, **(handlers or {})}
        self.received: list[dict[str, Any]] = []
        self.poll_statuses: list[int] = []
        self.paused = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    async def __aenter__(self) -> "FakePlugin":
        self._task = asyncio.create_task(self._run())
        return self

    async def __aexit__(self, *exc: object) -> None:
        assert self._task is not None
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task

    async def _run(self) -> None:
        async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
            while True:
                info = read_info(self.state_dir)
                if info is None:
                    await asyncio.sleep(0.05)
                    continue
                base = f"http://127.0.0.1:{info.port}"
                headers = {"Authorization": f"Bearer {info.token}"}
                try:
                    hello = await client.post(
                        f"{base}/hello",
                        json={
                            "generation": self.generation,
                            "protocol": self.protocol,
                            "plugin_version": "0.1.0",
                            "lightroom_version": "15.6",
                        },
                        headers=headers,
                    )
                    if hello.status_code != 200:
                        await asyncio.sleep(0.05)
                        continue
                    while True:
                        while self.paused.is_set():
                            await asyncio.sleep(0.02)
                        poll = await client.get(f"{base}/poll", params={"generation": self.generation}, headers=headers)
                        self.poll_statuses.append(poll.status_code)
                        if poll.status_code == 204:
                            continue
                        if poll.status_code == 409:
                            return  # like the real loop: superseded by a newer generation, so exit
                        if poll.status_code != 200:
                            break
                        command = poll.json()
                        self.received.append(command)
                        reply = await self._handle(command)
                        await client.post(f"{base}/result", json=reply, headers=headers)
                except httpx.TransportError:
                    pass
                await asyncio.sleep(0.05)

    async def _handle(self, command: dict[str, Any]) -> dict[str, Any]:
        handler = self.handlers.get(command["action"])
        base = {"id": command["id"], "generation": self.generation}
        if handler is None:
            return {**base, "ok": False, "error": {"code": "unknown_action", "params": {"action": command["action"]}}}
        try:
            return {**base, "ok": True, "result": await handler(command["params"])}
        except Exception:
            return {**base, "ok": False, "error": {"code": "handler_failed", "params": {"action": command["action"]}}}
