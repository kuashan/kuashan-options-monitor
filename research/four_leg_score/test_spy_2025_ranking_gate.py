"""Tests for no-weight dominance gate, never calling live market sources."""
from __future__ import annotations
import unittest
from research.four_leg_score.spy_2025_ranking_gate import known_at_entry,compare,summarize


class ParetoTests(unittest.TestCase):
    def test_short_put_tradeoff_credit_vs_downside_risk(self):
        a=(100.,4.,4.2,100.)
        b=(95.,2.,2.2,100.)
        self.assertEqual(compare("short_put",a,b),"TRADEOFF_ABSTAIN")

    def test_short_call_tradeoff_credit_vs_upside_risk(self):
        a=(100.,5.,5.3,100.)
        b=(105.,2.,2.3,100.)
        self.assertEqual(compare("short_call",a,b),"TRADEOFF_ABSTAIN")

    def test_long_call_premium_vs_upside_and_long_put(self):
        a=(100.,5.,5.2,100.)
        b=(105.,2.,2.2,100.)
        self.assertEqual(compare("long_call",a,b),"TRADEOFF_ABSTAIN")
        p=(100.,5.,5.2,100.)
        q=(95.,2.,2.2,100.)
        self.assertEqual(compare("long_put",p,q),"TRADEOFF_ABSTAIN")

    def test_dominance_works_for_better_quote_on_same_strike(self):
        a=(100.,2.,2.1,100.)
        b=(100.,1.,1.1,100.)
        self.assertEqual(compare("short_put",a,b),"ATM_DOMINATES")
        self.assertEqual(compare("short_call",a,b),"ATM_DOMINATES")
        self.assertEqual(compare("long_call",a,b),"OTM_DOMINATES")
        self.assertEqual(compare("long_put",a,b),"OTM_DOMINATES")

    def test_no_fake_naked_call_roi(self):
        s=summarize([(1.0,3.0,105.,100.),(-12.,3.,105.,100.)],"short_call")
        self.assertIsNone(s["mean_return_on_own_reference"])
        self.assertEqual(s["capital_reference"],"NONE_FOR_UNBOUNDED_NAKED_SHORT_CALL")

    def test_long_bounded_loss_and_short_put_cash_reference(self):
        a=summarize([(-2.01,2.,100.,100.)],"long_call")
        self.assertAlmostEqual(a["mean_return_on_own_reference"],-1.)
        b=summarize([(1.99,2.,95.,100.)],"short_put")
        self.assertAlmostEqual(b["mean_return_on_own_reference"],1.99/95.,places=5)


if __name__=="__main__":
    unittest.main()
