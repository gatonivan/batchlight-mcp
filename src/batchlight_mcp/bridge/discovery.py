"""How the plugin and other server processes find the hub: `bridge.json` plus `bridge.lock`.

Both live in the state folder. The plugin computes the same folder from Lightroom's
`appData` path, so the two must stay in step (see Bridge.lua).
"""

import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import IO

APP_DIR_NAME = "batchlight-mcp"
STATE_DIR_ENV = "BATCHLIGHT_STATE_DIR"
TEST_MODE_ENV = "BATCHLIGHT_TEST_MODE"
INFO_FILE = "bridge.json"
LOCK_FILE = "bridge.lock"


def default_state_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    if sys.platform == "win32":
        return Path(os.environ["APPDATA"]) / APP_DIR_NAME
    return Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / APP_DIR_NAME


def state_dir() -> Path:
    override = os.environ.get(STATE_DIR_ENV)
    return Path(override) if override else default_state_dir()


def test_mode() -> bool:
    return os.environ.get(TEST_MODE_ENV) == "1"


@dataclass(frozen=True)
class BridgeInfo:
    port: int
    token: str
    pid: int
    protocol: int
    server_version: str
    # Hubs started by the test suite set this, and the real plugin refuses to poll them.
    test: bool = False


def _ensure_dir(directory: Path) -> None:
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)


def write_info(directory: Path, info: BridgeInfo) -> None:
    """Write `bridge.json` atomically, readable by the owner only."""
    _ensure_dir(directory)
    tmp = directory / f".{INFO_FILE}.{os.getpid()}.tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(asdict(info), f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, directory / INFO_FILE)


def read_info(directory: Path) -> BridgeInfo | None:
    """The current hub's details, or None if there is no valid discovery file."""
    try:
        raw = json.loads((directory / INFO_FILE).read_text(encoding="utf-8"))
        info = BridgeInfo(**raw)
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(info.port, int) or not isinstance(info.token, str) or not info.token:
        return None
    return info


def remove_info(directory: Path, token: str) -> None:
    """Delete `bridge.json`, but only if it is still ours (a newer hub may have replaced it)."""
    current = read_info(directory)
    if current is not None and current.token == token:
        (directory / INFO_FILE).unlink(missing_ok=True)


class HubLock:
    """Exclusive, non-blocking OS lock on `bridge.lock`. Whoever holds it is the hub.

    The OS releases it when the holding process dies, so a crashed hub never blocks
    the next one.
    """

    def __init__(self, directory: Path) -> None:
        self._path = directory / LOCK_FILE
        self._file: IO[bytes] | None = None

    @property
    def held(self) -> bool:
        return self._file is not None

    def acquire(self) -> bool:
        if self._file is not None:
            return True
        _ensure_dir(self._path.parent)
        f = open(self._path, "a+b")
        try:
            _lock(f)
        except OSError:
            f.close()
            return False
        self._file = f
        return True

    def release(self) -> None:
        if self._file is None:
            return
        try:
            _unlock(self._file)
        finally:
            self._file.close()
            self._file = None


if sys.platform == "win32":
    import msvcrt

    def _lock(f: IO[bytes]) -> None:
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)

    def _unlock(f: IO[bytes]) -> None:
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _lock(f: IO[bytes]) -> None:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(f: IO[bytes]) -> None:
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
