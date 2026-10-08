"""Independent, deterministic tests for all four option directions (no market calls)."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import math
import unittest

from research.four_leg_score.engine import Snapshot, evaluate, expiry_payoff_per_share


BASE = Snapshot(
    leg="short_put",
    underlying_price=100.0,
    strike=95.0,
    bid=2.0,
    ask=2.5,
    iv=0.20,
    years_to_expiry=30 / 365,
    risk_free_rate=0.03,
    dividend_yield=0.01,
    fee_per_share=0.05,
)


class FourLegMetricsTests(unittest.TestCase):
    def test_all_four_legs_have_separate_otm_and_profit_probabilities(self):
        for leg in ("long_call", "long_put", "short_call", "short_put"):
            with self.subTest(leg=leg):
                metrics = evaluate(replace(BASE, leg=leg))
                for key in ("p_expiry_itm_q", "p_expiry_otm_q", "p_expiry_profit_q"):
                    self.assertGreaterEqual(metrics[key], 0.0)
                    self.assertLessEqual(metrics[key], 1.0)
                self.assertAlmostEqual(
                    metrics["p_expiry_itm_q"] + metrics["p_expiry_otm_q"], 1.0, places=12
                )
                self.assertIsNone(metrics["actual_assignment_probability"])
                self.assertIsNone(metrics["opportunity_score_0_100"])
                self.assertFalse(metrics["real_world_probability_calibrated"])
                self.assertEqual(metrics["order_actions"], [])
                self.assertIn("MISSING_SYNCHRONIZED_QUOTE_TIMESTAMPS", metrics["data_warnings"])

    def test_all_four_break_even_prices_are_correct(self):
        expected = {
            "long_call": 97.55,
            "long_put": 92.45,
            "short_call": 96.95,
            "short_put": 93.05,
        }
        for leg, value in expected.items():
            with self.subTest(leg=leg):
                self.assertAlmostEqual(evaluate(replace(BASE, leg=leg))["breakeven"], value, places=9)

    def test_payoff_at_break_even_is_zero(self):
        for leg in ("long_call", "long_put", "short_call", "short_put"):
            with self.subTest(leg=leg):
                x = replace(BASE, leg=leg)
                self.assertAlmostEqual(
                    expiry_payoff_per_share(x, evaluate(x)["breakeven"]), 0.0, places=8
                )

    def test_long_options_have_bounded_loss(self):
        for leg in ("long_call", "long_put"):
            out = evaluate(replace(BASE, leg=leg))
            self.assertEqual(out["max_loss_per_share"], BASE.ask + BASE.fee_per_share)
            self.assertIsNone(out["entry_credit_per_share"])
            self.assertIsNotNone(out["entry_debit_per_share"])

    def test_short_put_loss_and_short_call_infinite_risk(self):
        a = evaluate(BASE)
        b = evaluate(replace(BASE, leg="short_call"))
        self.assertAlmostEqual(a["max_loss_per_share"], BASE.strike - BASE.bid + BASE.fee_per_share)
        self.assertIsNone(b["max_loss_per_share"])
        self.assertTrue(b["unbounded_upside_loss"])
        self.assertIn("SHORT_CALL_UNCOVERED_UNBOUNDED_LOSS", b["data_warnings"])

    def test_probability_breakeven_vs_strike(self):
        for leg in ("short_put", "short_call"):
            x = evaluate(replace(BASE, leg=leg))
            self.assertGreater(x["p_expiry_profit_q"], x["p_expiry_otm_q"])
        for leg in ("long_call", "long_put"):
            x = evaluate(replace(BASE, leg=leg))
            self.assertLess(x["p_expiry_profit_q"], x["p_expiry_itm_q"])

    def test_timestamp_gate_synchronized_and_stale(self):
        now = datetime(2026, 10, 8, 13, 30, tzinfo=timezone.utc)
        good = replace(BASE, observed_at_utc=now,
                       underlying_quote_at_utc=now - timedelta(minutes=3),
                       option_quote_at_utc=now - timedelta(minutes=4))
        self.assertEqual(evaluate(good)["quote_quality_state"], "TIMESTAMP_CHECK_PASS")
        bad = replace(good, option_quote_at_utc=now - timedelta(hours=2))
        self.assertIn("STALE_UNDERLYING_OR_OPTION_QUOTE", evaluate(bad)["data_warnings"])
        self.assertIn("UNSYNCHRONIZED_QUOTES", evaluate(bad)["data_warnings"])

    def test_reject_bad_input_and_zero_bid_short(self):
        bad_inputs = [
            replace(BASE, underlying_price=-1),
            replace(BASE, iv=float("nan")),
            replace(BASE, ask=1.0),
            replace(BASE, years_to_expiry=0),
            replace(BASE, fee_per_share=-0.01),
            replace(BASE, leg="short_call", bid=0),
            replace(BASE, option_quote_at_utc=datetime(2026, 1, 1)),
        ]
        for x in bad_inputs:
            with self.subTest(x=x), self.assertRaises(ValueError):
                evaluate(x)

    def test_no_pretend_real_world_assignment_prediction(self):
        result = evaluate(BASE)
        self.assertEqual(result["measurement"], "BLACK_SCHOLES_RISK_NEUTRAL_NOT_REAL_WORLD")
        self.assertIsNone(result["actual_assignment_probability"])
        self.assertIsNone(result["risk_of_touch"])
        self.assertEqual(result["score_status"], "PENDING_OUT_OF_SAMPLE_CALIBRATION")

    def test_extreme_thresholds_remain_finite(self):
        # Breakeven for an extremely expensive long put is below zero.
        x = replace(BASE, leg="long_put", strike=1.0, ask=2.5, bid=2.0)
        a = evaluate(x)
        self.assertEqual(a["p_expiry_profit_q"], 0.0)
        self.assertTrue(math.isfinite(a["p_expiry_otm_q"]))


if __name__ == "__main__":
    unittest.main()
