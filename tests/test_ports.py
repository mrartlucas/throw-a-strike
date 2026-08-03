import unittest
from dataclasses import FrozenInstanceError

from throw_a_strike.application import (
    ApplicationCapabilities, AudioPort, AudioRequest, ClockPort,
    DisplayCapabilities, FakeAudioPort, FakeClockPort, FakeInputPort,
    FakeMainDisplayPort, FakeSecondaryDisplayPort, FakeStoragePort, InputEvent,
    InputEventKind, InputPort, InvalidPortValueError, MainDisplayPort,
    PortCapabilities, PortUnavailableError, SecondaryDisplayPort,
    StorageCapabilities, StoragePort, collect_application_capabilities,
    GameSession,
)


def snapshot():
    return GameSession().snapshot()


def dart(sequence=0):
    return InputEvent(InputEventKind.DART_HIT, sequence, sequence, 9, -2, 3.5)


class CapabilityTests(unittest.TestCase):
    def test_port_capabilities_accept_only_actual_bools(self):
        self.assertTrue(PortCapabilities(True).available)
        self.assertFalse(PortCapabilities(False).available)
        for value in (0, 1, "yes", object()):
            with self.subTest(value=value), self.assertRaises(InvalidPortValueError):
                PortCapabilities(value)

    def test_display_dimensions_may_be_unknown_or_known(self):
        self.assertEqual(DisplayCapabilities(True, None, None).width, None)
        self.assertEqual(DisplayCapabilities(True, 7, 11).height, 11)

    def test_display_dimensions_are_strict_and_paired(self):
        for dimensions in ((1, None), (None, 1), (0, 1), (-1, 1),
                           (1.0, 1), ("1", 1), (True, 1)):
            with self.subTest(dimensions=dimensions), self.assertRaises(InvalidPortValueError):
                DisplayCapabilities(True, *dimensions)
        with self.assertRaises(InvalidPortValueError):
            DisplayCapabilities(False, 1, 1)

    def test_storage_supports_read_only_but_not_unavailable_writable(self):
        self.assertEqual(StorageCapabilities(True, False), StorageCapabilities(True, False))
        with self.assertRaises(InvalidPortValueError): StorageCapabilities(False, True)
        for values in ((1, False), (True, 1)):
            with self.assertRaises(InvalidPortValueError): StorageCapabilities(*values)

    def test_capabilities_are_frozen_and_application_requires_exact_types(self):
        values = (PortCapabilities(True), DisplayCapabilities(True, None, None),
                  StorageCapabilities(True, False))
        for value in values:
            with self.assertRaises(FrozenInstanceError): value.available = False
        args = (values[1], DisplayCapabilities(False, None, None), values[0],
                values[0], values[0], values[2])
        capability = ApplicationCapabilities(*args)
        with self.assertRaises(FrozenInstanceError): capability.audio = PortCapabilities(False)
        for index in range(6):
            invalid = list(args); invalid[index] = object()
            with self.subTest(index=index), self.assertRaises(InvalidPortValueError):
                ApplicationCapabilities(*invalid)


class EventAndAudioTests(unittest.TestCase):
    def test_event_enum_is_exact(self):
        self.assertEqual([(x.name, x.value) for x in InputEventKind],
                         [("DART_HIT", "dart_hit"), ("CONTROL", "control")])

    def test_valid_events_are_normalized_and_frozen(self):
        hit = dart()
        self.assertEqual((hit.dart_index, hit.x, hit.y), (9, -2.0, 3.5))
        self.assertIs(type(hit.timestamp), float)
        control = InputEvent(InputEventKind.CONTROL, 1, 2, control_id="opaque")
        self.assertEqual(control.control_id, "opaque")
        with self.assertRaises(FrozenInstanceError): hit.x = 1

    def test_event_general_values_are_strict(self):
        for sequence in (-1, True, 1.0, "1"):
            with self.subTest(sequence=sequence), self.assertRaises(InvalidPortValueError):
                InputEvent(InputEventKind.CONTROL, sequence, 0, control_id="x")
        for timestamp in (-1, True, float("nan"), float("inf"), "1"):
            with self.subTest(timestamp=timestamp), self.assertRaises(InvalidPortValueError):
                InputEvent(InputEventKind.CONTROL, 0, timestamp, control_id="x")
        with self.assertRaises(InvalidPortValueError):
            InputEvent("control", 0, 0, control_id="x")

    def test_dart_fields_are_strict(self):
        for index in (None, -1, True, 1.0, "1"):
            with self.subTest(index=index), self.assertRaises(InvalidPortValueError):
                InputEvent(InputEventKind.DART_HIT, 0, 0, index, 1, 2)
        for coordinate in (True, float("nan"), float("inf"), "1"):
            with self.subTest(coordinate=coordinate), self.assertRaises(InvalidPortValueError):
                InputEvent(InputEventKind.DART_HIT, 0, 0, 1, coordinate, 2)
        for kwargs in ({"dart_index": 1, "x": 1},
                       {"dart_index": 1, "x": 1, "y": 2, "control_id": "x"}):
            with self.assertRaises(InvalidPortValueError):
                InputEvent(InputEventKind.DART_HIT, 0, 0, **kwargs)

    def test_control_fields_are_strict(self):
        for control in (None, "", " padded ", 1):
            with self.subTest(control=control), self.assertRaises(InvalidPortValueError):
                InputEvent(InputEventKind.CONTROL, 0, 0, control_id=control)
        with self.assertRaises(InvalidPortValueError):
            InputEvent(InputEventKind.CONTROL, 0, 0, x=1, control_id="x")

    def test_audio_request_validation_and_freezing(self):
        default = AudioRequest("cue")
        self.assertEqual((default.loop, default.volume), (False, 1.0))
        self.assertEqual(AudioRequest("cue", True, .25).volume, .25)
        for cue in ("", " cue ", 1):
            with self.assertRaises(InvalidPortValueError): AudioRequest(cue)
        for loop in (0, 1, "yes"):
            with self.assertRaises(InvalidPortValueError): AudioRequest("cue", loop)
        for volume in (-.1, 1.1, True, float("nan"), float("inf"), "1"):
            with self.assertRaises(InvalidPortValueError): AudioRequest("cue", volume=volume)
        with self.assertRaises(FrozenInstanceError): default.volume = 0


class ProtocolAndDisplayTests(unittest.TestCase):
    def test_fakes_satisfy_runtime_protocols(self):
        pairs = ((FakeMainDisplayPort(DisplayCapabilities(True, None, None)), MainDisplayPort),
                 (FakeSecondaryDisplayPort(DisplayCapabilities(True, None, None)), SecondaryDisplayPort),
                 (FakeInputPort(), InputPort), (FakeClockPort(), ClockPort),
                 (FakeAudioPort(), AudioPort), (FakeStoragePort(), StoragePort))
        for fake, protocol in pairs: self.assertIsInstance(fake, protocol)

    def test_collection_exact_missing_optional_and_detached(self):
        main_cap = DisplayCapabilities(True, 10, 20)
        main = FakeMainDisplayPort(main_cap); inp = FakeInputPort(); clock = FakeClockPort()
        result = collect_application_capabilities(main, inp, clock)
        self.assertEqual(result.main_display, main_cap)
        self.assertIsNot(result.main_display, main_cap)
        self.assertEqual(result.secondary_display, DisplayCapabilities(False, None, None))
        self.assertEqual(result.audio, PortCapabilities(False))
        self.assertEqual(result.storage, StorageCapabilities(False, False))

    def test_collection_reads_no_operations_and_validates_ports(self):
        result = collect_application_capabilities(
            FakeMainDisplayPort(DisplayCapabilities(False, None, None)),
            FakeInputPort(PortCapabilities(False)), FakeClockPort(capabilities=PortCapabilities(False)),
            FakeSecondaryDisplayPort(DisplayCapabilities(False, None, None)),
            FakeAudioPort(PortCapabilities(False)),
            FakeStoragePort(capabilities=StorageCapabilities(False, False)))
        self.assertFalse(result.main_display.available)
        for position in range(6):
            args = [FakeMainDisplayPort(DisplayCapabilities(True, None, None)),
                    FakeInputPort(), FakeClockPort(), None, None, None]
            args[position] = object()
            with self.subTest(position=position), self.assertRaises(InvalidPortValueError):
                collect_application_capabilities(*args)

    def test_displays_record_in_order_and_return_tuples(self):
        states = (snapshot(), snapshot())
        for display in (FakeMainDisplayPort(DisplayCapabilities(True, None, None)),
                        FakeSecondaryDisplayPort(DisplayCapabilities(True, 3, 4))):
            for state in states: display.present(state)
            self.assertEqual(display.presented, states)
            self.assertIs(type(display.presented), tuple)
            before = display.presented
            with self.assertRaises(InvalidPortValueError): display.present(object())
            self.assertEqual(display.presented, before)
            with self.assertRaises(FrozenInstanceError): display.presented[0].phase = None

    def test_unavailable_display_is_atomic(self):
        display = FakeMainDisplayPort(DisplayCapabilities(False, None, None))
        with self.assertRaises(PortUnavailableError): display.present(snapshot())
        self.assertEqual(display.presented, ())


class OperationalFakeTests(unittest.TestCase):
    def test_input_fifo_drain_empty_and_atomic_rejection(self):
        port = FakeInputPort(); events = (dart(1), dart(2))
        for event in events: port.push(event)
        self.assertEqual(port.queued_events, events); self.assertIs(type(port.queued_events), tuple)
        with self.assertRaises(InvalidPortValueError): port.push(object())
        self.assertEqual(port.poll(), events); self.assertEqual(port.poll(), ())
        unavailable = FakeInputPort(PortCapabilities(False))
        for operation in (lambda: unavailable.push(events[0]), unavailable.poll):
            with self.assertRaises(PortUnavailableError): operation()
        self.assertEqual(unavailable.queued_events, ())

    def test_clock_advances_cumulatively_and_rejects_atomically(self):
        clock = FakeClockPort(2)
        self.assertEqual(clock.monotonic_seconds(), 2.0)
        self.assertEqual(clock.advance(.5), 2.5); self.assertEqual(clock.advance(1), 3.5)
        for value in (-1, True, float("nan"), float("inf"), "1"):
            with self.assertRaises(InvalidPortValueError): clock.advance(value)
            self.assertEqual(clock.monotonic_seconds(), 3.5)
        for value in (-1, True, float("nan"), float("inf")):
            with self.assertRaises(InvalidPortValueError): FakeClockPort(value)
        unavailable = FakeClockPort(capabilities=PortCapabilities(False))
        with self.assertRaises(PortUnavailableError): unavailable.monotonic_seconds()
        with self.assertRaises(PortUnavailableError): unavailable.advance(1)

    def test_audio_histories_and_atomic_errors(self):
        audio = FakeAudioPort(); values = (AudioRequest("one"), AudioRequest("two"))
        for request in values: audio.play(request)
        audio.stop("one"); audio.stop()
        self.assertEqual(audio.played, values); self.assertEqual(audio.stopped, ("one", None))
        self.assertIs(type(audio.played), tuple); self.assertIs(type(audio.stopped), tuple)
        before = audio.stopped
        for cue in ("", " bad ", 1):
            with self.assertRaises(InvalidPortValueError): audio.stop(cue)
        self.assertEqual(audio.stopped, before)
        unavailable = FakeAudioPort(PortCapabilities(False))
        with self.assertRaises(PortUnavailableError): unavailable.play(values[0])
        with self.assertRaises(PortUnavailableError): unavailable.stop()

    def test_storage_initial_contents_and_validation(self):
        storage = FakeStoragePort((("z", b"last"), ("a", b"first")))
        self.assertEqual(storage.load("a"), b"first")
        self.assertEqual(storage.items, (("a", b"first"), ("z", b"last")))
        self.assertIs(type(storage.items), tuple)
        invalid = ([('a', b'x')], (("a", b"x"), ("a", b"y")),
                   ((" bad ", b"x"),), (("a", bytearray(b"x")),), (("a",),))
        for initial in invalid:
            with self.subTest(initial=initial), self.assertRaises(InvalidPortValueError):
                FakeStoragePort(initial)

    def test_storage_round_trip_replace_delete_and_validation(self):
        storage = FakeStoragePort(); storage.save("key", b"one")
        self.assertEqual(storage.load("key"), b"one")
        storage.save("key", b"two"); self.assertEqual(storage.load("key"), b"two")
        storage.delete("key"); storage.delete("key"); self.assertIsNone(storage.load("key"))
        before = storage.items
        for key in ("", " bad ", 1):
            with self.assertRaises(InvalidPortValueError): storage.save(key, b"x")
        for value in (bytearray(b"x"), memoryview(b"x"), "x"):
            with self.assertRaises(InvalidPortValueError): storage.save("key", value)
        self.assertEqual(storage.items, before)

    def test_read_only_and_unavailable_storage_are_atomic(self):
        read_only = FakeStoragePort((("key", b"value"),), StorageCapabilities(True, False))
        self.assertEqual(read_only.load("key"), b"value")
        for operation in (lambda: read_only.save("key", b"new"), lambda: read_only.delete("key")):
            with self.assertRaises(PortUnavailableError): operation()
        self.assertEqual(read_only.items, (("key", b"value"),))
        unavailable = FakeStoragePort((("key", b"value"),), StorageCapabilities(False, False))
        for operation in (lambda: unavailable.load("key"),
                          lambda: unavailable.save("key", b"new"),
                          lambda: unavailable.delete("key")):
            with self.assertRaises(PortUnavailableError): operation()
        self.assertEqual(unavailable.items, (("key", b"value"),))


if __name__ == "__main__":
    unittest.main()
