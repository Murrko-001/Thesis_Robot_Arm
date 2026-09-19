import json
import unittest
from unittest.mock import Mock, patch

import orchestrator


class SimulatedBoard:
    def __init__(self, board_id, events, replies=None):
        self.board_id = board_id
        self.events = events
        self.replies = replies if replies is not None else [
            b'{"status":"executing"}\n', b'{"status":"completed"}\n',
        ]
        self.chunks = []
        self.payloads = []

    def reset_input_buffer(self):
        self.chunks.clear()

    def write(self, message):
        self.payloads.append(json.loads(message))
        self.events.append(("write", self.board_id))
        self.chunks.extend(self.replies)
        return len(message)

    @property
    def in_waiting(self):
        return len(self.chunks[0]) if self.chunks else 0

    def read(self, size):
        chunk = self.chunks.pop(0)
        self.events.append(("read", self.board_id, chunk))
        return chunk


class CommandTests(unittest.TestCase):
    def test_routes_absolute_positions_and_preserves_group_order(self):
        payloads = orchestrator.build_board_payloads({"commands": [
            {"arms": [1, 2, 3, 4], "position": 1, "step_delay": 125},
            {"arms": [1], "position": 0},
        ]})
        self.assertEqual(payloads, {
            1: {"commands": [
                {"motors": [1, 3], "position": 45000, "step_delay": 125},
                {"motors": [1], "position": 0},
            ]},
            2: {"commands": [
                {"motors": [2, 3], "position": 45000, "step_delay": 125},
            ]},
        })

    def test_motors_alias_uses_logical_arm_ids(self):
        self.assertEqual(orchestrator.build_board_payloads({"commands": [
            {"motors": [4], "position": 0.5},
        ]}), {2: {"commands": [{"motors": [3], "position": 22500}]}})

    def test_invalid_requests_never_write_to_boards(self):
        valid = {"arms": [1], "position": 0.5}
        invalid_groups = [
            None, [], {},
            *[{**valid, "position": value} for value in (
                -0.01, 1.01, 45000, True, False, "0.5", None,
                float("nan"), float("inf"), float("-inf"),
            )],
            *[{**valid, "step_delay": value} for value in (0, -1, 32768, True, 1.5, None)],
            *[{**valid, "arms": value} for value in ([], [0], [5], [True], [1.0], "1", None)],
            {**valid, "step_count": 10},
            {**valid, "direction": "UP"},
            {**valid, "motors": [1]},
        ]
        invalid_payloads = [None, [], {}, {"commands": []}, {"commands": {}}]
        invalid_payloads += [{"commands": [valid, group]} for group in invalid_groups]
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                board = Mock()
                with self.assertRaises(ValueError):
                    orchestrator.send_json_command_to_mapped_boards({1: board}, payload)
                board.write.assert_not_called()

    def test_missing_board_prevents_all_writes(self):
        board = Mock()
        with self.assertRaises(ValueError):
            orchestrator.send_json_command_to_mapped_boards({1: board}, {
                "commands": [{"arms": [1, 4], "position": 1}],
            })
        board.write.assert_not_called()

    def test_repeated_targets_are_sent_as_absolute_positions(self):
        board = Mock()
        payload = {"commands": [{"arms": [2], "position": 0.5}]}
        with patch("builtins.print"):
            for _ in range(2):
                orchestrator.send_json_command_to_mapped_boards({1: board}, payload)
        self.assertEqual(board.write.call_count, 2)
        for call in board.write.call_args_list:
            message = call.args[0]
            self.assertTrue(message.endswith(b"\n"))
            self.assertEqual(json.loads(message), {
                "commands": [{"motors": [3], "position": 22500}],
            })

    def test_normalized_positions_convert_to_nearest_step(self):
        for position, expected in (
            (0, 0), (0.0, 0), (0.25, 11250), (0.5, 22500),
            (0.75, 33750), (1, 45000), (1.0, 45000),
            (0.12345, 5555), (0.12346, 5556),
        ):
            with self.subTest(position=position):
                payload = {"commands": [{"arms": [1], "position": position}]}
                result = orchestrator.build_board_payloads(payload)
                actual = result[1]["commands"][0]["position"]
                self.assertEqual(actual, expected)
                self.assertIs(type(actual), int)
                self.assertEqual(payload["commands"][0]["position"], position)

    def test_partial_connection_failure_closes_open_boards(self):
        board = Mock()
        with patch.object(orchestrator, "connect_to_single_board", side_effect=[
            board, orchestrator.serial.SerialException("unavailable"),
        ]):
            with self.assertRaises(orchestrator.serial.SerialException):
                orchestrator.connect_to_active_boards(True, True)
        board.close.assert_called_once()


class ProductionTests(unittest.TestCase):
    def test_every_selection_waits_at_middle_then_sets_only_selected_arm_high(self):
        for selected in (*orchestrator.ARMS_MAPPING, 9):
            with self.subTest(selected=selected):
                events = []
                boards = {index: SimulatedBoard(index, events) for index in (1, 2)}
                with patch("builtins.print"), patch.object(orchestrator.time, "sleep"):
                    orchestrator.select_arm(boards, selected)
                for arm, mapping in orchestrator.ARMS_MAPPING.items():
                    phases = boards[mapping["board_id"]].payloads
                    self.assertEqual(len(phases), 2)
                    for phase, expected in ((0, 22500), (1, 45000 if arm == selected else 0)):
                        targets = [group["position"] for group in phases[phase]["commands"]
                                   if mapping["motor"] in group["motors"]]
                        self.assertEqual(targets, [expected])
                writes = [i for i, event in enumerate(events) if event[0] == "write"]
                completed = [i for i, event in enumerate(events)
                             if event[0] == "read" and b"completed" in event[2]]
                self.assertLess(max(completed[:2]), writes[2])
                self.assertEqual(len(completed), 4)

    def test_invalid_selection_or_missing_board_sends_nothing(self):
        for selected in (0, 5, 10, True, 1.5, "1", 1):
            with self.subTest(selected=selected):
                board = Mock()
                with patch("builtins.print"), self.assertRaises(ValueError):
                    orchestrator.select_arm({1: board}, selected)
                board.write.assert_not_called()

    def test_board_error_or_restart_prevents_final_phase(self):
        for reply in (
            b'{"status":"error","message":"Invalid target"}\n',
            b'{"status":"board_ready"}\n',
            b'not json\n',
        ):
            with self.subTest(reply=reply):
                boards = {1: SimulatedBoard(1, [], [reply]), 2: SimulatedBoard(2, [])}
                with patch("builtins.print"), self.assertRaises(RuntimeError):
                    orchestrator.select_arm(boards, 1)
                for board in boards.values():
                    self.assertEqual(len(board.payloads), 1)

    def test_partial_lines_and_completion_without_executing(self):
        board = SimulatedBoard(1, [])
        board.chunks = [
            b'{"status":"completed"}\n',
            b'{"status":"exec', b'uting"}\n{"status":"com', b'pleted"}\n',
        ]
        with patch.object(orchestrator.time, "sleep"):
            orchestrator.wait_for_boards({1: board}, {1})
        self.assertEqual(board.chunks, [])

    def test_timeout_prevents_final_phase(self):
        boards = {index: SimulatedBoard(index, [], []) for index in (1, 2)}
        with patch("builtins.print"), patch.object(
            orchestrator.time, "monotonic", side_effect=[0, 31],
        ), self.assertRaises(TimeoutError):
            orchestrator.select_arm(boards, 1)
        for board in boards.values():
            self.assertEqual(len(board.payloads), 1)

    def test_debug_mode_accepts_json(self):
        payload = {"commands": [{"arms": [1, 4], "position": 0.5}]}
        with patch("sys.argv", ["orchestrator.py", "--debug"]), patch(
            "builtins.input", side_effect=[json.dumps(payload), "quit"],
        ), patch("builtins.print"), patch.object(
            orchestrator, "connect_to_active_boards", return_value={},
        ), patch.object(orchestrator, "send_json_command_to_mapped_boards") as send, patch.object(
            orchestrator, "read_and_print_responses",
        ):
            orchestrator.main()
        send.assert_called_once_with({}, payload)

    def test_default_mode_accepts_arm_index(self):
        with patch("sys.argv", ["orchestrator.py"]), patch(
            "builtins.input", side_effect=["4", "9", "quit"],
        ), patch("builtins.print"), patch.object(
            orchestrator, "connect_to_active_boards", return_value={},
        ), patch.object(orchestrator, "select_arm") as select:
            orchestrator.main()
        self.assertEqual([call.args for call in select.call_args_list], [({}, 4), ({}, 9)])


if __name__ == "__main__":
    unittest.main()
