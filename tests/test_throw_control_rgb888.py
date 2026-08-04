import unittest
from unittest.mock import patch
from pathlib import Path

from throw_a_strike.application import ThrowControlStyleSelector, build_throw_control_presentation
from throw_a_strike.domain import (
    ControlStyle, CurveLevel, PowerFeedback, ThrowControlCommand,
    ThrowControlCommandKind, ThrowControlMachine, ThrowControlPhase,
    ThrowControlSnapshot,
)
from throw_a_strike.rendering import (
    EMULATOR_MAIN_HEIGHT, EMULATOR_MAIN_WIDTH, EMULATOR_RGB888_BYTE_LENGTH,
    render_dart_accepted_rgb888, render_style_selection_rgb888, render_throw_control_rgb888,
)
import throw_a_strike.rendering.throw_control_rgb888 as renderer


FEEDBACK = {40: PowerFeedback.WEAK, 50: PowerFeedback.WEAK,
            60: PowerFeedback.GOOD, 70: PowerFeedback.GOOD,
            80: PowerFeedback.PERFECT, 90: PowerFeedback.POWER,
            100: PowerFeedback.OVERDRIVE}


def power_presentation(power):
    snapshot = ThrowControlSnapshot(ControlStyle.ADVANCED, ThrowControlPhase.SET_POWER,
        CurveLevel.STRAIGHT, power, None, FEEDBACK[power], False, None, None)
    return build_throw_control_presentation(snapshot)


class RendererTests(unittest.TestCase):
    def test_constants_bytes_and_determinism(self):
        self.assertEqual((EMULATOR_MAIN_WIDTH, EMULATOR_MAIN_HEIGHT,
                          EMULATOR_RGB888_BYTE_LENGTH), (128, 128, 49152))
        selection = ThrowControlStyleSelector(0).snapshot
        frame = render_style_selection_rgb888(selection)
        self.assertIs(type(frame), bytes)
        self.assertEqual(len(frame), 49152)
        self.assertEqual(frame, render_style_selection_rgb888(selection))

    def test_all_seven_power_values_and_five_full_feedback_labels(self):
        captured = []
        original = renderer._text
        def recording(buf, text, x, y, color, scale=1):
            captured.append(text)
            return original(buf, text, x, y, color, scale)
        frames = []
        with patch.object(renderer, "_text", side_effect=recording):
            for power in FEEDBACK:
                frames.append(render_throw_control_rgb888(power_presentation(power)))
        self.assertEqual(len(set(frames)), 7)
        for label in ("WEAK", "GOOD", "PERFECT", "POWER", "OVERDRIVE"):
            self.assertIn(label, captured)
        for abbreviation in ("PERF", "POWE", "OVER"):
            self.assertNotIn(abbreviation, captured)

    def test_every_curve_level_renders_distinct_hud(self):
        frames = []
        for curve in CurveLevel:
            snapshot = ThrowControlSnapshot(ControlStyle.ADVANCED, ThrowControlPhase.SET_CURVE,
                curve, 70, None, PowerFeedback.GOOD, False, None, None)
            frames.append(render_throw_control_rgb888(build_throw_control_presentation(snapshot)))
        self.assertEqual(len(set(frames)), 7)

    def test_ready_blink_changes_only_lower_hud_and_preserves_curve_power(self):
        presentation = build_throw_control_presentation(ThrowControlMachine(ControlStyle.QUICK).snapshot)
        shown = render_throw_control_rgb888(presentation, True)
        hidden = render_throw_control_rgb888(presentation, False)
        split = 88 * 128 * 3
        self.assertNotEqual(shown, hidden)
        self.assertEqual(shown[:split], hidden[:split])
        # Curve/power live below the flashing prompt rows and remain identical.
        self.assertEqual(shown[110*128*3:], hidden[110*128*3:])

    def test_warning_keeps_throw_now_during_ready_blink_off(self):
        machine = ThrowControlMachine(ControlStyle.QUICK)
        warning = machine.apply(ThrowControlCommand(ThrowControlCommandKind.TICK, 30))
        presentation = build_throw_control_presentation(warning)
        captured = []
        original = renderer._text
        with patch.object(renderer, "_text", side_effect=lambda b,t,x,y,c,scale=1:
                          (captured.append(t), original(b,t,x,y,c,scale))[1]):
            render_throw_control_rgb888(presentation, False)
        self.assertNotIn("THROW READY", captured)
        self.assertIn("THROW NOW", captured)

    def test_complete_has_no_invented_prompt_and_foul_differs(self):
        complete_machine = ThrowControlMachine(ControlStyle.QUICK)
        complete = build_throw_control_presentation(complete_machine.apply(
            ThrowControlCommand(ThrowControlCommandKind.DART_HIT, 1, dart_index=1, x=2, y=3)))
        ready = build_throw_control_presentation(ThrowControlMachine(ControlStyle.QUICK).snapshot)
        foul_machine = ThrowControlMachine(ControlStyle.QUICK)
        foul = build_throw_control_presentation(foul_machine.apply(
            ThrowControlCommand(ThrowControlCommandKind.TICK, 60)))
        self.assertIsNone(complete.primary_prompt)
        self.assertNotEqual(render_throw_control_rgb888(foul), render_throw_control_rgb888(ready))

    def test_dart_accepted_frame_has_exact_diagnostics_and_hud(self):
        machine=ThrowControlMachine(ControlStyle.QUICK)
        complete=build_throw_control_presentation(machine.apply(
            ThrowControlCommand(ThrowControlCommandKind.DART_HIT,1,dart_index=7,x=88,y=99)))
        captured=[]; original=renderer._text
        with patch.object(renderer,"_text",side_effect=lambda b,t,x,y,c,scale=1:
                          (captured.append(t),original(b,t,x,y,c,scale))[1]):
            frame=render_dart_accepted_rgb888(complete,7,88,99)
        self.assertEqual(len(frame),49152)
        self.assertIn("DART ACCEPTED",captured)
        self.assertIn("D7 X88 Y99",captured)
        self.assertIn("STR",captured); self.assertIn("70%",captured); self.assertIn("GOOD",captured)
        self.assertNotIn("0 PINS",captured)

    def test_dart_accepted_rejects_invalid_raw_values(self):
        machine=ThrowControlMachine(ControlStyle.QUICK)
        complete=build_throw_control_presentation(machine.apply(
            ThrowControlCommand(ThrowControlCommandKind.DART_HIT,1,dart_index=0,x=0,y=0)))
        for args in ((True,1,2),(-1,1,2),(0,True,2),(0,1,False),(0,1.0,2)):
            with self.subTest(args=args), self.assertRaises((TypeError,ValueError)):
                render_dart_accepted_rgb888(complete,*args)

    def test_ten_pin_deck_is_stable_upper_play_area(self):
        ready = build_throw_control_presentation(ThrowControlMachine(ControlStyle.QUICK).snapshot)
        frame = render_throw_control_rgb888(ready)
        upper = frame[:88*128*3]
        # Ten seven-by-seven symbols with lane-colored corner cutouts create ample white pixels.
        white = bytes((238, 244, 236))
        self.assertGreaterEqual(sum(upper[i:i+3] == white for i in range(0, len(upper), 3)), 300)

    def test_renderer_introduces_no_bowling_ball_primitive(self):
        source = Path("throw_a_strike/rendering/throw_control_rgb888.py").read_text().lower()
        self.assertNotIn("ball", source)
