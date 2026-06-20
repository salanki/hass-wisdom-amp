from __future__ import annotations

import asyncio

import pytest

from custom_components.wisdom_amp.pywisdomamp import (
    POWER_ON,
    POWER_TRANSITIONING,
    WisdomClient,
    WisdomConnectionError,
    WisdomTimeoutError,
)


class FakeWS:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.closed = False

    async def send_str(self, s: str) -> None:
        self.sent.append(s)

    async def close(self) -> None:
        self.closed = True


def _client() -> WisdomClient:
    # session unused for these internal-method tests
    return WisdomClient("host", session=object(), request_timeout=0.5)


def test_handle_pwrstate_routes_to_power_callback():
    c = _client()
    seen = []
    c.set_power_callback(seen.append)
    c._handle('pwrstate {"state":1}')
    assert c.power == POWER_ON
    assert seen == [POWER_ON]
    c._handle('pwrstate {"state":2}')
    assert c.power == POWER_TRANSITIONING


def test_handle_unsolicited_cfg_fires_changed_and_caches():
    c = _client()
    fired = []
    c.set_cfg_changed_callback(lambda: fired.append(True))
    c._handle('cfg {"gain":-12}')
    assert c.cfg == {"gain": -12}
    assert fired == [True]


def test_handle_cfg_with_waiter_resolves_and_skips_changed_cb():
    c = _client()
    fired = []
    c.set_cfg_changed_callback(lambda: fired.append(True))
    loop = asyncio.get_event_loop()
    fut = loop.create_future()
    c._waiters["cfg"] = fut
    c._handle('cfg {"gain":-9}')
    assert fut.result() == {"gain": -9}
    assert fired == []  # solicited cfg must not trigger a refresh storm


def test_handle_bare_and_malformed_verbs_do_not_crash():
    c = _client()
    fired = []
    c.set_cfg_changed_callback(lambda: fired.append(True))
    c._handle("cfgbusy")  # bare verb -> treated as config-changed
    c._handle("cfg not-json")  # malformed payload -> ignored, no cache update
    c._handle("rebooting")
    c._handle("log {\"placement\":\"new\",\"log\":\"hi\"}")
    assert fired == [True]  # only cfgbusy
    assert c.cfg is None


async def test_request_resolves_on_matching_verb():
    c = _client()
    c._ws = FakeWS()
    c._ready.set()

    async def _resolve():
        await asyncio.sleep(0.01)
        c._handle('cfg {"gain":-10}')

    asyncio.create_task(_resolve())
    data = await c.async_cfgget()
    assert data == {"gain": -10}
    assert c._ws.sent == ["cfgget"]


async def test_request_timeout_drops_socket():
    c = _client()
    ws = FakeWS()
    c._ws = ws
    c._ready.set()
    with pytest.raises(WisdomTimeoutError):
        await c.async_get_fwinfo()  # nothing resolves it
    assert ws.closed is True  # stream-corrupting timeout forces reconnect


async def test_outbound_command_formatting():
    c = _client()
    c._ws = FakeWS()
    c._ready.set()
    await c.async_setmutes(7)
    await c.async_power(True)
    await c.async_power(False)
    await c.async_cfgset({"gain": -6})
    assert c._ws.sent == ["setmutes 7", "on", "off", 'cfgset {"gain":-6}']


def test_close_fails_pending_waiters():
    c = _client()
    loop = asyncio.get_event_loop()
    fut = loop.create_future()
    c._waiters["cfg"] = fut
    c._fail_waiters(RuntimeError("boom"))
    assert fut.done() and isinstance(fut.exception(), RuntimeError)


async def test_drop_fails_pending_waiter_and_clears_ready():
    c = _client()
    c._ws = FakeWS()
    c._ready.set()
    loop = asyncio.get_event_loop()
    fut = loop.create_future()
    c._waiters["cfg"] = fut
    await c._drop()
    assert fut.done() and isinstance(fut.exception(), WisdomConnectionError)
    assert not c._ready.is_set()


async def test_send_failure_drops_socket():
    class BadWS(FakeWS):
        async def send_str(self, s: str) -> None:
            raise RuntimeError("boom")

    c = _client()
    ws = BadWS()
    c._ws = ws
    c._ready.set()
    with pytest.raises(WisdomConnectionError):
        await c.async_power(True)
    assert ws.closed is True
    assert not c._ready.is_set()
