import unittest
from unittest.mock import patch

from throw_a_strike.application import build_throw_control_presentation
from throw_a_strike.domain import (
    ControlStyle,
    CurveLevel,
    PlayerColor,
    ThrowControlCommand,
    ThrowControlCommandKind,
    ThrowControlMachine,
    ThrowSetup,
    build_ball_trajectory,
    resolve_ball_pinfall,
    sample_ball_roll,
)
from throw_a_strike.rendering import (
    EMULATOR_RGB888_BYTE_LENGTH,
    render_pinfall_rgb888,
    render_round_complete_rgb888,
    render_round_throw_rgb888,
    render_throw_result_rgb888,
    render_wrong_color_rgb888,
)
import throw_a_strike.rendering.throw_control_rgb888 as deck_renderer

WHITE = (238, 244, 236)
LANE = (52, 70, 79)
BLUE = (70, 135, 255)
RED_BALL = (225, 55, 65)
GREEN = (55, 205, 100)
YELLOW = (250, 210, 55)


class PinfallAnimationTests(unittest.TestCase):
    def setUp(self):
        self.setup = ThrowSetup(ControlStyle.QUICK, 0, 64, 72, CurveLevel.STRAIGHT, 70)
        machine = ThrowControlMachine(ControlStyle.QUICK, 0)
        machine.apply(ThrowControlCommand(ThrowControlCommandKind.DART_HIT, 1, 0, 64, 72))
        self.presentation = build_throw_control_presentation(machine.snapshot)
        self.trajectory = build_ball_trajectory(self.setup)
        self.resolution = resolve_ball_pinfall(self.trajectory)
        self.sample = sample_ball_roll(self.trajectory, self.resolution, self.trajectory.duration_seconds)

    def pixel(self, frame, x, y):
        index = (y * 128 + x) * 3
        return tuple(frame[index:index + 3])

    def test_byte_identical_full_rack_baseline_and_survivor_pixels(self):
        full = render_round_throw_rgb888(self.presentation, 1, 1, PlayerColor.BLUE)
        explicit = render_round_throw_rgb888(self.presentation, 1, 1, PlayerColor.BLUE, standing_pins=tuple(range(1, 11)))
        survivors = render_round_throw_rgb888(self.presentation, 2, 1, PlayerColor.BLUE, standing_pins=(7, 8, 9, 10))
        self.assertEqual(full, explicit)
        self.assertEqual(self.pixel(survivors, 64, 72), LANE)
        self.assertEqual(self.pixel(survivors, 34, 23), WHITE)
        self.assertEqual(len(survivors), EMULATOR_RGB888_BYTE_LENGTH)

    def test_future_active_finished_waves_and_exact_timing(self):
        future = render_pinfall_rgb888(self.presentation, self.setup, PlayerColor.BLUE, self.sample, self.resolution, 0.119)
        active = render_pinfall_rgb888(self.presentation, self.setup, PlayerColor.BLUE, self.sample, self.resolution, 0.120)
        falling = render_pinfall_rgb888(self.presentation, self.setup, PlayerColor.BLUE, self.sample, self.resolution, 0.240)
        finished = render_pinfall_rgb888(self.presentation, self.setup, PlayerColor.BLUE, self.sample, self.resolution, 0.300)
        self.assertEqual(self.pixel(future, 54, 56), WHITE)
        self.assertNotEqual(active, future)
        self.assertNotEqual(falling, active)
        self.assertEqual(self.pixel(finished, 64, 72), LANE)

    def test_final_survivor_rack_ball_contact_position_and_player_colors(self):
        for color, expected in ((PlayerColor.BLUE, BLUE), (PlayerColor.RED, RED_BALL),
                                (PlayerColor.GREEN, GREEN), (PlayerColor.YELLOW, YELLOW)):
            with self.subTest(color=color):
                frame = render_throw_result_rgb888(self.presentation, self.setup, color, self.sample, self.resolution)
                self.assertEqual(self.pixel(frame, self.sample.x, self.sample.y), expected)
                self.assertEqual(self.pixel(frame, self.resolution.contact_x, self.resolution.contact_y), expected)
                self.assertEqual(self.pixel(frame, 34, 23), WHITE)

    def test_result_label_raw_diagnostics_and_bottom_hud_are_preserved(self):
        labels = []
        original = deck_renderer._text
        with patch.object(deck_renderer, "_text", side_effect=lambda b, t, x, y, c, scale=1: (labels.append(t), original(b, t, x, y, c, scale))[1]):
            render_throw_result_rgb888(self.presentation, self.setup, PlayerColor.BLUE, self.sample, self.resolution)
        self.assertIn("6 PINS", labels)
        self.assertIn("D0 X64 Y72", labels)
        self.assertIn("STR", labels)
        self.assertIn("70%", labels)
        self.assertIn("GOOD", labels)

    def test_no_ball_during_non_ball_frames(self):
        prethrow = render_round_throw_rgb888(self.presentation, 1, 1, PlayerColor.BLUE)
        wrong = render_wrong_color_rgb888(self.presentation, 1, 1, PlayerColor.BLUE)
        complete = render_round_complete_rgb888(self.presentation)
        for frame in (prethrow, wrong, complete):
            self.assertNotEqual(self.pixel(frame, 64, 84), BLUE)


if __name__ == "__main__":
    unittest.main()
