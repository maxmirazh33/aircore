"""Constants for the Broadlink air conditioner integration."""

DOMAIN = "aircore"

CONF_HOST = "host"
CONF_MAC = "mac"
CONF_PORT = "port"
CONF_NAME = "name"
CONF_DEVICE = "device"

CONF_SCAN_INTERVAL_STATE = "scan_interval_state"
CONF_SCAN_INTERVAL_SENSOR = "scan_interval_sensor"
CONF_DEBUG_PACKETS = "debug_packets"
CONF_TIMEOUT = "timeout"
CONF_EXTRA_SENSORS = "extra_sensors"

DEFAULT_PORT = 80
DEFAULT_SCAN_INTERVAL_STATE = 30
DEFAULT_SCAN_INTERVAL_SENSOR = 30
DEFAULT_DEBUG_PACKETS = False
DEFAULT_TIMEOUT = 5
MANUAL_PROBE_TIMEOUT = 4.0
ATTEMPTS = 3
RETRY_PAUSE = 1.0
MIN_TIMEOUT = 2
MAX_TIMEOUT = 30
DEFAULT_EXTRA_SENSORS = True

MIN_SCAN_INTERVAL = 5
MAX_SCAN_INTERVAL = 600

DEVICE_TYPE = 0x4E2A

INITIAL_KEY = bytes(
    [0x09, 0x76, 0x28, 0x34, 0x3F, 0xE9, 0x9E, 0x23, 0x76, 0x5C, 0x15, 0x13, 0xAC, 0xCF, 0x8B, 0x02]
)
INITIAL_IV = bytes(
    [0x56, 0x2E, 0x17, 0x99, 0x6D, 0x09, 0x3D, 0x28, 0xDD, 0xB3, 0xBA, 0x69, 0x5A, 0x2E, 0x6F, 0x58]
)

MODE_AUTO = 0
MODE_COOL = 1
MODE_DRY = 2
MODE_HEAT = 4
MODE_FAN = 6

MIN_TEMP = 16
MAX_TEMP = 32

COIL_TEMP_MIN = -40.0
COIL_TEMP_MAX = 80.0

COMPRESSOR_LOAD_FULL = 70

SWING_POSITIONS = {
    0: "swing",
    1: "top",
    2: "middle1",
    3: "middle2",
    4: "middle3",
    5: "bottom",
    6: "swing",
    7: "auto",
}
SWING_POSITIONS_INVERT = {
    "swing": 0,
    "top": 1,
    "middle1": 2,
    "middle2": 3,
    "middle3": 4,
    "bottom": 5,
    "auto": 7,
}

MODE_NAMES = {
    MODE_AUTO: "auto",
    MODE_COOL: "cool",
    MODE_DRY: "dry",
    MODE_HEAT: "heat",
    MODE_FAN: "fan_only",
}

FAN_SPEEDS = {
    5: "auto",
    3: "low",
    2: "medium",
    1: "high",
}
FAN_SPEEDS_INVERT = {v: k for k, v in FAN_SPEEDS.items()}

SWING_H_POSITIONS = {
    0: "swing",
    1: "off",
}
SWING_H_POSITIONS_INVERT = {v: k for k, v in SWING_H_POSITIONS.items()}
