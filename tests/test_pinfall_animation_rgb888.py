import unittest
from throw_a_strike.application import build_throw_control_presentation
from throw_a_strike.domain import *
from throw_a_strike.rendering import *

class PinfallAnimationTests(unittest.TestCase):
    def test_frames_size_change_and_result(self):
        setup=ThrowSetup(ControlStyle.QUICK,0,64,72,CurveLevel.STRAIGHT,70)
        machine=ThrowControlMachine(ControlStyle.QUICK,0); machine.apply(ThrowControlCommand(ThrowControlCommandKind.DART_HIT,1,0,64,72)); pres=build_throw_control_presentation(machine.snapshot)
        traj=build_ball_trajectory(setup); res=resolve_ball_pinfall(traj); sample=sample_ball_roll(traj,res,traj.duration_seconds)
        a=render_pinfall_rgb888(pres,setup,PlayerColor.BLUE,sample,res,0.0)
        b=render_pinfall_rgb888(pres,setup,PlayerColor.BLUE,sample,res,0.2)
        c=render_throw_result_rgb888(pres,setup,PlayerColor.BLUE,sample,res)
        self.assertEqual(len(a),49152); self.assertNotEqual(a,b); self.assertEqual(len(c),49152)

if __name__ == '__main__': unittest.main()
