from __future__ import annotations

import pytest
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import format_mac

from .helpers import MAC

NORM = format_mac(MAC)


def _eid(hass, domain, key):
    return er.async_get(hass).async_get_entity_id(domain, "wisdom_amp", f"{NORM}_{key}")


async def test_gain_number(hass, setup_integration):
    entry, client = await setup_integration()
    eid = _eid(hass, "number", "system_gain")
    assert float(hass.states.get(eid).state) == -10.0
    await hass.services.async_call(
        "number", "set_value", {"entity_id": eid, "value": -20}, blocking=True
    )
    assert {"gain": -20.0} in client.cfgsets
    assert float(hass.states.get(eid).state) == -20.0


async def test_gain_out_of_range_rejected(hass, setup_integration):
    entry, client = await setup_integration()
    eid = _eid(hass, "number", "system_gain")
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "number", "set_value", {"entity_id": eid, "value": 6}, blocking=True
        )
    assert client.cfgsets == []


async def test_channel_trim_number(hass, setup_integration):
    entry, client = await setup_integration()
    eid = _eid(hass, "number", "channel_0_trim")
    assert hass.states.get(eid) is not None
    await hass.services.async_call(
        "number", "set_value", {"entity_id": eid, "value": -3}, blocking=True
    )
    assert client.cfgsets[-1]["channels[0]"]["trim"] == -3.0


async def test_unused_channel_has_no_entities(hass, setup_integration):
    entry, client = await setup_integration()
    assert _eid(hass, "number", "channel_1_trim") is None


async def test_power_switch(hass, setup_integration):
    entry, client = await setup_integration()
    eid = _eid(hass, "switch", "power")
    assert hass.states.get(eid).state == STATE_OFF
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": eid}, blocking=True
    )
    assert client.powers == [True]
    assert hass.states.get(eid).state == STATE_ON


async def test_mute_switch(hass, setup_integration):
    entry, client = await setup_integration()
    eid = _eid(hass, "switch", "mute_jacks_1_2_3")
    assert hass.states.get(eid).state == STATE_OFF
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": eid}, blocking=True
    )
    assert client.mutes[-1] == 0b111
    assert hass.states.get(eid).state == STATE_ON


async def test_diagnostic_sensors(hass, setup_integration):
    entry, client = await setup_integration()
    assert hass.states.get(_eid(hass, "sensor", "power_state")).state == "off"
    assert hass.states.get(_eid(hass, "sensor", "firmware")).state == "03.02.71"
    assert hass.states.get(_eid(hass, "sensor", "dante_name")).state == "Wisdom-East-Deck"


async def test_unload_closes_client(hass, setup_integration):
    entry, client = await setup_integration()
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert client.closed is True
