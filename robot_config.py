"""Hardware mapping, motor defaults, and controller timing."""

PORTS = {
    1: "/dev/cu.usbmodem101",
    2: "/dev/cu.usbmodem11301",
    3: "COM6",
}
ENABLED_BOARDS = (1, 2)
BAUD_RATE = 115_200

# Logical arm ID -> physical board and motor.
ARMS_MAPPING = {
    1: {"board_id": 1, "motor": 1},
    2: {"board_id": 1, "motor": 3},
    3: {"board_id": 2, "motor": 2},
    4: {"board_id": 2, "motor": 3},
}

BOTTOM_POSITION = 0.0
MIDDLE_POSITION = 0.5
TOP_POSITION = 1.0
STEPS_TO_TOP = 45_000
DEFAULT_STEP_DELAY_US = 125
MIN_STEP_DELAY_US = 1
MAX_STEP_DELAY_US = 32_767
LOWER_ALL = 9

SERIAL_TIMEOUT_SECONDS = 0.5
BOARD_STARTUP_SECONDS = 2
MOVE_TIMEOUT_SECONDS = 30
RESPONSE_POLL_SECONDS = 0.01
DEBUG_RESPONSE_WAIT_SECONDS = 0.1
