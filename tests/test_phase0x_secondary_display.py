"""Phase 0X secondary display emulator preview tests."""
import unittest
from unittest.mock import patch

from throw_a_strike.application import PortCapabilities
from throw_a_strike.application.regulation_presentation import RegulationPresentationEventKind
from throw_a_strike.domain import BowlingThrowResultKind, PINFALL_DURATION_SECONDS, PinImpactBias, PinfallResolution
from throw_a_strike.domain.bowling_round import FULL_RACK
from throw_a_strike.platform import DartsnutButtonId, DartsnutSdkFacade, FakeDartsnutSdk, RawDartHit
from throw_a_strike.rendering import EMULATOR_RGB888_BYTE_LENGTH
from throw_a_strike.runtime import EmulatorTenPinPhase, EmulatorTenPinRuntime, MemorySecondaryDisplayPort, gallery_view_models, render_gallery


class Clock:
    def __init__(self, t=0): self.t=float(t)
    @property
    def capabilities(self): return PortCapabilities(True)
    def monotonic_seconds(self): return self.t
    def set(self,t): self.t=float(t)


def resolution(kind, before=FULL_RACK, knocked=()):
    after=tuple(p for p in before if p not in knocked)
    if kind is BowlingThrowResultKind.PIN_HIT:
        return PinfallResolution(kind,before,knocked[0],0.5,64,72,0.0,-1.0,PinImpactBias.CENTER,((knocked[0],), tuple(knocked[1:])) if len(knocked)>1 else ((knocked[0],),),tuple(knocked),after)
    return PinfallResolution(kind,before,None,1.0,64,10,0.0,-1.0,PinImpactBias.CENTER,(),(),before)


class Phase0XSecondaryDisplayTests(unittest.TestCase):
    def make_runtime(self):
        sdk=FakeDartsnutSdk(); clock=Clock(0); secondary=MemorySecondaryDisplayPort()
        rt=EmulatorTenPinRuntime(DartsnutSdkFacade(sdk),clock,0,secondary)
        sdk.queue_button_events((DartsnutButtonId.A,)); step=rt.step()
        return sdk,clock,secondary,rt,step

    def roll_to_result(self, rt, sdk, clock, res):
        clock.set((rt.throw_ready_started_at or clock.t)+0.1)
        with patch('throw_a_strike.runtime.emulator_ten_pin.resolve_ball_pinfall', return_value=res):
            sdk.queue_dart_hits((RawDartHit(0,64,72),)); rt.step()
        clock.set(rt.ball_started_at+rt.ball_trajectory.duration_seconds); step=rt.step()
        if step.phase is EmulatorTenPinPhase.PINFALL:
            clock.set(rt.pinfall_started_at+PINFALL_DURATION_SECONDS); step=rt.step()
        return step

    def test_screen1_framebuffer_is_unchanged_when_secondary_preview_is_attached(self):
        sdk1=FakeDartsnutSdk(); clock1=Clock(0); rt1=EmulatorTenPinRuntime(DartsnutSdkFacade(sdk1),clock1,0)
        sdk1.queue_button_events((DartsnutButtonId.A,)); step1=rt1.step()
        sdk2=FakeDartsnutSdk(); clock2=Clock(0); secondary=MemorySecondaryDisplayPort(); rt2=EmulatorTenPinRuntime(DartsnutSdkFacade(sdk2),clock2,0,secondary)
        sdk2.queue_button_events((DartsnutButtonId.A,)); step2=rt2.step()
        self.assertEqual(step1.framebuffer, step2.framebuffer)
        self.assertEqual(sdk1.submitted_framebuffers, sdk2.submitted_framebuffers)

    def test_throw_ready_once_static_expiry_and_legal_dart_cancel(self):
        sdk,clock,secondary,rt,step=self.make_runtime()
        ready_events=[e for e in rt.presentation_timeline.events if e.kind is RegulationPresentationEventKind.THROW_READY]
        self.assertEqual(len(ready_events),1)
        first_frame=secondary.latest_framebuffer
        clock.set(0.25); rt.step(); self.assertEqual(secondary.latest_framebuffer, first_frame)
        clock.set(1.49); rt.step(); self.assertEqual(secondary.latest_framebuffer, first_frame)
        clock.set(1.5); rt.step(); self.assertNotEqual(secondary.latest_framebuffer, first_frame)
        self.assertEqual(len(secondary.latest_framebuffer), EMULATOR_RGB888_BYTE_LENGTH)
        sdk,clock,secondary,rt,step=self.make_runtime(); first_frame=secondary.latest_framebuffer
        self.roll_to_result(rt,sdk,clock,resolution(BowlingThrowResultKind.GUTTER))
        self.assertNotEqual(secondary.latest_framebuffer, first_frame)
        self.assertFalse(rt.presentation_timeline.view_model(clock.t).kind is RegulationPresentationEventKind.THROW_READY)

    def test_result_events_update_screen2_and_strike_turkey_order_before_next_ready(self):
        sdk,clock,secondary,rt,step=self.make_runtime(); before=secondary.latest_framebuffer
        self.roll_to_result(rt,sdk,clock,resolution(BowlingThrowResultKind.MISS))
        self.assertEqual(rt.presentation_timeline.view_model(clock.t).label, "MISS")
        self.assertNotEqual(secondary.latest_framebuffer, before)
        sdk,clock,secondary,rt,step=self.make_runtime()
        for _ in range(3):
            self.roll_to_result(rt,sdk,clock,resolution(BowlingThrowResultKind.PIN_HIT,FULL_RACK,FULL_RACK))
            if len([e for e in rt.presentation_timeline.events if e.kind is RegulationPresentationEventKind.STRIKE]) < 3:
                clock.set(rt.result_started_at+1.5); rt.step()
        strike=[e for e in rt.presentation_timeline.events if e.kind is RegulationPresentationEventKind.STRIKE][-1]
        turkey=[e for e in rt.presentation_timeline.events if e.kind is RegulationPresentationEventKind.TURKEY][-1]
        self.assertEqual(rt.presentation_timeline.view_model(strike.started_at).label, "STRIKE")
        self.assertEqual(rt.presentation_timeline.view_model(turkey.started_at).label, "TURKEY")
        self.assertLess(strike.deadline, turkey.deadline)
        clock.set(rt.result_started_at+1.5); rt.step()
        self.assertEqual(rt.presentation_timeline.view_model(clock.t).label, "THROW READY")

    def test_gallery_renders_every_required_event_headlessly(self):
        secondary=MemorySecondaryDisplayPort(); frames=render_gallery(secondary)
        labels=tuple(model.label for model in gallery_view_models())
        self.assertEqual(labels, ("THROW READY","STRIKE","SPARE","SPLIT","SPLIT CONVERTED","FIELD GOAL","GUTTER","MISS","FOUL","TURKEY","GAME OVER"))
        self.assertEqual(len(frames), len(labels))
        self.assertEqual(secondary.framebuffers, frames)
        self.assertTrue(all(type(frame) is bytes and len(frame)==EMULATOR_RGB888_BYTE_LENGTH for frame in frames))


if __name__ == "__main__":
    unittest.main()
