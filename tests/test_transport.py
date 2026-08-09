"""Checks of the network layer: authentication, errors and discovery."""

from unittest.mock import MagicMock, patch

import pytest

from custom_components.aircore.const import DEVICE_TYPE, INITIAL_IV, INITIAL_KEY
from custom_components.aircore.device import (
    AcAuthError,
    AcDevice,
    AcError,
    _aes,
    discover,
)

from .data import HOST, MAC

SESSION_ID = bytes([0x01, 0x02, 0x03, 0x04])
SESSION_KEY = bytes(range(0x10, 0x20))


def _reply(body: bytes, error: int = 0, key: bytes = INITIAL_KEY) -> bytes:
    """A device reply: a plain header and an encrypted body."""
    header = bytearray(0x38)
    header[0x22] = error & 0xFF
    header[0x23] = error >> 8
    return bytes(header) + _aes(key, INITIAL_IV, body, True)


@pytest.fixture
def udp():
    """A socket that answers whatever the test tells it to."""
    with patch("custom_components.aircore.device.socket.socket") as factory:
        sock = MagicMock()
        factory.return_value = sock
        yield sock


def test_authenticate_keeps_session(udp) -> None:
    """Authentication saves the identifier and key issued by the device."""
    body = bytearray(0x14)
    body[0x00:0x04] = SESSION_ID
    body[0x04:0x14] = SESSION_KEY
    udp.recvfrom.return_value = (_reply(bytes(body)), (HOST, 80))

    device = AcDevice(HOST, MAC)
    device.authenticate()

    assert device.authenticated is True
    assert device._id == SESSION_ID
    assert device._key == SESSION_KEY


def test_silent_device_is_an_error(udp) -> None:
    """A device that does not answer produces a readable error, not a timeout."""
    udp.recvfrom.side_effect = TimeoutError

    with pytest.raises(AcError, match=HOST):
        AcDevice(HOST, MAC).authenticate()


def test_truncated_reply_rejected(udp) -> None:
    """A reply shorter than the header is not decoded."""
    udp.recvfrom.return_value = (b"\x00" * 16, (HOST, 80))

    with pytest.raises(AcError):
        AcDevice(HOST, MAC).authenticate()


def test_device_error_code_reported(udp) -> None:
    """An error code in the header is reported as an authentication failure."""
    udp.recvfrom.return_value = (_reply(bytes(0x14), error=0xFFFD), (HOST, 80))

    with pytest.raises(AcAuthError):
        AcDevice(HOST, MAC).authenticate()


def test_expired_session_is_renewed(udp) -> None:
    """A rejected request triggers re-authentication instead of an error.

    The device forgets the session after a restart or a long pause; without a retry
    every entity would go unavailable until Home Assistant is reloaded.
    """
    device = AcDevice(HOST, MAC)
    device._authenticated = True

    with (
        patch.object(
            device, "_send", side_effect=[AcAuthError("session expired"), b"payload"]
        ) as send,
        patch.object(device, "authenticate") as authenticate,
    ):
        answer = device._request(b"data")

    assert answer == b"payload"
    assert authenticate.called
    assert send.call_count == 2


def test_discover_returns_only_air_conditioners(udp) -> None:
    """Other Broadlink gear on the network is filtered out of the results."""
    foreign = bytearray(0x40)
    foreign[0x34] = 0x10
    ours = bytearray(0x40)
    ours[0x34] = DEVICE_TYPE & 0xFF
    ours[0x35] = DEVICE_TYPE >> 8
    ours[0x3A:0x40] = bytes(reversed(bytes.fromhex(MAC)))

    udp.recvfrom.side_effect = [
        (bytes(foreign), ("192.0.2.20", 80)),
        (bytes(ours), (HOST, 80)),
        TimeoutError,
    ]

    found = discover(timeout=0.1, local_ip=HOST)

    assert found == [{"host": HOST, "mac": MAC, "devtype": DEVICE_TYPE}]


def test_discover_survives_silent_network(udp) -> None:
    """When nobody answers, discovery returns an empty list rather than failing."""
    udp.recvfrom.side_effect = TimeoutError

    assert discover(timeout=0.1, local_ip=HOST, attempts=1) == []
