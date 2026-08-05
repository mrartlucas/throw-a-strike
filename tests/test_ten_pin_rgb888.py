import unittest
from unittest.mock import patch
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
    def test_throw_ready_is_byte_identical_across_blink_ticks(self):
        p=self.presentation(); b=self.game(); on=render_ten_pin_attempt_rgb888(p,b,blink_on=True); off=render_ten_pin_attempt_rgb888(p,b,blink_on=False)
        self.assertEqual(on, off)
        self.assertEqual(self.pixels_changed(on,off), [])
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
    def test_text_call_masks_are_disjoint_for_attempt_warning_and_foul(self):
        import throw_a_strike.rendering.ten_pin_rgb888 as r
        calls=[]; orig_text=r._text; orig_center=r._center
        def cap_text(buf,text,x,y,c,scale=1): calls.append((text,x,y)); return orig_text(buf,text,x,y,c,scale)
        def cap_center(buf,text,y,c,scale=1): calls.append((text,(128-(len(text)*4-1)*scale)//2,y)); return orig_center(buf,text,y,c,scale)
        p=self.presentation(); b=self.game((7,3,1))
        with patch.object(r,'_text',cap_text), patch.object(r,'_center',cap_center): render_ten_pin_attempt_rgb888(p,b)
        boxes=[]
        for text,x,y in calls:
            boxes.append((text,x,y,x+(len(text)*4-1),y+4))
        for i,a in enumerate(boxes):
            for b2 in boxes[i+1:]:
                overlap=not (a[3] < b2[1] or b2[3] < a[1] or a[4] < b2[2] or b2[4] < a[2])
                self.assertFalse(overlap, (a,b2))
    def test_context_rejects_bool_and_ordinary_third_roll(self):
        from throw_a_strike.application import InvalidPortValueError
        for args in ((True,1),(1,True),(1,3)):
            with self.assertRaises(InvalidPortValueError): TenPinRenderContext(*args)
        self.assertEqual(TenPinRenderContext(10,3).roll_number,3)
    def test_pinfall_elapsed_validation(self):
        from throw_a_strike.application import InvalidPortValueError, ThrowControlPresentation, ThrowControlCurveIcon
        from throw_a_strike.domain import PlayerColor, ThrowSetup, ControlStyle, CurveLevel, BowlingThrowResultKind, PinfallResolution, PinImpactBias, BallTrajectorySample, ThrowControlPhase, PowerFeedback, ThrowControlOutcomeKind
        from throw_a_strike.rendering.ten_pin_rgb888 import render_ten_pin_pinfall_rgb888
        p=ThrowControlPresentation(ControlStyle.QUICK,ThrowControlPhase.COMPLETE,None,None,CurveLevel.STRAIGHT,ThrowControlCurveIcon.STRAIGHT,70,PowerFeedback.PERFECT,True,False,True,ThrowControlOutcomeKind.THROW)
        setup=ThrowSetup(ControlStyle.QUICK,0,64,72,CurveLevel.STRAIGHT,70); sample=BallTrajectorySample(0.5,64,72); res=PinfallResolution(BowlingThrowResultKind.GUTTER,(1,2,3,4,5,6,7,8,9,10),None,1.0,64,10,0.0,-1.0,PinImpactBias.CENTER,(),(),(1,2,3,4,5,6,7,8,9,10))
        b=self.game()
        for bad in (True,'1',float('nan'),float('inf'),float('-inf'),-0.1):
            with self.assertRaises(InvalidPortValueError): render_ten_pin_pinfall_rgb888(p,setup,PlayerColor.BLUE,sample,res,bad,b)
        self.assertEqual(len(render_ten_pin_pinfall_rgb888(p,setup,PlayerColor.BLUE,sample,res,0,b)),49152)
    def test_result_and_game_over_text_calls_include_required_labels(self):
        import throw_a_strike.rendering.ten_pin_rgb888 as r
        seen=[]; orig_text=r._text; orig_center=r._center
        def cap_text(buf,text,x,y,c,scale=1): seen.append(text); return orig_text(buf,text,x,y,c,scale)
        def cap_center(buf,text,y,c,scale=1): seen.append(text); return orig_center(buf,text,y,c,scale)
        with patch.object(r,'_text',cap_text), patch.object(r,'_center',cap_center):
            for rolls,score in (([0,0]*10,0),([9,0]*10,90),([5,5]*10+[5],150),([10,7,3,9,0,10,0,8,8,2,0,6,10,10,10,8,1],167),([10]*12,300)):
                g=BowlingGame(); [g.roll(v) for v in rolls]; render_ten_pin_game_over_rgb888(g.snapshot()); self.assertIn(f'FINAL {score}', seen)
                for n in range(1,11): self.assertIn(f'F{n}', seen)
    def test_result_labels_and_raw_diagnostic_are_drawn_exactly(self):
        import throw_a_strike.rendering.ten_pin_rgb888 as r
        from throw_a_strike.application import ThrowControlPresentation, ThrowControlCurveIcon
        from throw_a_strike.domain import PlayerColor, ThrowSetup, ControlStyle, CurveLevel, BowlingThrowResultKind, PinfallResolution, PinImpactBias, BallTrajectorySample, ThrowControlPhase, PowerFeedback, ThrowControlOutcomeKind
        from throw_a_strike.rendering.ten_pin_rgb888 import render_ten_pin_result_rgb888, TenPinRenderContext
        p=ThrowControlPresentation(ControlStyle.QUICK,ThrowControlPhase.COMPLETE,None,None,CurveLevel.STRAIGHT,ThrowControlCurveIcon.STRAIGHT,70,PowerFeedback.PERFECT,True,False,True,ThrowControlOutcomeKind.THROW)
        setup=ThrowSetup(ControlStyle.QUICK,0,64,72,CurveLevel.STRAIGHT,70); sample=BallTrajectorySample(0.5,64,72); before=(1,2,3,4,5,6,7,8,9,10)
        labels=("STRIKE","SPARE","1 PINS","10 PINS","MISS","GUTTER","FOUL")
        seen=[]; orig=r._center
        def cap(buf,text,y,c,scale=1): seen.append(text); return orig(buf,text,y,c,scale)
        with patch.object(r,'_center',cap):
            for label in labels:
                kind=BowlingThrowResultKind.GUTTER if label=="GUTTER" else BowlingThrowResultKind.MISS if label in ("MISS","FOUL") else BowlingThrowResultKind.PIN_HIT
                knocked=() if kind is not BowlingThrowResultKind.PIN_HIT else (1,) if label=="1 PINS" else before
                waves=() if not knocked else ((1,), tuple(knocked[1:])) if len(knocked)>1 else ((1,),)
                res=PinfallResolution(kind,before,1 if knocked else None,0.5 if knocked else 1.0,64,72 if knocked else 10,0.0,-1.0,PinImpactBias.CENTER,waves,knocked,tuple(p for p in before if p not in knocked))
                render_ten_pin_result_rgb888(p,setup,PlayerColor.BLUE,sample,res,self.game(),label,context=TenPinRenderContext(1,1))
        for label in labels: self.assertIn(label, seen)
        self.assertIn('D0 X64 Y72', seen)
    def test_game_over_draws_exact_marks_for_spare_fixtures(self):
        import throw_a_strike.rendering.ten_pin_rgb888 as r
        fixtures=(([7,3]+[0,0]*9,('7/',)),([0,10]+[0,0]*9,('-/',)),([10,7,3]+[0,0]*8,('X','7/')),([7,3,10]+[0,0]*8,('7/','X')))
        for rolls,marks in fixtures:
            seen=[]; orig=r._text
            def cap(buf,text,x,y,c,scale=1): seen.append(text); return orig(buf,text,x,y,c,scale)
            g=BowlingGame(); [g.roll(v) for v in rolls]
            with patch.object(r,'_text',cap): render_ten_pin_game_over_rgb888(g.snapshot())
            for mark in marks: self.assertIn(mark, seen)
            for frame in g.snapshot().frames:
                self.assertIn(f'F{frame.number}', seen)
                if frame.marks: self.assertIn(''.join(frame.marks), seen)
                if frame.cumulative_score is not None: self.assertIn(str(frame.cumulative_score), seen)
