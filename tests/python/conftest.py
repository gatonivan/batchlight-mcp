from pathlib import Path

import pytest

from batchlight_mcp.bridge import discovery

# Resolved before any test patches HOME, so it points at the real user's folder.
REAL_STATE_DIR = discovery.default_state_dir().resolve()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def isolated_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """No test may touch the real bridge.json or lock, or reach the real Lightroom."""
    state = tmp_path / "state"
    monkeypatch.setenv(discovery.STATE_DIR_ENV, str(state))
    monkeypatch.setenv(discovery.TEST_MODE_ENV, "1")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    for var in [v for v in __import__("os").environ if v.startswith("BATCHLIGHT_SHARE_")]:
        monkeypatch.delenv(var)
    if discovery.state_dir().resolve() == REAL_STATE_DIR or discovery.default_state_dir().resolve() == REAL_STATE_DIR:
        pytest.exit("test isolation failed: the real BatchLight state folder is in reach", returncode=3)
    return state
