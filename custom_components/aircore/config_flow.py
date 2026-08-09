"""Configuration flow for the integration."""

from __future__ import annotations

from functools import partial

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
import voluptuous as vol

from .const import (
    CONF_DEBUG_PACKETS,
    CONF_DEVICE,
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
    DOMAIN,
    MANUAL_PROBE_TIMEOUT,
    MAX_SCAN_INTERVAL,
    MAX_TIMEOUT,
    MIN_SCAN_INTERVAL,
    MIN_TIMEOUT,
)
from .device import AcDevice, AcError, discover


class BroadlinkAcConfigFlow(ConfigFlow, domain=DOMAIN):
    """Adding an air conditioner: network discovery first, manual entry as a fallback."""

    VERSION = 1

    def __init__(self) -> None:
        self._found: list[dict] = []
        self._errors: dict[str, str] = {}

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        """Offer the devices found on the network."""
        if user_input is not None:
            if user_input[CONF_DEVICE] == "manual":
                return await self.async_step_manual()

            chosen = next((d for d in self._found if d["mac"] == user_input[CONF_DEVICE]), None)
            if chosen is None:
                return await self.async_step_manual()

            return await self._create(
                user_input[CONF_NAME], chosen["host"], chosen["mac"], DEFAULT_PORT
            )

        self._found = await self.hass.async_add_executor_job(discover)
        configured = {entry.unique_id for entry in self._async_current_entries()}
        self._found = [d for d in self._found if d["mac"] not in configured]

        if not self._found:
            return await self.async_step_manual()

        options = {d["mac"]: f"{d['host']}  ({d['mac']})" for d in self._found}
        options["manual"] = "Enter address manually"

        schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE): vol.In(options),
                vol.Required(CONF_NAME): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_manual(self, user_input: dict | None = None) -> FlowResult:
        """Manual entry when a device did not answer the network-wide probe.

        Only the address is asked for: the MAC is what the device itself replies with,
        and typing it by hand is an extra chance to make a mistake.
        """
        errors = self._errors
        self._errors = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            found = await self.hass.async_add_executor_job(
                partial(discover, MANUAL_PROBE_TIMEOUT, None, 1, host)
            )
            if found:
                return await self._create(
                    user_input[CONF_NAME], host, found[0]["mac"], DEFAULT_PORT, errors
                )
            errors["base"] = "cannot_connect"

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME): str,
                vol.Required(CONF_HOST): str,
            }
        )
        return self.async_show_form(step_id="manual", data_schema=schema, errors=errors)

    async def _create(
        self, name: str, host: str, mac: str, port: int, errors: dict | None = None
    ) -> FlowResult:
        """Verify the connection and create the entry."""
        await self.async_set_unique_id(mac)
        self._abort_if_unique_id_configured()

        device = AcDevice(host, mac, port)
        try:
            await self.hass.async_add_executor_job(device.authenticate)
        except AcError:
            if errors is None:
                return self.async_abort(reason="cannot_connect")
            self._errors = {"base": "cannot_connect"}
            return await self.async_step_manual()

        return self.async_create_entry(
            title=name,
            data={CONF_HOST: host, CONF_MAC: mac, CONF_PORT: port, CONF_NAME: name},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return BroadlinkAcOptionsFlow()


class BroadlinkAcOptionsFlow(OptionsFlow):
    """Runtime options: polling rates, debugging, extra sensors."""

    async def async_step_init(self, user_input: dict | None = None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        interval = vol.All(int, vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL))
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL_STATE,
                    default=options.get(CONF_SCAN_INTERVAL_STATE, DEFAULT_SCAN_INTERVAL_STATE),
                ): interval,
                vol.Optional(
                    CONF_SCAN_INTERVAL_SENSOR,
                    default=options.get(CONF_SCAN_INTERVAL_SENSOR, DEFAULT_SCAN_INTERVAL_SENSOR),
                ): interval,
                vol.Optional(
                    CONF_EXTRA_SENSORS,
                    default=options.get(CONF_EXTRA_SENSORS, DEFAULT_EXTRA_SENSORS),
                ): bool,
                vol.Optional(
                    CONF_TIMEOUT,
                    default=options.get(CONF_TIMEOUT, DEFAULT_TIMEOUT),
                ): vol.All(int, vol.Range(min=MIN_TIMEOUT, max=MAX_TIMEOUT)),
                vol.Optional(
                    CONF_DEBUG_PACKETS,
                    default=options.get(CONF_DEBUG_PACKETS, DEFAULT_DEBUG_PACKETS),
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
