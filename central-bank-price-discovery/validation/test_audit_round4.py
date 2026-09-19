"""Tests for failure modes that could create a misleading lead-lag sample."""

import unittest
from datetime import date, timedelta
from audit_round4 import diagnostic_screen, parse_contract, pilot_rows, zero_quantity_changes


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.day = date(2001, 10, 10)
        self.meeting = date(2001, 11, 6)
        self.history = {key: (self.day, price) for key, price in
                        (("down", .6), ("same", .3), ("up", .1))}

    def test_quarterly_spelling_keeps_horizon(self):
        parsed = parse_contract("FRdwn0912Q")
        self.assertEqual((parsed["suffix"], parsed["horizon"]), ("0912Q", "quarterly"))

    def test_split_label_does_not_assign_basis_points(self):
        parsed = parse_contract("FR50+d1008")
        self.assertEqual(parsed["role"], "split_child")
        self.assertNotIn("basis_points", parsed)
        with self.assertRaises(ValueError):
            parse_contract("FRunknown1101")

    def test_coherence_is_checked_before_normalizing(self):
        history = {key: (self.day, .2) for key in self.history}
        reasons, _, probabilities = diagnostic_screen(history, self.day, self.meeting)
        self.assertIn("incoherent_raw_sum", reasons)
        self.assertFalse(probabilities)

    def test_missing_stale_and_future_components_are_rejected(self):
        for key, replacement, reason in (
            ("up", None, "missing_component_history"),
            ("up", (self.day - timedelta(days=4), .1), "stale_component"),
            ("up", (self.day + timedelta(days=1), .1), "future_price"),
        ):
            history = self.history.copy()
            if replacement is None:
                history.pop(key)
            else:
                history[key] = replacement
            self.assertIn(reason, diagnostic_screen(history, self.day, self.meeting)[0])

    def test_whole_announcement_day_is_excluded(self):
        reasons, _, probabilities = diagnostic_screen(self.history, self.day, self.day)
        self.assertIn("meeting_day_or_later", reasons)
        self.assertFalse(probabilities)

    def test_zero_quantity_change_is_flagged_and_does_not_refresh(self):
        checks = {
            "pilot": {"family": "51:1101", "meeting_date": "2001-11-06",
                      "contracts": {"down": "FRdown1101", "same": "FRsame1101", "up": "FRup1101"}},
            "diagnostic_screen": {"max_age_calendar_days": 3, "raw_probability_sum_tolerance": .1},
        }
        rows = []
        for direction, (_, price) in self.history.items():
            for offset in (0, 1):
                day = self.day + timedelta(days=offset)
                rows.append({"market_id": "51", "contract": checks["pilot"]["contracts"][direction],
                             "family": "51:1101", "day": day, "observation_date": str(day),
                             "horizon": "meeting_interval", "role": "directional",
                             "quantity": 10 if offset == 0 else 0,
                             "dollar_volume": 1 if offset == 0 else 0,
                             "low_price": price if offset == 0 else .8,
                             "high_price": price if offset == 0 else .8,
                             "last_price": price if offset == 0 else .8, "source_url": "fixture"})
        rows.sort(key=lambda row: (row["market_id"], row["contract"], row["day"]))
        self.assertEqual(len(zero_quantity_changes(rows)), 3)
        output = pilot_rows(rows, checks)
        self.assertEqual(output[1]["age_calendar_days_up"], 1)
        self.assertAlmostEqual(output[1]["diagnostic_p_up"], .1)
        self.assertFalse(output[1]["econometrics_ready"])

    def test_legacy_quarterly_zero_reappearance_is_separated(self):
        rows = [
            {"market_id": "51", "contract": "FRup0912Q", "family": "51:0912Q",
             "horizon": "quarterly", "role": "directional", "day": date(2012, 9, 13),
             "observation_date": "2012-09-13", "quantity": 1, "dollar_volume": .1,
             "low_price": .1, "high_price": .1, "last_price": .1, "source_url": "fixture"},
            {"market_id": "51", "contract": "FRup0912Q", "family": "51:0912Q",
             "horizon": "quarterly", "role": "directional", "day": date(2016, 6, 1),
             "observation_date": "2016-06-01", "quantity": 0, "dollar_volume": 0,
             "low_price": 0, "high_price": 0, "last_price": 0, "source_url": "fixture"},
        ]
        change = zero_quantity_changes(rows)[0]
        self.assertTrue(change["legacy_quarterly_zero_reappearance"])
        self.assertEqual(change["gap_calendar_days"], 1357)


if __name__ == "__main__":
    unittest.main()
