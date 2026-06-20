"""Live, read-only tests against a real Wisdom SA-3 amplifier.

- **read-only** — only getFWinfo / getDanteInfo / cfgget; never cfgset/on/off/setmutes.
- **opt-in** — excluded by default; run with ``pytest -m live`` (or ``make test-live``).
- skipped cleanly if ``WISDOM_AMP_HOST`` is unset.

Env: WISDOM_AMP_HOST (required), WISDOM_AMP_PORT (optional, default 81).
"""

from __future__ import annotations

import os

import pytest

from custom_components.wisdom_amp.coordinator import async_discover
from custom_components.wisdom_amp.pywisdomamp import DEFAULT_PORT, WisdomClient

pytestmark = [
    pytest.mark.live,
    pytest.mark.parametrize("expected_lingering_timers", [True]),
    pytest.mark.parametrize("expected_lingering_tasks", [True]),
]


def _host() -> tuple[str, int]:
    host = os.environ.get("WISDOM_AMP_HOST")
    if not host:
        pytest.skip("WISDOM_AMP_HOST not set")
    return host, int(os.environ.get("WISDOM_AMP_PORT", DEFAULT_PORT))


async def test_identity_and_cfg_readable():
    host, port = _host()
    client = WisdomClient(host, port)
    try:
        await client.async_connect()
        fw = await client.async_get_fwinfo()
        cfg = await client.async_cfgget()
    finally:
        await client.async_close()
    assert fw.get("MAC")
    assert "channels" in cfg and "gain" in cfg


async def test_discovery_finds_active_channel():
    host, port = _host()
    client = WisdomClient(host, port)
    try:
        await client.async_connect()
        info = await async_discover(client)
    finally:
        await client.async_close()
    assert info.mac
    assert any(c.active for c in info.channels)
