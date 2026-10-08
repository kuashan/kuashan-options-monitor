"""V1 integrated four-leg logic, HTTP, fail-closed & UI contract tests (offline)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen
import json
import unittest

from standalone_web.option_analysis import analyze_option, analyze_chain, MODEL
from standalone_web.tests.test_server import HttpTests

STAMP = "2026-10-09T01:00:00+00:00"
EXPIRY = "2026-11-20"

CALL = {
    "contract": "SPY261120C00600000", "strike": 600., "bid": 8.,
    "ask": 8.2, "iv": .22, "volume": 10, "open_interest": 200,
    "last_trade_at": STAMP, "quote_state": "valid_bid_ask",
}
PUT = {
    "contract": "SPY261120P00600000", "strike": 600., "bid": 9.,
    "ask": 9.2, "iv": .25, "volume": 15, "open_interest": 90,
    "last_trade_at": STAMP, "quote_state": "valid_bid_ask",
}


def snapshot(spot=600., expiry=EXPIRY):
    return {
        "symbol": "SPY", "provider": "mock Yahoo",
        "spot_last_daily_close": spot, "spot_kind": "historical_daily_close_not_live",
        "spot_last_daily_bar_at": "2026-10-08",
        "observed_at_utc": STAMP, "expiry": expiry,
        "expirations": [expiry], "calls": [CALL], "puts": [PUT],
        "counts": {"calls_source": 1, "puts_source": 1},
        "account_connected": False, "order_execution_enabled": False,
    }


class IntegratedAnalysisTests(unittest.TestCase):
    def test_four_legs_present_without_mutating_original(self):
        payload = snapshot()
        output = analyze_chain(payload)
        self.assertNotIn("analyses", payload["calls"][0])
        self.assertEqual(set(output["calls"][0]["analyses"]), {"long_call", "short_call"})
        self.assertEqual(set(output["puts"][0]["analyses"]), {"long_put", "short_put"})
        self.assertEqual(output["model"]["name"], MODEL)
        self.assertEqual(len(output["model"]["retained_score_factors"]), 3)
        self.assertEqual(output["order_execution_enabled"], False)

    def test_score_is_exactly_minimum_of_three_not_composite_fake_win_rate(self):
        for leg, option in (("long_call",CALL),("long_put",PUT),("short_put",PUT)):
            with self.subTest(leg=leg):
                a=analyze_option(leg, option, 600., EXPIRY, STAMP)
                self.assertIsInstance(a["score_0_100"], int)
                self.assertGreaterEqual(a["score_0_100"], 0)
                self.assertLessEqual(a["score_0_100"], 100)
                self.assertEqual(a["score_0_100"],round(100*min(a["score_factors"].values())))
                self.assertTrue(0 <= a["p_expiry_profit_q"] <= 1)
                self.assertIsNone(a["formal_opportunity_score_0_100"])
                self.assertIsNone(a["actual_assignment_probability"])
                self.assertEqual(a["order_actions"],[])
                self.assertEqual(a["assumptions"]["option_quote_timestamp"],"UNAVAILABLE")

    def test_unbounded_short_call_is_analyzed_but_not_graded(self):
        a=analyze_option("short_call",CALL,600.,EXPIRY,STAMP)
        self.assertIsNone(a["score_0_100"])
        self.assertTrue(a["unbounded_max_loss"])
        self.assertEqual(a["score_status"],"UNBOUNDED_RISK_NO_COMPARABLE_SCORE")
        self.assertIsNotNone(a["adverse_20pct_pnl_per_share"])
        self.assertTrue(0<=a["p_expiry_profit_q"]<=1)

    def test_exclude_nonvalidated_features(self):
        excluded=analyze_chain(snapshot())["model"]["excluded_from_score"]
        self.assertIn("20day_momentum",excluded)
        self.assertIn("greeks_stacking",excluded)
        self.assertIn("naive_50_50_probability_blend",excluded)

    def test_missing_spot_iv_quote_and_same_day_expiry_fail_closed(self):
        cases = [
            (None,PUT,EXPIRY,"标的"),
            (600.,dict(PUT, bid=None),EXPIRY,"Bid/Ask"),
            (600.,dict(PUT, iv=None),EXPIRY,"IV"),
            (600.,dict(PUT, bid=5., ask=4.),EXPIRY,"Bid/Ask"),
            (600.,dict(PUT, bid=.01, ask=5.),EXPIRY,"价差"),
            (600.,PUT,"2026-10-09","到期"),
        ]
        for spot, option, expiry, key in cases:
            with self.subTest(reason=key):
                r=analyze_option("short_put",option,spot,expiry,STAMP)
                self.assertIsNone(r["score_0_100"])
                self.assertIsNone(r["p_expiry_profit_q"])
                self.assertIn(key,r["score_reason"])

    def test_quote_last_trade_does_not_become_verified_quote_time(self):
        option=dict(PUT, last_trade_at=STAMP)
        r=analyze_option("long_put",option,600.,EXPIRY,STAMP)
        self.assertEqual(r["score_status"],"UNCALIBRATED_RULE_REFERENCE_DAILY_CLOSE")
        self.assertFalse(r["assumptions"]["scenarios_are_forecasts"])

    def test_theoretical_expiry_breakevens_correct_for_four_legs(self):
        expected={
            "long_call": 600+8.2+.01,
            "short_call": 600+8-.01,
            "long_put": 600-9.2-.01,
            "short_put": 600-9+.01,
        }
        for leg,be in expected.items():
            with self.subTest(leg=leg):
                row=CALL if leg.endswith("call") else PUT
                out=analyze_option(leg,row,600.,EXPIRY,STAMP)
                self.assertAlmostEqual(out["breakeven"],be,places=5)


class UiIntegrationContractTests(unittest.TestCase):
    def test_html_has_all_four_tabs_and_conversation_safe_no_account_forms(self):
        page=(Path(__file__).resolve().parents[1]/"static"/"index.html").read_text()
        for leg in ("long_call","long_put","short_call","short_put"):
            self.assertIn('data-leg="'+leg+'"',page)
        for field in ("option-symbol","option-expiry","option-chain-tbody","detail-body"):
            self.assertIn('id="'+field+'"',page)
        self.assertNotIn('id="account"',page)
        self.assertNotIn('id="refresh"',page)

    def test_javascript_only_uses_public_options_and_health_routes(self):
        script=(Path(__file__).resolve().parents[1]/"static"/"app.js").read_text()
        self.assertIn('"/api/v1/options?"',script)
        self.assertIn('"/api/v1/health"',script)
        self.assertNotIn('"/api/v1/positions"',script)
        self.assertNotIn('"/api/v1/send_order"',script)
        self.assertIn("textContent",script)
        self.assertNotIn("innerHTML",script)


class FourLegHttpTests(HttpTests):
    def test_integration_public_options_route_includes_analysis(self):
        with patch("standalone_web.public_marketdata.fetch_public_option_chain",return_value=snapshot()):
            with urlopen(self.url+"/api/v1/options?symbol=SPY") as response:
                v=json.load(response)
                self.assertTrue(v["ok"])
                model=v["data"]["model"]
                self.assertEqual(model["name"],MODEL)
                self.assertFalse(model["formal_score_available"])
                for kind in ("calls","puts"):
                    self.assertEqual(len(v["data"][kind]),1)
                    for a in v["data"][kind][0]["analyses"].values():
                        self.assertIsNone(a["formal_opportunity_score_0_100"])
                        self.assertEqual(a["order_actions"],[])

    def test_original_trade_api_still_forbidden(self):
        from urllib.error import HTTPError
        for suffix in ("/api/v1/positions","/api/v1/order","/api/v1/accounts"):
            with self.subTest(path=suffix),self.assertRaises(HTTPError) as exc:
                urlopen(self.url+suffix)
            self.assertEqual(exc.exception.code,403)


if __name__ == "__main__":
    unittest.main()
