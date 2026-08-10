"""Protocol decoding checks against packets captured from live devices."""

from unittest.mock import patch

import pytest

from custom_components.aircore.device import (
    AcDevice,
    AcError,
    AcState,
    checksum16,
)

from .data import HOST, MAC, SENSOR_WORKING, STATE_SAMPLE


@pytest.fixture
def device():
    return AcDevice(HOST, MAC)


def test_mac_normalization():
    """MAC is accepted in any form: colons, dashes or none."""
    assert AcDevice("1.2.3.4", "00:00:5e:00:53:af").mac == "00005e0053af"
    assert AcDevice("1.2.3.4", "00-00-5E-00-53-AF").mac == "00005e0053af"
    assert AcDevice("1.2.3.4", "00005E0053AF").mac == "00005e0053af"


def test_checksum_matches_device():
    """Checksum matches the one the device accepts without refusal."""
    request = bytes([0xBB, 0x00, 0x06, 0x80, 0x00, 0x00, 0x02, 0x00, 0x11, 0x01])
    assert checksum16(request) == 0x2B7E


def test_parse_state_sample(device):
    """Settings decoding: values match what the device reports."""
    state = device.parse_state(STATE_SAMPLE, AcState())

    assert state.target_temperature == 24
    assert state.power is True
    assert state.mode == 1
    assert state.fan_speed == 3
    assert state.fixation_vertical == 1
    assert state.fixation_horizontal == 1


def test_parse_state_half_degree(device):
    """Half a degree arrives as a separate bit, not in the main byte."""
    packet = bytearray(STATE_SAMPLE)
    packet[0x0C] |= 0x80
    state = device.parse_state(bytes(packet), AcState())

    assert state.target_temperature == 24.5


def test_parse_sensor_reads_compressor(device):
    """Compressor, its load and the coil are read from the sensor packet."""
    state = device.parse_sensor(SENSOR_WORKING, AcState())

    assert state.ambient_temperature is not None
    assert isinstance(state.compressor, bool)
    assert 0 <= state.compressor_load <= 100


def test_coil_temperature_out_of_range_discarded(device):
    """An impossible coil temperature is discarded.

    Occasionally the device sends a corrupted packet where values jump at once and
    return a second later. Such readings must not reach the sensors.
    """
    packet = bytearray(SENSOR_WORKING)
    packet[0x10] = 244
    state = device.parse_sensor(bytes(packet), AcState())

    assert state.coil_temperature is None


def test_coil_below_zero_is_kept(device):
    """A sub-zero reading is not noise but a sign of a freezing coil.

    Warnings about a clogged filter or low refrigerant rely on exactly these values,
    so they must not be discarded.
    """
    packet = bytearray(SENSOR_WORKING)
    packet[0x10] = 0
    state = device.parse_sensor(bytes(packet), AcState())

    assert state.coil_temperature == 0.0


def test_coil_heating_range_is_kept(device):
    """In heating mode the coil is hot, and those readings are legitimate."""
    packet = bytearray(SENSOR_WORKING)
    packet[0x10] = 110
    state = device.parse_sensor(bytes(packet), AcState())

    assert state.coil_temperature == 55.0


def test_parse_sensor_rejects_short_packet(device):
    """A reply that is too short is an error, not something to decode."""
    with pytest.raises(AcError):
        device.parse_sensor(b"\x00" * 10, AcState())


def test_write_state_builds_expected_payload(device):
    """The write command is assembled exactly as the device expects it."""
    state = AcState(
        power=True,
        mode=1,
        target_temperature=24.0,
        fan_speed=3,
        fixation_vertical=1,
    )
    device._authenticated = True

    with patch.object(device, "_send", return_value=b"\x00" * 40) as send:
        device.write_state(state)

    payload = send.call_args[0][1]
    body = payload[2:25]

    assert body[0x00] == 0xBB
    assert body[0x06] == 0x0F
    assert body[0x0A] == ((24 - 8) << 3) | 1
    assert body[0x0D] == 3 << 5
    assert body[0x12] >> 5 & 1 == 1


def test_read_state_retries_when_busy(device):
    """The device serves one request at a time, so busy replies are retried."""
    device._authenticated = True
    busy = bytes.fromhex("0a00bb0001000000000043ff2e7e0000")
    good = bytes(2) + STATE_SAMPLE

    with (
        patch.object(device, "_send", side_effect=[busy, good]),
        patch("custom_components.aircore.device.time.sleep"),
    ):
        answer = device.read_state()

    assert answer[0x00] == 0xBB
    assert answer[0x02] == 0x07


def test_compressor_ignored_when_device_is_off(device):
    """Compressor activity on a powered-off device means a foreign byte layout.

    Compressor fields were derived on units of a single model. If another brand uses
    that byte for something else, it will be non-zero while the device is off. An empty
    sensor beats a plausible but wrong number.
    """
    packet = bytearray(SENSOR_WORKING)
    packet[0x18] = 40
    state = AcState(power=False)

    device.parse_sensor(bytes(packet), state)

    assert state.compressor is False
    assert state.compressor_load is None
    assert state.extras_trusted is False


def test_compressor_trusted_when_device_is_on(device):
    """On a running device compressor readings are accepted."""
    packet = bytearray(SENSOR_WORKING)
    packet[0x18] = 35
    state = AcState(power=True)

    device.parse_sensor(bytes(packet), state)

    assert state.compressor is True
    assert state.compressor_load == 50
    assert state.extras_trusted is True


def test_untrusted_extras_are_not_reported(device):
    """When the byte layout is not trusted, output is not invented."""
    packet = bytearray(SENSOR_WORKING)
    packet[0x18] = 55
    state = AcState(power=False)

    device.parse_sensor(bytes(packet), state)

    assert state.extras_trusted is False
    assert state.compressor_load is None


def test_target_temperature_is_clamped(device):
    """A target beyond device limits is clamped instead of overflowing the byte.

    The temperature field is five bits wide: a value of 40 would produce 256 and
    destroy the packet.
    """
    device._authenticated = True

    with patch.object(device, "_send", return_value=b"\x00" * 40) as send:
        device.write_state(AcState(power=True, target_temperature=40.0))

    body = send.call_args[0][1][2:25]
    assert body[0x0A] >> 3 == 32 - 8

    with patch.object(device, "_send", return_value=b"\x00" * 40) as send:
        device.write_state(AcState(power=True, target_temperature=5.0))

    body = send.call_args[0][1][2:25]
    assert body[0x0A] >> 3 == 16 - 8


def test_lost_packet_does_not_fail_the_poll(device):
    """A single lost packet is retried rather than reported as a failure.

    Communication is UDP over WiFi: without the retry every such loss would take the
    entities to unavailable until the next poll.
    """
    device._authenticated = True
    good = bytes(2) + STATE_SAMPLE

    with (
        patch.object(device, "_send", side_effect=[AcError("no answer"), good]),
        patch("custom_components.aircore.device.time.sleep"),
    ):
        answer = device.read_state()

    assert answer[0x00] == 0xBB


def test_silent_device_still_reports_after_the_retries(device):
    """A device that keeps quiet is reported once the attempts run out."""
    device._authenticated = True

    with (
        patch.object(device, "_send", side_effect=AcError("no answer")),
        patch("custom_components.aircore.device.time.sleep"),
        pytest.raises(AcError, match="no answer"),
    ):
        device.read_state()


def test_write_survives_a_lost_packet(device):
    """A command is not lost with the packet that carried it."""
    device._authenticated = True

    with (
        patch.object(device, "_send", side_effect=[AcError("no answer"), b"\x00" * 40]) as send,
        patch("custom_components.aircore.device.time.sleep"),
    ):
        device.write_state(AcState(power=True, target_temperature=22.0))

    assert send.call_count == 2
