"""Shared test fixtures."""

from unittest.mock import patch

import pytest

from custom_components.aircore.const import (
    CONF_HOST,
    CONF_MAC,
    CONF_NAME,
    CONF_PORT,
    DOMAIN,
)

from .data import HOST, MAC, NAME, PORT

try:
    import pytest_homeassistant_custom_component  # noqa: F401

    pytest_plugins = "pytest_homeassistant_custom_component"
    HA_TEST_ENV = True
except ImportError:
    HA_TEST_ENV = False


if HA_TEST_ENV:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    @pytest.fixture(autouse=True)
    def auto_enable_custom_integrations(enable_custom_integrations):
        """Allow loading the custom integration in every test."""
        yield

    @pytest.fixture
    def mock_config_entry() -> MockConfigEntry:
        """An already configured device."""
        return MockConfigEntry(
            domain=DOMAIN,
            title=NAME,
            unique_id=MAC,
            data={
                CONF_HOST: HOST,
                CONF_MAC: MAC,
                CONF_PORT: PORT,
                CONF_NAME: NAME,
            },
        )


@pytest.fixture
def mock_send():
    """Replaces device I/O while keeping packet decoding real."""
    with patch("custom_components.aircore.device.AcDevice._send") as send:
        yield send
