"""Async client for the Wisdom Audio SA-3 WebSocket control protocol.

The SA-3 exposes an **unauthenticated** WebSocket on ``ws://<ip>:81``. Messages
in both directions are plain text ``"<verb> <json>"`` (some verbs are bare, e.g.
``cfgbusy``). It is a **mixed push/response** stream with **no request IDs**: the
amp pushes ``log`` (a flood on connect), ``pwrstate``, ``cfgbusy``, ``rebooting``,
and even ``cfg`` (after a config apply) unsolicited — the same verbs that also
answer requests. Correlation therefore can't be a naive ``verb -> future`` map.

Design:
* aiohttp ``ws_connect`` (handles handshake / masking / fragmentation) on a
  caller-supplied session — the client never owns the session.
* One **reader task** routes every frame: unsolicited frames go to callbacks;
  request responses resolve at most one outstanding waiter per verb.
* An ``asyncio.Lock`` **serializes request/response exchanges** so only one waiter
  per verb is ever live; concurrent callers coalesce behind the lock.
* A request **timeout drops the socket and reconnects** — a late reply would
  otherwise satisfy the wrong future on this ID-less protocol.
* On every (re)connect: reset transient mutes (``setmutes 0``); on reconnect also
  fail pending waiters and notify the owner to resync.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

import aiohttp

from .exceptions import WisdomConnectionError, WisdomTimeoutError
from .models import POWER_UNKNOWN, power_from_pwrstate

_LOGGER = logging.getLogger(__name__)

DEFAULT_PORT = 81
REQUEST_TIMEOUT = 8.0
MAX_BACKOFF = 30.0


class WisdomClient:
    """Persistent WebSocket client for a single Wisdom SA-3 amplifier."""

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_PORT,
        session: aiohttp.ClientSession | None = None,
        *,
        request_timeout: float = REQUEST_TIMEOUT,
    ) -> None:
        self._host = host
        self._port = port
        self._session = session
        self._request_timeout = request_timeout

        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._reader_task: asyncio.Task | None = None
        self._req_lock = asyncio.Lock()
        self._waiters: dict[str, asyncio.Future] = {}
        self._ready = asyncio.Event()
        self._closing = False
        self._connected_once = False

        self._cfg: dict[str, Any] | None = None
        self._power = POWER_UNKNOWN

        self._power_cb: Callable[[str], None] | None = None
        self._cfg_changed_cb: Callable[[], None] | None = None
        self._reconnect_cb: Callable[[], None] | None = None

    # -- properties / callbacks -----------------------------------------

    @property
    def host(self) -> str:
        return self._host

    @property
    def power(self) -> str:
        return self._power

    @property
    def cfg(self) -> dict[str, Any] | None:
        return self._cfg

    def set_power_callback(self, cb: Callable[[str], None] | None) -> None:
        self._power_cb = cb

    def set_cfg_changed_callback(self, cb: Callable[[], None] | None) -> None:
        self._cfg_changed_cb = cb

    def set_reconnect_callback(self, cb: Callable[[], None] | None) -> None:
        self._reconnect_cb = cb

    @property
    def _url(self) -> str:
        return f"ws://{self._host}:{self._port}"

    # -- lifecycle ------------------------------------------------------

    async def async_connect(self) -> None:
        """Start the reader and wait for the first ready connection."""
        if self._session is None:
            self._session = aiohttp.ClientSession()
            self._owns_session = True
        else:
            self._owns_session = False
        if self._reader_task is None or self._reader_task.done():
            self._reader_task = asyncio.create_task(self._run())
        try:
            await asyncio.wait_for(self._ready.wait(), self._request_timeout)
        except asyncio.TimeoutError as err:
            await self.async_close()
            raise WisdomConnectionError(
                f"could not connect to {self._url}"
            ) from err

    async def async_close(self) -> None:
        """Tear down the reader task and socket; fail pending waiters."""
        self._closing = True
        if self._reader_task is not None:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._reader_task = None
        await self._drop()
        self._fail_waiters(WisdomConnectionError("client closed"))
        if getattr(self, "_owns_session", False) and self._session is not None:
            await self._session.close()
            self._session = None

    async def _drop(self) -> None:
        ws, self._ws = self._ws, None
        self._ready.clear()
        # Fail any in-flight request promptly instead of letting it hang until
        # its own timeout when the socket goes away.
        self._fail_waiters(WisdomConnectionError("connection lost"))
        if ws is not None and not ws.closed:
            try:
                await ws.close()
            except Exception:  # noqa: BLE001 - best-effort
                pass

    def _fail_waiters(self, err: Exception) -> None:
        for fut in list(self._waiters.values()):
            if not fut.done():
                fut.set_exception(err)
        self._waiters.clear()

    # -- reader loop ----------------------------------------------------

    async def _run(self) -> None:
        backoff = 1.0
        while not self._closing:
            try:
                assert self._session is not None
                ws = await self._session.ws_connect(self._url, heartbeat=20)
                self._ws = ws
                self._fail_waiters(WisdomConnectionError("reconnected"))
                self._ready.set()
                # NOTE: we deliberately do NOT send "setmutes 0" here. Mute state
                # is write-only on this protocol (not readable anywhere), and the
                # device keeps mutes across client connections — so forcing them
                # off on reconnect would clobber mutes set elsewhere (e.g. the
                # Wisdom web UI). HA only ever changes mutes on an explicit
                # service call. (Mutes still clear on a device reboot, which we
                # can't observe.)
                if self._connected_once and self._reconnect_cb is not None:
                    self._reconnect_cb()
                self._connected_once = True
                backoff = 1.0

                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        self._handle(msg.data)
                    elif msg.type in (
                        aiohttp.WSMsgType.CLOSED,
                        aiohttp.WSMsgType.CLOSING,
                        aiohttp.WSMsgType.ERROR,
                    ):
                        break
            except asyncio.CancelledError:
                raise
            except Exception as err:  # noqa: BLE001 - keep reader alive
                _LOGGER.debug("Wisdom %s reader error: %s", self._host, err)
            finally:
                await self._drop()
            if self._closing:
                break
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF)

    def _handle(self, data: str) -> None:
        verb, _, body = data.partition(" ")
        payload: Any = None
        if body:
            try:
                payload = json.loads(body)
            except ValueError:
                payload = None  # bare verb or non-JSON tail

        waiter = self._waiters.get(verb)
        from_request = waiter is not None and not waiter.done()
        if from_request:
            # `cfg` is always a FULL current snapshot (cfgget's reply and the
            # post-apply push are identical in shape), so resolving a pending
            # cfgget waiter with any cfg frame yields valid current data — an
            # unsolicited cfg simply satisfies the waiter slightly early. The
            # request lock guarantees only one waiter per verb at a time.
            waiter.set_result(payload)

        if verb == "pwrstate":
            state = payload.get("state") if isinstance(payload, dict) else None
            self._power = power_from_pwrstate(state)
            if self._power_cb is not None:
                self._power_cb(self._power)
        elif verb == "cfg":
            if isinstance(payload, dict):
                self._cfg = payload
                # An unsolicited cfg (after a config apply) means the owner should
                # re-read; a solicited one is already delivered to the waiter.
                if not from_request and self._cfg_changed_cb is not None:
                    self._cfg_changed_cb()
        elif verb == "cfgbusy":
            if self._cfg_changed_cb is not None:
                self._cfg_changed_cb()
        # log / rebooting / others: ignored (rebooting drops the socket anyway)

    # -- requests -------------------------------------------------------

    async def _await_ready(self) -> None:
        try:
            await asyncio.wait_for(self._ready.wait(), self._request_timeout)
        except asyncio.TimeoutError as err:
            raise WisdomConnectionError("not connected") from err

    async def _request(self, verb: str, resp_verb: str) -> Any:
        async with self._req_lock:
            await self._await_ready()
            loop = asyncio.get_running_loop()
            fut: asyncio.Future = loop.create_future()
            self._waiters[resp_verb] = fut
            try:
                await self._send(verb)
                return await asyncio.wait_for(fut, self._request_timeout)
            except asyncio.TimeoutError as err:
                await self._drop()  # stream-corrupting: force a clean reconnect
                raise WisdomTimeoutError(
                    f"no '{resp_verb}' response within {self._request_timeout}s"
                ) from err
            finally:
                self._waiters.pop(resp_verb, None)

    async def _send(self, text: str) -> None:
        ws = self._ws
        if ws is None or ws.closed:
            raise WisdomConnectionError("not connected")
        try:
            await ws.send_str(text)
        except Exception as err:  # noqa: BLE001
            # A failed send means the socket is dead — drop it so the reader
            # reconnects and follow-up calls don't pass _await_ready() against it.
            await self._drop()
            raise WisdomConnectionError(f"send failed: {err}") from err

    async def async_cfgget(self) -> dict[str, Any]:
        data = await self._request("cfgget", "cfg")
        return data if isinstance(data, dict) else {}

    async def async_get_fwinfo(self) -> dict[str, Any]:
        data = await self._request("getFWinfo", "fwinfo")
        return data if isinstance(data, dict) else {}

    async def async_get_dante_info(self) -> dict[str, Any]:
        data = await self._request("getDanteInfo", "updateDanteInfo")
        return data if isinstance(data, dict) else {}

    # -- writes (no direct response; device follows with cfgbusy + cfg) --

    async def async_cfgset(self, partial: dict[str, Any]) -> None:
        await self._await_ready()
        await self._send(f"cfgset {json.dumps(partial, separators=(',', ':'))}")

    async def async_power(self, on: bool) -> None:
        await self._await_ready()
        await self._send("on" if on else "off")

    async def async_setmutes(self, mask: int) -> None:
        await self._await_ready()
        await self._send(f"setmutes {int(mask)}")
