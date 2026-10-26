"""The bridge contract shared with the Lua plugin.

The single source is `plugin/BatchLight.lrplugin/contract.json`. It lives inside the
plugin folder so the plugin reads the same file at runtime and `install-plugin`
copies it along.
"""

import json
from importlib.resources import files
from string import Formatter
from typing import Any

PLUGIN_DIR = files("batchlight_mcp") / "plugin" / "BatchLight.lrplugin"

CONTRACT: dict[str, Any] = json.loads((PLUGIN_DIR / "contract.json").read_text(encoding="utf-8"))
PROTOCOL: int = CONTRACT["protocol"]
POLL_HOLD_SECONDS: float = CONTRACT["poll_hold_seconds"]
MAX_BODY_BYTES: int = CONTRACT["max_body_bytes"]
ACTIONS: dict[str, dict[str, str]] = CONTRACT["actions"]
ERRORS: dict[str, str] = CONTRACT["errors"]


def template_fields(code: str) -> set[str]:
    """Names of the placeholders in an error code's message template."""
    return {name for _, name, _, _ in Formatter().parse(ERRORS[code]) if name}


def message(code: str, **params: Any) -> str:
    """Build the AI-facing message for an error code from safe parameters only.

    Unknown codes become `internal_error`, and missing parameters render as `?`, so a
    malformed error from the plugin can never smuggle raw text through.
    """
    if code not in ERRORS:
        code = "internal_error"
    values = {name: params.get(name, "?") for name in template_fields(code)}
    return ERRORS[code].format(**values)


class BridgeError(Exception):
    """A failure with a contract error code. Its message is safe to show the AI."""

    def __init__(self, code: str, **params: Any) -> None:
        self.code = code if code in ERRORS else "internal_error"
        self.params = params
        super().__init__(message(self.code, **params))
