"""Climate entity of the air conditioner."""

from __future__ import annotations

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_NAME,
    FAN_SPEEDS,
    FAN_SPEEDS_INVERT,
    MAX_TEMP,
    MIN_TEMP,
    MODE_AUTO,
    MODE_COOL,
    MODE_DRY,
    MODE_FAN,
    MODE_HEAT,
    SWING_H_POSITIONS,
    SWING_H_POSITIONS_INVERT,
    SWING_POSITIONS,
    SWING_POSITIONS_INVERT,
)
from .entity import AcEntity

HVAC_TO_MODE = {
    HVACMode.AUTO: MODE_AUTO,
    HVACMode.COOL: MODE_COOL,
    HVACMode.DRY: MODE_DRY,
    HVACMode.HEAT: MODE_HEAT,
    HVACMode.FAN_ONLY: MODE_FAN,
}
MODE_TO_HVAC = {v: k for k, v in HVAC_TO_MODE.items()}

FAN_MODES = dict(FAN_SPEEDS_INVERT)
FAN_MODES["mute"] = FAN_SPEEDS_INVERT["low"]
FAN_MODES["turbo"] = FAN_SPEEDS_INVERT["high"]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    name = entry.data.get(CONF_NAME, entry.title)
    async_add_entities([AcClimate(coordinator, entry.entry_id, name)])


class AcClimate(AcEntity, ClimateEntity):
    """Control of mode, target temperature, fan and louvres."""

    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = MIN_TEMP
    _attr_max_temp = MAX_TEMP
    _attr_target_temperature_step = 0.5
    _attr_hvac_modes = [
        HVACMode.OFF,
        HVACMode.COOL,
        HVACMode.HEAT,
        HVACMode.DRY,
        HVACMode.FAN_ONLY,
        HVACMode.AUTO,
    ]
    _attr_fan_modes = ["auto", "mute", "low", "medium", "high", "turbo"]
    _attr_swing_modes = list(SWING_POSITIONS_INVERT)
    _attr_swing_horizontal_modes = list(SWING_H_POSITIONS_INVERT)
    _attr_translation_key = "ac"
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.SWING_MODE
        | ClimateEntityFeature.SWING_HORIZONTAL_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    @property
    def unique_id(self) -> str:
        return f"{self.coordinator.device.mac}_climate"

    @property
    def current_temperature(self) -> float | None:
        return self.coordinator.state.ambient_temperature

    @property
    def target_temperature(self) -> float:
        return self.coordinator.state.target_temperature

    @property
    def hvac_mode(self) -> HVACMode:
        if not self.coordinator.state.power:
            return HVACMode.OFF
        return MODE_TO_HVAC.get(self.coordinator.state.mode, HVACMode.AUTO)

    @property
    def fan_mode(self) -> str:
        state = self.coordinator.state
        if state.mute:
            return "mute"
        if state.turbo:
            return "turbo"
        return FAN_SPEEDS.get(state.fan_speed, "auto")

    @property
    def swing_mode(self) -> str:
        return SWING_POSITIONS.get(self.coordinator.state.fixation_vertical, "auto")

    @property
    def swing_horizontal_mode(self) -> str:
        return SWING_H_POSITIONS.get(self.coordinator.state.fixation_horizontal, "off")

    @property
    def extra_state_attributes(self) -> dict:
        state = self.coordinator.state
        return {
            "compressor": state.compressor,
            "compressor_load": state.compressor_load,
            "coil_temperature": state.coil_temperature,
            "ifeel": state.ifeel,
        }

    async def async_set_temperature(self, **kwargs) -> None:
        """Set the target temperature, and the mode when it comes along.

        Home Assistant lets a single call carry the mode as well, and leaves it to the
        integration to apply. Both go to the device in one packet: it takes settings as
        a block anyway, and a separate mode command would be a second beep.
        """
        changes: dict[str, object] = {}

        hvac_mode = kwargs.get(ATTR_HVAC_MODE)
        if hvac_mode is not None:
            if hvac_mode == HVACMode.OFF:
                changes["power"] = False
            else:
                changes["power"] = True
                changes["mode"] = HVAC_TO_MODE[hvac_mode]

        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is not None:
            changes["target_temperature"] = float(temperature)

        if changes:
            await self.coordinator.async_write(**changes)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            await self.coordinator.async_write(power=False)
            return
        await self.coordinator.async_write(power=True, mode=HVAC_TO_MODE[hvac_mode])

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        await self.coordinator.async_write(
            fan_speed=FAN_MODES[fan_mode],
            mute=fan_mode == "mute",
            turbo=fan_mode == "turbo",
        )

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        await self.coordinator.async_write(fixation_vertical=SWING_POSITIONS_INVERT[swing_mode])

    async def async_set_swing_horizontal_mode(self, swing_horizontal_mode: str) -> None:
        await self.coordinator.async_write(
            fixation_horizontal=SWING_H_POSITIONS_INVERT[swing_horizontal_mode]
        )

    async def async_turn_on(self) -> None:
        await self.coordinator.async_write(power=True)

    async def async_turn_off(self) -> None:
        await self.coordinator.async_write(power=False)
