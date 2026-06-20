from __future__ import annotations

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.device_registry import format_mac
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wisdom_amp.const import DOMAIN

from .helpers import MAC, FakeClient

NORM_MAC = format_mac(MAC)


@pytest.fixture(autouse=True)
def _patch(monkeypatch, enable_custom_integrations):
    monkeypatch.setattr(
        "custom_components.wisdom_amp.config_flow.async_get_clientsession",
        lambda hass: None,
    )

    def _install(client):
        monkeypatch.setattr(
            "custom_components.wisdom_amp.config_flow.WisdomClient",
            lambda *a, **k: client,
        )

    _install(FakeClient())
    return _install


async def test_user_flow_creates_entry(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "10.0.0.9", CONF_PORT: 81}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Wisdom-East-Deck"
    assert result["result"].unique_id == NORM_MAC
    assert result["data"] == {CONF_HOST: "10.0.0.9", CONF_PORT: 81}


async def test_user_flow_cannot_connect(hass, _patch):
    from custom_components.wisdom_amp.pywisdomamp import WisdomConnectionError

    class Dead(FakeClient):
        async def async_connect(self):
            raise WisdomConnectionError("no route")

    _patch(Dead())
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "10.0.0.9"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_no_mac(hass, _patch):
    _patch(FakeClient(fw={"app_ver": "x"}))
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "10.0.0.9"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "no_mac"}


async def test_duplicate_aborts(hass):
    MockConfigEntry(domain=DOMAIN, unique_id=NORM_MAC, data={CONF_HOST: "1.1.1.1"}).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "10.0.0.9"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure_wrong_device(hass, _patch):
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="11:22:33:44:55:66", data={CONF_HOST: "1.1.1.1"}
    )
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "10.0.0.9"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_device"
    assert entry.data[CONF_HOST] == "1.1.1.1"  # unchanged
