"""Switch platform: amp power and per jack-group mute."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import WisdomConfigEntry
from .coordinator import WisdomCoordinator
from .entity import WisdomEntity
from .pywisdomamp import POWER_OFF, POWER_ON, JackGroup, WisdomError


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WisdomConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    entities: list[SwitchEntity] = [WisdomPowerSwitch(coordinator)]
    entities.extend(
        WisdomMuteSwitch(coordinator, group)
        for group in coordinator.info.jack_groups
    )
    async_add_entities(entities)


class WisdomPowerSwitch(WisdomEntity, SwitchEntity):
    """Amp power (on/off verbs); live state from the pushed pwrstate frame."""

    _attr_translation_key = "power"
    _attr_device_class = SwitchDeviceClass.SWITCH

    def __init__(self, coordinator: WisdomCoordinator) -> None:
        super().__init__(coordinator, "power")

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data
        if data is None:
            return None
        if data.power == POWER_ON:
            return True
        if data.power == POWER_OFF:
            return False
        return None  # transitioning / unknown

    async def async_turn_on(self, **kwargs: Any) -> None:
        try:
            await self.coordinator.async_set_power(True)
        except WisdomError as err:
            raise HomeAssistantError(f"Failed to power on: {err}") from err

    async def async_turn_off(self, **kwargs: Any) -> None:
        try:
            await self.coordinator.async_set_power(False)
        except WisdomError as err:
            raise HomeAssistantError(f"Failed to power off: {err}") from err


class WisdomMuteSwitch(WisdomEntity, SwitchEntity):
    """Mute a jack-group (speakers sharing the same output jacks).

    Mutes are transient on the device (reset on reboot/reconnect); the
    coordinator clears its model on reconnect to match.
    """

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_icon = "mdi:volume-mute"

    def __init__(self, coordinator: WisdomCoordinator, group: JackGroup) -> None:
        super().__init__(coordinator, f"mute_{group.key}")
        self._group_key = group.key
        self._attr_name = f"{group.name} mute"

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data
        if data is None:
            return None
        return self._group_key in data.muted_groups

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)

    async def _set(self, mute: bool) -> None:
        try:
            await self.coordinator.async_set_group_mute(self._group_key, mute)
        except WisdomError as err:
            raise HomeAssistantError(f"Failed to set mute: {err}") from err
