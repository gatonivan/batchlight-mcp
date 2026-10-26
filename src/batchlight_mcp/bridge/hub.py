"""The hub: a token-protected HTTP server on 127.0.0.1 that the Lightroom plugin long-polls.

Only one server process on the machine runs it (see connection.py). Commands from
this process and from relays are queued here, handed to the plugin through held
`GET /poll` requests, and answered through `POST /result`.
"""

import asyncio
import contextlib
import hmac
import logging
import secrets
import socket
import time
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

import uvicorn
from starlette.applications import Starlette
from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

from ..contract import ACTIONS, MAX_BODY_BYTES, POLL_HOLD_SECONDS, PROTOCOL, BridgeError

log = logging.getLogger(__name__)

# A plugin counts as connected while a poll is held, or within this long of its last poll.
CONNECTED_GRACE_SECONDS = 15.0
# The plugin checks for a new hub every 2 s, so a hub this young waits a little for it.
FRESH_HUB_SECONDS = 10.0
PLUGIN_GRACE_SECONDS = 3.0


@dataclass
class Command:
    action: str
    params: dict[str, Any]
    expires_at: float
    id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def envelope(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "action": self.action,
            "params": self.params,
            "expires_at": self.expires_at,
            "protocol": PROTOCOL,
        }


@dataclass(frozen=True)
class PluginSession:
    generation: int
    protocol: int
    plugin_version: str
    lightroom_version: str


class _RequestChecks:
    """Reject anything that isn't the plugin or a relay on this machine.

    Mirrors the protections the MCP SDK applies to its own HTTP transport: browsers
    (any `Origin`) and DNS rebinding (a foreign `Host`) are refused before auth.
    """

    def __init__(self, app: ASGIApp, hub: "Hub") -> None:
        self.app = app
        self.hub = hub

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        problem = self._check(scope, Headers(scope=scope))
        if problem is not None:
            status, reason = problem
            log.warning("bridge refused %s %s: %s", scope["method"], scope["path"], reason)
            await JSONResponse({"error": reason}, status_code=status)(scope, receive, send)
            return
        await self.app(scope, receive, send)

    def _check(self, scope: Scope, headers: Headers) -> tuple[int, str] | None:
        if "origin" in headers:
            return 403, "origin_not_allowed"
        if headers.get("host") != f"127.0.0.1:{self.hub.port}":
            return 403, "bad_host"
        auth = headers.get("authorization", "")
        expected = f"Bearer {self.hub.token}"
        if not hmac.compare_digest(auth.encode(), expected.encode()):
            return 401, "bad_token"
        if scope["method"] == "POST":
            if headers.get("content-type", "").split(";")[0].strip() != "application/json":
                return 415, "json_only"
            length = headers.get("content-length")
            if length is None or not length.isdigit():
                return 411, "length_required"
            if int(length) > MAX_BODY_BYTES:
                return 413, "body_too_large"
        return None


class _QuietServer(uvicorn.Server):
    """uvicorn without its signal handlers: the MCP server owns process shutdown."""

    @contextlib.contextmanager
    def capture_signals(self) -> Iterator[None]:
        yield


class Hub:
    def __init__(
        self,
        *,
        server_version: str,
        poll_hold: float = POLL_HOLD_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        wall: Callable[[], float] = time.time,
    ) -> None:
        self.server_version = server_version
        self.token = secrets.token_urlsafe(32)
        self.port: int | None = None
        self.poll_hold = poll_hold
        self._clock = clock
        self._wall = wall
        self._queue: asyncio.Queue[Command] = asyncio.Queue()
        self._waiters: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._session: PluginSession | None = None
        self._last_seen: float | None = None
        self._polls_held = 0
        self._closing = asyncio.Event()
        self._interrupt = asyncio.Event()  # set (and replaced) to wake held polls
        self._server: _QuietServer | None = None
        self._serve_task: asyncio.Task[None] | None = None
        self.started_at = clock()
        # Results that arrived after their caller gave up. M3 writes these to the edit journal.
        self.late_results: list[dict[str, Any]] = []
        self.app = _RequestChecks(
            Starlette(
                routes=[
                    Route("/hello", self._hello, methods=["POST"]),
                    Route("/poll", self._poll, methods=["GET"]),
                    Route("/result", self._result, methods=["POST"]),
                    Route("/submit", self._submit, methods=["POST"]),
                    Route("/hub-status", self._hub_status, methods=["GET"]),
                ]
            ),
            self,
        )

    # -- lifecycle -------------------------------------------------------------

    async def start(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        self.port = sock.getsockname()[1]
        config = uvicorn.Config(
            self.app,
            lifespan="off",
            access_log=False,  # uvicorn's access log writes to stdout, which belongs to MCP
            log_config=None,
            timeout_graceful_shutdown=1,
            ws="none",
        )
        self._server = _QuietServer(config)
        self._serve_task = asyncio.create_task(self._server.serve(sockets=[sock]))
        while not self._server.started:
            if self._serve_task.done():
                self._serve_task.result()  # surfaces the startup failure
                raise RuntimeError("bridge hub stopped during startup")
            await asyncio.sleep(0.01)
        self.started_at = self._clock()
        log.info("bridge hub listening on 127.0.0.1:%d", self.port)

    async def stop(self) -> None:
        """Stop within about a second, even with a poll held open."""
        self._closing.set()
        self._wake_held_polls()  # held polls return at once
        for fut in self._waiters.values():
            if not fut.done():
                fut.set_exception(BridgeError("hub_changed", action="?"))
        if self._server is not None and self._serve_task is not None:
            self._server.should_exit = True
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._serve_task, timeout=3)

    # -- state -----------------------------------------------------------------

    def plugin_connected(self) -> bool:
        if self._session is None:
            return False
        if self._polls_held > 0:
            return True
        return self._last_seen is not None and self._clock() - self._last_seen < self.poll_hold + CONNECTED_GRACE_SECONDS

    def status(self) -> dict[str, Any]:
        session = self._session
        return {
            "server_version": self.server_version,
            "server_protocol": PROTOCOL,
            "plugin_connected": self.plugin_connected(),
            "plugin_version": session.plugin_version if session else None,
            "plugin_protocol": session.protocol if session else None,
            "lightroom_version": session.lightroom_version if session else None,
            "seconds_since_seen": None if self._last_seen is None else round(self._clock() - self._last_seen, 1),
            "hub_age_seconds": round(self._clock() - self.started_at, 1),
        }

    async def wait_for_plugin(self, seconds: float) -> bool:
        deadline = self._clock() + seconds
        while not self.plugin_connected() and self._clock() < deadline:
            await asyncio.sleep(0.1)
        return self.plugin_connected()

    async def _settle(self) -> None:
        """A just-started hub gives the plugin a moment to find it before answering."""
        if not self.plugin_connected() and self._clock() - self.started_at < FRESH_HUB_SECONDS:
            await self.wait_for_plugin(PLUGIN_GRACE_SECONDS)

    async def settled_status(self) -> dict[str, Any]:
        await self._settle()
        return self.status()

    def _seen(self) -> None:
        self._last_seen = self._clock()

    # -- commands --------------------------------------------------------------

    async def request(
        self, action: str, params: dict[str, Any] | None = None, *, start_within: float = 10.0, timeout: float = 15.0
    ) -> dict[str, Any]:
        """Send one command to the plugin and return its result.

        `start_within` only stops a command from *starting*. Once the plugin has begun,
        its result is always reported, late if necessary (see `late_results`).
        """
        if action not in ACTIONS:
            raise BridgeError("unknown_action", action=action)
        await self._settle()
        if not self.plugin_connected():
            raise BridgeError("plugin_not_connected")
        session = self._session
        assert session is not None
        if session.protocol != PROTOCOL:
            raise BridgeError("protocol_mismatch", plugin_protocol=session.protocol, server_protocol=PROTOCOL)
        command = Command(action=action, params=params or {}, expires_at=self._wall() + start_within)
        fut: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._waiters[command.id] = fut
        self._queue.put_nowait(command)
        try:
            reply = await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            raise BridgeError("timeout", action=action, seconds=round(timeout)) from None
        finally:
            # A command nobody waits for is skipped if it hasn't started (cancellation passes through).
            self._waiters.pop(command.id, None)
        if reply.get("ok") is True:
            result = reply.get("result")
            return result if isinstance(result, dict) else {}
        error = reply.get("error") if isinstance(reply.get("error"), dict) else {}
        params_out = error.get("params") if isinstance(error.get("params"), dict) else {}
        raise BridgeError(str(error.get("code", "internal_error")), **{"action": action, **params_out})

    async def _next_command(self, generation: int) -> Command | None:
        """Wait for the next live command, the end of the hold, shutdown, or a newer plugin loop.

        Returns None when the hold ends without a command. The caller checks whether
        the hub is closing or this poll's loop was superseded.
        """
        deadline = self._clock() + self.poll_hold
        while not self._closing.is_set() and self._is_current(generation):
            remaining = deadline - self._clock()
            if remaining <= 0:
                return None
            getter = asyncio.ensure_future(self._queue.get())
            interrupt = asyncio.ensure_future(self._interrupt.wait())
            await asyncio.wait({getter, interrupt}, timeout=remaining, return_when=asyncio.FIRST_COMPLETED)
            interrupt.cancel()
            if not getter.done():
                getter.cancel()  # no await since wait(), so it cannot have taken an item meanwhile
                continue
            command = getter.result()
            if not self._is_current(generation):
                # A newer loop said hello while this poll was held: hand the command to it.
                self._queue.put_nowait(command)
                return None
            fut = self._waiters.get(command.id)
            if fut is None or fut.done():
                log.info("skipping %s %s: its caller stopped waiting", command.action, command.id)
                continue
            if self._wall() > command.expires_at:
                fut.set_exception(BridgeError("expired", action=command.action))
                continue
            return command
        return None

    def _is_current(self, generation: int) -> bool:
        return self._session is not None and self._session.generation == generation

    def _wake_held_polls(self) -> None:
        """Make every held poll re-check shutdown and its generation."""
        self._interrupt.set()
        self._interrupt = asyncio.Event()

    # -- endpoints -------------------------------------------------------------

    async def _hello(self, request: Request) -> Response:
        body = await _json_body(request)
        try:
            session = PluginSession(
                generation=int(body["generation"]),
                protocol=int(body["protocol"]),
                plugin_version=str(body.get("plugin_version", "unknown")),
                lightroom_version=str(body.get("lightroom_version", "unknown")),
            )
        except (KeyError, TypeError, ValueError):
            return JSONResponse({"error": "bad_hello"}, status_code=400)
        # The latest hello wins, even with a lower generation (plugin prefs can be reset).
        # Polls still held by an older loop are released with 409 so they can't take commands.
        self._session = session
        self._seen()
        self._wake_held_polls()
        log.info(
            "plugin %s connected (Lightroom %s, generation %d, protocol %d)",
            session.plugin_version,
            session.lightroom_version,
            session.generation,
            session.protocol,
        )
        return JSONResponse({"protocol": PROTOCOL, "server_version": self.server_version})

    async def _poll(self, request: Request) -> Response:
        session = self._session
        if session is None:
            return JSONResponse({"error": "hello_required"}, status_code=428)
        if request.query_params.get("generation") != str(session.generation):
            return JSONResponse({"error": "stale_generation"}, status_code=409)
        if self._closing.is_set():
            return JSONResponse({"error": "hub_closing"}, status_code=503)
        self._polls_held += 1
        self._seen()
        try:
            command = await self._next_command(session.generation)
        finally:
            self._polls_held -= 1
            self._seen()
        if command is not None:
            return JSONResponse(command.envelope())
        if self._closing.is_set():
            return JSONResponse({"error": "hub_closing"}, status_code=503)
        if not self._is_current(session.generation):
            return JSONResponse({"error": "stale_generation"}, status_code=409)
        return Response(status_code=204)

    async def _result(self, request: Request) -> Response:
        body = await _json_body(request)
        command_id = body.get("id")
        if not isinstance(command_id, str):
            return JSONResponse({"error": "bad_result"}, status_code=400)
        self._seen()
        fut = self._waiters.get(command_id)
        if fut is None or fut.done():
            log.warning("late result for command %s", command_id)
            self.late_results.append(body)
            return JSONResponse({"accepted": "late"})
        fut.set_result(body)
        return JSONResponse({"accepted": True})

    async def _submit(self, request: Request) -> Response:
        body = await _json_body(request)
        action = body.get("action")
        params = body.get("params")
        if not isinstance(action, str) or not isinstance(params, dict):
            return JSONResponse({"error": "bad_submit"}, status_code=400)
        try:
            result = await self.request(
                action,
                params,
                start_within=float(body.get("start_within", 10.0)),
                timeout=float(body.get("timeout", 15.0)),
            )
        except BridgeError as e:
            return JSONResponse({"ok": False, "error": {"code": e.code, "params": e.params}})
        return JSONResponse({"ok": True, "result": result})

    async def _hub_status(self, request: Request) -> Response:
        return JSONResponse(await self.settled_status())


async def _json_body(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}
