import unittest

import throw_a_strike.adapters as adapters
from throw_a_strike.adapters import DartsnutInputPort
from throw_a_strike.application import (
    ClockPort,
    InputEvent,
    InputEventKind,
    InputPort,
    InvalidPortValueError,
    PortCapabilities,
    PortUnavailableError,
)
from throw_a_strike.platform import (
    DartsnutButtonId,
    DartsnutSdkFacade,
    DartsnutSdkOperation,
    DartsnutSdkOperationError,
    FakeDartsnutSdk,
    InvalidDartsnutSdkResponseError,
    RawDartHit,
)


class RecordingClock:
    def __init__(self, values=(1.0,), available=True):
        self.values = list(values)
        self.capability_reads = 0
        self.time_reads = 0
        self.available = available

    @property
    def capabilities(self):
        self.capability_reads += 1
        return PortCapabilities(self.available)

    def monotonic_seconds(self):
        self.time_reads += 1
        value = self.values.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value


class FaultSdk(FakeDartsnutSdk):
    def __init__(self):
        super().__init__()
        self.dart_failure = None
        self.button_failure = None

    def get_dart_hits(self):
        if self.dart_failure is not None:
            self._calls.append(DartsnutSdkOperation.DART_HITS)
            raise self.dart_failure
        return super().get_dart_hits()

    def get_button_events(self):
        if self.button_failure is not None:
            self._calls.append(DartsnutSdkOperation.BUTTON_EVENTS)
            raise self.button_failure
        return super().get_button_events()


def setup_port(clock=None, initial_sequence=0):
    sdk = FakeDartsnutSdk()
    clock = clock or RecordingClock()
    return sdk, clock, DartsnutInputPort(DartsnutSdkFacade(sdk), clock, initial_sequence)


class PublicStructureTests(unittest.TestCase):
    def test_exact_export_and_protocol_compliance(self):
        self.assertEqual(adapters.__all__, ("DartsnutInputPort", "DartsnutEmulatorInputPort"))
        _, _, port = setup_port()
        self.assertIsInstance(port, InputPort)
        self.assertEqual(
            {name for name in dir(DartsnutInputPort) if not name.startswith("_")},
            {"capabilities", "poll"},
        )

    def test_dependencies_are_not_public(self):
        _, _, port = setup_port()
        self.assertFalse(hasattr(port, "facade"))
        self.assertFalse(hasattr(port, "clock"))


class ConstructionTests(unittest.TestCase):
    def test_construction_only_reads_capabilities_once(self):
        sdk = FakeDartsnutSdk()
        clock = RecordingClock()
        DartsnutInputPort(DartsnutSdkFacade(sdk), clock)
        self.assertEqual(sdk.calls, ())
        self.assertEqual((clock.capability_reads, clock.time_reads), (1, 0))

    def test_invalid_facades(self):
        class Child(DartsnutSdkFacade):
            pass

        clock = RecordingClock()
        with self.assertRaises(InvalidPortValueError):
            DartsnutInputPort(None, clock)  # type: ignore[arg-type]
        with self.assertRaises(InvalidPortValueError):
            DartsnutInputPort(Child(FakeDartsnutSdk()), clock)

    def test_invalid_clocks(self):
        facade = DartsnutSdkFacade(FakeDartsnutSdk())
        for clock in (None, RecordingClock, object()):
            with self.subTest(clock=clock), self.assertRaises(InvalidPortValueError):
                DartsnutInputPort(facade, clock)  # type: ignore[arg-type]

    def test_capability_access_failure_is_converted(self):
        class BadClock:
            @property
            def capabilities(self):
                raise RuntimeError("capabilities")

            def monotonic_seconds(self):
                return 0.0

        with self.assertRaises(InvalidPortValueError):
            DartsnutInputPort(DartsnutSdkFacade(FakeDartsnutSdk()), BadClock())

    def test_nonexact_capabilities_are_rejected(self):
        class Child(PortCapabilities):
            pass

        class BadClock(RecordingClock):
            @property
            def capabilities(self):
                return Child(True)

        with self.assertRaises(InvalidPortValueError):
            DartsnutInputPort(DartsnutSdkFacade(FakeDartsnutSdk()), BadClock())

    def test_initial_sequences(self):
        class IntegerChild(int):
            pass

        for invalid in (-1, True, 1.0, "1", IntegerChild(1)):
            with self.subTest(value=invalid), self.assertRaises(InvalidPortValueError):
                setup_port(initial_sequence=invalid)
        for valid in (0, 23):
            sdk, _, port = setup_port(initial_sequence=valid)
            sdk.queue_dart_hits((RawDartHit(0, 1, 2),))
            self.assertEqual(port.poll()[0].sequence, valid)


class CapabilityAndEmptyTests(unittest.TestCase):
    def test_capabilities_are_detached_exact_snapshot(self):
        sdk, clock, port = setup_port()
        first = port.capabilities
        clock.available = False
        second = port.capabilities
        self.assertIs(type(first), PortCapabilities)
        self.assertEqual((first, second), (PortCapabilities(True), PortCapabilities(True)))
        self.assertIsNot(first, second)
        self.assertEqual((clock.capability_reads, clock.time_reads, sdk.calls), (1, 0, ()))

    def test_unavailable_poll_has_no_side_effects(self):
        sdk, clock, port = setup_port(RecordingClock(available=False), initial_sequence=9)
        for _ in range(2):
            with self.assertRaises(PortUnavailableError):
                port.poll()
        self.assertEqual((sdk.calls, clock.time_reads), ((), 0))

    def test_repeated_empty_polls_are_independent_and_do_not_advance(self):
        sdk, clock, port = setup_port(initial_sequence=7)
        self.assertIs(type(port.poll()), tuple)
        self.assertEqual(port.poll(), ())
        sdk.queue_button_events((DartsnutButtonId.A,))
        self.assertEqual(port.poll()[0].sequence, 7)
        self.assertEqual(clock.time_reads, 1)
        self.assertEqual(
            sdk.calls,
            (DartsnutSdkOperation.DART_HITS, DartsnutSdkOperation.BUTTON_EVENTS) * 3,
        )
        self.assertNotIn(DartsnutSdkOperation.RESET_BLOCKING_STATE, sdk.calls)


class TranslationTests(unittest.TestCase):
    def test_darts_preserve_order_duplicates_indices_and_coordinates(self):
        sdk, clock, port = setup_port()
        hits = (
            RawDartHit(11, 0, 127), RawDartHit(0, 127, 0), RawDartHit(0, 127, 0)
        )
        sdk.queue_dart_hits(hits)
        result = port.poll()
        self.assertEqual(
            result,
            tuple(InputEvent(InputEventKind.DART_HIT, i, 1.0, h.dart_index, h.x, h.y) for i, h in enumerate(hits)),
        )
        self.assertTrue(all(event.control_id is None for event in result))
        self.assertEqual(clock.time_reads, 1)

    def test_every_verified_button_is_preserved_in_facade_order(self):
        sdk, _, port = setup_port()
        buttons = tuple(DartsnutButtonId)
        sdk.queue_button_events(buttons)
        result = port.poll()
        self.assertEqual([event.control_id for event in result], [button.value for button in buttons])
        self.assertTrue(all(event.kind is InputEventKind.CONTROL for event in result))
        self.assertTrue(all(event.dart_index is event.x is event.y is None for event in result))

    def test_mixed_batch_is_darts_then_buttons_with_one_timestamp(self):
        sdk, clock, port = setup_port(RecordingClock((4.25,)))
        sdk.queue_dart_hits((RawDartHit(2, 3, 4), RawDartHit(1, 9, 8)))
        sdk.queue_button_events((DartsnutButtonId.HOME, DartsnutButtonId.B))
        result = port.poll()
        self.assertEqual([event.kind for event in result], [InputEventKind.DART_HIT] * 2 + [InputEventKind.CONTROL] * 2)
        self.assertEqual([event.sequence for event in result], [0, 1, 2, 3])
        self.assertEqual({event.timestamp for event in result}, {4.25})
        self.assertEqual(clock.time_reads, 1)
        self.assertEqual(sdk.calls, (DartsnutSdkOperation.DART_HITS, DartsnutSdkOperation.BUTTON_EVENTS))
        self.assertNotIn(DartsnutSdkOperation.RESET_BLOCKING_STATE, sdk.calls)

    def test_sequences_continue_across_polls_without_empty_gaps(self):
        sdk, _, port = setup_port(RecordingClock((1.0, 2.0)), initial_sequence=5)
        sdk.queue_dart_hits((RawDartHit(0, 0, 0),))
        self.assertEqual([event.sequence for event in port.poll()], [5])
        self.assertEqual(port.poll(), ())
        sdk.queue_button_events((DartsnutButtonId.RESERVED, DartsnutButtonId.A))
        self.assertEqual([event.sequence for event in port.poll()], [6, 7])

    def test_integer_timestamp_is_normalized_and_polls_can_differ(self):
        sdk, _, port = setup_port(RecordingClock((2, 3.5)))
        for button in (DartsnutButtonId.A, DartsnutButtonId.B):
            sdk.queue_button_events((button,))
            event = port.poll()[0]
            self.assertIs(type(event.timestamp), float)
        self.assertEqual(event.timestamp, 3.5)


class FailureTests(unittest.TestCase):
    def test_invalid_timestamps_do_not_commit_sequence(self):
        for invalid in (-1, True, float("inf"), float("nan")):
            with self.subTest(value=invalid):
                sdk, _, port = setup_port(RecordingClock((invalid, 2.0)), initial_sequence=10)
                sdk.queue_dart_hits((RawDartHit(0, 1, 1),))
                with self.assertRaises(InvalidPortValueError):
                    port.poll()
                sdk.queue_dart_hits((RawDartHit(0, 1, 1),))
                self.assertEqual(port.poll()[0].sequence, 10)

    def test_facade_failures_propagate_exactly_without_retry(self):
        for malformed in (True, False):
            with self.subTest(malformed=malformed):
                sdk = FaultSdk()
                facade = DartsnutSdkFacade(sdk)
                clock = RecordingClock()
                port = DartsnutInputPort(facade, clock, 4)
                if malformed:
                    error = InvalidDartsnutSdkResponseError(DartsnutSdkOperation.DART_HITS, "bad")
                    # A malformed raw return makes the facade create its own response error.
                    sdk.get_dart_hits = lambda: None
                    with self.assertRaises(InvalidDartsnutSdkResponseError):
                        port.poll()
                else:
                    cause = RuntimeError("dart")
                    sdk.dart_failure = cause
                    with self.assertRaises(DartsnutSdkOperationError) as raised:
                        port.poll()
                    self.assertIs(raised.exception.cause, cause)
                self.assertEqual(clock.time_reads, 0)

    def test_button_failure_consumes_darts_but_not_sequence(self):
        sdk = FaultSdk()
        sdk.queue_dart_hits((RawDartHit(0, 1, 2),))
        sdk.button_failure = RuntimeError("button")
        port = DartsnutInputPort(DartsnutSdkFacade(sdk), RecordingClock(), 12)
        with self.assertRaises(DartsnutSdkOperationError):
            port.poll()
        self.assertEqual(sdk.queued_dart_batch_count, 0)
        sdk.button_failure = None
        sdk.queue_button_events((DartsnutButtonId.A,))
        self.assertEqual(port.poll()[0].sequence, 12)
        self.assertNotIn(DartsnutSdkOperation.RESET_BLOCKING_STATE, sdk.calls)

    def test_clock_failure_consumes_both_sources_but_not_sequence(self):
        error = PortUnavailableError("clock")
        sdk, clock, port = setup_port(RecordingClock((error, 8.0)), initial_sequence=3)
        sdk.queue_dart_hits((RawDartHit(0, 1, 2),))
        sdk.queue_button_events((DartsnutButtonId.A,))
        with self.assertRaises(PortUnavailableError) as raised:
            port.poll()
        self.assertIs(raised.exception, error)
        self.assertEqual((sdk.queued_dart_batch_count, sdk.queued_button_batch_count), (0, 0))
        sdk.queue_button_events((DartsnutButtonId.B,))
        self.assertEqual(port.poll()[0].sequence, 3)

    def test_arbitrary_clock_exception_identity_is_preserved(self):
        error = LookupError("clock")
        sdk, _, port = setup_port(RecordingClock((error,)))
        sdk.queue_button_events((DartsnutButtonId.A,))
        with self.assertRaises(LookupError) as raised:
            port.poll()
        self.assertIs(raised.exception, error)

    def test_base_exception_is_not_caught(self):
        error = KeyboardInterrupt()
        sdk, _, port = setup_port(RecordingClock((error,)))
        sdk.queue_button_events((DartsnutButtonId.A,))
        with self.assertRaises(KeyboardInterrupt) as raised:
            port.poll()
        self.assertIs(raised.exception, error)


if __name__ == "__main__":
    unittest.main()
