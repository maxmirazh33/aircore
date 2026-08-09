"""Configuration flow checks."""

from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest

from custom_components.aircore.const import (
    CONF_DEBUG_PACKETS,
    CONF_DEVICE,
    CONF_EXTRA_SENSORS,
    CONF_HOST,
    CONF_MAC,
    CONF_NAME,
    CONF_SCAN_INTERVAL_SENSOR,
    CONF_SCAN_INTERVAL_STATE,
    DOMAIN,
)
from custom_components.aircore.device import AcError

from .data import HOST, MAC, NAME

DISCOVERED = [{"host": HOST, "mac": MAC, "devtype": 0x4E2A}]


@pytest.fixture
def mock_setup():
    with patch("custom_components.aircore.async_setup_entry", return_value=True) as setup:
        yield setup


async def test_discovery_offers_found_device(hass: HomeAssistant, mock_setup) -> None:
    """A discovered device is offered in a list; no address typing required."""
    with (
        patch("custom_components.aircore.config_flow.discover", return_value=DISCOVERED),
        patch("custom_components.aircore.config_flow.AcDevice.authenticate"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "user"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_DEVICE: MAC, CONF_NAME: NAME}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == NAME
    assert result["data"][CONF_HOST] == HOST
    assert result["data"][CONF_MAC] == MAC


async def test_falls_back_to_manual_when_nothing_found(hass: HomeAssistant) -> None:
    """When the network stays silent, manual entry is offered straight away."""
    with patch("custom_components.aircore.config_flow.discover", return_value=[]):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "manual"


async def test_manual_entry_asks_the_device_for_its_mac(hass: HomeAssistant, mock_setup) -> None:
    """Manual entry needs the address only: the MAC comes from the device.

    A probe aimed at one address also gets through a router that drops broadcasts,
    which is the very reason manual entry exists.
    """
    with (
        patch(
            "custom_components.aircore.config_flow.discover", side_effect=[[], DISCOVERED]
        ) as probe,
        patch("custom_components.aircore.config_flow.AcDevice.authenticate"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_NAME: NAME, CONF_HOST: HOST},
        )
        await hass.async_block_till_done()

    assert probe.call_args[0][3] == HOST
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_MAC] == MAC
    assert result["data"][CONF_HOST] == HOST


async def test_silent_address_reported(hass: HomeAssistant) -> None:
    """An address nothing answers from is reported instead of creating a dead entry."""
    with patch("custom_components.aircore.config_flow.discover", return_value=[]):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_NAME: NAME, CONF_HOST: HOST},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "cannot_connect"


async def test_unreachable_device_reported(hass: HomeAssistant) -> None:
    """A device that answers the probe but refuses a session reports an error."""
    with (
        patch("custom_components.aircore.config_flow.discover", side_effect=[[], DISCOVERED]),
        patch(
            "custom_components.aircore.config_flow.AcDevice.authenticate",
            side_effect=AcError("no connection"),
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_NAME: NAME, CONF_HOST: HOST},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "cannot_connect"


async def test_same_device_not_added_twice(
    hass: HomeAssistant, mock_setup, mock_config_entry
) -> None:
    """A device cannot be added twice: it is identified by MAC."""
    mock_config_entry.add_to_hass(hass)

    with (
        patch("custom_components.aircore.config_flow.discover", side_effect=[[], DISCOVERED]),
        patch("custom_components.aircore.config_flow.AcDevice.authenticate"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_NAME: NAME, CONF_HOST: HOST},
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_change_intervals(hass: HomeAssistant, mock_setup, mock_config_entry) -> None:
    """Polling intervals and toggles are changed through the options flow."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_SCAN_INTERVAL_STATE: 15,
            CONF_SCAN_INTERVAL_SENSOR: 60,
            CONF_EXTRA_SENSORS: False,
            CONF_DEBUG_PACKETS: True,
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options[CONF_SCAN_INTERVAL_STATE] == 15
    assert mock_config_entry.options[CONF_SCAN_INTERVAL_SENSOR] == 60
    assert mock_config_entry.options[CONF_EXTRA_SENSORS] is False
    assert mock_config_entry.options[CONF_DEBUG_PACKETS] is True


async def test_manual_entry_chosen_from_the_list(hass: HomeAssistant) -> None:
    """Manual entry stays reachable even when devices were found."""
    with patch("custom_components.aircore.config_flow.discover", return_value=DISCOVERED):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_DEVICE: "manual", CONF_NAME: NAME}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "manual"
