import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from mcp import Client
from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from batchlight_mcp.policy import DataClass, Policy, Tagged, register_tool, safe
from batchlight_mcp.server import build_server

from .fakes import FakePlugin

pytestmark = pytest.mark.anyio


@pytest.fixture(params=["auto", "legacy"])
async def client(request):
    async with Client(build_server(), mode=request.param) as c:
        yield c


def _text(result: Any) -> str:
    return result.content[0].text


async def test_lightroom_status_is_listed_as_read_only(client):
    tools = {t.name: t for t in (await client.list_tools()).tools}
    assert tools["lightroom_status"].annotations.read_only_hint is True
    assert "Lightroom Classic" in tools["lightroom_status"].description


async def test_status_without_lightroom_explains_the_fix(client):
    result = await client.call_tool("lightroom_status", {})
    report = json.loads(_text(result))
    assert report["connected"] is False
    assert "Plug-in Manager" in report["problems"][0]
    assert report["server"]["role"] == "hub"


async def test_status_with_the_plugin_connected(client, isolated_state: Path):
    async with FakePlugin(isolated_state):
        report = json.loads(_text(await client.call_tool("lightroom_status", {})))
    assert report["connected"] is True
    assert report["problems"] == []
    assert report["lightroom"] == {"version": "15.6", "module": "library", "selected_photos": 3}
    assert report["plugin"] == {"version": "0.1.0", "protocol": 1}


class TestPolicy:
    def test_untagged_values_are_dropped(self):
        policy = Policy.from_env({})
        assert policy.apply({"a": safe(1), "b": 2, "c": [safe(3), 4]}) == {"a": 1, "c": [3]}

    def test_sensitive_classes_are_off_by_default(self):
        policy = Policy.from_env({})
        result = {
            "name": Tagged("Smith-Wedding_0412.NEF", DataClass.FILENAME),
            "gps": Tagged("40.71,-74.00", DataClass.LOCATION),
            "person": Tagged("Maria", DataClass.PEOPLE),
            "path": Tagged("/Users/someone/Pictures", DataClass.PATH),
            "keywords": Tagged(["client: Acme"], DataClass.KEYWORDS),
            "camera": Tagged("A7 IV", DataClass.EXIF),
        }
        assert policy.apply(result) == {"camera": "A7 IV"}

    def test_classes_can_be_opted_into(self):
        policy = Policy.from_env({"BATCHLIGHT_SHARE_FILENAMES": "1", "BATCHLIGHT_SHARE_EXIF": "0"})
        result = {"name": Tagged("a.NEF", DataClass.FILENAME), "camera": Tagged("A7 IV", DataClass.EXIF)}
        assert policy.apply(result) == {"name": "a.NEF"}


async def test_unexpected_tool_errors_never_reach_the_ai_as_raw_text():
    server = MCPServer("t")

    async def leaky() -> Tagged:
        """A tool that fails with a path in its exception."""
        raise RuntimeError("/Users/someone/Pictures/Smith Wedding.lrcat is locked")

    register_tool(server, leaky, policy=Policy.from_env({}), annotations=ToolAnnotations(read_only_hint=True))
    async with Client(server, mode="legacy") as c:
        result = await c.call_tool("leaky", {})
    assert result.is_error
    assert "Smith" not in _text(result) and "/Users" not in _text(result)
    assert "internal error" in _text(result)


def test_stdout_carries_only_json_rpc(isolated_state: Path):
    """Spawn the real server: every byte on stdout must be a JSON-RPC message."""
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "stdout-test", "version": "0"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "lightroom_status", "arguments": {}}},
    ]
    proc = subprocess.Popen(
        [sys.executable, "-u", "-m", "batchlight_mcp", "serve"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ},
    )
    assert proc.stdin and proc.stdout
    responses: dict[int, Any] = {}
    lines: list[bytes] = []
    try:
        for message in requests:
            proc.stdin.write((json.dumps(message) + "\n").encode())
            proc.stdin.flush()
            if "id" not in message:
                continue
            while message["id"] not in responses:
                line = proc.stdout.readline()
                assert line, f"server exited early: {proc.stderr.read().decode() if proc.stderr else ''}"
                lines.append(line)
                parsed = json.loads(line)
                if "id" in parsed:
                    responses[parsed["id"]] = parsed
        proc.stdin.close()
        rest, _ = proc.communicate(timeout=10)
        lines.extend(line for line in rest.splitlines(keepends=True) if line.strip())
    finally:
        if proc.poll() is None:
            proc.kill()
    for line in lines:
        assert json.loads(line)["jsonrpc"] == "2.0", line
    assert proc.returncode == 0
    report = json.loads(responses[3]["result"]["content"][0]["text"])
    assert report["connected"] is False
    assert not (isolated_state / "bridge.json").exists(), "the hub must remove its discovery file on exit"
