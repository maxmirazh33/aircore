"""Shared entity behaviour: binding to the device."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AcCoordinator


class AcEntity(CoordinatorEntity[AcCoordinator]):
    """An entity belonging to a single air conditioner."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: AcCoordinator, entry_id: str, name: str) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._device_name = name

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.device.mac)},
            name=self._device_name,
            manufacturer="Broadlink",
            model="Air conditioner",
            connections={("mac", self.coordinator.device.mac)},
        )

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success
