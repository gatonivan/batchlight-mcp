import re
import tomllib
from pathlib import Path

from batchlight_mcp import __version__
from batchlight_mcp.contract import ACTIONS, CONTRACT, ERRORS, PLUGIN_DIR, BridgeError, message, template_fields

ROOT = Path(__file__).resolve().parents[2]


def test_examples_use_known_actions_and_codes():
    examples = CONTRACT["examples"]
    assert examples["command"]["action"] in ACTIONS
    assert examples["result_error"]["error"]["code"] in ERRORS
    assert examples["command"]["protocol"] == CONTRACT["protocol"]


def test_every_template_renders_with_its_fields():
    for code in ERRORS:
        rendered = message(code, **{name: "X" for name in template_fields(code)})
        assert "{" not in rendered and "?" not in rendered.replace("?", "", 0) or code


def test_unknown_codes_and_missing_params_never_leak_raw_text():
    assert message("no_such_code") == ERRORS["internal_error"]
    assert "'?'" in message("timeout", seconds=5)
    error = BridgeError("totally made up", raw="/Users/someone/secret.lrcat")
    assert error.code == "internal_error"
    assert "secret" not in str(error)


def test_plugin_version_matches_package_version():
    info = (Path(str(PLUGIN_DIR)) / "Info.lua").read_text(encoding="utf-8")
    plugin_version = re.search(r"display = '([^']+)'", info).group(1)
    project_version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    assert plugin_version == project_version == __version__


def test_plugin_ships_its_contract_and_json_library():
    names = {p.name for p in Path(str(PLUGIN_DIR)).iterdir()}
    assert {"Info.lua", "contract.json", "dkjson.lua", "Core.lua", "Bridge.lua", "Handlers.lua"} <= names
