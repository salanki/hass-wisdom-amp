"""Discovery and polling for a single Wisdom SA-3 amplifier."""

from __future__ import annotations

import asyncio
import copy
import logging
from dataclasses import replace
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .pywisdomamp import (
    ChannelInfo,
    ChannelState,
    JackGroup,
    WisdomClient,
    WisdomConnectionError,
    WisdomInfo,
    WisdomStatus,
    WisdomError,
)

_LOGGER = logging.getLogger(__name__)


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _dante_name(resp: Any) -> str | None:
    if isinstance(resp, str):
        return resp or None
    if isinstance(resp, dict):
        for key in ("friendlyName", "name", "danteName", "friendly_name"):
            val = resp.get(key)
            if isinstance(val, str) and val:
                return val
    return None


def _build_jack_groups(cfg: dict[str, Any]) -> tuple[JackGroup, ...]:
    """Group speakers by their driver jack-set (identical sets share one mute)."""
    by_key: dict[str, JackGroup] = {}
    for sp in cfg.get("speakers", []):
        drivers = sp.get("definition", {}).get("drivers", [])
        jacks = tuple(
            sorted({d.get("jack") for d in drivers if isinstance(d.get("jack"), int)})
        )
        if not jacks:
            continue
        key = "jacks_" + "_".join(str(j) for j in jacks)
        name = sp.get("name") or f"Jacks {', '.join(str(j) for j in jacks)}"
        if key in by_key:
            existing = by_key[key]
            by_key[key] = replace(existing, name=f"{existing.name} / {name}")
        else:
            by_key[key] = JackGroup(key=key, name=name, jacks=jacks)
    return tuple(by_key.values())


async def async_discover(client: WisdomClient) -> WisdomInfo:
    """Read identity + topology once at setup."""
    fw = await client.async_get_fwinfo()
    mac = fw.get("MAC")
    if not mac:
        raise WisdomConnectionError("amplifier did not report a MAC address")

    try:
        dante = await client.async_get_dante_info()
    except WisdomError:
        dante = {}
    cfg = await client.async_cfgget()

    channels = tuple(
        ChannelInfo(index=i, name=(c.get("name") or "").strip(), active=bool((c.get("name") or "").strip()))
        for i, c in enumerate(cfg.get("channels", []))
    )
    return WisdomInfo(
        mac=mac,
        firmware=fw.get("app_ver"),
        platform=fw.get("app_plfm"),
        hostname=cfg.get("network", {}).get("hostname"),
        dante_name=_dante_name(dante),
        channels=channels,
        jack_groups=_build_jack_groups(cfg),
    )


class WisdomCoordinator(DataUpdateCoordinator[WisdomStatus]):
    """Polls amp config; owns the client, refresh scheduling, and mute mask."""

    def __init__(
        self, hass: HomeAssistant, client: WisdomClient, info: WisdomInfo
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{info.mac}",
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self.client = client
        self.info = info
        self._muted_groups: set[str] = set()
        self._write_lock = asyncio.Lock()
        client.set_power_callback(self._on_power)
        client.set_cfg_changed_callback(self._on_cfg_changed)
        client.set_reconnect_callback(self._on_reconnect)

    @property
    def active_channels(self) -> list[ChannelInfo]:
        return [c for c in self.info.channels if c.active]

    async def _async_update_data(self) -> WisdomStatus:
        try:
            cfg = await self.client.async_cfgget()
        except WisdomConnectionError as err:
            raise UpdateFailed(str(err)) from err
        return self._status_from_cfg(cfg)

    def _status_from_cfg(self, cfg: dict[str, Any]) -> WisdomStatus:
        channels = {
            i: ChannelState(index=i, trim=_num(c.get("trim")), delay=_num(c.get("delay")))
            for i, c in enumerate(cfg.get("channels", []))
        }
        return WisdomStatus(
            power=self.client.power,
            gain=_num(cfg.get("gain")),
            channels=channels,
            muted_groups=frozenset(self._muted_groups),
        )

    # -- push callbacks (run on the loop from the client reader task) ----

    @callback
    def _on_power(self, power: str) -> None:
        if self.data is not None:
            self.async_set_updated_data(replace(self.data, power=power))

    @callback
    def _on_cfg_changed(self) -> None:
        self.hass.async_create_task(self.async_request_refresh())

    @callback
    def _on_reconnect(self) -> None:
        # Device reset transient mutes on reconnect — clear our model to match.
        self._muted_groups.clear()
        if self.data is not None:
            self.async_set_updated_data(
                replace(self.data, muted_groups=frozenset())
            )
        self.hass.async_create_task(self.async_request_refresh())

    # -- control helpers -------------------------------------------------

    async def async_set_gain(self, value: float) -> None:
        await self.client.async_cfgset({"gain": value})
        if self.data is not None:
            self.async_set_updated_data(replace(self.data, gain=value))
        await self.async_request_refresh()

    async def async_set_channel_field(
        self, index: int, field: str, value: float
    ) -> None:
        """Update one channel field via the device's INDEXED write.

        The correct write is ``cfgset {"channels[N]": {<full channel object>}}``
        (exactly what the SA-3 web app sends). The whole-array form
        ``cfgset {"channels": [...]}`` does NOT merge/replace — it **clears** the
        channel list on the device. We read fresh under a lock, deep-copy the one
        channel object (preserving its equalizers/source/etc.), change the single
        field, and send it back under the indexed key. The brief read→write window
        where an external (web-UI) edit could be lost cannot be fully closed
        without firmware revision IDs.
        """
        async with self._write_lock:
            cfg = await self.client.async_cfgget()
            channels = cfg.get("channels", [])
            if index >= len(channels):
                raise WisdomError(f"channel {index} no longer exists")
            channel = copy.deepcopy(channels[index])
            channel[field] = value
            await self.client.async_cfgset({f"channels[{index}]": channel})
        if self.data is not None and index in self.data.channels:
            new_ch = dict(self.data.channels)
            new_ch[index] = replace(new_ch[index], **{field: value})
            self.async_set_updated_data(replace(self.data, channels=new_ch))
        await self.async_request_refresh()

    async def async_set_power(self, on: bool) -> None:
        await self.client.async_power(on)
        # Real state arrives via the pushed pwrstate frame.

    def _mask_for(self, groups: set[str]) -> int:
        by_key = {g.key: g for g in self.info.jack_groups}
        mask = 0
        for key in groups:
            group = by_key.get(key)
            if group:
                for jack in group.jacks:
                    mask |= 1 << (jack - 1)
        return mask

    def mute_mask(self) -> int:
        return self._mask_for(self._muted_groups)

    async def async_set_group_mute(self, key: str, mute: bool) -> None:
        # Compute the desired state, send it, and only commit to our model on a
        # successful write — otherwise our mask could drift ahead of the device.
        desired = set(self._muted_groups)
        if mute:
            desired.add(key)
        else:
            desired.discard(key)
        await self.client.async_setmutes(self._mask_for(desired))
        self._muted_groups = desired
        if self.data is not None:
            self.async_set_updated_data(
                replace(self.data, muted_groups=frozenset(desired))
            )
