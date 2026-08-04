import unittest

import throw_a_strike.domain as domain
from throw_a_strike.domain.player_darts import (
    InvalidPlayerDartValueError, PlayerColor, emulator_dart_color,
    emulator_dart_indices_for_color, emulator_dart_indices_for_player,
    is_emulator_dart_for_player, player_color_for_number,
)


class PlayerDartPolicyTests(unittest.TestCase):
    def test_exact_colors_and_players(self):
        self.assertEqual(tuple((c.name,c.value) for c in PlayerColor), (
            ("BLUE","blue"),("RED","red"),("GREEN","green"),("YELLOW","yellow")))
        self.assertEqual(tuple(player_color_for_number(n) for n in range(1,5)),tuple(PlayerColor))

    def test_all_emulator_indices_have_one_locked_color(self):
        expected=(PlayerColor.BLUE,PlayerColor.RED,PlayerColor.GREEN,PlayerColor.YELLOW)*3
        self.assertEqual(tuple(emulator_dart_color(i) for i in range(12)),expected)
        self.assertEqual(tuple(emulator_dart_indices_for_color(c) for c in PlayerColor),
                         ((0,4,8),(1,5,9),(2,6,10),(3,7,11)))
        for player in range(1,5):
            indices=emulator_dart_indices_for_player(player)
            self.assertIs(type(indices),tuple)
            self.assertEqual(indices,tuple(sorted(indices)))
            for index in range(12):
                self.assertEqual(is_emulator_dart_for_player(player,index),index in indices)

    def test_exact_validation_rejects_bools_subclasses_and_out_of_range(self):
        class IntSubclass(int): pass
        for value in (True,False,0,5,1.0,IntSubclass(1)):
            with self.subTest(player=value),self.assertRaises(InvalidPlayerDartValueError):
                player_color_for_number(value)
        for value in (True,False,-1,12,1.0,IntSubclass(1)):
            with self.subTest(index=value),self.assertRaises(InvalidPlayerDartValueError):
                emulator_dart_color(value)
        for value in ("blue",1,None):
            with self.subTest(color=value),self.assertRaises(InvalidPlayerDartValueError):
                emulator_dart_indices_for_color(value)

    def test_policy_has_no_throw_number_and_obsolete_helpers_are_not_public(self):
        source=__import__('pathlib').Path('throw_a_strike/domain/player_darts.py').read_text()
        self.assertNotIn('BowlingThrowNumber',source)
        self.assertFalse(hasattr(domain,'expected_emulator_dart_index'))
        self.assertFalse(hasattr(domain,'is_expected_emulator_dart'))

if __name__ == '__main__': unittest.main()
