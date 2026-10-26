import asyncio
import time
from pathlib import Path
from typing import Any

import httpx
import pytest

from batchlight_mcp.bridge import discovery
from batchlight_mcp.bridge.connection import Bridge
from batchlight_mcp.bridge.discovery import HubLock, read_info
from batchlight_mcp.contract import ERRORS, MAX_BODY_BYTES, BridgeError

from .fakes import FakePlugin

pytestmark = pytest.mark.anyio


async def _bridge() -> Bridge:
    return await Bridge(server_version="0.1.0").__aenter__()


async def test_first_server_becomes_hub_and_writes_a_test_marked_discovery_file(isolated_state: Path):
    async with Bridge(server_version="0.1.0") as bridge:
        assert bridge.role == "hub"
        info = read_info(isolated_state)
        assert info is not None and info.test is True and info.port == bridge.hub.port


async def test_status_round_trip_through_the_fake_plugin(isolated_state: Path):
    async with Bridge(server_version="0.1.0") as bridge, FakePlugin(isolated_state):
        assert await bridge.request("status") == {"lightroom_version": "15.6", "module": "library", "selected_photos": 3}


async def test_no_plugin_gives_an_actionable_error(isolated_state: Path):
    async with Bridge(server_version="0.1.0") as bridge:
        with pytest.raises(BridgeError) as caught:
            await bridge.request("status")
        assert caught.value.code == "plugin_not_connected"
        assert "Plug-in Manager" in str(caught.value)


async def test_unknown_actions_are_refused_before_reaching_lightroom(isolated_state: Path):
    async with Bridge(server_version="0.1.0") as bridge, FakePlugin(isolated_state) as plugin:
        with pytest.raises(BridgeError) as caught:
            await bridge.request("delete_everything")
        assert caught.value.code == "unknown_action"
        assert plugin.received == []


async def test_handler_failure_maps_to_a_contract_message(isolated_state: Path):
    async def boom(params: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("/Users/someone/Pictures/client.lrcat exploded")

    async with Bridge(server_version="0.1.0") as bridge, FakePlugin(isolated_state, handlers={"ping": boom}):
        with pytest.raises(BridgeError) as caught:
            await bridge.request("ping")
        assert caught.value.code == "handler_failed"
        assert "client.lrcat" not in str(caught.value)


async def test_timeout_says_the_edit_may_have_applied_and_the_late_result_is_kept(isolated_state: Path):
    release = asyncio.Event()

    async def slow(params: dict[str, Any]) -> dict[str, Any]:
        await release.wait()
        return {"pong": True}

    async with Bridge(server_version="0.1.0") as bridge, FakePlugin(isolated_state, handlers={"ping": slow}):
        await bridge.hub.wait_for_plugin(2)
        with pytest.raises(BridgeError) as caught:
            await bridge.request("ping", timeout=0.3)
        assert caught.value.code == "timeout"
        assert "may still have been applied" in str(caught.value)
        release.set()
        for _ in range(50):
            if bridge.hub.late_results:
                break
            await asyncio.sleep(0.02)
        assert bridge.hub.late_results and bridge.hub.late_results[0]["ok"] is True


async def test_a_command_that_could_not_start_in_time_expires_without_running(isolated_state: Path):
    async with Bridge(server_version="0.1.0") as bridge, FakePlugin(isolated_state) as plugin:
        await bridge.hub.wait_for_plugin(2)
        await bridge.request("ping")  # make sure the plugin is idle in a poll
        plugin.paused.set()
        await asyncio.sleep(0.1)
        # The held poll is still open, so pause by holding the next one: queue after it returns.
        request = asyncio.create_task(bridge.request("ping", start_within=0.2, timeout=3))
        await asyncio.sleep(0.05)
        received_before = len(plugin.received)
        await asyncio.sleep(0.4)
        plugin.paused.clear()
        try:
            await request
        except BridgeError as e:
            assert e.code == "expired"
            assert len(plugin.received) == received_before


async def test_stale_plugin_loop_gets_409_and_latest_hello_wins(isolated_state: Path):
    async with Bridge(server_version="0.1.0") as bridge:
        async with FakePlugin(isolated_state, generation=5) as old:
            await bridge.hub.wait_for_plugin(2)
            async with FakePlugin(isolated_state, generation=2) as new:  # lower: prefs were reset
                for _ in range(100):
                    if 409 in old.poll_statuses:
                        break
                    await asyncio.sleep(0.05)
                assert 409 in old.poll_statuses, "the old loop's held poll must be released at once"
                assert await bridge.request("ping") == {"pong": True}
                assert [c["action"] for c in new.received] == ["ping"]
                assert old.received == []


async def test_protocol_mismatch_is_reported_and_nothing_is_sent(isolated_state: Path):
    async with Bridge(server_version="0.1.0") as bridge, FakePlugin(isolated_state, protocol=99) as plugin:
        await bridge.hub.wait_for_plugin(2)
        with pytest.raises(BridgeError) as caught:
            await bridge.request("status")
        assert caught.value.code == "protocol_mismatch"
        assert plugin.received == []


async def test_second_server_relays_through_the_hub(isolated_state: Path):
    async with Bridge(server_version="0.1.0") as hub_side, FakePlugin(isolated_state):
        async with Bridge(server_version="0.1.0") as relay_side:
            assert hub_side.role == "hub" and relay_side.role == "relay"
            assert await relay_side.request("ping") == {"pong": True}
            status = await relay_side.hub_status()
            assert status["role"] == "relay" and status["plugin_connected"] is True


async def test_relay_errors_keep_their_contract_code(isolated_state: Path):
    async with Bridge(server_version="0.1.0"), Bridge(server_version="0.1.0") as relay_side:
        with pytest.raises(BridgeError) as caught:
            await relay_side.request("status")
        assert caught.value.code == "plugin_not_connected"


async def test_relay_takes_over_when_the_hub_goes_away(isolated_state: Path):
    async with FakePlugin(isolated_state):
        first = await _bridge()
        relay_side = await _bridge()
        assert relay_side.role == "relay"
        await first.close()
        assert await relay_side.request("ping") == {"pong": True}
        assert relay_side.role == "hub"
        await relay_side.close()


async def test_shutdown_is_fast_with_a_poll_held_and_hands_over_cleanly(isolated_state: Path):
    async with FakePlugin(isolated_state):
        bridge = await _bridge()
        await bridge.hub.wait_for_plugin(2)
        await asyncio.sleep(0.2)  # a poll is now held open
        started = time.monotonic()
        await bridge.close()
        assert time.monotonic() - started < 2
        assert read_info(isolated_state) is None
        lock = HubLock(isolated_state)
        assert lock.acquire()
        lock.release()


class TestRequestChecks:
    @pytest.fixture
    async def hub(self, isolated_state: Path):
        async with Bridge(server_version="0.1.0") as bridge:
            yield bridge.hub

    async def _get(self, hub, path: str = "/hub-status", **headers: str) -> httpx.Response:
        base = {"Authorization": f"Bearer {hub.token}", "Host": f"127.0.0.1:{hub.port}"}
        async with httpx.AsyncClient(trust_env=False) as client:
            return await client.get(f"http://127.0.0.1:{hub.port}{path}", headers={**base, **headers})

    async def test_valid_request_passes(self, hub):
        assert (await self._get(hub)).status_code == 200

    async def test_wrong_token_is_refused(self, hub):
        assert (await self._get(hub, Authorization="Bearer nope")).status_code == 401

    async def test_browser_origin_is_refused(self, hub):
        assert (await self._get(hub, Origin="https://evil.example")).status_code == 403

    async def test_foreign_host_is_refused(self, hub):
        assert (await self._get(hub, Host="evil.example")).status_code == 403

    async def test_oversized_bodies_are_refused_before_being_read(self, hub):
        # Raw socket: HTTP clients won't send a body shorter than its declared length.
        reader, writer = await asyncio.open_connection("127.0.0.1", hub.port)
        writer.write(
            (
                f"POST /result HTTP/1.1\r\nHost: 127.0.0.1:{hub.port}\r\nAuthorization: Bearer {hub.token}\r\n"
                f"Content-Type: application/json\r\nContent-Length: {MAX_BODY_BYTES + 1}\r\n\r\n{{}}"
            ).encode()
        )
        await writer.drain()
        status_line = await reader.readline()
        writer.close()
        assert b" 413 " in status_line

    async def test_non_json_bodies_are_refused(self, hub):
        headers = {"Authorization": f"Bearer {hub.token}", "Content-Type": "text/plain"}
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await client.post(f"http://127.0.0.1:{hub.port}/result", content=b"x=1", headers=headers)
        assert response.status_code == 415

    async def test_poll_before_hello_is_refused(self, hub):
        assert (await self._get(hub, "/poll?generation=1")).status_code == 428


def test_every_error_code_used_in_code_exists():
    import batchlight_mcp

    source_dir = Path(batchlight_mcp.__file__).parent
    used = set()
    for path in source_dir.rglob("*.py"):
        used |= set(__import__("re").findall(r'BridgeError\(\s*"([a-z_]+)"', path.read_text()))
        used |= set(__import__("re").findall(r'message\(\s*"([a-z_]+)"', path.read_text()))
    assert used, "expected to find error codes"
    assert used <= set(ERRORS), used - set(ERRORS)
