"""Hardware mapping, motor defaults, and controller timing."""

PORTS = {
    1: "/dev/cu.usbmodem101",
    2: "/dev/cu.usbmodem11101",
    3: "/dev/cu.usbmodem11201",
}
ENABLED_BOARDS = (1, 2, 3)
BAUD_RATE = 115_200

# Logical arm ID -> physical board and motor.
ARMS_MAPPING = {
    1: {"board_id": 1, "motor": 1},
    2: {"board_id": 1, "motor": 2},
    3: {"board_id": 1, "motor": 3},
    4: {"board_id": 2, "motor": 1},
    5: {"board_id": 2, "motor": 2},
    6: {"board_id": 2, "motor": 3},
    7: {"board_id": 3, "motor": 1},
    8: {"board_id": 3, "motor": 2},
}

# BOTTOM_POSITION = 0.02
# MIDDLE_POSITION = 0.5
# TOP_POSITION = 1.0
BOTTOM_POSITION = 0.02
MIDDLE_POSITION = 0.2
TOP_POSITION = 0.4
STEPS_TO_TOP = 45_000
DEFAULT_STEP_DELAY_US = 100
LOWER_ALL = 9
# False sends final targets directly, including when lowering all arms.
MOVE_THROUGH_MIDDLE = False

SERIAL_TIMEOUT_SECONDS = 0.5
BOARD_STARTUP_SECONDS = 2
MOVE_TIMEOUT_SECONDS = 30
RESPONSE_POLL_SECONDS = 0.01
