"""The privacy gate: the only way anything reaches the AI (PLAN.md §5).

Tools return values wrapped in `Tagged` with a data class. The policy keeps a value
only if its class is shared, and drops anything untagged (deny by default). Errors
reach the AI only as contract messages, never as raw exception text.
"""

import functools
import json
import logging
import os
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from .contract import BridgeError, message

log = logging.getLogger(__name__)


class DataClass(StrEnum):
    SAFE = "safe"  # versions, counts, develop settings, colour statistics: always shared
    FILENAME = "filename"
    EXIF = "exif"
    PREVIEW = "preview"
    PATH = "path"
    LOCATION = "location"
    PEOPLE = "people"
    KEYWORDS = "keywords"


# Data class -> (env var, shared by default). Mirrors the table in PLAN.md §2.
SETTINGS: dict[DataClass, tuple[str, bool]] = {
    DataClass.FILENAME: ("BATCHLIGHT_SHARE_FILENAMES", False),
    DataClass.EXIF: ("BATCHLIGHT_SHARE_EXIF", True),
    DataClass.PREVIEW: ("BATCHLIGHT_SHARE_PREVIEWS", True),
    DataClass.PATH: ("BATCHLIGHT_SHARE_PATHS", False),
    DataClass.LOCATION: ("BATCHLIGHT_SHARE_LOCATION", False),
    DataClass.PEOPLE: ("BATCHLIGHT_SHARE_PEOPLE", False),
    DataClass.KEYWORDS: ("BATCHLIGHT_SHARE_KEYWORDS", False),
}


@dataclass(frozen=True)
class Tagged:
    value: Any
    data_class: DataClass


def safe(value: Any) -> Tagged:
    return Tagged(value, DataClass.SAFE)


_DROPPED = object()


@dataclass(frozen=True)
class Policy:
    shared: frozenset[DataClass]

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "Policy":
        shared = {DataClass.SAFE}
        for data_class, (var, default) in SETTINGS.items():
            raw = env.get(var)
            if (default if raw is None else raw.strip().lower() in {"1", "true", "yes", "on"}):
                shared.add(data_class)
        return cls(frozenset(shared))

    def apply(self, value: Any) -> Any:
        """Keep only values tagged with a shared class; drop everything else."""
        kept = self._apply(value, "result")
        return None if kept is _DROPPED else kept

    def _apply(self, value: Any, where: str) -> Any:
        if isinstance(value, Tagged):
            return value.value if value.data_class in self.shared else _DROPPED
        if isinstance(value, dict):
            kept = {k: self._apply(v, f"{where}.{k}") for k, v in value.items()}
            return {k: v for k, v in kept.items() if v is not _DROPPED}
        if isinstance(value, list):
            return [v for v in (self._apply(item, f"{where}[]") for item in value) if v is not _DROPPED]
        log.warning("privacy policy dropped an untagged value at %s", where)
        return _DROPPED


def register_tool(
    server: MCPServer,
    fn: Callable[..., Awaitable[Any]],
    *,
    policy: Policy,
    annotations: ToolAnnotations,
) -> None:
    """Register a tool so its result and its errors can only leave through the policy."""
    name = fn.__name__

    @functools.wraps(fn)
    async def gated(*args: Any, **kwargs: Any) -> str:
        try:
            result = await fn(*args, **kwargs)
        except BridgeError as e:
            raise ToolError(str(e)) from None
        except Exception:
            log.exception("tool %s failed", name)  # full detail stays in the local log
            raise ToolError(message("internal_error")) from None
        return json.dumps(policy.apply(result), indent=2, ensure_ascii=False)

    server.add_tool(gated, name=name, annotations=annotations, structured_output=False)
