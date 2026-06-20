"""The Wisdom SA-3 amplifier integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TypeAlias

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DEFAULT_PORT
from .coordinator import WisdomCoordinator, async_discover
from .pywisdomamp import WisdomClient, WisdomError

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
]


@dataclass
class WisdomRuntimeData:
    client: WisdomClient
    coordinator: WisdomCoordinator


WisdomConfigEntry: TypeAlias = ConfigEntry[WisdomRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: WisdomConfigEntry) -> bool:
    client = WisdomClient(
        entry.data[CONF_HOST],
        entry.data.get(CONF_PORT, DEFAULT_PORT),
        async_get_clientsession(hass),
    )
    try:
        await client.async_connect()
        info = await async_discover(client)
        coordinator = WisdomCoordinator(hass, client, info)
        await coordinator.async_config_entry_first_refresh()
        entry.runtime_data = WisdomRuntimeData(client=client, coordinator=coordinator)
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except WisdomError as err:
        await client.async_close()
        raise ConfigEntryNotReady(str(err)) from err
    except Exception:
        await client.async_close()
        raise
    return True


async def async_unload_entry(hass: HomeAssistant, entry: WisdomConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.client.async_close()
    return unload_ok
