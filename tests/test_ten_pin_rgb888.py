import unittest
from throw_a_strike.rendering.ten_pin_rgb888 import render_ten_pin_game_over_rgb888
from throw_a_strike.rendering import EMULATOR_RGB888_BYTE_LENGTH
from throw_a_strike.domain import BowlingGame
class TenPinRendererTests(unittest.TestCase):
    def test_game_over_framebuffer_size_and_no_deck_pins(self):
        game=BowlingGame()
        for _ in range(12): game.roll(10)
        frame=render_ten_pin_game_over_rgb888(game.snapshot())
        self.assertEqual(len(frame), EMULATOR_RGB888_BYTE_LENGTH)
        # A deck pin-center pixel remains background because game over has no pins.
        i=(72*128+64)*3
        self.assertEqual(tuple(frame[i:i+3]), (8,12,20))
