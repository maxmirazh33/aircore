"""Diagnostics for bug reports."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_HOST, CONF_MAC

TO_REDACT = {CONF_HOST, CONF_MAC, "unique_id"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Collect device state and raw packets.

    Raw packets are the most valuable part of a report: they show what the device
    actually sent, without guesswork about how the integration interpreted it.
    """
    coordinator = entry.runtime_data
    state = coordinator.state

    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "state": {
            "power": state.power,
            "mode": state.mode,
            "target_temperature": state.target_temperature,
            "fan_speed": state.fan_speed,
            "mute": state.mute,
            "turbo": state.turbo,
            "sleep": state.sleep,
            "ifeel": state.ifeel,
            "display": state.display,
            "mildew": state.mildew,
            "health": state.health,
            "clean": state.clean,
            "fixation_vertical": state.fixation_vertical,
            "fixation_horizontal": state.fixation_horizontal,
            "ambient_temperature": state.ambient_temperature,
            "compressor": state.compressor,
            "compressor_load": state.compressor_load,
            "coil_temperature": state.coil_temperature,
        },
        "raw": {
            "state": state.raw_state.hex() if state.raw_state else None,
            "sensor": state.raw_sensor.hex() if state.raw_sensor else None,
        },
    }
