"""Additional measurements of the air conditioner."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_NAME,
    FAN_SPEEDS,
    MODE_NAMES,
    SWING_H_POSITIONS,
    SWING_POSITIONS,
)
from .device import AcState
from .entity import AcEntity


def _fan_speed(state: AcState) -> str:
    """Fan speed as a single value: mute and turbo are separate flags on the device."""
    if state.mute:
        return "mute"
    if state.turbo:
        return "turbo"
    return FAN_SPEEDS.get(state.fan_speed, "auto")


@dataclass(frozen=True, kw_only=True)
class AcSensorDescription(SensorEntityDescription):
    """Measurement description and how to obtain it."""

    value: Callable[[AcState], float | str | None]
    needs_trust: bool = False


SENSORS: tuple[AcSensorDescription, ...] = (
    AcSensorDescription(
        key="compressor_load",
        translation_key="compressor_load",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        needs_trust=True,
        value=lambda state: state.compressor_load,
    ),
    AcSensorDescription(
        key="coil_temperature",
        translation_key="coil_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda state: state.coil_temperature,
    ),
    AcSensorDescription(
        key="ambient_temperature",
        translation_key="ambient_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda state: state.ambient_temperature,
    ),
    AcSensorDescription(
        key="target_temperature",
        translation_key="target_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda state: state.target_temperature,
    ),
    AcSensorDescription(
        key="mode",
        translation_key="mode",
        device_class=SensorDeviceClass.ENUM,
        options=["off", *MODE_NAMES.values()],
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda state: MODE_NAMES.get(state.mode, "auto") if state.power else "off",
    ),
    AcSensorDescription(
        key="fan_speed",
        translation_key="fan_speed",
        device_class=SensorDeviceClass.ENUM,
        options=["auto", "mute", "low", "medium", "high", "turbo"],
        entity_category=EntityCategory.DIAGNOSTIC,
        value=_fan_speed,
    ),
    AcSensorDescription(
        key="swing",
        translation_key="swing",
        device_class=SensorDeviceClass.ENUM,
        options=list(SWING_POSITIONS.values()),
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda state: SWING_POSITIONS.get(state.fixation_vertical, "auto"),
    ),
    AcSensorDescription(
        key="swing_horizontal",
        translation_key="swing_horizontal",
        device_class=SensorDeviceClass.ENUM,
        options=list(SWING_H_POSITIONS.values()),
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda state: SWING_H_POSITIONS.get(state.fixation_horizontal, "off"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    name = entry.data.get(CONF_NAME, entry.title)
    async_add_entities(
        AcSensor(coordinator, entry.entry_id, name, description) for description in SENSORS
    )


class AcSensor(AcEntity, SensorEntity):
    """A single device measurement."""

    entity_description: AcSensorDescription

    def __init__(self, coordinator, entry_id, name, description: AcSensorDescription) -> None:
        super().__init__(coordinator, entry_id, name)
        self.entity_description = description

    @property
    def unique_id(self) -> str:
        return f"{self.coordinator.device.mac}_{self.entity_description.key}"

    @property
    def native_value(self) -> float | str | None:
        state = self.coordinator.state
        if self.entity_description.needs_trust and not state.extras_trusted:
            return None
        return self.entity_description.value(state)
