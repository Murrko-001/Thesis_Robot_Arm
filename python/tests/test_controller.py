import json
import unittest
from typing import List, Optional, Tuple, Union
from unittest.mock import Mock, patch

import config
import controller


class Board:
    def __init__(
        self,
        board_id: int,
        events: List[Union[Tuple[str, int], Tuple[str, int, bytes]]],
        replies: Optional[List[bytes]] = None,
    ) -> None:
        self.board_id = board_id
        self.events = events
        self.replies = replies if replies is not None else [
            b'{"status":"exec', b'uting"}\n{"status":"completed"}\n',
        ]
        self.chunks = []
        self.payloads = []

    def write(self, message: bytes) -> None:
        assert message.endswith(b"\n")
        self.payloads.append(json.loads(message))
        self.events.append(("write", self.board_id))
        self.chunks.extend(self.replies)

    @property
    def in_waiting(self) -> int:
        return len(self.chunks[0]) if self.chunks else 0

    def read(self, size: int) -> bytes:
        chunk = self.chunks.pop(0) if size else b""
        self.events.append(("read", self.board_id, chunk))
        return chunk


class ControllerTests(unittest.TestCase):
    def test_routes_commands_and_converts_positions(self) -> None:
        result = controller.board_payloads({"commands": [
            {"arms": [1, 2, 3, 4], "position": 0.5, "step_delay": 250},
            {"arms": [1], "position": 0},
        ]})
        self.assertEqual(result, {
            1: {"commands": [
                {"motors": [1, 3], "position": 22500, "step_delay": 250},
                {"motors": [1], "position": 0, "step_delay": config.DEFAULT_STEP_DELAY_US},
            ]},
            2: {"commands": [{"motors": [2, 3], "position": 22500, "step_delay": 250}]},
        })

    def test_selections_wait_for_both_boards_between_phases(self) -> None:
        for middle in (False, True):
            for selected in (*config.ARMS_MAPPING, config.LOWER_ALL):
                with self.subTest(middle=middle, selected=selected):
                    events = []
                    boards = {i: Board(i, events) for i in (1, 2)}
                    with patch.object(config, "MOVE_THROUGH_MIDDLE", middle), patch(
                        "controller.time.sleep",
                    ), patch("builtins.print"):
                        controller.select_arm(boards, selected)
                    for arm, mapping in config.ARMS_MAPPING.items():
                        payloads = boards[mapping["board_id"]].payloads
                        targets = [group["position"] for payload in payloads
                                   for group in payload["commands"] if mapping["motor"] in group["motors"]]
                        final = config.TOP_POSITION if arm == selected else config.BOTTOM_POSITION
                        expected = [round(final * config.STEPS_TO_TOP)]
                        if middle:
                            expected.insert(0, round(config.MIDDLE_POSITION * config.STEPS_TO_TOP))
                        self.assertEqual(targets, expected)
                    writes = [i for i, event in enumerate(events) if event[0] == "write"]
                    reads = [i for i, event in enumerate(events) if event[0] == "read"]
                    self.assertLess(writes[1], reads[0])
                    if middle:
                        completions = [i for i, event in enumerate(events)
                                       if event[0] == "read" and b"completed" in event[2]]
                        self.assertLess(max(completions[:2]), writes[2])

    def test_invalid_command_or_missing_board_prevents_all_writes(self) -> None:
        for command in (
            {"arms": [1], "position": 2},
            {"arms": [5], "position": 0.5},
            {"arms": [1], "position": 0.5, "step_delay": 0},
            {"arms": [4], "position": 0.5},
        ):
            board = Mock()
            with self.assertRaises(ValueError):
                controller.send_command({1: board}, {"commands": [
                    {"arms": [1], "position": 0.5}, command,
                ]})
            board.write.assert_not_called()

    def test_board_failure_prevents_next_phase(self) -> None:
        for reply in (b'{"status":"error","message":"Failed"}\n',
                      b'{"status":"board_ready"}\n', b'not json\n'):
            boards = {i: Board(i, [], [reply]) for i in (1, 2)}
            with patch.object(config, "MOVE_THROUGH_MIDDLE", True), patch("builtins.print"):
                with self.assertRaises(RuntimeError):
                    controller.select_arm(boards, 1)
            self.assertTrue(all(len(board.payloads) == 1 for board in boards.values()))

    def test_timeout_prevents_next_phase(self) -> None:
        boards = {i: Board(i, [], []) for i in (1, 2)}
        with patch("controller.time.monotonic", side_effect=[0, config.MOVE_TIMEOUT_SECONDS + 1]):
            with self.assertRaises(TimeoutError):
                controller.select_arm(boards, 1)
        self.assertTrue(all(len(board.payloads) == 1 for board in boards.values()))

    def test_arm_input_selects_arm_and_closes_connections(self) -> None:
        board = Mock()
        with patch("sys.argv", ["controller.py"]), patch(
            "builtins.input", side_effect=['{"commands": []}', "1", "9", "quit"],
        ), patch("builtins.print"), patch("controller.time.sleep"), patch(
            "controller.serial.Serial", return_value=board,
        ), patch("controller.select_arm") as select:
            controller.main()
        boards = dict.fromkeys(config.ENABLED_BOARDS, board)
        self.assertEqual([call.args for call in select.call_args_list], [(boards, 1), (boards, 9)])
        self.assertEqual(board.close.call_count, len(config.ENABLED_BOARDS))

    def test_connection_failure_closes_already_open_port(self) -> None:
        board = Mock()
        with patch("sys.argv", ["controller.py"]), patch("builtins.print"), patch(
            "controller.serial.Serial", side_effect=[board, OSError("Unavailable")],
        ):
            controller.main()
        board.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
