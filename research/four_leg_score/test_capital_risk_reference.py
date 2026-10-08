"""Small deterministic tests of denominator and stress definitions (no data download)."""
from __future__ import annotations

import unittest

from research.four_leg_score.spy_three_regime_payoff import (
    _risk_reference, _stats, expiry_pl, FEE_PER_SHARE,
)


class CapitalAndRiskReferenceTests(unittest.TestCase):
    def test_long_call_and_long_put_denominator_equals_max_debit_loss(self):
        for leg in ("long_call", "long_put"):
            with self.subTest(leg=leg):
                r = _risk_reference(leg, quote=3.5, strike=100, spot=101)
                self.assertEqual(r["capital_at_risk"], 3.5+FEE_PER_SHARE)
                self.assertEqual(r["max_theoretical_loss"], 3.5+FEE_PER_SHARE)
                self.assertFalse(r["max_loss_unbounded"])

    def test_short_put_full_cash_strike_and_downside_max_loss(self):
        r = _risk_reference("short_put", quote=2.5, strike=95, spot=100)
        self.assertEqual(r["capital_at_risk"], 95.0)
        self.assertAlmostEqual(r["max_theoretical_loss"], 95.0-2.5+FEE_PER_SHARE)
        self.assertEqual(r["denominator_type"], "GROSS_CASH_SECURED_STRIKE")

    def test_naked_short_call_never_gets_finite_max_risk_or_capital_roi(self):
        r = _risk_reference("short_call", quote=1.3, strike=105, spot=100)
        self.assertIsNone(r["capital_at_risk"])
        self.assertIsNone(r["max_theoretical_loss"])
        self.assertTrue(r["max_loss_unbounded"])
        o = _stats([(1.29, 1.3, 105, 100), (-15, 1.3, 105, 100)], "short_call")
        self.assertIsNone(o["normalized_pnl_on_leg_capital_reference"])
        self.assertIsNone(o["capital_required_per_share_mean"])
        self.assertTrue(o["unbounded_theoretical_loss"])
        self.assertLess(o["fixed_expiry_stress_scenarios"]["adverse_spot_50pct"]["mean_usd_per_share"], 0)

    def test_exposure_scaled_is_not_capital_return(self):
        # Short put: close -> S_T=100 yields $1.99 credit per share;
        # dividing by strike 95 differs from dividing by entry spot 100.
        rows = [(1.99, 2.0, 95.0, 100.0), (-3.01, 2.0, 95.0, 100.0)]
        out = _stats(rows, "short_put")
        self.assertAlmostEqual(
            out["exposure_scaled_pnl_over_entry_spot"]["mean"], -0.0051
        )
        self.assertAlmostEqual(
            out["normalized_pnl_on_leg_capital_reference"]["mean"],
            (-1.02/95)/2, places=5
        )

    def test_risk_stress_is_deterministic_and_not_forecast(self):
        # Naked short call struck at 105 with 2 bid:
        # S_T=120 => 2-15-0.01=-13.01; S_T=150 => 2-45-0.01=-43.01.
        x = _stats([(1.99, 2.0, 105, 100)], "short_call")
        self.assertAlmostEqual(x["fixed_expiry_stress_scenarios"]["adverse_spot_20pct"]["mean_usd_per_share"], -13.01)
        self.assertAlmostEqual(x["fixed_expiry_stress_scenarios"]["adverse_spot_50pct"]["mean_usd_per_share"], -43.01)

    def test_debit_cannot_be_negative_and_short_put_credit_must_be_valid(self):
        for args in [("short_put", 96.0, 95, 100),
                     ("short_put", 0.001, 95, 100),
                     ("long_put", -1, 95, 100)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                _risk_reference(*args)

    def test_expiry_payoff_symmetry_includes_bid_ask_spread_and_fees(self):
        for side in ("call", "put"):
            for terminal in (50, 100, 150):
                pl_l = expiry_pl("long_"+side, 100, terminal, 2, 2.5)
                pl_s = expiry_pl("short_"+side, 100, terminal, 2, 2.5)
                self.assertAlmostEqual(pl_l+pl_s, 2-2.5-2*FEE_PER_SHARE)


if __name__ == "__main__":
    unittest.main()
