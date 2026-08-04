"""Pure player-color policy for the confirmed Dartsnut emulator grouping."""

from enum import Enum


class InvalidPlayerDartValueError(ValueError):
    """Raised when a player-dart policy value violates its exact contract."""


class PlayerColor(str, Enum):
    BLUE = "blue"
    RED = "red"
    GREEN = "green"
    YELLOW = "yellow"


_COLORS = tuple(PlayerColor)
_INDICES = {
    PlayerColor.BLUE: (0, 4, 8),
    PlayerColor.RED: (1, 5, 9),
    PlayerColor.GREEN: (2, 6, 10),
    PlayerColor.YELLOW: (3, 7, 11),
}


def player_color_for_number(player_number: int) -> PlayerColor:
    if type(player_number) is not int or not 1 <= player_number <= 4:
        raise InvalidPlayerDartValueError(
            "player_number must be an exact integer from 1 through 4")
    return _COLORS[player_number - 1]


def emulator_dart_color(dart_index: int) -> PlayerColor:
    if type(dart_index) is not int or not 0 <= dart_index <= 11:
        raise InvalidPlayerDartValueError(
            "dart_index must be an exact integer from 0 through 11")
    return _COLORS[dart_index % 4]


def emulator_dart_indices_for_color(color: PlayerColor) -> tuple[int, int, int]:
    if type(color) is not PlayerColor:
        raise InvalidPlayerDartValueError("color must be an exact PlayerColor")
    return _INDICES[color]


def emulator_dart_indices_for_player(player_number: int) -> tuple[int, int, int]:
    return emulator_dart_indices_for_color(player_color_for_number(player_number))


def is_emulator_dart_for_player(player_number: int, dart_index: int) -> bool:
    return emulator_dart_color(dart_index) is player_color_for_number(player_number)


__all__ = ("InvalidPlayerDartValueError", "PlayerColor", "player_color_for_number",
           "emulator_dart_color", "emulator_dart_indices_for_color",
           "emulator_dart_indices_for_player", "is_emulator_dart_for_player")
