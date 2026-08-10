"""Polling the air conditioner and holding its state."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .device import AcDevice, AcError, AcState

_LOGGER = logging.getLogger(__name__)


class AcCoordinator(DataUpdateCoordinator[AcState]):
    """Keeps a single connection to the device and polls it on a schedule.

    Settings and sensor data come from different requests, so their intervals are
    independent: settings change rarely, while temperature and compressor activity
    are worth watching more often.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        device: AcDevice,
        name: str,
        state_interval: int,
        sensor_interval: int,
        debug_packets: bool,
    ) -> None:
        self.device = device
        self.state = AcState()
        self.sensor_interval = sensor_interval
        self.debug_packets = debug_packets
        self._ticks = 0

        base = min(state_interval, sensor_interval)
        self._state_every = max(1, round(state_interval / base))
        self._sensor_every = max(1, round(sensor_interval / base))

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {name}",
            update_interval=timedelta(seconds=base),
        )

    async def _async_update_data(self) -> AcState:
        try:
            return await self.hass.async_add_executor_job(self._poll)
        except AcError as err:
            raise UpdateFailed(str(err)) from err

    def _poll(self) -> AcState:
        self._ticks += 1
        first_run = self.state.raw_state is None

        if first_run or self._ticks % self._state_every == 0:
            raw_state = self.device.read_state()
            self.device.parse_state(raw_state, self.state)
            if self.debug_packets:
                _LOGGER.debug("%s: settings %s", self.device.mac, raw_state.hex())

        if self._ticks % self._sensor_every == 0 or self.state.ambient_temperature is None:
            raw_sensor = self.device.read_sensor()
            self.device.parse_sensor(raw_sensor, self.state)
            if self.debug_packets:
                _LOGGER.debug("%s: sensor %s", self.device.mac, raw_sensor.hex())

        return self.state

    async def async_write(self, **changes) -> None:
        """Change device settings.

        Edits are applied to the state before sending so the interface responds at once.
        If the device rejects the command, previous values are restored — otherwise the
        screen would show something the device does not have until the next poll.
        """
        previous = {key: getattr(self.state, key) for key in changes}
        for key, value in changes.items():
            setattr(self.state, key, value)

        try:
            await self.hass.async_add_executor_job(self.device.write_state, self.state)
        except AcError as err:
            for key, value in previous.items():
                setattr(self.state, key, value)
            self.async_update_listeners()
            raise HomeAssistantError(f"The device rejected the command: {err}") from err

        self.async_update_listeners()
        await self.async_request_refresh()
