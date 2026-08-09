"""Compressor running indicator."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_NAME
from .entity import AcEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    name = entry.data.get(CONF_NAME, entry.title)
    async_add_entities([AcCompressor(coordinator, entry.entry_id, name)])


class AcCompressor(AcEntity, BinarySensorEntity):
    """Whether the compressor is running right now.

    Out of the box the air conditioner reports only «on / off», which leaves it unclear
    whether it is cooling or merely spinning the fan. This flag comes from the sensor
    packet and reflects actual work.
    """

    _attr_translation_key = "compressor"
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    @property
    def unique_id(self) -> str:
        return f"{self.coordinator.device.mac}_compressor"

    @property
    def is_on(self) -> bool | None:
        state = self.coordinator.state
        return state.compressor if state.extras_trusted else None
