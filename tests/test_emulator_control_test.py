import unittest
from throw_a_strike.application import PortCapabilities
from throw_a_strike.domain import BowlingThrowResultKind, PlayerColor, ThrowControlPhase
from throw_a_strike.platform import DartsnutButtonId,DartsnutSdkFacade,FakeDartsnutSdk,RawDartHit
from throw_a_strike.runtime import *

class Clock:
    def __init__(self,*values): self.values=list(values); self.reads=0
    @property
    def capabilities(self): return PortCapabilities(True)
    def monotonic_seconds(self): self.reads+=1; return float(self.values.pop(0))

class RuntimeBallTests(unittest.TestCase):
    def start(self,clock):
        sdk=FakeDartsnutSdk(); runtime=EmulatorControlTestRuntime(DartsnutSdkFacade(sdk),clock,0)
        sdk.queue_button_events((DartsnutButtonId.A,)); runtime.step(); return sdk,runtime
    def test_legal_quick_throw_rolls_then_records_at_arrival(self):
        clock=Clock(1,2,2.45,2.9,4.39,4.4); sdk,runtime=self.start(clock)
        sdk.queue_dart_hits((RawDartHit(0,21,45),)); first=runtime.step()
        self.assertEqual(first.phase,EmulatorControlTestPhase.BALL_ROLL); self.assertIsNone(first.accepted_setup)
        self.assertEqual(runtime.ball_trajectory.duration_seconds,.9); self.assertIsNone(runtime.round_snapshot.first_result)
        reads=clock.reads; held=runtime.step(); self.assertEqual(clock.reads,reads+1); self.assertEqual(held.phase,EmulatorControlTestPhase.BALL_ROLL); self.assertIsNone(runtime.round_snapshot.first_result)
        arrived=runtime.step(); self.assertEqual(arrived.phase,EmulatorControlTestPhase.ACCEPTED_HOLD)
        result=runtime.round_snapshot.first_result; self.assertEqual(result.kind,BowlingThrowResultKind.MISS); self.assertEqual((result.dart_index,result.aim_x,result.aim_y),(0,21,45)); self.assertEqual(runtime.accepted_timestamp,2.9)
        self.assertEqual(runtime.step().phase,EmulatorControlTestPhase.ACCEPTED_HOLD)
        self.assertEqual(runtime.step().phase,EmulatorControlTestPhase.ATTEMPT)
    def test_roll_polls_no_input_and_submits_one_frame(self):
        clock=Clock(1,2,2.1,2.2); sdk,runtime=self.start(clock); sdk.queue_dart_hits((RawDartHit(0,64,23),)); runtime.step()
        sdk.queue_dart_hits((RawDartHit(4,10,10),)); queued=len(sdk._dart_batches); frames=len(sdk.submitted_framebuffers); runtime.step()
        self.assertEqual(len(sdk.submitted_framebuffers),frames+1)
        self.assertEqual(len(sdk._dart_batches),queued); self.assertEqual(sdk.reset_blocking_count,0)
    def test_wrong_color_and_foul_create_no_trajectory(self):
        clock=Clock(1,2,2); sdk,runtime=self.start(clock); sdk.queue_dart_hits((RawDartHit(1,3,4),)); self.assertEqual(runtime.step().phase,EmulatorControlTestPhase.WRONG_COLOR_HOLD); self.assertIsNone(runtime.ball_trajectory)
        clock=Clock(1,31); sdk,runtime=self.start(clock); self.assertEqual(runtime.step().phase,EmulatorControlTestPhase.FOUL_HOLD); self.assertIsNone(runtime.ball_trajectory)
    def test_two_throws_complete_only_after_each_animation_and_hold(self):
        clock=Clock(1,2,2.9,4.4,5,5.9,7.4); sdk,runtime=self.start(clock)
        sdk.queue_dart_hits((RawDartHit(0,20,40),)); runtime.step(); runtime.step(); runtime.step()
        self.assertEqual(runtime.phase,EmulatorControlTestPhase.ATTEMPT)
        sdk.queue_dart_hits((RawDartHit(4,88,99),)); runtime.step(); self.assertIsNone(runtime.round_snapshot.second_result)
        runtime.step(); self.assertEqual(runtime.round_snapshot.second_result.aim_y,99)
        self.assertEqual(runtime.step().phase,EmulatorControlTestPhase.ROUND_COMPLETE); self.assertEqual(runtime.round_snapshot.standing_pins,tuple(range(1,11)))
    def test_step_validation_rejects_accepted_setup_during_roll(self):
        clock=Clock(1,2); sdk,runtime=self.start(clock); sdk.queue_dart_hits((RawDartHit(0,20,40),)); step=runtime.step()
        with self.assertRaises(Exception): EmulatorControlTestStep(step.phase,step.selection,step.presentation,step.framebuffer,True,runtime.accepted_setup)
if __name__=='__main__': unittest.main()
