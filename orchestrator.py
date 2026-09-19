"""Interactive arm selection; use --debug for normalized JSON commands."""

import argparse
import json
import time

import serial

import robot_config as config
from board_connection import (
    BoardConnections,
    ResponseReader,
    close_boards,
    connect_boards,
    debug_responses,
    send_command,
)
from motor_commands import selection_phases


def select_arm(boards: BoardConnections, arm: int) -> None:
    for phase in selection_phases(arm):
        send_command(boards, phase, wait=True)


def handle_selection(boards: BoardConnections, text: str) -> None:
    if not text:
        return
    arm = int(text)
    select_arm(boards, arm)
    print("All arms down." if arm == config.LOWER_ALL else f"Arm {arm} up; others down.")


def handle_debug_command(boards: BoardConnections, text: str, reader: ResponseReader) -> None:
    if text:
        send_command(boards, json.loads(text))
        time.sleep(config.DEBUG_RESPONSE_WAIT_SECONDS)
    for board_id, response in debug_responses(boards, reader):
        print(f"[Board {board_id}] {response}")


def show_controls(debug: bool) -> None:
    print("Start with all arms at the bottom. Type 'quit' to exit.")
    if debug:
        example = {"commands": [{
            "arms": [next(iter(config.ARMS_MAPPING))],
            "position": config.MIDDLE_POSITION,
            "step_delay": config.DEFAULT_STEP_DELAY_US,
        }]}
        print(f"JSON debug mode. Example: {json.dumps(example)}")
        print("Press Enter to read responses.")
    else:
        arms = ", ".join(map(str, sorted(config.ARMS_MAPPING)))
        print(f"Select arm {arms}, or {config.LOWER_ALL} to lower all.")


def run_interactive(boards: BoardConnections, *, debug: bool = False) -> None:
    show_controls(debug)
    reader = ResponseReader()
    prompt = "JSON >>> " if debug else "Arm >>> "
    while True:
        text = input(prompt).strip()
        if text.lower() in ("exit", "quit"):
            return
        try:
            if debug:
                handle_debug_command(boards, text, reader)
            else:
                handle_selection(boards, text)
        except ValueError as error:
            print(f"Error: {error}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Select one arm to raise, or lower all arms.")
    parser.add_argument("--debug", action="store_true", help="Accept normalized JSON movement commands.")
    args = parser.parse_args()
    boards: BoardConnections = {}
    try:
        boards = connect_boards()
        run_interactive(boards, debug=args.debug)
    except (EOFError, KeyboardInterrupt):
        print()
    except (serial.SerialException, OSError, ValueError, RuntimeError, KeyError) as error:
        print(f"Error: {error}")
    finally:
        close_boards(boards)


if __name__ == "__main__":
    main()
