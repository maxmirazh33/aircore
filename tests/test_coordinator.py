"""Polling schedule checks."""

from unittest.mock import MagicMock

from custom_components.aircore.coordinator import AcCoordinator


def _coordinator(hass, state_interval, sensor_interval):
    device = MagicMock()
    return AcCoordinator(hass, device, "Device", state_interval, sensor_interval, False)


async def test_sensor_may_be_polled_more_often_than_settings(hass) -> None:
    """Sensors may be polled more often than settings.

    The step used to be derived from the settings interval, so 30 seconds requested for
    sensors alongside 60 for settings silently became 60 as well.
    """
    coordinator = _coordinator(hass, 60, 30)

    assert coordinator.update_interval.total_seconds() == 30
    assert coordinator._state_every == 2
    assert coordinator._sensor_every == 1


async def test_settings_may_be_polled_more_often_than_sensors(hass) -> None:
    """The reverse ratio holds as well."""
    coordinator = _coordinator(hass, 15, 60)

    assert coordinator.update_interval.total_seconds() == 15
    assert coordinator._state_every == 1
    assert coordinator._sensor_every == 4


async def test_failed_command_restores_previous_state(hass) -> None:
    """When a command is rejected, the interface does not show what is not there.

    Edits are applied ahead of time for responsiveness, so on failure they must be
    rolled back — otherwise a value the device never accepted stays on screen.
    """
    from unittest.mock import MagicMock

    from homeassistant.exceptions import HomeAssistantError
    import pytest

    from custom_components.aircore.device import AcError

    device = MagicMock()
    device.write_state.side_effect = AcError("no connection")
    coordinator = AcCoordinator(hass, device, "Device", 30, 30, False)
    coordinator.state.target_temperature = 24.0

    with pytest.raises(HomeAssistantError):
        await coordinator.async_write(target_temperature=18.0)

    assert coordinator.state.target_temperature == 24.0
