from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers.device_registry import format_mac
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wisdom_amp.const import DOMAIN

from .helpers import MAC, FakeClient


@pytest.hookimpl(trylast=True)
def pytest_runtest_setup(item):
    """Re-enable sockets for tests marked ``live`` so they reach a real amp."""
    if item.get_closest_marker("live") is not None:
        import socket

        import pytest_socket

        pytest_socket.enable_socket()
        socket.socket.connect = pytest_socket._true_connect


@pytest.fixture(scope="session", autouse=True)
def _prewarm_aiohttp_shutdown_thread():
    """Pre-create + close an aiohttp session once so the daemon shutdown thread
    exists before pytest-homeassistant-custom-component's per-test thread check."""
    import asyncio

    import aiohttp

    async def _poke():
        session = aiohttp.ClientSession()
        await session.close()

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_poke())
    finally:
        loop.close()
    yield


@pytest.fixture
def fake_client() -> FakeClient:
    return FakeClient()


@pytest.fixture
def setup_integration(hass, enable_custom_integrations, monkeypatch):
    """Set up the integration backed by a FakeClient; returns (entry, client)."""

    async def _setup(client: FakeClient | None = None):
        client = client or FakeClient()
        monkeypatch.setattr(
            "custom_components.wisdom_amp.WisdomClient",
            lambda *a, **k: client,
        )
        monkeypatch.setattr(
            "custom_components.wisdom_amp.async_get_clientsession",
            lambda hass: MagicMock(),
        )
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_HOST: "10.0.0.9", CONF_PORT: 81},
            unique_id=format_mac(MAC),
            title="Wisdom East Deck",
        )
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        return entry, client

    return _setup
