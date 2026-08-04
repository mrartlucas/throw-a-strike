import unittest
from throw_a_strike.application import build_throw_control_presentation
from throw_a_strike.domain import *
from throw_a_strike.rendering import *

class BallRendererTests(unittest.TestCase):
    def setUp(self):
        machine=ThrowControlMachine(ControlStyle.QUICK,0); machine.apply(ThrowControlCommand(ThrowControlCommandKind.DART_HIT,1,0,64,23))
        self.presentation=build_throw_control_presentation(machine.snapshot); self.setup=machine.snapshot.outcome.setup
        self.trajectory=build_ball_trajectory(self.setup)
    def pixel(self,frame,x,y):
        i=(y*128+x)*3; return tuple(frame[i:i+3])
    def test_start_target_color_holes_and_size(self):
        start=sample_ball_trajectory(self.trajectory,0); end=sample_ball_trajectory(self.trajectory,99)
        a=render_ball_roll_rgb888(self.presentation,1,1,PlayerColor.BLUE,start)
        b=render_ball_arrival_rgb888(self.presentation,self.setup,PlayerColor.BLUE,end)
        self.assertEqual((len(a),len(b)),(49152,49152)); self.assertEqual(self.pixel(a,64,84),(70,135,255)); self.assertEqual(self.pixel(a,63,83),(8,12,20)); self.assertEqual(self.pixel(b,64,23),(70,135,255))
    def test_deterministic_and_curves_differ(self):
        sample=sample_ball_trajectory(self.trajectory,.45)
        self.assertEqual(render_ball_roll_rgb888(self.presentation,1,1,PlayerColor.BLUE,sample),render_ball_roll_rgb888(self.presentation,1,1,PlayerColor.BLUE,sample))
        left=build_ball_trajectory(ThrowSetup(ControlStyle.ADVANCED,0,64,23,CurveLevel.LEFT_3,70)); right=build_ball_trajectory(ThrowSetup(ControlStyle.ADVANCED,0,64,23,CurveLevel.RIGHT_3,70))
        self.assertNotEqual(sample_ball_trajectory(left,.45).x,sample_ball_trajectory(right,.45).x)
    def test_prethrow_has_no_ball_at_start(self):
        # The lane pin at 64,72 is unchanged; the start center remains lane color.
        frame=render_round_throw_rgb888(self.presentation,1,1,PlayerColor.BLUE)
        self.assertEqual(self.pixel(frame,64,84),(52,70,79))
if __name__=='__main__': unittest.main()
