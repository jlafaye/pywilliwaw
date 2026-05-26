from pywilliwaw.fan import (
    TemperatureSensor,
    Williwaw,
    discover,
    find_by_address,
    find_by_name,
)
from pywilliwaw.protocol import (
    COMMAND_CHAR,
    FANCONTROL_CHAR,
    FANSTATE_CHAR,
    SENSORS_CHAR,
    SENSORLIST_CHAR,
    DEVICENAME_CHAR,
    OSCILLATION_SPEED_HIGH,
    OSCILLATION_SPEED_LOW,
    OSCILLATION_SPEED_MEDIUM,
    SLEEP_MAX_MIN,
    SPEED_MAX,
    SPEED_MIN,
    FanControlPacket,
    make_fan_toggle_cmd,
    make_oscillation_toggle_cmd,
    make_center_cmd,
    make_calibrate_sensors_cmd,
)

__all__ = [
    "Williwaw",
    "TemperatureSensor",
    "discover",
    "find_by_address",
    "find_by_name",
    # characteristics
    "COMMAND_CHAR",
    "FANCONTROL_CHAR",
    "FANSTATE_CHAR",
    "SENSORS_CHAR",
    "SENSORLIST_CHAR",
    "DEVICENAME_CHAR",
    # limits
    "SPEED_MIN",
    "SPEED_MAX",
    "SLEEP_MAX_MIN",
    "OSCILLATION_SPEED_LOW",
    "OSCILLATION_SPEED_MEDIUM",
    "OSCILLATION_SPEED_HIGH",
    # FANCONTROL packet
    "FanControlPacket",
    # 1-byte command builders
    "make_fan_toggle_cmd",
    "make_oscillation_toggle_cmd",
    "make_center_cmd",
    "make_calibrate_sensors_cmd",
]
