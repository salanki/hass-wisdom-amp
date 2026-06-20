"""Diagnostic sensors: power state, firmware, Dante name."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import WisdomConfigEntry
from .coordinator import WisdomCoordinator
from .entity import WisdomEntity
from .pywisdomamp import (
    POWER_OFF,
    POWER_ON,
    POWER_TRANSITIONING,
    POWER_UNKNOWN,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WisdomConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        [
            WisdomPowerStateSensor(coordinator),
            WisdomFirmwareSensor(coordinator),
            WisdomDanteNameSensor(coordinator),
        ]
    )


class WisdomPowerStateSensor(WisdomEntity, SensorEntity):
    _attr_translation_key = "power_state"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [POWER_ON, POWER_OFF, POWER_TRANSITIONING, POWER_UNKNOWN]
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: WisdomCoordinator) -> None:
        super().__init__(coordinator, "power_state")

    @property
    def native_value(self) -> str | None:
        data = self.coordinator.data
        return data.power if data is not None else None


class WisdomFirmwareSensor(WisdomEntity, SensorEntity):
    _attr_translation_key = "firmware"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:chip"

    def __init__(self, coordinator: WisdomCoordinator) -> None:
        super().__init__(coordinator, "firmware")

    @property
    def native_value(self) -> str | None:
        return self.coordinator.info.firmware


class WisdomDanteNameSensor(WisdomEntity, SensorEntity):
    _attr_translation_key = "dante_name"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:lan"

    def __init__(self, coordinator: WisdomCoordinator) -> None:
        super().__init__(coordinator, "dante_name")

    @property
    def native_value(self) -> str | None:
        return self.coordinator.info.dante_name
