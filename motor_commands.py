"""Validate user commands and translate arm positions into board payloads."""

from typing import Any, Dict, List

import robot_config as config

JsonPayload = Dict[str, Any]


def validate_position(position: Any) -> None:
    if type(position) not in (int, float) or not config.BOTTOM_POSITION <= position <= config.TOP_POSITION:
        raise ValueError("Position must be a number from 0 (bottom) to 1 (top).")


def validate_step_delay(delay: Any) -> None:
    if type(delay) is not int or not config.MIN_STEP_DELAY_US <= delay <= config.MAX_STEP_DELAY_US:
        raise ValueError(
            f"Step delay must be an integer from {config.MIN_STEP_DELAY_US} "
            f"to {config.MAX_STEP_DELAY_US} microseconds."
        )


def command_arms(command: JsonPayload) -> List[int]:
    """Resolve the motors alias; both names refer to logical arm IDs."""
    if "arms" in command and "motors" in command:
        raise ValueError("Specify arms or motors, not both; both refer to logical arm IDs.")
    arms = command.get("arms", command.get("motors"))
    if not isinstance(arms, list) or not arms:
        raise ValueError("Expected a non-empty arms array (or motors alias).")
    if any(type(arm) is not int or arm not in config.ARMS_MAPPING for arm in arms):
        raise ValueError(f"Arm IDs must be integers from {sorted(config.ARMS_MAPPING)}.")
    return arms


def validate_command(command: Any) -> List[int]:
    if not isinstance(command, dict):
        raise ValueError("Each command must be an object.")
    if "step_count" in command or "direction" in command:
        raise ValueError("Use position instead of step_count and direction.")
    validate_position(command.get("position"))
    validate_step_delay(command.get("step_delay", config.DEFAULT_STEP_DELAY_US))
    return command_arms(command)


def group_motors_by_board(arms: List[int]) -> Dict[int, List[int]]:
    motors: Dict[int, List[int]] = {}
    for arm in arms:
        mapping = config.ARMS_MAPPING[arm]
        motors.setdefault(mapping["board_id"], []).append(mapping["motor"])
    return motors


def build_board_payloads(payload: JsonPayload) -> Dict[int, JsonPayload]:
    """Validate every group before sending; preserve order so the last target wins."""
    if not isinstance(payload, dict):
        raise ValueError("Expected a JSON object.")
    commands = payload.get("commands")
    if not isinstance(commands, list) or not commands:
        raise ValueError("Expected a non-empty commands array.")

    payloads: Dict[int, JsonPayload] = {}
    for command in commands:
        arms = validate_command(command)
        for board_id, motors in group_motors_by_board(arms).items():
            group = {
                "motors": motors,
                "position": round(command["position"] * config.STEPS_TO_TOP),
                "step_delay": command.get("step_delay", config.DEFAULT_STEP_DELAY_US),
            }
            payloads.setdefault(board_id, {"commands": []})["commands"].append(group)
    return payloads


def selection_phases(arm: int) -> List[JsonPayload]:
    """All arms reach the middle before the selected arm rises and the rest lower."""
    if type(arm) is not int or (arm not in config.ARMS_MAPPING and arm != config.LOWER_ALL):
        raise ValueError(
            f"Choose an arm from {sorted(config.ARMS_MAPPING)}, or {config.LOWER_ALL} to lower all."
        )
    arms = sorted(config.ARMS_MAPPING)
    return [
        {"commands": [{"arms": arms, "position": config.MIDDLE_POSITION}]},
        {"commands": [
            {"arms": [index], "position": config.TOP_POSITION if index == arm else config.BOTTOM_POSITION}
            for index in arms
        ]},
    ]
