"""R1 tests: gate public Yahoo observations instead of manufacturing scores."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import unittest

from research.four_leg_score.quote_gate import assess_observation


OBSERVED = datetime(2026, 10, 8, 15, 45, tzinfo=timezone.utc)


def verified():
    snap = {
        "provider": "fixture_verified_quotes",
        "symbol": "SPY",
        "spot_kind": "verified_intraday_quote",
        "spot_current": 670.0,
        "spot_quote_at_utc": (OBSERVED - timedelta(minutes=3)).isoformat(),
        "observed_at_utc": OBSERVED.isoformat(),
        "expiry": "2026-11-20",
    }
    row = {
        "contract": "SPY261120P00650000",
        "strike": 650.0,
        "bid": 8.0,
        "ask": 8.3,
        "iv": 0.22,
        "quote_at_utc": (OBSERVED - timedelta(minutes=4)).isoformat(),
        "last_trade_at": "2026-10-01T15:00:00+00:00",  # never used as quote timestamp
    }
    return snap, row


class QuoteGateTests(unittest.TestCase):
    def test_synthetic_verified_snapshot_admits_only_theoretical_q(self):
        s, r = verified()
        for leg in ("long_call", "long_put", "short_call", "short_put"):
            with self.subTest(leg=leg):
                out = assess_observation(s, r, leg)
                self.assertEqual(out["quote_data_status"], "THEORETICAL_INPUT_READY")
                self.assertTrue(out["theoretical_q_eligible"])
                self.assertEqual(out["quote_issues"], [])
                self.assertIsNone(out["actual_assignment_probability"])
                self.assertIsNone(out["formal_opportunity_score_0_100"])
                self.assertFalse(out["real_world_probability_calibrated"])
                self.assertEqual(out["order_actions"], [])

    def test_real_observer_shape_blocks_all_four_legs(self):
        s, r = verified()
        s.pop("spot_current")
        s.pop("spot_quote_at_utc")
        s["spot_kind"] = "historical_daily_close_not_live"
        s["spot_last_daily_close"] = 670.0
        s["spot_last_daily_bar_at"] = "2026-10-07"
        r.pop("quote_at_utc")
        for leg in ("long_call", "long_put", "short_call", "short_put"):
            with self.subTest(leg=leg):
                out = assess_observation(s, r, leg)
                self.assertFalse(out["theoretical_q_eligible"])
                self.assertIn("SPOT_NOT_VERIFIED_INTRADAY_QUOTE", out["quote_issues"])
                self.assertIn("CURRENT_SPOT_MISSING", out["quote_issues"])
                self.assertIn("UNDERLYING_QUOTE_TIME_MISSING_OR_INVALID", out["quote_issues"])
                self.assertIn("OPTION_QUOTE_TIME_MISSING_OR_INVALID", out["quote_issues"])
                self.assertIsNone(out["formal_opportunity_score_0_100"])

    def test_last_trade_time_does_not_substitute_option_quote_time(self):
        s, r = verified()
        r["last_trade_at"] = OBSERVED.isoformat()
        r.pop("quote_at_utc")
        self.assertIn(
            "OPTION_QUOTE_TIME_MISSING_OR_INVALID",
            assess_observation(s, r, "short_put")["quote_issues"],
        )

    def test_stale_and_misaligned_quotes_block(self):
        s, r = verified()
        s["spot_quote_at_utc"] = (OBSERVED - timedelta(hours=2)).isoformat()
        out = assess_observation(s, r, "short_put")
        self.assertIn("UNDERLYING_QUOTE_OUT_OF_WINDOW", out["quote_issues"])
        self.assertIn("QUOTES_NOT_TIME_ALIGNED", out["quote_issues"])

    def test_option_timestamp_in_future_blocks(self):
        s, r = verified()
        r["quote_at_utc"] = (OBSERVED + timedelta(minutes=1)).isoformat()
        self.assertIn(
            "OPTION_QUOTE_OUT_OF_WINDOW",
            assess_observation(s, r, "long_put")["quote_issues"],
        )

    def test_invalid_quote_and_iv_block(self):
        for values, reason in (
            ({"bid": 0}, "OPTION_BID_ASK_UNUSABLE"),
            ({"ask": 7}, "OPTION_BID_ASK_UNUSABLE"),
            ({"bid": 1, "ask": 3}, "OPTION_SPREAD_TOO_WIDE"),
            ({"iv": None}, "OPTION_IV_UNUSABLE"),
            ({"iv": float("nan")}, "OPTION_IV_UNUSABLE"),
            ({"strike": None}, "STRIKE_UNUSABLE"),
            ({"contract": ""}, "CONTRACT_ID_MISSING"),
        ):
            s, r = verified()
            r.update(values)
            with self.subTest(values=values):
                self.assertIn(reason, assess_observation(s, r, "long_call")["quote_issues"])

    def test_invalid_or_naive_timestamp_not_accepted(self):
        s, r = verified()
        s["spot_quote_at_utc"] = "2026-10-08T15:44:00"
        self.assertIn(
            "UNDERLYING_QUOTE_TIME_MISSING_OR_INVALID",
            assess_observation(s, r, "long_call")["quote_issues"],
        )

    def test_reject_unsupported_leg(self):
        s, r = verified()
        with self.assertRaises(ValueError):
            assess_observation(s, r, "iron_condor")


if __name__ == "__main__":
    unittest.main()
