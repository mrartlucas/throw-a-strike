import json
import unittest
from dataclasses import FrozenInstanceError

from throw_a_strike.domain.config import (
    InvalidMatchConfigError, LOCKED_BRANDING, MatchConfig, Mode, Theme,
)


class LockedValuesTests(unittest.TestCase):
    def test_locked_modes(self):
        self.assertEqual([m.value for m in Mode], ["ten_pin", "hundred_pin", "remix", "party"])

    def test_locked_themes(self):
        self.assertEqual([t.value for t in Theme], ["regular", "blacklight"])

    def test_locked_branding(self):
        self.assertEqual(LOCKED_BRANDING.presenter, "Throw A Way Games")
        self.assertEqual(LOCKED_BRANDING.game_title, "Throw a Strike")
        self.assertEqual(LOCKED_BRANDING.title_treatment, "Throw A Way Games presents\nThrow a Strike")

    def test_branding_is_frozen(self):
        with self.assertRaises(FrozenInstanceError):
            LOCKED_BRANDING.presenter = "changed"  # type: ignore[misc]


class MatchConfigTests(unittest.TestCase):
    def make(self, **changes):
        values = dict(mode=Mode.REMIX, theme=Theme.REGULAR, player_count=1, frame_count=3, seed=0)
        values.update(changes)
        return MatchConfig(**values)

    def test_player_counts_one_through_four(self):
        for count in range(1, 5):
            self.assertEqual(self.make(player_count=count).player_count, count)

    def test_invalid_player_counts_and_types(self):
        for count in (0, -1, 5, True, False, 1.0, "1", None):
            with self.subTest(count=count), self.assertRaises(InvalidMatchConfigError):
                self.make(player_count=count)

    def test_ten_pin_accepts_only_ten(self):
        self.assertEqual(self.make(mode=Mode.TEN_PIN, frame_count=10).frame_count, 10)
        for count in (3, 5, 9, 11):
            with self.assertRaises(InvalidMatchConfigError):
                self.make(mode=Mode.TEN_PIN, frame_count=count)

    def test_other_modes_accept_three_five_and_ten(self):
        for mode in (Mode.HUNDRED_PIN, Mode.REMIX, Mode.PARTY):
            for count in (3, 5, 10):
                self.assertEqual(self.make(mode=mode, frame_count=count).frame_count, count)

    def test_invalid_frame_counts_and_types(self):
        for count in (0, -1, 1, 4, 11, True, 3.0, "3"):
            with self.subTest(count=count), self.assertRaises(InvalidMatchConfigError):
                self.make(frame_count=count)

    def test_unsigned_seed_boundaries(self):
        self.assertEqual(self.make(seed=0).seed, 0)
        self.assertEqual(self.make(seed=(1 << 64) - 1).seed, (1 << 64) - 1)

    def test_invalid_seeds(self):
        for seed in (-1, 1 << 64, True, False, 1.0, "1", None):
            with self.subTest(seed=seed), self.assertRaises(InvalidMatchConfigError):
                self.make(seed=seed)

    def test_constructor_requires_enum_members(self):
        for changes in ({"mode": "remix"}, {"theme": "regular"}):
            with self.assertRaises(InvalidMatchConfigError):
                self.make(**changes)

    def test_config_is_frozen(self):
        with self.assertRaises(FrozenInstanceError):
            self.make().seed = 2  # type: ignore[misc]

    def test_payload_is_json_safe_and_round_trips(self):
        config = self.make(player_count=4, frame_count=10, seed=123)
        self.assertIsInstance(json.dumps(config.to_payload()), str)
        self.assertEqual(MatchConfig.from_payload(config.to_payload()), config)

    def test_payload_is_detached(self):
        config = self.make(seed=5)
        payload = config.to_payload()
        payload["seed"] = 6
        self.assertEqual(config.seed, 5)

    def test_unsupported_missing_extra_and_non_mapping_payloads(self):
        payload = self.make().to_payload()
        invalid = [dict(payload, schema_version=2), {k: v for k, v in payload.items() if k != "seed"}, dict(payload, extra=1), []]
        for item in invalid:
            with self.subTest(item=item), self.assertRaises(InvalidMatchConfigError):
                MatchConfig.from_payload(item)

    def test_invalid_payload_values(self):
        payload = self.make().to_payload()
        for key, value in (("mode", "arcade"), ("theme", "dark"), ("player_count", True), ("frame_count", 4), ("seed", -1)):
            changed = dict(payload)
            changed[key] = value
            with self.subTest(key=key), self.assertRaises(InvalidMatchConfigError):
                MatchConfig.from_payload(changed)


if __name__ == "__main__":
    unittest.main()
