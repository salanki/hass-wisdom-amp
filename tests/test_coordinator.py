from __future__ import annotations

import copy

from custom_components.wisdom_amp.coordinator import (
    _build_jack_groups,
    async_discover,
)

from .helpers import EAST_DECK_CFG, FakeClient


async def test_discover_identity_channels_and_jack_groups():
    client = FakeClient()
    info = await async_discover(client)
    assert info.mac == "8C:1F:64:D5:6C:86"
    assert info.firmware == "03.02.71"
    assert info.dante_name == "Wisdom-East-Deck"
    # ch0 active (named), ch1 unused (empty name)
    assert [c.active for c in info.channels] == [True, False]
    assert info.channels[0].name == "East Deck L150"
    # one speaker on jacks 1/2/3 -> one group
    assert len(info.jack_groups) == 1
    assert info.jack_groups[0].jacks == (1, 2, 3)


def test_jack_groups_collapse_identical_and_keep_distinct():
    cfg = copy.deepcopy(EAST_DECK_CFG)
    cfg["speakers"] = [
        {"name": "L", "definition": {"drivers": [{"jack": 1}, {"jack": 2}]}},
        {"name": "R", "definition": {"drivers": [{"jack": 1}, {"jack": 2}]}},
        {"name": "Sub", "definition": {"drivers": [{"jack": 3}]}},
    ]
    groups = _build_jack_groups(cfg)
    keys = {g.key: g for g in groups}
    assert set(keys) == {"jacks_1_2", "jacks_3"}
    assert keys["jacks_1_2"].name == "L / R"  # identical jack-sets collapse


async def test_discover_requires_mac():
    client = FakeClient(fw={"app_ver": "x"})  # no MAC
    import pytest

    from custom_components.wisdom_amp.pywisdomamp import WisdomConnectionError

    with pytest.raises(WisdomConnectionError):
        await async_discover(client)


async def test_setup_builds_status(setup_integration):
    entry, client = await setup_integration()
    status = entry.runtime_data.coordinator.data
    assert status.gain == -10.0
    assert status.channels[0].trim == 0.0
    assert status.power == "off"


async def test_channel_write_uses_indexed_key_preserving_eq(setup_integration):
    entry, client = await setup_integration()
    coord = entry.runtime_data.coordinator
    await coord.async_set_channel_field(0, "trim", -3.0)
    # Must use the indexed single-channel key (NOT the whole-array form, which
    # clears channels on the device), carrying the full channel object.
    sent = client.cfgsets[-1]
    assert "channels[0]" in sent
    assert "channels" not in sent  # never the destructive whole-array form
    assert sent["channels[0]"]["trim"] == -3.0
    assert sent["channels[0]"]["equalizers"][0]["fc"] == 60  # EQ preserved
    # the other channel is left untouched on the device
    assert client.cfg["channels"][1]["name"] == ""
    assert len(client.cfg["channels"]) == 2


async def test_mute_mask_from_jack_groups(setup_integration):
    entry, client = await setup_integration()
    coord = entry.runtime_data.coordinator
    key = coord.info.jack_groups[0].key  # jacks 1,2,3
    await coord.async_set_group_mute(key, True)
    assert client.mutes[-1] == 0b111  # bits for jacks 1,2,3
    await coord.async_set_group_mute(key, False)
    assert client.mutes[-1] == 0


async def test_mute_failure_leaves_state_unchanged(setup_integration):
    import pytest

    from custom_components.wisdom_amp.pywisdomamp import WisdomError

    entry, client = await setup_integration()
    coord = entry.runtime_data.coordinator
    key = coord.info.jack_groups[0].key

    async def _boom(mask):
        raise WisdomError("send failed")

    client.async_setmutes = _boom
    with pytest.raises(WisdomError):
        await coord.async_set_group_mute(key, True)
    assert coord._muted_groups == set()  # not committed on failure
