"""Protocol of air conditioners with a Broadlink WiFi module.

Communication runs over UDP; the payload is encrypted with AES-128-CBC using a key
issued by the device during authentication. State decoding matches public
implementations; on top of that it reads fields absent from them: compressor activity,
its output and coil temperature. Those were derived from day-long packet dumps and
verified against the actual state of the units.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import random
import socket
import threading
import time

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .const import (
    COIL_TEMP_MAX,
    COIL_TEMP_MIN,
    COMPRESSOR_LOAD_FULL,
    DEVICE_TYPE,
    INITIAL_IV,
    INITIAL_KEY,
    MAX_TEMP,
    MIN_TEMP,
)

_LOGGER = logging.getLogger(__name__)


class AcError(Exception):
    """Communication with the air conditioner failed."""


class AcAuthError(AcError):
    """The device rejected the request as unauthorised."""


@dataclass
class AcState:
    """Device state decoded from a reply."""

    power: bool = False
    mode: int = 0
    target_temperature: float = 24.0
    fan_speed: int = 5
    mute: bool = False
    turbo: bool = False
    sleep: bool = False
    ifeel: bool = False
    health: bool = False
    clean: bool = False
    display: bool = True
    mildew: bool = False
    fixation_vertical: int = 0
    fixation_horizontal: int = 0
    ambient_temperature: float | None = None
    compressor: bool = False
    compressor_load: int | None = None
    coil_temperature: float | None = None
    extras_trusted: bool = True
    raw_state: bytes | None = field(default=None, repr=False)
    raw_sensor: bytes | None = field(default=None, repr=False)


def _aes(key: bytes, iv: bytes, data: bytes, encrypt: bool) -> bytes:
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    worker = cipher.encryptor() if encrypt else cipher.decryptor()
    if len(data) % 16:
        data = data + bytes(16 - len(data) % 16)
    return worker.update(data) + worker.finalize()


def checksum16(payload: bytes) -> int:
    """Payload checksum, computed the way the device does it."""
    total = 0
    padded = payload + b"\x00"
    for i in range(0, len(payload), 2):
        total += (payload[i] << 8) + padded[i + 1]
    total = (total >> 16) + (total & 0xFFFF)
    return ~total & 0xFFFF


class AcDevice:
    """A single device: transport, authentication and state decoding."""

    def __init__(self, host: str, mac: str, port: int = 80, timeout: float = 5.0) -> None:
        self.host = host
        self.port = port
        self.mac = mac.replace(":", "").replace("-", "").lower()
        self.timeout = timeout
        self._key = INITIAL_KEY
        self._iv = INITIAL_IV
        self._id = bytes(4)
        self._counter = random.randint(0, 0xFFFF)
        self._authenticated = False
        self._busy = threading.Lock()

    @property
    def authenticated(self) -> bool:
        return self._authenticated

    def _mac_bytes(self) -> bytes:
        return bytes.fromhex(self.mac)

    def _build_packet(self, command: int, payload: bytes) -> bytes:
        self._counter = (self._counter + 1) & 0xFFFF
        header = bytearray(0x38)
        header[0x00:0x08] = bytes([0x5A, 0xA5, 0xAA, 0x55, 0x5A, 0xA5, 0xAA, 0x55])
        header[0x24] = DEVICE_TYPE & 0xFF
        header[0x25] = DEVICE_TYPE >> 8
        header[0x26] = command
        header[0x28] = self._counter & 0xFF
        header[0x29] = self._counter >> 8
        header[0x2A:0x30] = self._mac_bytes()
        header[0x30:0x34] = self._id

        checksum = 0xBEAF
        for byte in payload:
            checksum = (checksum + byte) & 0xFFFF
        header[0x34] = checksum & 0xFF
        header[0x35] = checksum >> 8

        encrypted = _aes(self._key, self._iv, payload, True)
        packet = bytes(header) + encrypted

        total = 0xBEAF
        for byte in packet:
            total = (total + byte) & 0xFFFF
        packet = bytearray(packet)
        packet[0x20] = total & 0xFF
        packet[0x21] = total >> 8
        return bytes(packet)

    def _send(self, command: int, payload: bytes) -> bytes:
        packet = self._build_packet(command, payload)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(self.timeout)
        try:
            sock.sendto(packet, (self.host, self.port))
            response, _ = sock.recvfrom(2048)
        except TimeoutError as err:
            raise AcError(f"device {self.host} did not respond") from err
        finally:
            sock.close()

        if len(response) < 0x38:
            raise AcError("reply too short")

        error = response[0x22] | (response[0x23] << 8)
        if error:
            raise AcAuthError(f"device returned error {error:#06x}")

        return _aes(self._key, self._iv, response[0x38:], False)

    def authenticate(self) -> None:
        """Obtain a session key. Without it the device answers nothing."""
        payload = bytearray(0x50)
        payload[0x04:0x13] = b"1" * 15
        payload[0x1E] = 0x01
        payload[0x2D] = 0x01
        payload[0x30:0x37] = b"Test  1"

        self._key = INITIAL_KEY
        self._iv = INITIAL_IV
        self._id = bytes(4)

        decrypted = self._send(0x65, bytes(payload))
        if len(decrypted) < 0x14:
            raise AcAuthError("authentication reply too short")

        self._id = decrypted[0x00:0x04]
        self._key = decrypted[0x04:0x14]
        self._authenticated = True
        _LOGGER.debug("%s: authenticated", self.mac)

    def _request(self, payload: bytes) -> bytes:
        if not self._authenticated:
            self.authenticate()
        try:
            return self._send(0x6A, payload)
        except AcAuthError:
            self._authenticated = False
            self.authenticate()
            return self._send(0x6A, payload)

    @staticmethod
    def _wrap(payload: bytes) -> bytes:
        body = bytearray(32)
        body[0] = len(payload) + 2
        body[2 : 2 + len(payload)] = payload
        crc = checksum16(payload)
        body[len(payload) + 2] = (crc >> 8) & 0xFF
        body[len(payload) + 3] = crc & 0xFF
        return bytes(body)

    def _read(self, selector: int, minimum: int, what: str) -> bytes:
        """Read a data block.

        The device serves one request at a time and refuses concurrent ones, so a short
        reply is not treated as an error straight away — the request is retried.
        """
        request = bytes([0xBB, 0x00, 0x06, 0x80, 0x00, 0x00, 0x02, 0x00, selector, 0x01])
        last = b""
        for attempt in range(3):
            answer = self._request(self._wrap(request))
            if len(answer) >= minimum and answer[0x04] == 0x07:
                return answer[2:]
            last = answer
            _LOGGER.debug("%s: device busy, retry %s (%s)", self.mac, attempt + 1, what)
            time.sleep(1.0 + attempt)
        raise AcError(f"device did not return {what}: {last[:8].hex()}")

    def read_state(self) -> bytes:
        """Device settings: mode, target temperature, fan."""
        with self._busy:
            return self._read(0x11, 0x17, "settings")

    def read_sensor(self) -> bytes:
        """Sensor block: room temperature and compressor data."""
        with self._busy:
            return self._read(0x21, 0x24, "sensor data")

    def write_state(self, state: AcState) -> None:
        """Send settings to the device.

        The device serves one request at a time and refuses anything that arrives while
        it is busy, so a command landing in the middle of a poll would wait out a retry
        pause. Requests of our own are lined up instead of racing.
        """
        target = min(max(state.target_temperature, MIN_TEMP), MAX_TEMP)
        temperature = int(target)
        half = 1 if (target - temperature) >= 0.5 else 0

        payload = bytearray(23)
        payload[0x00] = 0xBB
        payload[0x02] = 0x06
        payload[0x03] = 0x80
        payload[0x06] = 0x0F
        payload[0x08] = 0x01
        payload[0x09] = 0x01
        payload[0x0A] = ((temperature - 8) << 3) | (state.fixation_vertical & 0x07)
        payload[0x0B] = (state.fixation_horizontal & 0x07) << 5
        payload[0x0C] = (half << 7) | 0x0F
        payload[0x0D] = (state.fan_speed & 0x07) << 5
        payload[0x0E] = (int(state.mute) << 7) | (int(state.turbo) << 6)
        payload[0x0F] = (
            ((state.mode & 0x0F) << 5) | (int(state.sleep) << 2) | (int(state.ifeel) << 3)
        )
        payload[0x12] = (int(state.power) << 5) | (int(state.clean) << 2) | (int(state.health) << 1)
        payload[0x14] = (int(state.display) << 4) | (int(state.mildew) << 3)

        with self._busy:
            self._request(self._wrap(bytes(payload)))

    def parse_state(self, data: bytes, state: AcState) -> AcState:
        """Decode a settings reply."""
        state.target_temperature = 8 + (data[0x0A] >> 3) + (0.5 if data[0x0C] >> 7 else 0)
        state.power = bool(data[0x12] >> 5 & 1)
        state.mode = data[0x0F] >> 5 & 0x0F
        state.sleep = bool(data[0x0F] >> 2 & 1)
        state.ifeel = bool(data[0x0F] >> 3 & 1)
        state.fan_speed = data[0x0D] >> 5 & 0x07
        state.mute = bool(data[0x0E] >> 7 & 1)
        state.turbo = bool(data[0x0E] >> 6 & 1)
        state.display = bool(data[0x14] >> 4 & 1)
        state.mildew = bool(data[0x14] >> 3 & 1)
        state.health = bool(data[0x12] >> 1 & 1)
        state.clean = bool(data[0x12] >> 2 & 1)
        state.fixation_vertical = data[0x0A] & 0x07
        state.fixation_horizontal = data[0x0B] >> 5 & 0x07
        state.raw_state = data
        return state

    def parse_sensor(self, data: bytes, state: AcState) -> AcState:
        """Decode a sensor reply.

        Room temperature sits in the low five bits of byte 15; the high bit adds 32
        degrees, tenths live in byte 31. Bytes 24/25/28 are active only while the
        compressor runs, and bytes 16-18 repeat the coil temperature.
        """
        if len(data) < 34:
            raise AcError("sensor reply too short")

        whole = data[0x0F] & 0x1F
        if data[0x0F] > 63:
            whole += 32
        state.ambient_temperature = whole + data[0x1F] / 10

        raw_load = data[0x18]
        if state.power or raw_load == 0:
            state.compressor = bool(raw_load)
            state.compressor_load = min(round(raw_load * 100 / COMPRESSOR_LOAD_FULL), 100)
            state.extras_trusted = True
        else:
            state.compressor = False
            state.compressor_load = None
            state.extras_trusted = False
            _LOGGER.debug(
                "%s: compressor reported active while the device is off (%s) — "
                "reading discarded, likely a different model",
                self.mac,
                raw_load,
            )

        coil = data[0x10] / 2
        if COIL_TEMP_MIN <= coil <= COIL_TEMP_MAX:
            state.coil_temperature = coil
        else:
            state.coil_temperature = None
            _LOGGER.debug(
                "%s: coil temperature %s outside the physically possible range — "
                "corrupted packet, reading discarded",
                self.mac,
                coil,
            )

        state.raw_sensor = data
        return state


def _local_ip() -> str:
    """Address the host is reachable at on the local network.

    Inside a container the hostname resolves to 127.0.1.1 and devices would never reply
    there, so the address is discovered with a throwaway outbound connection.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "0.0.0.0"
    finally:
        sock.close()


def discover(
    timeout: float = 6.0,
    local_ip: str | None = None,
    attempts: int = 2,
    target: str = "255.255.255.255",
) -> list[dict]:
    """Discover air conditioners on the network.

    Devices answer the probe with their address, MAC and type, so entering them by hand
    is unnecessary. Only air conditioners are returned; other Broadlink gear is filtered
    out. Aimed at a single address the probe also works past a router that drops
    broadcasts.
    """

    address = local_ip or _local_ip()
    packet = bytearray(0x30)
    timezone_offset = int(-time.timezone / 3600)
    now = time.localtime()

    packet[0x08] = timezone_offset & 0xFF if timezone_offset >= 0 else (0xFF + timezone_offset + 1)
    packet[0x09] = 0xFF if timezone_offset < 0 else 0
    packet[0x0A] = 0xFF if timezone_offset < 0 else 0
    packet[0x0B] = 0xFF if timezone_offset < 0 else 0
    packet[0x0C] = now.tm_year & 0xFF
    packet[0x0D] = now.tm_year >> 8
    packet[0x0E] = now.tm_min
    packet[0x0F] = now.tm_hour
    packet[0x10] = int(str(now.tm_year)[2:])
    packet[0x11] = now.tm_wday
    packet[0x12] = now.tm_mday
    packet[0x13] = now.tm_mon
    try:
        packet[0x18:0x1C] = bytes(reversed(socket.inet_aton(address)))
    except OSError:
        packet[0x18:0x1C] = bytes(4)
    packet[0x26] = 6

    checksum = 0xBEAF
    for byte in packet:
        checksum = (checksum + byte) & 0xFFFF
    packet[0x20] = checksum & 0xFF
    packet[0x21] = checksum >> 8

    found: dict[str, dict] = {}
    for _ in range(max(1, attempts)):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(timeout)
        try:
            sock.sendto(bytes(packet), (target, 80))
            deadline = time.time() + timeout
            while time.time() < deadline:
                try:
                    response, addr = sock.recvfrom(1024)
                except TimeoutError:
                    break
                if len(response) < 0x40:
                    continue
                devtype = response[0x34] | response[0x35] << 8
                if devtype != DEVICE_TYPE:
                    continue
                mac = bytes(reversed(response[0x3A:0x40])).hex()
                found[mac] = {"host": addr[0], "mac": mac, "devtype": devtype}
        finally:
            sock.close()
        if found:
            break

    return list(found.values())
