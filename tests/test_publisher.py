import unittest
from dataclasses import FrozenInstanceError

from throw_a_strike.application import (
    ApplicationCapabilities,
    DisplayCapabilities,
    FakeMainPresentationPort,
    FakeSecondaryPresentationPort,
    GameSession,
    InvalidPresentationPublisherValueError,
    MainPresentationPort,
    PortCapabilities,
    PortUnavailableError,
    PresentationBundle,
    PresentationPublishError,
    PresentationPublisher,
    PublicationReceipt,
    PublicationTarget,
    ScoreboardPlacement,
    SecondaryPresentationPort,
    StorageCapabilities,
    build_presentation,
)
from throw_a_strike.domain.config import MatchConfig, Mode, Theme


def application_capabilities(secondary=False, dimensions=False):
    return ApplicationCapabilities(
        DisplayCapabilities(True, None, None),
        DisplayCapabilities(
            secondary, 320 if dimensions else None, 200 if dimensions else None
        ),
        PortCapabilities(True),
        PortCapabilities(True),
        PortCapabilities(False),
        StorageCapabilities(False, False),
    )


def bundles():
    empty = build_presentation(GameSession().snapshot(), application_capabilities())
    session = GameSession()
    session.configure(MatchConfig(Mode.TEN_PIN, Theme.REGULAR, 1, 10, 42))
    ready = build_presentation(session.snapshot(), application_capabilities())
    session.start()
    main = build_presentation(session.snapshot(), application_capabilities())
    secondary = build_presentation(
        session.snapshot(), application_capabilities(True)
    )
    return empty, ready, main, secondary


class MutableCapabilityPort:
    def __init__(self, capability, fail=None, events=None):
        self.capability = capability
        self.fail = fail
        self.calls = []
        self.events = events

    @property
    def capabilities(self):
        return self.capability

    def present(self, model):
        self.calls.append(model)
        if self.events is not None:
            self.events.append(self)
        if self.fail is not None:
            raise self.fail


class PublisherValueTests(unittest.TestCase):
    def test_publication_target_is_exact(self):
        self.assertEqual(
            [(item.name, item.value) for item in PublicationTarget],
            [("MAIN", "main"), ("SECONDARY", "secondary")],
        )

    def test_valid_receipts_and_frozen_state(self):
        for placement, secondary in (
            (ScoreboardPlacement.NONE, False),
            (ScoreboardPlacement.MAIN, False),
            (ScoreboardPlacement.SECONDARY, True),
        ):
            receipt = PublicationReceipt(placement, True, secondary)
            with self.assertRaises(FrozenInstanceError):
                receipt.main_published = False

    def test_receipt_rejects_invalid_values(self):
        invalid = (
            (object(), True, False),
            (ScoreboardPlacement.NONE, 1, False),
            (ScoreboardPlacement.NONE, True, 0),
            (ScoreboardPlacement.NONE, False, False),
            (ScoreboardPlacement.MAIN, True, True),
            (ScoreboardPlacement.SECONDARY, True, False),
        )
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(
                InvalidPresentationPublisherValueError
            ):
                PublicationReceipt(*values)

    def test_publish_error_validation_and_properties(self):
        cause = RuntimeError("broken")
        error = PresentationPublishError(PublicationTarget.MAIN, False, False, cause)
        self.assertIs(error.target, PublicationTarget.MAIN)
        self.assertIs(error.cause, cause)
        for values in (
            (object(), False, False, cause),
            (PublicationTarget.MAIN, True, False, cause),
            (PublicationTarget.SECONDARY, False, False, cause),
            (PublicationTarget.MAIN, False, False, object()),
        ):
            with self.assertRaises(InvalidPresentationPublisherValueError):
                PresentationPublishError(*values)


class FakePortTests(unittest.TestCase):
    def setUp(self):
        self.none, _, self.main, self.secondary = bundles()

    def test_fakes_satisfy_only_presentation_protocols(self):
        main = FakeMainPresentationPort(DisplayCapabilities(True, None, None))
        secondary = FakeSecondaryPresentationPort(DisplayCapabilities(True, None, None))
        self.assertIsInstance(main, MainPresentationPort)
        self.assertIsInstance(secondary, SecondaryPresentationPort)
        self.assertNotIsInstance(object(), MainPresentationPort)

    def test_main_records_exact_models_in_order_and_tuple_snapshots(self):
        port = FakeMainPresentationPort(DisplayCapabilities(True, 128, 160))
        old = port.presented
        port.present(self.none.main)
        port.present(self.main.main)
        self.assertEqual(port.presented, (self.none.main, self.main.main))
        self.assertIs(port.presented[0], self.none.main)
        self.assertIsInstance(port.presented, tuple)
        self.assertEqual(old, ())

    def test_secondary_records_exact_models_with_unknown_dimensions(self):
        port = FakeSecondaryPresentationPort(DisplayCapabilities(True, None, None))
        port.present(self.secondary.secondary)
        port.present(self.secondary.secondary)
        self.assertEqual(port.presented, (self.secondary.secondary,) * 2)
        self.assertIsInstance(port.presented, tuple)

    def test_fakes_reject_wrong_models_atomically(self):
        ports = (
            FakeMainPresentationPort(DisplayCapabilities(True, None, None)),
            FakeSecondaryPresentationPort(DisplayCapabilities(True, None, None)),
        )
        for port in ports:
            with self.assertRaises(InvalidPresentationPublisherValueError):
                port.present(object())
            self.assertEqual(port.presented, ())

    def test_unavailable_fakes_reject_atomically(self):
        cases = (
            (FakeMainPresentationPort(DisplayCapabilities(False, None, None)), self.main.main),
            (FakeSecondaryPresentationPort(DisplayCapabilities(False, None, None)), self.secondary.secondary),
        )
        for port, model in cases:
            with self.assertRaises(PortUnavailableError):
                port.present(model)
            self.assertEqual(port.presented, ())


class PublisherTests(unittest.TestCase):
    def setUp(self):
        self.none, self.ready, self.main, self.secondary = bundles()
        self.available = DisplayCapabilities(True, None, None)

    def test_construction_validates_ports_without_presenting(self):
        main = MutableCapabilityPort(self.available)
        secondary = MutableCapabilityPort(self.available)
        PresentationPublisher(main)
        PresentationPublisher(main, secondary)
        self.assertEqual((main.calls, secondary.calls), ([], []))
        for args in ((object(),), (main, object())):
            with self.assertRaises(InvalidPresentationPublisherValueError):
                PresentationPublisher(*args)
        bad = MutableCapabilityPort(object())
        with self.assertRaises(InvalidPresentationPublisherValueError):
            PresentationPublisher(bad)

    def test_unavailable_ports_can_be_configured(self):
        unavailable = DisplayCapabilities(False, None, None)
        PresentationPublisher(MutableCapabilityPort(unavailable))
        PresentationPublisher(
            MutableCapabilityPort(self.available), MutableCapabilityPort(unavailable)
        )

    def test_none_and_main_publish_only_exact_main_once(self):
        main_port = FakeMainPresentationPort(self.available)
        secondary_port = FakeSecondaryPresentationPort(self.available)
        publisher = PresentationPublisher(main_port, secondary_port)
        for bundle in (self.none, self.ready, self.main):
            receipt = publisher.publish(bundle)
            self.assertIs(main_port.presented[-1], bundle.main)
            self.assertIs(receipt.scoreboard_placement, bundle.scoreboard_placement)
            self.assertTrue(receipt.main_published)
            self.assertFalse(receipt.secondary_published)
        self.assertEqual(secondary_port.presented, ())

    def test_unused_unavailable_secondary_does_not_block(self):
        publisher = PresentationPublisher(
            FakeMainPresentationPort(self.available),
            FakeSecondaryPresentationPort(DisplayCapabilities(False, None, None)),
        )
        publisher.publish(self.none)
        publisher.publish(self.main)

    def test_secondary_publishes_exact_objects_main_first(self):
        events = []
        main = MutableCapabilityPort(self.available, events=events)
        secondary = MutableCapabilityPort(self.available, events=events)
        receipt = PresentationPublisher(main, secondary).publish(self.secondary)
        self.assertEqual(events, [main, secondary])
        self.assertIs(main.calls[0], self.secondary.main)
        self.assertIs(secondary.calls[0], self.secondary.secondary)
        self.assertEqual(
            receipt,
            PublicationReceipt(ScoreboardPlacement.SECONDARY, True, True),
        )

    def test_known_dimensions_do_not_change_secondary_behavior(self):
        for dimensions in (False, True):
            bundle = build_presentation(
                GameSession().snapshot(), application_capabilities()
            )
            main = FakeMainPresentationPort(
                DisplayCapabilities(True, 128 if dimensions else None, 160 if dimensions else None)
            )
            PresentationPublisher(main).publish(bundle)
            self.assertIs(main.presented[0], bundle.main)

    def test_preflight_failures_make_no_calls(self):
        main = MutableCapabilityPort(self.available)
        secondary = MutableCapabilityPort(self.available)
        publisher = PresentationPublisher(main, secondary)
        with self.assertRaises(InvalidPresentationPublisherValueError):
            publisher.publish(object())

        class BundleSubclass(PresentationBundle):
            pass

        subclass = BundleSubclass(
            self.none.main, self.none.secondary, self.none.scoreboard_placement
        )
        with self.assertRaises(InvalidPresentationPublisherValueError):
            publisher.publish(subclass)
        self.assertEqual((main.calls, secondary.calls), ([], []))

    def test_required_port_preflight_failures_make_no_calls(self):
        unavailable = DisplayCapabilities(False, None, None)
        cases = (
            (MutableCapabilityPort(unavailable), None, self.none, PortUnavailableError),
            (MutableCapabilityPort(self.available), None, self.secondary, InvalidPresentationPublisherValueError),
            (MutableCapabilityPort(self.available), MutableCapabilityPort(unavailable), self.secondary, PortUnavailableError),
        )
        for main, secondary, bundle, error in cases:
            with self.subTest(error=error):
                publisher = PresentationPublisher(main, secondary)
                with self.assertRaises(error):
                    publisher.publish(bundle)
                self.assertEqual(main.calls, [])

    def test_capabilities_are_revalidated_before_publication(self):
        main = MutableCapabilityPort(self.available)
        secondary = MutableCapabilityPort(self.available)
        publisher = PresentationPublisher(main, secondary)
        main.capability = object()
        with self.assertRaises(InvalidPresentationPublisherValueError):
            publisher.publish(self.none)
        main.capability = self.available
        secondary.capability = object()
        with self.assertRaises(InvalidPresentationPublisherValueError):
            publisher.publish(self.secondary)
        self.assertEqual(main.calls, [])

    def test_main_failure_is_chained_and_not_retried(self):
        cause = RuntimeError("main")
        main = MutableCapabilityPort(self.available, cause)
        secondary = MutableCapabilityPort(self.available)
        with self.assertRaises(PresentationPublishError) as caught:
            PresentationPublisher(main, secondary).publish(self.secondary)
        self.assertIs(caught.exception.target, PublicationTarget.MAIN)
        self.assertEqual((caught.exception.main_published, caught.exception.secondary_published), (False, False))
        self.assertIs(caught.exception.__cause__, cause)
        self.assertEqual(len(main.calls), 1)
        self.assertEqual(secondary.calls, [])

    def test_secondary_failure_preserves_main_and_is_not_retried(self):
        cause = RuntimeError("secondary")
        main = FakeMainPresentationPort(self.available)
        secondary = MutableCapabilityPort(self.available, cause)
        with self.assertRaises(PresentationPublishError) as caught:
            PresentationPublisher(main, secondary).publish(self.secondary)
        self.assertIs(caught.exception.target, PublicationTarget.SECONDARY)
        self.assertEqual((caught.exception.main_published, caught.exception.secondary_published), (True, False))
        self.assertIs(caught.exception.__cause__, cause)
        self.assertEqual(main.presented, (self.secondary.main,))
        self.assertEqual(len(secondary.calls), 1)

    def test_repeated_publication_is_not_deduplicated(self):
        main = FakeMainPresentationPort(self.available)
        secondary = FakeSecondaryPresentationPort(self.available)
        publisher = PresentationPublisher(main, secondary)
        publisher.publish(self.secondary)
        first_history = main.presented
        publisher.publish(self.secondary)
        self.assertEqual(main.presented, (self.secondary.main,) * 2)
        self.assertEqual(secondary.presented, (self.secondary.secondary,) * 2)
        self.assertEqual(first_history, (self.secondary.main,))


if __name__ == "__main__":
    unittest.main()
