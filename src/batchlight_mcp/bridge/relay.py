"""Relay: how a server process that isn't the hub sends commands through the one that is."""

from pathlib import Path
from typing import Any

import httpx

from ..contract import BridgeError
from .discovery import read_info


class HubUnavailable(Exception):
    """No hub answered before the request was sent, so it's safe to retry or take over."""


class Relay:
    def __init__(self, state_dir: Path) -> None:
        self._state_dir = state_dir

    def _target(self) -> tuple[str, dict[str, str]]:
        info = read_info(self._state_dir)
        if info is None:
            raise HubUnavailable("no bridge.json")
        return f"http://127.0.0.1:{info.port}", {"Authorization": f"Bearer {info.token}"}

    async def submit(
        self, action: str, params: dict[str, Any], *, start_within: float, timeout: float
    ) -> dict[str, Any]:
        base, headers = self._target()
        payload = {"action": action, "params": params, "start_within": start_within, "timeout": timeout}
        # trust_env=False: never route localhost traffic through a proxy from the environment.
        async with httpx.AsyncClient(timeout=timeout + 5, trust_env=False) as client:
            try:
                response = await client.post(f"{base}/submit", json=payload, headers=headers)
            except httpx.ConnectError as e:
                raise HubUnavailable(str(e)) from None
            except httpx.TransportError:
                # Sent, then the hub went away: the command may have run.
                raise BridgeError("hub_changed", action=action) from None
        if response.status_code in (401, 403):
            raise HubUnavailable("stale bridge.json")
        if response.status_code != 200:
            raise BridgeError("hub_unavailable")
        body = response.json()
        if body.get("ok") is True:
            return body.get("result") or {}
        error = body.get("error") or {}
        raise BridgeError(str(error.get("code", "internal_error")), **(error.get("params") or {}))

    async def hub_status(self) -> dict[str, Any]:
        base, headers = self._target()
        async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
            try:
                response = await client.get(f"{base}/hub-status", headers=headers)
            except httpx.TransportError as e:
                raise HubUnavailable(str(e)) from None
        if response.status_code != 200:
            raise HubUnavailable(f"hub answered {response.status_code}")
        return response.json()
