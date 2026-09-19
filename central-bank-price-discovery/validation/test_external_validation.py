"""Tests for external-source classification and pilot sensitivity policies."""

import json
from pathlib import Path
import unittest

from audit_external_validation import build_pilot_sensitivity, validate_external_checks


HERE = Path(__file__).resolve().parent


class ExternalValidationTests(unittest.TestCase):
    def setUp(self):
        self.checks = json.loads((HERE / "external_source_checks.json").read_text())

    def test_event_checks_do_not_create_a_paired_futures_leg(self):
        result = validate_external_checks(self.checks)
        self.assertEqual(result["external_direction_check"], "passes")
        self.assertEqual(result["paired_daily_futures_leg"], "missing")
        self.assertFalse(result["econometrics_ready"])

    def test_duplicate_sf_fed_workbooks_are_not_two_sources(self):
        files = {item["name"]: item for item in self.checks["files"]}
        self.assertEqual(
            files["monetary-policy-surprises-data.xlsx"]["sha256"],
            files["sf_fed_monetary_policy_surprises.xlsx"]["sha256"],
        )

    def test_zero_quantity_price_change_affects_policy_comparison(self):
        rows = [
            {"date": "2001-10-03", "reported_last_down": ".55", "reported_quantity_down": "10",
             "reported_last_same": ".55", "reported_quantity_same": "10",
             "reported_last_up": ".065", "reported_quantity_up": "10"},
            {"date": "2001-10-04", "reported_last_down": ".571", "reported_quantity_down": "0",
             "reported_last_same": ".485", "reported_quantity_same": "0",
             "reported_last_up": ".002", "reported_quantity_up": "0"},
        ]
        from datetime import date
        _, summary = build_pilot_sensitivity(rows, date(2001, 11, 6))
        counts = {row["policy"]: row["valid_pre_meeting_days"] for row in summary}
        self.assertEqual(counts["reported_last_regardless_of_quantity"], 1)
        self.assertEqual(counts["positive_quantity_carry_3_calendar_days"], 0)


if __name__ == "__main__":
    unittest.main()
