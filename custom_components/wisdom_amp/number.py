"""Number platform: system gain and per-channel trim / delay."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory, UnitOfSoundPressure, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import WisdomConfigEntry
from .const import (
    DELAY_MAX,
    DELAY_MIN,
    DELAY_STEP,
    GAIN_MAX,
    GAIN_MIN,
    GAIN_STEP,
    TRIM_MAX,
    TRIM_MIN,
    TRIM_STEP,
)
from .coordinator import WisdomCoordinator
from .entity import WisdomEntity
from .pywisdomamp import ChannelInfo, WisdomError


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WisdomConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    entities: list[NumberEntity] = [WisdomGainNumber(coordinator)]
    for channel in coordinator.active_channels:
        entities.append(WisdomChannelTrimNumber(coordinator, channel))
        entities.append(WisdomChannelDelayNumber(coordinator, channel))
    async_add_entities(entities)


class WisdomGainNumber(WisdomEntity, NumberEntity):
    """System (master) gain in dB."""

    _attr_mode = NumberMode.SLIDER
    _attr_native_min_value = GAIN_MIN
    _attr_native_max_value = GAIN_MAX
    _attr_native_step = GAIN_STEP
    _attr_native_unit_of_measurement = UnitOfSoundPressure.DECIBEL
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:tune-vertical"
    _attr_translation_key = "system_gain"

    def __init__(self, coordinator: WisdomCoordinator) -> None:
        super().__init__(coordinator, "system_gain")

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data
        return data.gain if data is not None else None

    async def async_set_native_value(self, value: float) -> None:
        clamped = min(GAIN_MAX, max(GAIN_MIN, value))
        try:
            await self.coordinator.async_set_gain(clamped)
        except WisdomError as err:
            raise HomeAssistantError(f"Failed to set system gain: {err}") from err


class _WisdomChannelNumber(WisdomEntity, NumberEntity):
    """Base for a per-channel field (trim / delay)."""

    _attr_mode = NumberMode.SLIDER
    _attr_entity_category = EntityCategory.CONFIG
    _field: str
    _label: str

    def __init__(self, coordinator: WisdomCoordinator, channel: ChannelInfo) -> None:
        super().__init__(coordinator, f"channel_{channel.index}_{self._field}")
        self._index = channel.index
        self._attr_name = f"{channel.name} {self._label}"

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data
        if data is None:
            return None
        state = data.channels.get(self._index)
        return getattr(state, self._field) if state is not None else None

    async def _write(self, value: float) -> None:
        try:
            await self.coordinator.async_set_channel_field(
                self._index, self._field, value
            )
        except WisdomError as err:
            raise HomeAssistantError(
                f"Failed to set channel {self._field}: {err}"
            ) from err


class WisdomChannelTrimNumber(_WisdomChannelNumber):
    _field = "trim"
    _label = "trim"
    _attr_native_min_value = TRIM_MIN
    _attr_native_max_value = TRIM_MAX
    _attr_native_step = TRIM_STEP
    _attr_native_unit_of_measurement = UnitOfSoundPressure.DECIBEL
    _attr_icon = "mdi:tune"

    async def async_set_native_value(self, value: float) -> None:
        await self._write(min(TRIM_MAX, max(TRIM_MIN, value)))


class WisdomChannelDelayNumber(_WisdomChannelNumber):
    _field = "delay"
    _label = "delay"
    _attr_native_min_value = DELAY_MIN
    _attr_native_max_value = DELAY_MAX
    _attr_native_step = DELAY_STEP
    _attr_native_unit_of_measurement = UnitOfTime.MILLISECONDS
    _attr_icon = "mdi:timer-outline"

    async def async_set_native_value(self, value: float) -> None:
        await self._write(min(DELAY_MAX, max(DELAY_MIN, value)))
