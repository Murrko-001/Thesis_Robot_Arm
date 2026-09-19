import serial
import time
import sys
import json
from typing import Dict, Any, List, Optional

# Type aliases for enhanced readability
BoardConnections = Dict[int, serial.Serial]
JsonPayload = Dict[str, Any]

# Available serial ports mapping
PORTS: Dict[int, str] = {
    1: '/dev/cu.usbmodem101',
    2: '/dev/cu.usbmodem11301',
    3: 'COM6'
}
BAUD_RATE: int = 115_200

# Constants (Fixed: 45000 instead of tuple 45,000)
TOP_POSITION: int = 45_000
MID_POSITION: int = int(TOP_POSITION / 2)

# Logical arm ID -> Physical Board ID & Motor ID mapping
ARMS_MAPPING: Dict[int, Dict[str, int]] = {
    1: {"board_id": 1, "motor": 1},
    2: {"board_id": 1, "motor": 3},
    3: {"board_id": 2, "motor": 2},
    4: {"board_id": 2, "motor": 3},
}


def connect_to_single_board(board_id: int, port: str) -> serial.Serial:
    """
    Establishes a serial connection to a single board.
    """
    print(f"Connecting to Board {board_id} on port {port}...")
    try:
        board_connection = serial.Serial(port, BAUD_RATE, timeout=0.5)
        return board_connection
    except Exception as error:
        print(f"Error connecting to Board {board_id}: {error}")
        print("Make sure your Arduino IDE Serial Monitor is CLOSED.")
        sys.exit(1)


def connect_to_active_boards(use_board_1: bool = False, use_board_2: bool = False, use_board_3: bool = False) -> BoardConnections:
    """
    Connects to all enabled boards based on boolean flags.
    """
    active_boards: BoardConnections = {}
    flags: Dict[int, bool] = {1: use_board_1, 2: use_board_2, 3: use_board_3}

    print("--- Board Initialization ---")
    for board_id, should_use in flags.items():
        if not should_use:
            print(f"Board {board_id} is disabled. Skipping.")
            continue
            
        port: str = PORTS[board_id]
        board_connection = connect_to_single_board(board_id, port)
        active_boards[board_id] = board_connection

    if not active_boards:
        print("No boards were initialized. Exiting program.")
        sys.exit(1)

    print("Waiting 2 seconds for boards to initialize...")
    time.sleep(2)
    
    for board_connection in active_boards.values():
        board_connection.reset_input_buffer()

    print(f"Successfully connected to {len(active_boards)} board(s).\n")
    return active_boards


def build_board_payloads(command_payload: JsonPayload) -> Dict[int, JsonPayload]:
    """
    Parses global command payload and routes instructions to specific board payloads 
    based on ARMS_MAPPING. Accepts either 'arms' or 'motors' in the JSON command.
    """
    raw_commands: List[Dict[str, Any]] = command_payload.get("commands", [])
    if not raw_commands:
        return {}

    # Dictionary holding per-board structured commands: {board_id: {"commands": [...]}}
    board_payloads: Dict[int, JsonPayload] = {}

    for cmd in raw_commands:
        # Support both 'arms' and 'motors' key in input JSON
        target_arms: List[int] = cmd.get("arms") or cmd.get("motors", [])
        
        # Group target physical motor IDs by board_id for this specific command group
        motors_by_board: Dict[int, List[int]] = {}

        for arm_id in target_arms:
            if arm_id in ARMS_MAPPING:
                mapped_board: int = ARMS_MAPPING[arm_id]["board_id"]
                mapped_motor: int = ARMS_MAPPING[arm_id]["motor"]
                
                if mapped_board not in motors_by_board:
                    motors_by_board[mapped_board] = []
                motors_by_board[mapped_board].append(mapped_motor)
            else:
                print(f"Warning: Arm/Motor ID {arm_id} not found in ARMS_MAPPING.")

        # Construct individual command group for each target board
        for board_id, physical_motors in motors_by_board.items():
            board_cmd: Dict[str, Any] = cmd.copy()
            
            # Clean up keys and assign converted physical motor list
            board_cmd.pop("arms", None)
            board_cmd["motors"] = physical_motors

            if board_id not in board_payloads:
                board_payloads[board_id] = {"commands": []}
            
            board_payloads[board_id]["commands"].append(board_cmd)

    return board_payloads


def send_json_command_to_mapped_boards(boards: BoardConnections, command_payload: JsonPayload) -> None:
    """
    Translates input JSON via ARMS_MAPPING and sends targeted payloads 
    ONLY to the necessary active boards.
    """
    board_payloads: Dict[int, JsonPayload] = build_board_payloads(command_payload)

    if not board_payloads:
        print("No valid board targets found in command payload.")
        return

    for board_id, board_payload in board_payloads.items():
        if board_id not in boards:
            print(f"Warning: Command target Board {board_id} is needed but NOT connected!")
            continue

        try:
            json_string: str = json.dumps(board_payload) + "\n"
            command_bytes: bytes = json_string.encode('utf-8')

            # Send payload specifically to this board
            boards[board_id].write(command_bytes)
            print(f"[Sent to Board {board_id}]: {json_string.strip()}")
            
        except Exception as error:
            print(f"Error sending command to Board {board_id}: {error}")


def read_and_print_responses(boards: BoardConnections, wait_time_seconds: float = 0.1) -> None:
    """
    Reads and displays incoming responses from all active boards.
    """
    time.sleep(wait_time_seconds)

    for board_id, board_connection in boards.items():
        while board_connection.in_waiting > 0:
            try:
                response_bytes: bytes = board_connection.readline()
                response_string: str = response_bytes.decode('utf-8').strip()
                
                if response_string:
                    print(f"[Board {board_id} - {PORTS[board_id]}]: {response_string}")
            except Exception as error:
                print(f"[Board {board_id}] Error while reading: {error}")


def parse_user_input(user_input: str) -> Optional[JsonPayload]:
    """
    Parses user text string into a valid JSON object.
    """
    try:
        parsed_data: JsonPayload = json.loads(user_input)
        return parsed_data
    except json.JSONDecodeError as error:
        print(f"Error: Invalid JSON format. (Detail: {error})")
        return None


def close_all_connections(boards: BoardConnections) -> None:
    """
    Safely closes serial connections for all active boards.
    """
    print("\nClosing all connections...")
    for board_connection in boards.values():
        if board_connection.is_open:
            board_connection.close()
    print("All connections successfully closed.")


def main() -> None:
    active_boards: BoardConnections = connect_to_active_boards(
        use_board_1=True, 
        use_board_2=True, 
        use_board_3=False
    )

    print("--- INTERACTIVE MULTI-BOARD CONTROLLER (MAPPED VERSION) ---")
    print("Type your JSON command using arm IDs (1 to 4) and press Enter.")
    print('Example: {"commands": [{"arms": [1, 4], "direction": "UP", "step_count": 5000, "step_delay": 125}]}')
    print("Type 'exit' or 'quit' to close.\n")

    while True:
        user_input: str = input("Enter JSON command >>> ").strip()

        if user_input.lower() in ['exit', 'quit']:
            close_all_connections(active_boards)
            break

        if not user_input:
            read_and_print_responses(active_boards, wait_time_seconds=0)
            continue

        command_payload: Optional[JsonPayload] = parse_user_input(user_input)
        
        if command_payload is not None:
            # Route and send command payloads only to target boards
            send_json_command_to_mapped_boards(active_boards, command_payload)
            
            # Read ACK responses from boards
            read_and_print_responses(active_boards, wait_time_seconds=0.1)


if __name__ == "__main__":
    main()