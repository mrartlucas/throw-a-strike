import unittest
from throw_a_strike.application import PortCapabilities
from throw_a_strike.platform import DartsnutButtonId,DartsnutSdkFacade,FakeDartsnutSdk,RawDartHit
from throw_a_strike.runtime import EmulatorControlTestPhase,EmulatorControlTestRuntime,run_emulator_control_test

class Clock:
    def __init__(self,*values): self.values=list(values); self.reads=0
    @property
    def capabilities(self): return PortCapabilities(True)
    def monotonic_seconds(self): self.reads+=1; return float(self.values.pop(0))

class RuntimeTests(unittest.TestCase):
    def test_quick_flow_and_terminal_hold(self):
        sdk=FakeDartsnutSdk(); facade=DartsnutSdkFacade(sdk); clock=Clock(1,2)
        runtime=EmulatorControlTestRuntime(facade,clock,0); self.assertEqual(len(sdk.submitted_framebuffers),0)
        sdk.queue_button_events((DartsnutButtonId.A,)); initial=runtime.step(); self.assertEqual(initial.phase,EmulatorControlTestPhase.ATTEMPT)
        sdk.queue_dart_hits((RawDartHit(3,21,45),)); done=runtime.step(); self.assertTrue(done.terminal); self.assertEqual(len(done.framebuffer),49152)
        calls=len(sdk.calls); runtime.step(); self.assertEqual(clock.reads,2); self.assertGreater(len(sdk.calls),calls)
    def test_advanced_recovery_hold(self):
        sdk=FakeDartsnutSdk(); sdk.queue_button_events((DartsnutButtonId.RIGHT,)); sdk.queue_button_events((DartsnutButtonId.A,)); runtime=EmulatorControlTestRuntime(DartsnutSdkFacade(sdk),Clock(1,2,3,4),0)
        self.assertEqual(runtime.step().phase,EmulatorControlTestPhase.SELECT_STYLE)
        self.assertEqual(runtime.step().phase,EmulatorControlTestPhase.ATTEMPT)
        sdk.queue_dart_hits((RawDartHit(1,2,3),)); result=runtime.step(); self.assertEqual(result.phase,EmulatorControlTestPhase.RECOVERY_HOLD)
        remaining=sdk.queued_dart_batch_count; runtime.step(); self.assertEqual(sdk.queued_dart_batch_count,remaining)
    def test_run_closes(self):
        sdk=FakeDartsnutSdk(); sleeps=[]; run_emulator_control_test(DartsnutSdkFacade(sdk),Clock(0),0,max_iterations=1,sleeper=sleeps.append)
        self.assertEqual(sdk.close_count,1); self.assertEqual(len(sleeps),1)
