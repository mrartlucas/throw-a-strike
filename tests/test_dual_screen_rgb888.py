import unittest

from throw_a_strike.application import InvalidPortValueError
from throw_a_strike.domain import (
    BallTrajectorySample,
    BowlingGame,
    BowlingThrowResultKind,
    PinImpactBias,
    PinfallResolution,
    PlayerColor,
)
from throw_a_strike.domain.bowling_round import FULL_RACK
from throw_a_strike.platform import DartsnutButtonId, DartsnutSdkFacade, FakeDartsnutSdk
from throw_a_strike.rendering import (
    FULL_FRAME_RGB888_BYTE_LENGTH,
    MAIN_RGB888_BYTE_LENGTH,
    SECONDARY_RGB888_BYTE_LENGTH,
    compose_dartsnut_full_frame,
    render_secondary_ball_roll_rgb888,
    render_secondary_game_over_rgb888,
    render_secondary_pinfall_rgb888,
    render_secondary_result_rgb888,
    render_secondary_scoreboard_rgb888,
    render_secondary_waiting_rgb888,
)
from throw_a_strike.runtime import EmulatorTenPinRuntime
from tests.test_emulator_ten_pin import Clock


class DualScreenRendererTests(unittest.TestCase):
    def game(self, rolls=()):
        game = BowlingGame()
        for pins in rolls:
            game.roll(pins)
        return game.snapshot()

    def test_compose_maps_secondary_to_lower_left_and_preserves_main(self):
        main = bytes((12, 34, 56)) * (128 * 128)
        secondary = bytes((78, 90, 123)) * (64 * 32)
        full = compose_dartsnut_full_frame(main, secondary)
        self.assertEqual(len(full), FULL_FRAME_RGB888_BYTE_LENGTH)
        self.assertEqual(full[:MAIN_RGB888_BYTE_LENGTH], main)
        row_bytes = 128 * 3
        secondary_row_bytes = 64 * 3
        for row in range(32):
            offset = (128 + row) * row_bytes
            self.assertEqual(full[offset:offset + secondary_row_bytes], secondary[row * secondary_row_bytes:(row + 1) * secondary_row_bytes])
            self.assertEqual(full[offset + secondary_row_bytes:offset + row_bytes], bytes((8, 12, 20)) * 64)

    def test_compose_rejects_wrong_frame_sizes_and_types(self):
        main = bytes(MAIN_RGB888_BYTE_LENGTH)
        secondary = bytes(SECONDARY_RGB888_BYTE_LENGTH)
        for bad_main in (bytearray(main), bytes(MAIN_RGB888_BYTE_LENGTH - 1)):
            with self.assertRaises(InvalidPortValueError):
                compose_dartsnut_full_frame(bad_main, secondary)
        for bad_secondary in (bytearray(secondary), bytes(SECONDARY_RGB888_BYTE_LENGTH - 1)):
            with self.assertRaises(InvalidPortValueError):
                compose_dartsnut_full_frame(main, bad_secondary)

    def test_secondary_states_are_exact_64x32_rgb888_and_not_blank(self):
        bowling = self.game()
        sample = BallTrajectorySample(0.5, 64, 54)
        resolution = PinfallResolution(
            BowlingThrowResultKind.PIN_HIT,
            FULL_RACK,
            1,
            0.5,
            64,
            54,
            0.0,
            -1.0,
            PinImpactBias.CENTER,
            ((1,),),
            (1,),
            tuple(pin for pin in FULL_RACK if pin != 1),
        )
        frames = (
            render_secondary_waiting_rgb888(),
            render_secondary_scoreboard_rgb888(bowling, 1, 1),
            render_secondary_ball_roll_rgb888(sample),
            render_secondary_pinfall_rgb888(sample, resolution, 0.4),
            render_secondary_result_rgb888("1 PINS", bowling, 1, 1),
        )
        self.assertTrue(all(type(frame) is bytes and len(frame) == SECONDARY_RGB888_BYTE_LENGTH for frame in frames))
        self.assertEqual(len(set(frames)), len(frames))
        self.assertTrue(all(any(frame) for frame in frames))

    def test_secondary_game_over_contains_score_specific_pixels(self):
        zero = render_secondary_game_over_rgb888(self.game([0, 0] * 10))
        perfect = render_secondary_game_over_rgb888(self.game([10] * 12))
        self.assertEqual(len(zero), SECONDARY_RGB888_BYTE_LENGTH)
        self.assertNotEqual(zero, perfect)

    def test_runtime_submits_full_128x160_frame(self):
        sdk = FakeDartsnutSdk()
        clock = Clock(0)
        runtime = EmulatorTenPinRuntime(DartsnutSdkFacade(sdk), clock, 0)
        select = runtime.step()
        self.assertEqual(len(select.framebuffer), FULL_FRAME_RGB888_BYTE_LENGTH)
        sdk.queue_button_events((DartsnutButtonId.A,))
        attempt = runtime.step()
        self.assertEqual(len(attempt.framebuffer), FULL_FRAME_RGB888_BYTE_LENGTH)
        self.assertEqual(sdk.submitted_framebuffers[-1], attempt.framebuffer)
        lower_left = attempt.framebuffer[128 * 128 * 3:128 * 128 * 3 + 64 * 3]
        self.assertNotEqual(lower_left, bytes((8, 12, 20)) * 64)


if __name__ == "__main__":
    unittest.main()
