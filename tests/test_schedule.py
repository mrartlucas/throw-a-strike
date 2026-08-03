import copy
import json
import unittest
from dataclasses import FrozenInstanceError

from throw_a_strike.domain.config import MatchConfig, Mode, Theme
from throw_a_strike.domain.schedule import (
    InvalidScheduleConfigurationError, PartyFrameSchedule, PartySchedule,
    PartySetupDefinition, RemixFrameSchedule, RemixObject, RemixSchedule,
    ScheduleModeError, build_party_schedule, build_remix_schedule,
)


def config(mode=Mode.REMIX, frames=3, theme=Theme.REGULAR, players=2, seed=42):
    return MatchConfig(mode, theme, players, frames, seed)


def catalog():
    # Canonical catalog used by the locked seed-42 Party vector below.
    return (
        PartySetupDefinition("classic", "triangle", ("pin",), (), ("bonus", "swap", "double"), 100),
        PartySetupDefinition("orbit", "ring", ("orb", "star"), ("pulse",), ("mystery_a", "mystery_b"), 75),
    )


class RemixTests(unittest.TestCase):
    def test_locked_object_catalog(self):
        self.assertEqual([o.value for o in RemixObject], [
            "tennis_ball", "baseball", "basketball", "beach_ball", "football",
            "soccer_ball", "golf_ball", "medicine_ball", "rubber_ball",
        ])

    def test_wrong_mode_is_rejected(self):
        with self.assertRaises(ScheduleModeError):
            build_remix_schedule(config(Mode.PARTY))

    def test_supported_schedule_lengths_numbering_objects_and_maximums(self):
        for count in (3, 5, 10):
            schedule = build_remix_schedule(config(frames=count))
            self.assertEqual(len(schedule.frames), count)
            self.assertEqual(tuple(f.frame_number for f in schedule.frames), tuple(range(1, count + 1)))
            self.assertTrue(all(len(f.objects) == 2 for f in schedule.frames))
            self.assertEqual(schedule.frame_max_scores, (10,) * count)

    def test_same_config_is_equal(self):
        self.assertEqual(build_remix_schedule(config()), build_remix_schedule(config()))

    def test_theme_and_player_count_do_not_change_competitive_frames(self):
        baseline = build_remix_schedule(config()).frames
        self.assertEqual(baseline, build_remix_schedule(config(theme=Theme.BLACKLIGHT)).frames)
        self.assertEqual(baseline, build_remix_schedule(config(players=4)).frames)

    def test_locked_seed_42_three_frame_vector(self):
        # Remix, 3 frames, seed 42; theme/player count are intentionally irrelevant.
        actual = tuple(tuple(o.value for o in f.objects) for f in build_remix_schedule(config()).frames)
        self.assertEqual(actual, (
            ("tennis_ball", "basketball"),
            ("soccer_ball", "golf_ball"),
            ("tennis_ball", "golf_ball"),
        ))

    def test_payload_is_json_safe_detached_and_round_trips(self):
        schedule = build_remix_schedule(config())
        payload = schedule.to_payload()
        self.assertIsInstance(json.dumps(payload), str)
        self.assertEqual(RemixSchedule.from_payload(payload), schedule)
        payload["frames"][0]["objects"][0] = "football"
        self.assertEqual(schedule.frames[0].objects[0], RemixObject.TENNIS_BALL)

    def test_malformed_payloads_are_rejected(self):
        base = build_remix_schedule(config()).to_payload()
        variants = []
        for mutate in (
            lambda p: p.update(schema_version=2),
            lambda p: p["frames"].pop(),
            lambda p: p["frames"][0].update(frame_number=2),
            lambda p: p["frames"][0].update(objects=["football"]),
            lambda p: p["frames"][0].update(objects=["invalid", "football"]),
            lambda p: p.update(frame_max_scores=[9, 10, 10]),
        ):
            item = copy.deepcopy(base); mutate(item); variants.append(item)
        for item in variants:
            with self.subTest(item=item), self.assertRaises(InvalidScheduleConfigurationError):
                RemixSchedule.from_payload(item)

    def test_direct_construction_rejects_non_integer_frame_maximums(self):
        schedule = build_remix_schedule(config())
        for malformed in (10.0, True, "10"):
            maximums = (malformed, 10, 10)
            with self.subTest(malformed=malformed), self.assertRaises(
                InvalidScheduleConfigurationError
            ):
                RemixSchedule(schedule.config, schedule.frames, maximums)  # type: ignore[arg-type]

    def test_payload_rejects_non_integer_frame_maximums(self):
        base = build_remix_schedule(config()).to_payload()
        for malformed in (10.0, True, "10"):
            payload = copy.deepcopy(base)
            payload["frame_max_scores"][0] = malformed
            with self.subTest(malformed=malformed), self.assertRaises(
                InvalidScheduleConfigurationError
            ):
                RemixSchedule.from_payload(payload)

    def test_schedule_frames_and_collections_are_frozen_tuples(self):
        schedule = build_remix_schedule(config())
        self.assertIsInstance(schedule.frames, tuple)
        self.assertIsInstance(schedule.frame_max_scores, tuple)
        self.assertIsInstance(schedule.frames[0].objects, tuple)
        with self.assertRaises(FrozenInstanceError):
            schedule.frames = ()  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            schedule.frames[0].frame_number = 2  # type: ignore[misc]


class PartyDefinitionTests(unittest.TestCase):
    def test_empty_optional_metadata_is_allowed(self):
        item = PartySetupDefinition("plain", "line", ("target",), (), (), 1)
        self.assertEqual(item.reaction_ids, ())
        self.assertEqual(item.mystery_outcome_ids, ())

    def test_invalid_identifiers_are_rejected(self):
        constructors = (
            lambda: PartySetupDefinition("", "line", ("target",), (), (), 1),
            lambda: PartySetupDefinition(" id ", "line", ("target",), (), (), 1),
            lambda: PartySetupDefinition("id", "", ("target",), (), (), 1),
            lambda: PartySetupDefinition("id", "line", (), (), (), 1),
            lambda: PartySetupDefinition("id", "line", (" target ",), (), (), 1),
        )
        for constructor in constructors:
            with self.assertRaises(InvalidScheduleConfigurationError): constructor()

    def test_duplicate_metadata_identifiers_are_rejected(self):
        for position in (0, 1, 2):
            values = [("x", "x"), (), ()]
            values[position] = ("x", "x")
            if position != 0: values[0] = ("target",)
            with self.subTest(position=position), self.assertRaises(InvalidScheduleConfigurationError):
                PartySetupDefinition("id", "line", *values, 1)

    def test_invalid_maximum_scores_are_rejected(self):
        for maximum in (0, -1, True, False, 1.0, "1"):
            with self.assertRaises(InvalidScheduleConfigurationError):
                PartySetupDefinition("id", "line", ("target",), (), (), maximum)


class PartyScheduleTests(unittest.TestCase):
    def party_config(self, **changes):
        values = dict(mode=Mode.PARTY, frames=3, theme=Theme.REGULAR, players=2, seed=42)
        values.update(changes)
        return config(**values)

    def test_wrong_mode_is_rejected(self):
        with self.assertRaises(ScheduleModeError): build_party_schedule(config(), catalog())

    def test_non_tuple_empty_invalid_and_duplicate_catalogs_are_rejected(self):
        duplicate = (catalog()[0], catalog()[0])
        for value in (list(catalog()), (), ("not-definition",), duplicate):
            with self.subTest(value=value), self.assertRaises(InvalidScheduleConfigurationError):
                build_party_schedule(self.party_config(), value)  # type: ignore[arg-type]

    def test_supported_lengths_and_complete_copied_metadata(self):
        for count in (3, 5, 10):
            schedule = build_party_schedule(self.party_config(frames=count), catalog())
            self.assertEqual(len(schedule.frames), count)
            self.assertEqual(tuple(f.frame_number for f in schedule.frames), tuple(range(1, count + 1)))
            for frame in schedule.frames:
                source = next(x for x in catalog() if x.setup_id == frame.setup_id)
                self.assertEqual((frame.formation_id, frame.target_type_ids, frame.reaction_ids, frame.maximum_score),
                                 (source.formation_id, source.target_type_ids, source.reaction_ids, source.maximum_score))

    def test_determinism_theme_and_player_fairness(self):
        baseline = build_party_schedule(self.party_config(), catalog())
        self.assertEqual(baseline, build_party_schedule(self.party_config(), catalog()))
        self.assertEqual(baseline.frames, build_party_schedule(self.party_config(theme=Theme.BLACKLIGHT), catalog()).frames)
        self.assertEqual(baseline.frames, build_party_schedule(self.party_config(players=4), catalog()).frames)

    def test_frame_seeds_are_unsigned_deterministic_and_maximums_match(self):
        schedule = build_party_schedule(self.party_config(), catalog())
        self.assertTrue(all(0 <= f.frame_seed < 1 << 64 for f in schedule.frames))
        self.assertEqual(schedule.frame_max_scores, tuple(f.maximum_score for f in schedule.frames))

    def test_fingerprint_detects_every_content_field_and_order(self):
        baseline = build_party_schedule(self.party_config(), catalog()).catalog_fingerprint
        changes = (
            (PartySetupDefinition("changed", "triangle", ("pin",), (), ("bonus", "swap", "double"), 100), catalog()[1]),
            (PartySetupDefinition("classic", "changed", ("pin",), (), ("bonus", "swap", "double"), 100), catalog()[1]),
            (PartySetupDefinition("classic", "triangle", ("changed",), (), ("bonus", "swap", "double"), 100), catalog()[1]),
            (PartySetupDefinition("classic", "triangle", ("pin",), ("changed",), ("bonus", "swap", "double"), 100), catalog()[1]),
            (PartySetupDefinition("classic", "triangle", ("pin",), (), ("changed",), 100), catalog()[1]),
            (PartySetupDefinition("classic", "triangle", ("pin",), (), ("bonus", "swap", "double"), 101), catalog()[1]),
            tuple(reversed(catalog())),
        )
        for changed in changes:
            self.assertNotEqual(build_party_schedule(self.party_config(), changed).catalog_fingerprint, baseline)

    def test_locked_seed_42_catalog_vector_and_mystery_order(self):
        # Party, 3 frames, seed 42 and the exact ordered catalog returned by catalog().
        schedule = build_party_schedule(self.party_config(), catalog())
        self.assertEqual(schedule.catalog_fingerprint, "a2028a8ffdbe73705c2503ef705d61c3cf1a562b0b23d7fe6332febd42381bd6")
        self.assertEqual(tuple((f.setup_id, f.mystery_outcome_ids, f.maximum_score, f.frame_seed) for f in schedule.frames), (
            ("classic", ("double", "swap", "bonus"), 100, 6363321364370863855),
            ("classic", ("swap", "bonus", "double"), 100, 8975723300030796048),
            ("orbit", ("mystery_a", "mystery_b"), 75, 13362449695662286053),
        ))

    def test_payload_is_json_safe_detached_and_round_trips_without_catalog(self):
        schedule = build_party_schedule(self.party_config(), catalog())
        payload = schedule.to_payload()
        self.assertIsInstance(json.dumps(payload), str)
        self.assertEqual(PartySchedule.from_payload(payload), schedule)
        payload["frames"][0]["target_type_ids"][0] = "changed"
        self.assertEqual(schedule.frames[0].target_type_ids, ("pin",))

    def test_malformed_payloads_are_rejected(self):
        base = build_party_schedule(self.party_config(), catalog()).to_payload()
        variants = []
        for mutate in (
            lambda p: p.update(schema_version=2), lambda p: p["frames"].pop(),
            lambda p: p["frames"][0].update(frame_number=2),
            lambda p: p.update(frame_max_scores=[1, 100, 75]),
            lambda p: p.update(catalog_fingerprint="bad"),
            lambda p: p["frames"][0].update(frame_seed=-1),
        ):
            item=copy.deepcopy(base); mutate(item); variants.append(item)
        for item in variants:
            with self.assertRaises(InvalidScheduleConfigurationError): PartySchedule.from_payload(item)

    def test_direct_construction_rejects_non_integer_frame_maximums(self):
        one_point_catalog = (
            PartySetupDefinition("one", "single", ("target",), (), (), 1),
        )
        schedule = build_party_schedule(self.party_config(), one_point_catalog)
        for malformed in (1.0, True, "1"):
            maximums = (malformed, 1, 1)
            with self.subTest(malformed=malformed), self.assertRaises(
                InvalidScheduleConfigurationError
            ):
                PartySchedule(
                    schedule.config,
                    schedule.catalog_fingerprint,
                    schedule.frames,
                    maximums,  # type: ignore[arg-type]
                )

    def test_payload_rejects_non_integer_frame_maximums(self):
        one_point_catalog = (
            PartySetupDefinition("one", "single", ("target",), (), (), 1),
        )
        base = build_party_schedule(
            self.party_config(), one_point_catalog
        ).to_payload()
        for malformed in (1.0, True, "1"):
            payload = copy.deepcopy(base)
            payload["frame_max_scores"][0] = malformed
            with self.subTest(malformed=malformed), self.assertRaises(
                InvalidScheduleConfigurationError
            ):
                PartySchedule.from_payload(payload)

    def test_schedules_frames_and_all_metadata_are_frozen_tuples(self):
        schedule = build_party_schedule(self.party_config(), catalog())
        self.assertIsInstance(schedule.frames, tuple); self.assertIsInstance(schedule.frame_max_scores, tuple)
        frame = schedule.frames[0]
        for value in (frame.target_type_ids, frame.reaction_ids, frame.mystery_outcome_ids): self.assertIsInstance(value, tuple)
        with self.assertRaises(FrozenInstanceError): schedule.frames = ()  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError): frame.maximum_score = 1  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
