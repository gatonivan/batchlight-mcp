"""One server process's view of the bridge: be the hub if possible, otherwise relay.

Whoever holds `bridge.lock` is the hub. Every other process relays through it, and
the first relay to find the hub gone takes the lock over.
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Literal

from ..contract import PROTOCOL, BridgeError
from . import discovery
from .hub import Hub
from .relay import HubUnavailable, Relay

log = logging.getLogger(__name__)

# A hub shutting down holds the lock for about a second after its discovery file goes.
TAKEOVER_WAIT_SECONDS = 3.0


class Bridge:
    def __init__(self, *, server_version: str, state_dir: Path | None = None) -> None:
        self.server_version = server_version
        self.state_dir = state_dir or discovery.state_dir()
        self._lock = discovery.HubLock(self.state_dir)
        self._hub: Hub | None = None
        self._relay = Relay(self.state_dir)

    async def __aenter__(self) -> "Bridge":
        await self._try_become_hub()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    @property
    def role(self) -> Literal["hub", "relay"]:
        return "hub" if self._hub is not None else "relay"

    @property
    def hub(self) -> Hub | None:
        return self._hub

    async def _try_become_hub(self, wait: float = 0.0) -> bool:
        """Take the hub role if the lock is free. `wait` covers a hub that is mid-shutdown."""
        if self._hub is not None:
            return True
        deadline = asyncio.get_running_loop().time() + wait
        while not self._lock.acquire():
            if asyncio.get_running_loop().time() >= deadline:
                log.info("another BatchLight server is the hub; relaying through it")
                return False
            await asyncio.sleep(0.2)
        hub = Hub(server_version=self.server_version)
        try:
            await hub.start()
            assert hub.port is not None
            discovery.write_info(
                self.state_dir,
                discovery.BridgeInfo(
                    port=hub.port,
                    token=hub.token,
                    pid=os.getpid(),
                    protocol=PROTOCOL,
                    server_version=self.server_version,
                    test=discovery.test_mode(),
                ),
            )
        except BaseException:
            await hub.stop()
            self._lock.release()
            raise
        self._hub = hub
        return True

    async def request(
        self, action: str, params: dict[str, Any] | None = None, *, start_within: float = 10.0, timeout: float = 15.0
    ) -> dict[str, Any]:
        params = params or {}
        if self._hub is None:
            try:
                return await self._relay.submit(action, params, start_within=start_within, timeout=timeout)
            except HubUnavailable as e:
                log.info("hub unavailable (%s); trying to take over", e)
                if not await self._try_become_hub(wait=TAKEOVER_WAIT_SECONDS):
                    raise BridgeError("hub_unavailable") from None
        assert self._hub is not None
        return await self._hub.request(action, params, start_within=start_within, timeout=timeout)

    async def hub_status(self) -> dict[str, Any]:
        if self._hub is None:
            try:
                status = await self._relay.hub_status()
            except HubUnavailable as e:
                log.info("hub unavailable (%s); trying to take over", e)
                if not await self._try_become_hub(wait=TAKEOVER_WAIT_SECONDS):
                    raise BridgeError("hub_unavailable") from None
            else:
                return {**status, "role": "relay"}
        assert self._hub is not None
        return {**await self._hub.settled_status(), "role": "hub"}

    async def close(self) -> None:
        """Hand over cleanly: polls return, the discovery file goes, then the lock."""
        hub, self._hub = self._hub, None
        if hub is None:
            return
        try:
            discovery.remove_info(self.state_dir, hub.token)
            await hub.stop()
        finally:
            self._lock.release()
