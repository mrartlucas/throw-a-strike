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

from throw_a_strike.application import ThrowControlStyleSelector, InputEvent, InputEventKind, build_throw_control_presentation
from throw_a_strike.domain import ControlStyle
from throw_a_strike.rendering.ten_pin_rgb888 import render_ten_pin_attempt_rgb888, render_ten_pin_game_over_rgb888, TenPinRenderContext

class TenPinRendererCorrectionTests(unittest.TestCase):
    def presentation(self):
        sel=ThrowControlStyleSelector(0).apply((InputEvent(InputEventKind.CONTROL,0,1,control_id='btn_a'),),1)
        from throw_a_strike.application import ThrowControlCoordinator
        from tests.test_emulator_ten_pin import Clock
        class Empty:
            @property
            def capabilities(self): return Clock().capabilities
            def poll(self): return ()
        return build_throw_control_presentation(ThrowControlCoordinator(ControlStyle.QUICK,Empty(),Clock(),0).snapshot)
    def game(self, rolls=()):
        g=BowlingGame()
        for r in rolls: g.roll(r)
        return g.snapshot()
    def pixels_changed(self,a,b,ymin=88):
        return [(i//3)%128 for i in range(ymin*128*3,len(a),3) if a[i:i+3]!=b[i:i+3]]
    def test_throw_ready_blink_changes_prompt_pixels_only(self):
        p=self.presentation(); b=self.game(); on=render_ten_pin_attempt_rgb888(p,b,blink_on=True); off=render_ten_pin_attempt_rgb888(p,b,blink_on=False)
        self.assertNotEqual(on,off); self.assertTrue(self.pixels_changed(on,off))
        self.assertEqual(on[:88*128*3], off[:88*128*3])
    def test_score_strip_does_not_touch_gameplay_area(self):
        p=self.presentation(); b=self.game((7,3,1)); f=render_ten_pin_attempt_rgb888(p,b)
        self.assertEqual(tuple(f[(84*128+64)*3:(84*128+64)*3+3]), (52,70,79))
        self.assertEqual(tuple(f[(72*128+64)*3:(72*128+64)*3+3]), (238,244,236))
    def test_slash_glyph_visible_for_spare_game_over(self):
        g=BowlingGame();
        for _ in range(10): g.roll(7); g.roll(3)
        g.roll(7); frame=render_ten_pin_game_over_rgb888(g.snapshot())
        self.assertNotEqual(frame, bytes([8,12,20])* (128*128))
    def test_final_zero_ninety_150_167_300_render(self):
        cases=(([0,0]*10,0),([9,0]*10,90),([5,5]*10+[5],150),([10,7,3,9,0,10,0,8,8,2,0,6,10,10,10,8,1],167),([10]*12,300))
        for rolls,score in cases:
            g=BowlingGame(); [g.roll(r) for r in rolls]; frame=render_ten_pin_game_over_rgb888(g.snapshot()); self.assertEqual(len(frame),49152); self.assertEqual(g.confirmed_score,score)
    def test_incomplete_game_over_rejected(self):
        from throw_a_strike.application import InvalidPortValueError
        with self.assertRaises(InvalidPortValueError): render_ten_pin_game_over_rgb888(BowlingGame().snapshot())
    def test_invalid_context_rejected(self):
        from throw_a_strike.application import InvalidPortValueError
        with self.assertRaises(InvalidPortValueError): TenPinRenderContext(1,0)
