import unittest

from throw_a_strike.adapters import DartsnutEmulatorInputPort
from throw_a_strike.application import InputEventKind, PortCapabilities
from throw_a_strike.platform import DartsnutButtonId, DartsnutSdkFacade, FakeDartsnutSdk, RawDartHit


class Clock:
    def __init__(self, *values): self.values=list(values); self.reads=0
    @property
    def capabilities(self): return PortCapabilities(True)
    def monotonic_seconds(self):
        self.reads += 1
        return self.values.pop(0)


class EmulatorInputTests(unittest.TestCase):
    def setUp(self):
        self.sdk=FakeDartsnutSdk(); self.clock=Clock(5,6,7,8)
        self.port=DartsnutEmulatorInputPort(DartsnutSdkFacade(self.sdk),self.clock,10)

    def test_first_poll_suppresses_hits_but_emits_button(self):
        self.sdk.set_active_darts((RawDartHit(0,62,43),))
        self.sdk.queue_dart_hits((RawDartHit(0,62,43),))
        self.sdk.queue_button_events((DartsnutButtonId.A,))
        events=self.port.poll()
        self.assertEqual([(e.kind,e.sequence,e.control_id) for e in events],[(InputEventKind.CONTROL,10,"btn_a")])
        self.assertEqual(self.clock.reads,1)

    def test_state_transitions_coordinate_changes_and_empty_clock_policy(self):
        self.assertEqual(self.port.poll(),())
        self.assertEqual(self.clock.reads,0)
        self.sdk.set_active_darts((RawDartHit(4,35,81),))
        event,=self.port.poll()
        self.assertEqual((event.dart_index,event.x,event.y,event.sequence,event.timestamp),(4,35,81,10,5))
        self.assertEqual(self.port.poll(),())
        self.sdk.set_active_darts(())
        self.assertEqual(self.port.poll(),())
        self.sdk.set_active_darts((RawDartHit(4,36,82),))
        event,=self.port.poll()
        self.assertEqual((event.x,event.y,event.sequence),(36,82,11))

    def test_normal_hit_wins_and_deduplicates_active_change(self):
        self.port.poll()
        self.sdk.set_active_darts((RawDartHit(0,90,70),))
        self.sdk.queue_dart_hits((RawDartHit(0,91,71),))
        events=self.port.poll()
        self.assertEqual(len(events),1)
        self.assertEqual((events[0].dart_index,events[0].x,events[0].y),(0,91,71))

    def test_multiple_darts_sorted_before_controls_with_shared_timestamp(self):
        self.port.poll()
        self.sdk.set_active_darts((RawDartHit(8,1,2),RawDartHit(0,3,4),RawDartHit(4,5,6)))
        self.sdk.queue_button_events((DartsnutButtonId.B,DartsnutButtonId.A))
        events=self.port.poll()
        self.assertEqual([e.dart_index for e in events[:3]],[0,4,8])
        self.assertTrue(all(e.kind is InputEventKind.DART_HIT for e in events[:3]))
        self.assertTrue(all(e.kind is InputEventKind.CONTROL for e in events[3:]))
        self.assertEqual([e.sequence for e in events],list(range(10,15)))
        self.assertEqual({e.timestamp for e in events},{5})


if __name__ == "__main__": unittest.main()
