"""Constants for the Williwaw integration."""

DOMAIN = "williwaw"
CONF_ADDRESS = "address"

# Fan speed range (native device values)
SPEED_MIN = 1
SPEED_MAX = 15
SPEED_RANGE = (SPEED_MIN, SPEED_MAX)

# Sleep timer range (minutes)
SLEEP_TIMER_MIN = 0
SLEEP_TIMER_MAX = 1440  # 24 h
