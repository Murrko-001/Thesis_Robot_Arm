"""Serial connections, command delivery, and board completion acknowledgements."""

import json
import logging
import time
from typing import Dict, Iterable, Iterator, Set, Tuple

import serial

import robot_config as config
from motor_commands import JsonPayload, build_board_payloads

BoardConnections = Dict[int, serial.Serial]


def connect_boards(board_ids: Iterable[int] = config.ENABLED_BOARDS) -> BoardConnections:
    boards: BoardConnections = {}
    try:
        for board_id in board_ids:
            boards[board_id] = serial.Serial(
                config.PORTS[board_id], config.BAUD_RATE, timeout=config.SERIAL_TIMEOUT_SECONDS,
            )
        if not boards:
            raise ValueError("No boards enabled.")
        time.sleep(config.BOARD_STARTUP_SECONDS)
        for connection in boards.values():
            connection.reset_input_buffer()
    except (serial.SerialException, OSError, ValueError, KeyError, KeyboardInterrupt):
        close_boards(boards)
        raise
    return boards


def close_boards(boards: BoardConnections) -> None:
    for board_id, connection in boards.items():
        try:
            connection.close()
        except (serial.SerialException, OSError) as error:
            logging.warning("Error closing Board %s: %s", board_id, error)


def send_command(boards: BoardConnections, payload: JsonPayload, *, wait: bool = False) -> None:
    payloads = build_board_payloads(payload)
    missing = sorted(set(payloads) - set(boards))
    if missing:
        raise ValueError(f"Target boards are not connected: {missing}.")
    if wait:
        # Only used for sequential production phases, with no previous move in flight.
        for board_id in payloads:
            boards[board_id].reset_input_buffer()
    for board_id, board_payload in payloads.items():
        message = json.dumps(board_payload, separators=(",", ":"))
        boards[board_id].write((message + "\n").encode("utf-8"))
    if wait:
        wait_for_boards(boards, set(payloads))


class ResponseReader:
    """Retain partial serial lines between polls, separately for each board."""

    def __init__(self) -> None:
        self.buffers: Dict[int, bytes] = {}

    def read_lines(self, board_id: int, connection: serial.Serial) -> Iterator[bytes]:
        available = connection.in_waiting
        if available:
            self.buffers[board_id] = self.buffers.get(board_id, b"") + connection.read(available)
        while b"\n" in self.buffers.get(board_id, b""):
            line, self.buffers[board_id] = self.buffers[board_id].split(b"\n", 1)
            if line.strip():
                yield line


def response_status(board_id: int, line: bytes) -> str:
    try:
        response = json.loads(line)
    except (ValueError, UnicodeError) as error:
        raise RuntimeError(f"Board {board_id} returned an invalid response.") from error
    if not isinstance(response, dict):
        raise RuntimeError(f"Board {board_id} returned an invalid response.")
    status = response.get("status", "")
    if status == "error":
        raise RuntimeError(f"Board {board_id}: {response.get('message', 'Movement failed.')}")
    if status == "board_ready":
        raise RuntimeError(f"Board {board_id} restarted; position tracking was reset.")
    return status


def wait_for_boards(
    boards: BoardConnections,
    board_ids: Set[int],
    timeout_seconds: float = config.MOVE_TIMEOUT_SECONDS,
) -> None:
    """A phase finishes only after every board reports executing then completed."""
    pending = set(board_ids)
    started: Set[int] = set()
    reader = ResponseReader()
    deadline = time.monotonic() + timeout_seconds
    while pending:
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Timed out waiting for boards {sorted(pending)}; transition stopped.")
        for board_id in sorted(pending):
            for line in reader.read_lines(board_id, boards[board_id]):
                status = response_status(board_id, line)
                if status == "executing":
                    started.add(board_id)
                elif status == "completed" and board_id in started:
                    pending.remove(board_id)
                    break
        if pending:
            time.sleep(config.RESPONSE_POLL_SECONDS)


def debug_responses(boards: BoardConnections, reader: ResponseReader) -> Iterator[Tuple[int, str]]:
    for board_id, connection in boards.items():
        while connection.in_waiting:
            for line in reader.read_lines(board_id, connection):
                yield board_id, line.decode("utf-8", errors="replace").strip()
