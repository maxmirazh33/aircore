"""Entity checks on a fully set up integration."""

from dataclasses import replace
import logging
from unittest.mock import patch

from homeassistant.components.climate import (
    ATTR_FAN_MODE,
    ATTR_HVAC_MODE,
    ATTR_SWING_HORIZONTAL_MODE,
    ATTR_SWING_MODE,
    SERVICE_SET_FAN_MODE,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_SWING_HORIZONTAL_MODE,
    SERVICE_SET_SWING_MODE,
    SERVICE_SET_TEMPERATURE,
    HVACMode,
)
from homeassistant.components.climate import (
    DOMAIN as CLIMATE_DOMAIN,
)
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_TEMPERATURE,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
import pytest

from custom_components.aircore.const import (
    CONF_DEBUG_PACKETS,
    CONF_EXTRA_SENSORS,
    CONF_SCAN_INTERVAL_STATE,
)
from custom_components.aircore.device import AcError, AcState

from .data import SENSOR_WORKING, STATE_SAMPLE

CLIMATE = "climate.air_conditioner"


@pytest.fixture
def mock_device():
    """A device that answers with captured packets and records writes.

    Written state is copied: the coordinator hands over one and the same object and
    refreshes it right after the write, so a stored reference would show the reading
    that followed instead of what was sent.
    """
    written: list[AcState] = []

    def remember(state: AcState) -> None:
        written.append(replace(state))

    with (
        patch("custom_components.aircore.device.AcDevice.authenticate"),
        patch("custom_components.aircore.device.AcDevice.read_state", return_value=STATE_SAMPLE),
        patch("custom_components.aircore.device.AcDevice.read_sensor", return_value=SENSOR_WORKING),
        patch(
            "custom_components.aircore.device.AcDevice.write_state", side_effect=remember
        ) as write,
    ):
        write.written = written
        yield write


@pytest.fixture
async def setup_integration(hass: HomeAssistant, mock_config_entry, mock_device):
    """A configured device with all its entities."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    return mock_config_entry


async def test_entities_created(hass: HomeAssistant, setup_integration) -> None:
    """Every platform is set up: climate, sensors and switches."""
    assert setup_integration.state is ConfigEntryState.LOADED

    climate = hass.states.get(CLIMATE)
    assert climate is not None
    assert climate.state == HVACMode.COOL
    assert climate.attributes[ATTR_TEMPERATURE] == 24

    assert hass.states.get("sensor.air_conditioner_coil_temperature") is not None
    assert hass.states.get("binary_sensor.air_conditioner_compressor") is not None
    assert hass.states.get("switch.air_conditioner_display") is not None


async def test_climate_reports_readings(hass: HomeAssistant, setup_integration) -> None:
    """Readings from the sensor packet reach the climate entity."""
    climate = hass.states.get(CLIMATE)

    assert climate.attributes["current_temperature"] is not None
    assert climate.attributes["fan_mode"] == "mute"
    assert climate.attributes["swing_mode"] == "top"
    assert climate.attributes["swing_horizontal_mode"] == "off"


async def test_set_temperature(hass: HomeAssistant, setup_integration, mock_device) -> None:
    """A new target is sent to the device and shown at once."""
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: CLIMATE, ATTR_TEMPERATURE: 21.5},
        blocking=True,
    )

    assert mock_device.called
    assert mock_device.written[-1].target_temperature == 21.5


async def test_turn_off_and_on(hass: HomeAssistant, setup_integration, mock_device) -> None:
    """Power is switched through both the mode and the dedicated services."""
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: CLIMATE, ATTR_HVAC_MODE: HVACMode.OFF},
        blocking=True,
    )
    assert mock_device.written[-1].power is False

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: CLIMATE, ATTR_HVAC_MODE: HVACMode.HEAT},
        blocking=True,
    )
    state = mock_device.written[-1]
    assert state.power is True
    assert state.mode == 4


async def test_fan_modes_map_to_device_fields(
    hass: HomeAssistant, setup_integration, mock_device
) -> None:
    """Mute and turbo are separate flags rather than fan speeds."""
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_FAN_MODE,
        {ATTR_ENTITY_ID: CLIMATE, ATTR_FAN_MODE: "turbo"},
        blocking=True,
    )
    state = mock_device.written[-1]
    assert state.turbo is True
    assert state.mute is False

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_FAN_MODE,
        {ATTR_ENTITY_ID: CLIMATE, ATTR_FAN_MODE: "mute"},
        blocking=True,
    )
    state = mock_device.written[-1]
    assert state.mute is True
    assert state.turbo is False


async def test_swing_modes(hass: HomeAssistant, setup_integration, mock_device) -> None:
    """Louvre position and horizontal swing are sent separately."""
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_SWING_MODE,
        {ATTR_ENTITY_ID: CLIMATE, ATTR_SWING_MODE: "bottom"},
        blocking=True,
    )
    assert mock_device.written[-1].fixation_vertical == 5

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_SWING_HORIZONTAL_MODE,
        {ATTR_ENTITY_ID: CLIMATE, ATTR_SWING_HORIZONTAL_MODE: "swing"},
        blocking=True,
    )
    assert mock_device.written[-1].fixation_horizontal == 0


async def test_switch_toggles_feature(hass: HomeAssistant, setup_integration, mock_device) -> None:
    """A switch changes exactly its own field of the state."""
    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: "switch.air_conditioner_display"},
        blocking=True,
    )
    assert mock_device.written[-1].display is False

    assert hass.states.get("switch.air_conditioner_sleep_mode") is not None
    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: "switch.air_conditioner_sleep_mode"},
        blocking=True,
    )
    assert mock_device.written[-1].sleep is True


async def test_rejected_command_restores_previous_value(
    hass: HomeAssistant, setup_integration, mock_device
) -> None:
    """When the device refuses, the interface does not keep a value it never accepted."""
    before = hass.states.get(CLIMATE).attributes[ATTR_TEMPERATURE]
    mock_device.side_effect = AcError("refused")

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_TEMPERATURE,
            {ATTR_ENTITY_ID: CLIMATE, ATTR_TEMPERATURE: 30.0},
            blocking=True,
        )
    await hass.async_block_till_done()

    assert hass.states.get(CLIMATE).attributes[ATTR_TEMPERATURE] == before


async def test_compressor_reported(hass: HomeAssistant, setup_integration) -> None:
    """The compressor sensor follows the device, not the power flag alone."""
    compressor = hass.states.get("binary_sensor.air_conditioner_compressor")

    assert compressor.state in (STATE_ON, STATE_OFF)
    assert hass.states.get("sensor.air_conditioner_compressor_output").state != STATE_UNKNOWN


async def test_untrusted_extras_are_empty(
    hass: HomeAssistant, mock_config_entry, mock_device
) -> None:
    """On a foreign byte layout the compressor sensors stay empty instead of lying."""
    packet = bytearray(SENSOR_WORKING)
    packet[0x18] = 40
    off = bytearray(STATE_SAMPLE)
    off[0x12] &= ~0x20

    mock_config_entry.add_to_hass(hass)
    with (
        patch(
            "custom_components.aircore.device.AcDevice.read_state",
            return_value=bytes(off),
        ),
        patch(
            "custom_components.aircore.device.AcDevice.read_sensor",
            return_value=bytes(packet),
        ),
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert hass.states.get("binary_sensor.air_conditioner_compressor").state == STATE_UNKNOWN
    assert hass.states.get("sensor.air_conditioner_compressor_output").state == STATE_UNKNOWN


async def test_extra_sensors_can_be_disabled(
    hass: HomeAssistant, mock_config_entry, mock_device
) -> None:
    """With extra sensors off only the climate entity remains."""
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(mock_config_entry, options={CONF_EXTRA_SENSORS: False})
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(CLIMATE) is not None
    assert hass.states.get("sensor.air_conditioner_coil_temperature") is None
    assert hass.states.get("switch.air_conditioner_display") is None


async def test_unload(hass: HomeAssistant, setup_integration) -> None:
    """The integration unloads without leaving entities behind."""
    assert await hass.config_entries.async_unload(setup_integration.entry_id)
    await hass.async_block_till_done()

    assert setup_integration.state is ConfigEntryState.NOT_LOADED
    assert hass.states.get(CLIMATE).state == STATE_UNAVAILABLE


async def test_setup_retries_when_device_is_silent(hass: HomeAssistant, mock_config_entry) -> None:
    """An unreachable device does not break setup: it is retried."""
    mock_config_entry.add_to_hass(hass)
    with (
        patch("custom_components.aircore.device.AcDevice.authenticate"),
        patch(
            "custom_components.aircore.device.AcDevice.read_state",
            side_effect=AcError("no answer"),
        ),
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_diagnostics_hide_addresses(hass: HomeAssistant, setup_integration) -> None:
    """A report carries the packets but not the address or MAC of the device."""
    from custom_components.aircore.diagnostics import async_get_config_entry_diagnostics

    report = await async_get_config_entry_diagnostics(hass, setup_integration)

    assert report["raw"]["state"] is not None
    assert report["state"]["target_temperature"] == 24
    assert report["entry"]["host"] == "**REDACTED**"
    assert report["entry"]["mac"] == "**REDACTED**"


async def test_dedicated_power_services(
    hass: HomeAssistant, setup_integration, mock_device
) -> None:
    """The unit is switched on and off without touching its mode."""
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: CLIMATE},
        blocking=True,
    )
    assert mock_device.written[-1].power is False

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: CLIMATE},
        blocking=True,
    )
    written = mock_device.written[-1]
    assert written.power is True
    assert written.mode == 1


async def test_changed_options_reload_the_entry(
    hass: HomeAssistant, setup_integration, mock_device
) -> None:
    """New options are applied without restarting Home Assistant."""
    hass.config_entries.async_update_entry(
        setup_integration, options={CONF_SCAN_INTERVAL_STATE: 60, CONF_DEBUG_PACKETS: True}
    )
    await hass.async_block_till_done()

    assert setup_integration.state is ConfigEntryState.LOADED
    assert setup_integration.runtime_data.debug_packets is True


async def test_debug_mode_logs_packets(
    hass: HomeAssistant, setup_integration, mock_device, caplog
) -> None:
    """In debug mode raw packets end up in the log — that is what reports rely on."""
    coordinator = setup_integration.runtime_data
    coordinator.debug_packets = True

    with caplog.at_level(logging.DEBUG, logger="custom_components.aircore.coordinator"):
        await coordinator.async_refresh()

    assert STATE_SAMPLE.hex() in caplog.text
    assert SENSOR_WORKING.hex() in caplog.text


async def test_temperature_and_mode_arrive_together(
    hass: HomeAssistant, setup_integration, mock_device
) -> None:
    """A single call may carry the mode alongside the temperature.

    Automations switch a unit on exactly this way — set the target and the mode in one
    service call. Ignoring the mode left the unit off while it beeped, having accepted
    the packet.
    """
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: CLIMATE, ATTR_HVAC_MODE: HVACMode.OFF},
        blocking=True,
    )

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: CLIMATE, ATTR_TEMPERATURE: 22.0, ATTR_HVAC_MODE: HVACMode.COOL},
        blocking=True,
    )

    written = mock_device.written[-1]
    assert written.power is True
    assert written.mode == 1
    assert written.target_temperature == 22.0


async def test_mode_off_in_a_temperature_call_switches_off(
    hass: HomeAssistant, setup_integration, mock_device
) -> None:
    """The same call with an off mode switches the unit off rather than just retargeting."""
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: CLIMATE, ATTR_TEMPERATURE: 22.0, ATTR_HVAC_MODE: HVACMode.OFF},
        blocking=True,
    )

    assert mock_device.written[-1].power is False


async def test_swing_positions_match_the_device(
    hass: HomeAssistant, setup_integration, mock_device
) -> None:
    """Swinging is what the device reports as zero, not as six.

    Asking for six makes the unit answer zero, and an unknown value used to be shown as
    «auto» — so a swinging louvre was displayed as a fixed automatic position.
    """
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_SWING_MODE,
        {ATTR_ENTITY_ID: CLIMATE, ATTR_SWING_MODE: "swing"},
        blocking=True,
    )
    assert mock_device.written[-1].fixation_vertical == 0

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_SWING_MODE,
        {ATTR_ENTITY_ID: CLIMATE, ATTR_SWING_MODE: "auto"},
        blocking=True,
    )
    assert mock_device.written[-1].fixation_vertical == 7
