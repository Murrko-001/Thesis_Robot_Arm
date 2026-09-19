"""Convert normalized arm positions (0–1) to absolute steps for the boards."""

import argparse
import json
import time
from typing import Any, Dict, List, Optional, Set

import serial

BoardConnections = Dict[int, serial.Serial]
JsonPayload = Dict[str, Any]

PORTS = {
    1: "/dev/cu.usbmodem101",
    2: "/dev/cu.usbmodem11301",
    3: "COM6",
}
BAUD_RATE = 115_200
STEPS_TO_TOP = 45_000
MAX_STEP_DELAY_US = 32_767
MOVE_TIMEOUT_SECONDS = 30
LOWER_ALL = 9

# Logical arm ID -> physical board and motor.
ARMS_MAPPING = {
    1: {"board_id": 1, "motor": 1},
    2: {"board_id": 1, "motor": 3},
    3: {"board_id": 2, "motor": 2},
    4: {"board_id": 2, "motor": 3},
}


def connect_to_single_board(board_id: int, port: str) -> serial.Serial:
    print(f"Connecting to Board {board_id} on {port}...")
    return serial.Serial(port, BAUD_RATE, timeout=0.5)


def connect_to_active_boards(
    use_board_1: bool = False,
    use_board_2: bool = False,
    use_board_3: bool = False,
) -> BoardConnections:
    boards: BoardConnections = {}
    try:
        for board_id, enabled in enumerate((use_board_1, use_board_2, use_board_3), 1):
            if enabled:
                boards[board_id] = connect_to_single_board(board_id, PORTS[board_id])
        if not boards:
            raise ValueError("No boards enabled.")

        time.sleep(2)
        for connection in boards.values():
            connection.reset_input_buffer()
    except (serial.SerialException, OSError, ValueError, KeyboardInterrupt):
        close_all_connections(boards)
        raise
    return boards


def validate_command(command: Any) -> List[int]:
    """Validate a group and return its logical arm IDs (including the motors alias)."""
    if not isinstance(command, dict):
        raise ValueError("Each command must be an object.")
    if "step_count" in command or "direction" in command:
        raise ValueError("Use position instead of step_count and direction.")

    position = command.get("position")
    if type(position) not in (int, float) or not 0 <= position <= 1:
        raise ValueError("Position must be a number from 0 (bottom) to 1 (top).")
    if "step_delay" in command:
        delay = command["step_delay"]
        if type(delay) is not int or not 1 <= delay <= MAX_STEP_DELAY_US:
            raise ValueError(f"Step delay must be an integer from 1 to {MAX_STEP_DELAY_US} microseconds.")

    if "arms" in command and "motors" in command:
        raise ValueError("Specify arms or motors, not both; both refer to logical arm IDs.")
    arms = command.get("arms", command.get("motors"))
    if not isinstance(arms, list) or not arms:
        raise ValueError("Expected a non-empty arms array (or motors alias).")
    if any(type(arm) is not int or arm not in ARMS_MAPPING for arm in arms):
        raise ValueError(f"Arm IDs must be integers from {sorted(ARMS_MAPPING)}.")
    return arms


def build_board_payloads(command_payload: JsonPayload) -> Dict[int, JsonPayload]:
    """Validate normalized targets, round to whole steps, and route in group order."""
    if not isinstance(command_payload, dict):
        raise ValueError("Expected a JSON object.")
    commands = command_payload.get("commands")
    if not isinstance(commands, list) or not commands:
        raise ValueError("Expected a non-empty commands array.")

    payloads: Dict[int, JsonPayload] = {}
    for command in commands:
        arms = validate_command(command)
        position_steps = round(command["position"] * STEPS_TO_TOP)
        motors_by_board: Dict[int, List[int]] = {}
        for arm in arms:
            mapping = ARMS_MAPPING[arm]
            motors_by_board.setdefault(mapping["board_id"], []).append(mapping["motor"])

        for board_id, motors in motors_by_board.items():
            group = {"motors": motors, "position": position_steps}
            if "step_delay" in command:
                group["step_delay"] = command["step_delay"]
            payloads.setdefault(board_id, {"commands": []})["commands"].append(group)
    return payloads


def send_json_command_to_mapped_boards(
    boards: BoardConnections,
    command_payload: JsonPayload,
    *,
    wait: bool = False,
    verbose: bool = True,
) -> None:
    payloads = build_board_payloads(command_payload)
    missing = sorted(set(payloads) - set(boards))
    if missing:
        raise ValueError(f"Target boards are not connected: {missing}.")

    if wait:
        # Production waits after every phase, so no previous move is in flight.
        for board_id in payloads:
            boards[board_id].reset_input_buffer()

    for board_id, payload in payloads.items():
        message = json.dumps(payload, separators=(",", ":"))
        boards[board_id].write((message + "\n").encode("utf-8"))
        if verbose:
            print(f"[Sent to Board {board_id}]: {message}")

    if wait:
        wait_for_boards(boards, set(payloads))


def wait_for_boards(
    boards: BoardConnections,
    board_ids: Set[int],
    timeout_seconds: float = MOVE_TIMEOUT_SECONDS,
) -> None:
    """Wait for executing/completed from every board, retaining partial serial lines."""
    pending = set(board_ids)
    started: Set[int] = set()
    buffers = {board_id: b"" for board_id in pending}
    deadline = time.monotonic() + timeout_seconds
    while pending:
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Timed out waiting for boards {sorted(pending)}; transition stopped.")
        for board_id in sorted(pending):
            connection = boards[board_id]
            available = connection.in_waiting
            if not available:
                continue
            buffers[board_id] += connection.read(available)
            while b"\n" in buffers[board_id]:
                line, buffers[board_id] = buffers[board_id].split(b"\n", 1)
                if not line.strip():
                    continue
                try:
                    response = json.loads(line)
                except (ValueError, UnicodeError) as error:
                    raise RuntimeError(f"Board {board_id} returned an invalid response.") from error
                if not isinstance(response, dict):
                    raise RuntimeError(f"Board {board_id} returned an invalid response.")
                status = response.get("status")
                if status == "error":
                    raise RuntimeError(f"Board {board_id}: {response.get('message', 'Movement failed.')}")
                if status == "board_ready":
                    raise RuntimeError(f"Board {board_id} restarted; position tracking was reset.")
                if status == "executing":
                    started.add(board_id)
                elif status == "completed" and board_id in started:
                    pending.remove(board_id)
                    break
        if pending:
            time.sleep(0.01)


def select_arm(boards: BoardConnections, arm: int) -> None:
    """Move every arm to the middle, then raise the selection and lower the rest."""
    if type(arm) is not int or (arm not in ARMS_MAPPING and arm != LOWER_ALL):
        raise ValueError(f"Choose an arm from {sorted(ARMS_MAPPING)}, or 9 to lower all.")

    print("Moving all arms to the middle...")
    send_json_command_to_mapped_boards(boards, {
        "commands": [{"arms": sorted(ARMS_MAPPING), "position": 0.5}],
    }, wait=True, verbose=False)

    print("Moving to final positions...")
    send_json_command_to_mapped_boards(boards, {
        "commands": [
            {"arms": [index], "position": 1 if index == arm else 0}
            for index in sorted(ARMS_MAPPING)
        ],
    }, wait=True, verbose=False)
    print("All arms are down." if arm == LOWER_ALL else f"Arm {arm} is up; all others are down.")


def read_and_print_responses(boards: BoardConnections, wait_time_seconds: float = 0.1) -> None:
    time.sleep(wait_time_seconds)
    for board_id, connection in boards.items():
        while connection.in_waiting:
            response = connection.readline().decode("utf-8", errors="replace").strip()
            if response:
                print(f"[Board {board_id}]: {response}")


def parse_user_input(user_input: str) -> Optional[JsonPayload]:
    try:
        payload = json.loads(user_input)
        if not isinstance(payload, dict):
            raise ValueError("Expected a JSON object.")
        return payload
    except ValueError as error:
        print(f"Error: {error}")
        return None


def close_all_connections(boards: BoardConnections) -> None:
    for board_id, connection in boards.items():
        try:
            connection.close()
        except (serial.SerialException, OSError) as error:
            print(f"Error closing Board {board_id}: {error}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Select an arm to raise, or 9 to lower all arms.")
    parser.add_argument("--debug", action="store_true", help="Accept normalized JSON movement commands.")
    args = parser.parse_args()
    boards: BoardConnections = {}
    try:
        boards = connect_to_active_boards(use_board_1=True, use_board_2=True)
        print("All motors must start at the bottom when the boards boot.")
        if args.debug:
            print("Debug mode: positions use 0 = bottom, 0.5 = middle, 1 = top.")
            print('Example: {"commands": [{"arms": [1, 4], "position": 0.5, "step_delay": 125}]}')
            print("Press Enter to read board responses.")
        else:
            print(f"Choose an arm from {sorted(ARMS_MAPPING)}, or 9 to lower all.")
            print("Every selection moves all arms through the middle first.")
        print("Type 'exit' or 'quit' to close.")

        while True:
            user_input = input("JSON >>> " if args.debug else "Arm >>> ").strip()
            if user_input.lower() in ("exit", "quit"):
                break
            if not user_input:
                if args.debug:
                    read_and_print_responses(boards, wait_time_seconds=0)
                continue
            if not args.debug:
                try:
                    arm = int(user_input)
                    select_arm(boards, arm)
                except ValueError as error:
                    print(f"Error: {error}")
                continue
            payload = parse_user_input(user_input)
            if payload is not None:
                try:
                    send_json_command_to_mapped_boards(boards, payload)
                except ValueError as error:
                    print(f"Error: {error}")
                    continue
                read_and_print_responses(boards)
    except (EOFError, KeyboardInterrupt):
        print()
    except (serial.SerialException, OSError, ValueError, RuntimeError) as error:
        print(f"Error: {error}")
    finally:
        close_all_connections(boards)


if __name__ == "__main__":
    main()
