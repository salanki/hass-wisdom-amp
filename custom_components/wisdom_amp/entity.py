"""Base entity for the Wisdom SA-3 amplifier integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import (
    CONNECTION_NETWORK_MAC,
    DeviceInfo,
    format_mac,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import WisdomCoordinator


class WisdomEntity(CoordinatorEntity[WisdomCoordinator]):
    """Common device wiring for all Wisdom amp entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: WisdomCoordinator, key: str) -> None:
        super().__init__(coordinator)
        mac = coordinator.info.mac
        self._attr_unique_id = f"{format_mac(mac)}_{key}"

    @property
    def device_info(self) -> DeviceInfo:
        info = self.coordinator.info
        connections = set()
        if info.mac:
            connections.add((CONNECTION_NETWORK_MAC, format_mac(info.mac)))
        return DeviceInfo(
            identifiers={(DOMAIN, format_mac(info.mac))},
            name=info.name,
            manufacturer="Wisdom Audio",
            model=info.model,
            sw_version=info.firmware,
            connections=connections,
        )
