"""Integration for air conditioners with a Broadlink WiFi module."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import (
    CONF_DEBUG_PACKETS,
    CONF_EXTRA_SENSORS,
    CONF_HOST,
    CONF_MAC,
    CONF_NAME,
    CONF_PORT,
    CONF_SCAN_INTERVAL_SENSOR,
    CONF_SCAN_INTERVAL_STATE,
    CONF_TIMEOUT,
    DEFAULT_DEBUG_PACKETS,
    DEFAULT_EXTRA_SENSORS,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL_SENSOR,
    DEFAULT_SCAN_INTERVAL_STATE,
    DEFAULT_TIMEOUT,
)
from .coordinator import AcCoordinator
from .device import AcDevice

type AcConfigEntry = ConfigEntry[AcCoordinator]

PLATFORMS = [Platform.CLIMATE, Platform.BINARY_SENSOR, Platform.SENSOR, Platform.SWITCH]


async def async_setup_entry(hass: HomeAssistant, entry: AcConfigEntry) -> bool:
    """Set up the device and its entities."""
    device = AcDevice(
        entry.data[CONF_HOST],
        entry.data[CONF_MAC],
        entry.data.get(CONF_PORT, DEFAULT_PORT),
        entry.options.get(CONF_TIMEOUT, DEFAULT_TIMEOUT),
    )

    coordinator = AcCoordinator(
        hass,
        device,
        entry.data.get(CONF_NAME, entry.title),
        entry.options.get(CONF_SCAN_INTERVAL_STATE, DEFAULT_SCAN_INTERVAL_STATE),
        entry.options.get(CONF_SCAN_INTERVAL_SENSOR, DEFAULT_SCAN_INTERVAL_SENSOR),
        entry.options.get(CONF_DEBUG_PACKETS, DEFAULT_DEBUG_PACKETS),
    )
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, _platforms(entry))
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AcConfigEntry) -> bool:
    """Tear the device down."""
    return await hass.config_entries.async_unload_platforms(entry, _platforms(entry))


def _platforms(entry: AcConfigEntry) -> list[Platform]:
    """Platforms of this entry: extra sensors are optional."""
    if entry.options.get(CONF_EXTRA_SENSORS, DEFAULT_EXTRA_SENSORS):
        return list(PLATFORMS)
    return [Platform.CLIMATE]


async def _async_reload(hass: HomeAssistant, entry: AcConfigEntry) -> None:
    """Reload after options were changed."""
    await hass.config_entries.async_reload(entry.entry_id)
