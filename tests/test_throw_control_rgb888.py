import unittest
from unittest.mock import patch
from pathlib import Path

from throw_a_strike.application import ThrowControlStyleSelector, build_throw_control_presentation
from throw_a_strike.domain import (
    ControlStyle, CurveLevel, PowerFeedback, ThrowControlCommand,
    ThrowControlCommandKind, ThrowControlMachine, ThrowControlPhase,
    ThrowControlSnapshot, PlayerColor, THROW_FOUL_SECONDS, THROW_WARNING_SECONDS,
)
from throw_a_strike.rendering import (
    EMULATOR_MAIN_HEIGHT, EMULATOR_MAIN_WIDTH, EMULATOR_RGB888_BYTE_LENGTH,
    render_dart_accepted_rgb888, render_round_complete_rgb888, render_round_throw_rgb888,
    render_style_selection_rgb888, render_throw_control_rgb888, render_wrong_color_rgb888,
)
import throw_a_strike.rendering.throw_control_rgb888 as renderer


FEEDBACK = {40: PowerFeedback.WEAK, 50: PowerFeedback.WEAK,
            60: PowerFeedback.GOOD, 70: PowerFeedback.PERFECT,
            80: PowerFeedback.GOOD, 90: PowerFeedback.POWER,
            100: PowerFeedback.OVERDRIVE}


def power_presentation(power):
    snapshot = ThrowControlSnapshot(ControlStyle.ADVANCED, ThrowControlPhase.SET_POWER,
        CurveLevel.STRAIGHT, power, None, FEEDBACK[power], False, None, None)
    return build_throw_control_presentation(snapshot)


class RendererTests(unittest.TestCase):
    def arrow_pixels(self, icon):
        buf = renderer._canvas()
        renderer._arrow(buf, icon, 0, 0)
        return {
            (x, y) for y in range(11) for x in range(11)
            if bytes(buf[(y * 128 + x) * 3:(y * 128 + x) * 3 + 3]) == bytes(renderer._CYAN)
        }

    def test_straight_arrow_points_up_with_center_shaft_and_two_sided_head(self):
        pixels = self.arrow_pixels(renderer.ThrowControlCurveIcon.STRAIGHT)
        self.assertIn((5, 2), pixels)
        self.assertTrue(all((5, y) in pixels for y in range(2, 11)))
        self.assertTrue(any(x < 5 and y > 2 for x, y in pixels))
        self.assertTrue(any(x > 5 and y > 2 for x, y in pixels))
        self.assertNotIn((10, 6), pixels)

    def test_left_and_right_arrow_geometry_remains_locked(self):
        self.assertEqual(self.arrow_pixels(renderer.ThrowControlCurveIcon.LEFT), {
            (10, 9), (9, 9), (8, 9), (7, 9), (6, 9), (5, 9),
            (4, 8), (3, 7), (3, 6), (2, 5), (1, 5), (1, 4), (1, 6), (1, 7), (1, 8),
            (2, 4), (3, 4), (4, 4), (5, 4),
        })
        self.assertEqual(self.arrow_pixels(renderer.ThrowControlCurveIcon.RIGHT), {
            (0, 9), (1, 9), (2, 9), (3, 9), (4, 9), (5, 9),
            (6, 8), (7, 7), (7, 6), (8, 5), (9, 5), (9, 4), (9, 6), (9, 7), (9, 8),
            (8, 4), (7, 4), (6, 4), (5, 4),
        })

    def test_every_renderer_is_exact_rgb888_size_and_deterministic(self):
        machine = ThrowControlMachine(ControlStyle.QUICK)
        ready = build_throw_control_presentation(machine.snapshot)
        complete = build_throw_control_presentation(machine.apply(
            ThrowControlCommand(ThrowControlCommandKind.DART_HIT, 1, dart_index=0, x=1, y=2)))
        selection = ThrowControlStyleSelector(0).snapshot
        render_calls = (
            lambda: render_throw_control_rgb888(ready),
            lambda: render_dart_accepted_rgb888(complete, 0, 1, 2),
            lambda: render_round_throw_rgb888(ready, 1, 1, PlayerColor.BLUE),
            lambda: render_wrong_color_rgb888(ready, 1, 1, PlayerColor.BLUE),
            lambda: render_round_complete_rgb888(complete),
            lambda: render_style_selection_rgb888(selection),
        )
        for render in render_calls:
            with self.subTest(render=render):
                first = render()
                self.assertEqual(len(first), EMULATOR_RGB888_BYTE_LENGTH)
                self.assertEqual(first, render())

    def assert_round_labels(self, presentation, expected, throw=1):
        captured=[]; original=renderer._text
        with patch.object(renderer,"_text",side_effect=lambda b,t,x,y,c,scale=1:
                          (captured.append(t),original(b,t,x,y,c,scale))[1]):
            frame=render_round_throw_rgb888(presentation,throw,1,PlayerColor.BLUE)
        self.assertEqual(len(frame),49152)
        for label in expected: self.assertIn(label,captured)
        return captured

    def test_round_header_preserves_quick_ready_warning_and_locked_hud(self):
        machine=ThrowControlMachine(ControlStyle.QUICK)
        ready=build_throw_control_presentation(machine.snapshot)
        labels=self.assert_round_labels(ready,("THROW 1","P1 BLUE","THROW READY",
                                                "STR","70%","PERFECT","Q"))
        captured=[]; original=renderer._text
        with patch.object(renderer,"_text",side_effect=lambda b,t,x,y,c,scale=1:
                          (captured.append(t),original(b,t,x,y,c,scale))[1]):
            render_round_throw_rgb888(ready,1,1,PlayerColor.BLUE,False)
        self.assertIn("THROW READY",captured)
        for label in ("THROW 1","P1 BLUE","STR","70%","PERFECT","Q"):
            self.assertIn(label,captured)
        warning=build_throw_control_presentation(machine.apply(
            ThrowControlCommand(ThrowControlCommandKind.TICK,THROW_WARNING_SECONDS)))
        labels=self.assert_round_labels(warning,("THROW 1","P1 BLUE","THROW NOW"))
        captured=[]; original=renderer._text
        with patch.object(renderer,"_text",side_effect=lambda b,t,x,y,c,scale=1:
                          (captured.append(t),original(b,t,x,y,c,scale))[1]):
            render_round_throw_rgb888(warning,1,1,PlayerColor.BLUE,False)
        self.assertNotIn("THROW READY",captured); self.assertIn("THROW NOW",captured)
        for label in ("THROW 1","P1 BLUE","STR","70%","PERFECT","Q"):
            self.assertIn(label,captured)

    def test_round_header_preserves_advanced_setup_and_recovery_prompts(self):
        curve_machine=ThrowControlMachine(ControlStyle.ADVANCED)
        curve=build_throw_control_presentation(curve_machine.snapshot)
        for blink in (True,False):
            captured=[]; original=renderer._text
            with patch.object(renderer,"_text",side_effect=lambda b,t,x,y,c,scale=1:
                              (captured.append(t),original(b,t,x,y,c,scale))[1]):
                render_round_throw_rgb888(curve,1,1,PlayerColor.BLUE,blink)
            for label in ("THROW 1","P1 BLUE","SET CURVE","STR","70%","PERFECT","A"):
                self.assertIn(label,captured)
        power=build_throw_control_presentation(curve_machine.apply(
            ThrowControlCommand(ThrowControlCommandKind.CONFIRM,1)))
        for blink in (True,False):
            captured=[]; original=renderer._text
            with patch.object(renderer,"_text",side_effect=lambda b,t,x,y,c,scale=1:
                              (captured.append(t),original(b,t,x,y,c,scale))[1]):
                render_round_throw_rgb888(power,1,1,PlayerColor.BLUE,blink)
            self.assertIn("SET LANE ARROW",captured)
        recovery_machine=ThrowControlMachine(ControlStyle.ADVANCED)
        recovery=build_throw_control_presentation(recovery_machine.apply(
            ThrowControlCommand(ThrowControlCommandKind.DART_HIT,1,dart_index=0,x=1,y=2)))
        self.assert_round_labels(recovery,("TOO SOON","REMOVE DART"))
        second_machine=ThrowControlMachine(ControlStyle.ADVANCED)
        self.assert_round_labels(build_throw_control_presentation(second_machine.snapshot),
                                 ("THROW 2","P1 BLUE","SET CURVE"),2)

    def test_round_header_preserves_foul_and_zero_pins(self):
        machine=ThrowControlMachine(ControlStyle.QUICK)
        foul=build_throw_control_presentation(machine.apply(
            ThrowControlCommand(ThrowControlCommandKind.TICK,THROW_FOUL_SECONDS)))
        self.assert_round_labels(foul,("THROW 1","P1 BLUE","FOUL","0 PINS"))

    def test_round_throw_wrong_dart_and_complete_labels(self):
        presentation=build_throw_control_presentation(ThrowControlMachine(ControlStyle.QUICK).snapshot)
        captured=[]; original=renderer._text
        with patch.object(renderer,"_text",side_effect=lambda b,t,x,y,c,scale=1:
                          (captured.append(t),original(b,t,x,y,c,scale))[1]):
            active=render_round_throw_rgb888(presentation,2,1,PlayerColor.BLUE)
            wrong=render_wrong_color_rgb888(presentation,2,1,PlayerColor.BLUE)
            complete_machine=ThrowControlMachine(ControlStyle.QUICK)
            terminal=build_throw_control_presentation(complete_machine.apply(
                ThrowControlCommand(ThrowControlCommandKind.DART_HIT,1,dart_index=4,x=1,y=2)))
            finished=render_round_complete_rgb888(terminal)
        self.assertEqual({len(active),len(wrong),len(finished)},{49152})
        for label in ("THROW 2","USE BLUE DART","WRONG COLOR","ROUND COMPLETE"):
            self.assertIn(label,captured)

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
        for label in ("WEAK", "PERFECT", "PERFECT", "POWER", "OVERDRIVE"):
            self.assertIn(label, captured)
        for abbreviation in ("PERF", "POWE", "OVER"):
            self.assertNotIn(abbreviation, captured)

    def test_every_curve_level_renders_distinct_hud(self):
        frames = []
        for curve in CurveLevel:
            snapshot = ThrowControlSnapshot(ControlStyle.ADVANCED, ThrowControlPhase.SET_CURVE,
                curve, 70, None, PowerFeedback.PERFECT, False, None, None)
            frames.append(render_throw_control_rgb888(build_throw_control_presentation(snapshot)))
        self.assertEqual(len(set(frames)), 7)

    def test_ready_prompt_is_static_across_blink_ticks(self):
        presentation = build_throw_control_presentation(ThrowControlMachine(ControlStyle.QUICK).snapshot)
        shown = render_throw_control_rgb888(presentation, True)
        hidden = render_throw_control_rgb888(presentation, False)
        self.assertEqual(shown, hidden)


    def test_power_bar_has_seven_segments_and_exact_fill(self):
        for power,filled in ((40,1),(70,4),(80,5),(100,7),(90,6),(50,2)):
            with self.subTest(power=power):
                calls=[]
                original=renderer._rect
                with patch.object(renderer,"_rect",side_effect=lambda b,x,y,w,h,c:
                                  (calls.append((x,y,w,h,c)),original(b,x,y,w,h,c))[1]):
                    frame=render_throw_control_rgb888(power_presentation(power))
                segments=[call for call in calls if call[1:4] == (118,4,2)]
                self.assertEqual(len(segments),7)
                self.assertEqual(sum(call[4] == renderer._CYAN for call in segments),filled)
                self.assertEqual(len(frame),EMULATOR_RGB888_BYTE_LENGTH)

    def test_warning_keeps_throw_now_during_ready_blink_off(self):
        machine = ThrowControlMachine(ControlStyle.QUICK)
        warning = machine.apply(ThrowControlCommand(
            ThrowControlCommandKind.TICK,
            THROW_WARNING_SECONDS,
        ))
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
            ThrowControlCommand(ThrowControlCommandKind.TICK, THROW_FOUL_SECONDS)))
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
        self.assertIn("STR",captured); self.assertIn("70%",captured); self.assertIn("PERFECT",captured)
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
