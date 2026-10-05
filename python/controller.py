"""Select an arm to raise, or lower all arms."""

import argparse
import json
import time
from typing import Any, Dict

import serial

import config

JsonPayload = Dict[str, Any]


def validate_command(arms: Any, position: Any, delay: Any) -> None:
    if not isinstance(arms, list) or not arms:
        raise ValueError(f"arms must contain IDs from {list(config.ARMS_MAPPING)}.")
    for arm in arms:
        if type(arm) is not int or arm not in config.ARMS_MAPPING:
            raise ValueError(f"arms must contain IDs from {list(config.ARMS_MAPPING)}.")
    if type(position) not in (int, float) or not 0 <= position <= 1:
        raise ValueError("position must be a number from 0 to 1.")
    if type(delay) is not int or not 1 <= delay <= 32767:
        raise ValueError("step_delay must be an integer from 1 to 32767 microseconds.")


def board_payloads(payload: JsonPayload) -> Dict[int, JsonPayload]:
    """Convert arm positions (0–1) to motor positions in steps, grouped by board."""
    commands = payload.get("commands") if isinstance(payload, dict) else None

    if not isinstance(commands, list) or not commands:
        raise ValueError('Expected {"commands": [{"arms": [1], "position": 0.5}]}.')

    payloads = {}
    for command in commands:
        if not isinstance(command, dict):
            raise ValueError("Each command must be an object.")
        
        arms = command.get("arms")
        position = command.get("position")
        delay = command.get("step_delay", config.DEFAULT_STEP_DELAY_US)

        validate_command(arms, position, delay)
        motors_by_board = {}
        for arm in arms:
            mapping = config.ARMS_MAPPING[arm]
            motors_by_board.setdefault(mapping["board_id"], []).append(mapping["motor"])

        for board_id, motor_ids in motors_by_board.items():
            if board_id not in payloads:
                payloads[board_id] = {"commands": []}
            payloads[board_id]["commands"].append({
                "motors": motor_ids,
                "position": round(position * config.STEPS_TO_TOP),
                "step_delay": delay,
            })
    return payloads


def send_command(boards: Dict[int, serial.Serial], payload: JsonPayload) -> None:
    """Send to all target boards, then print responses until all have finished."""
    payloads = board_payloads(payload)
    missing = payloads.keys() - boards.keys()
    if missing:
        raise ValueError(f"Boards are not connected: {sorted(missing)}.")

    for board_id, command in payloads.items():
        message = json.dumps(command, separators=(",", ":")) + "\n"
        boards[board_id].write(message.encode())

    pending = set(payloads)
    started = set()
    buffers = {board_id: b"" for board_id in pending}
    deadline = time.monotonic() + config.MOVE_TIMEOUT_SECONDS

    while pending:
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Timed out waiting for boards {sorted(pending)}.")
        for board_id in sorted(pending):
            connection = boards[board_id]
            buffers[board_id] += connection.read(connection.in_waiting)
            while b"\n" in buffers[board_id]:
                line, buffers[board_id] = buffers[board_id].split(b"\n", 1)
                if not line.strip():
                    continue

                print(f"[Board {board_id}] {line.decode(errors='replace')}")
                try:
                    response = json.loads(line)
                    status = response["status"]
                except (ValueError, KeyError, TypeError) as error:
                    raise RuntimeError(f"Board {board_id} returned an invalid response.") from error

                if status in ("error", "board_ready"):
                    message = response.get("message", "Board restarted.")
                    raise RuntimeError(f"Board {board_id}: {message}")
                if status == "executing":
                    started.add(board_id)
                elif status == "completed" and board_id in started:
                    pending.discard(board_id)
        if pending:
            time.sleep(config.RESPONSE_POLL_SECONDS)


def select_arm(boards: Dict[int, serial.Serial], arm: int) -> None:
    if arm not in config.ARMS_MAPPING and arm != config.LOWER_ALL:
        raise ValueError(
            f"Choose an arm from {list(config.ARMS_MAPPING)}, "
            f"or {config.LOWER_ALL} to lower all."
        )

    if config.MOVE_THROUGH_MIDDLE:
        middle = {"arms": list(config.ARMS_MAPPING), "position": config.MIDDLE_POSITION}
        send_command(boards, {"commands": [middle]})

    commands = []
    for arm_id in config.ARMS_MAPPING:
        position = config.TOP_POSITION if arm_id == arm else config.BOTTOM_POSITION
        commands.append({"arms": [arm_id], "position": position})
    send_command(boards, {"commands": commands})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    boards = {}
    try:
        for board_id in config.ENABLED_BOARDS:
            boards[board_id] = serial.Serial(
                config.PORTS[board_id],
                config.BAUD_RATE,
                timeout=config.SERIAL_TIMEOUT_SECONDS,
            )

        time.sleep(config.BOARD_STARTUP_SECONDS)
        for connection in boards.values():
            connection.reset_input_buffer()

        print("Start with all arms at the bottom. Type 'quit' to exit.")
        print(f"Select arm {list(config.ARMS_MAPPING)}, or {config.LOWER_ALL} to lower all.")

        while True:
            text = input("Arm >>> ").strip()
            if text.lower() in ("quit", "exit"):
                break
            if not text:
                continue

            try:
                select_arm(boards, int(text))
            except ValueError as error:
                print(f"Error: {error}")
    except (EOFError, KeyboardInterrupt):
        print()
    except (OSError, RuntimeError) as error:
        print(f"Error: {error}")
    finally:
        for connection in boards.values():
            connection.close()


if __name__ == "__main__":
    main()
