import os
import stat
import sys
from pathlib import Path

import pytest

from batchlight_mcp.bridge import discovery
from batchlight_mcp.bridge.discovery import BridgeInfo, HubLock, read_info, remove_info, write_info

INFO = BridgeInfo(port=50123, token="tok", pid=42, protocol=1, server_version="0.1.0")


def test_state_dir_is_isolated_for_tests(isolated_state: Path):
    assert discovery.state_dir() == isolated_state
    assert discovery.test_mode()


def test_write_then_read_round_trips(isolated_state: Path):
    write_info(isolated_state, INFO)
    assert read_info(isolated_state) == INFO
    assert not list(isolated_state.glob(".*.tmp")), "atomic write must not leave temp files"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
def test_discovery_file_and_folder_are_owner_only(isolated_state: Path):
    write_info(isolated_state, INFO)
    assert stat.S_IMODE(os.stat(isolated_state / "bridge.json").st_mode) == 0o600
    assert stat.S_IMODE(os.stat(isolated_state).st_mode) == 0o700


@pytest.mark.parametrize("content", ["", "{not json", '{"port": 1}', '{"port": "x", "token": "t", "pid": 1, "protocol": 1, "server_version": "v"}'])
def test_invalid_discovery_files_read_as_missing(isolated_state: Path, content: str):
    isolated_state.mkdir(parents=True)
    (isolated_state / "bridge.json").write_text(content)
    assert read_info(isolated_state) is None


def test_remove_only_deletes_our_own_file(isolated_state: Path):
    write_info(isolated_state, INFO)
    remove_info(isolated_state, token="someone-else")
    assert read_info(isolated_state) == INFO
    remove_info(isolated_state, token="tok")
    assert read_info(isolated_state) is None


def test_lock_is_exclusive_and_released(isolated_state: Path):
    first, second = HubLock(isolated_state), HubLock(isolated_state)
    assert first.acquire()
    assert not second.acquire()
    first.release()
    assert second.acquire()
    second.release()
