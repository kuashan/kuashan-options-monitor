"""No-network tests for public-marketdata observer; all brokerage paths remain unused."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import sys
import types
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen

from standalone_web import public_marketdata as data
from standalone_web.tests.test_server import HttpTests


class Frame:
    def __init__(self, records):
        self.records = records

    def iterrows(self):
        for i, record in enumerate(self.records):
            yield i, record


class FakeTicker:
    calls = Frame([
        {
            "contractSymbol": "SPY261016C00500000", "strike": 500,
            "bid": 1.5, "ask": 1.6, "lastPrice": 1.4,
            "volume": 22, "openInterest": 44, "impliedVolatility": 0.17,
            "lastTradeDate": datetime(2026, 10, 7, tzinfo=timezone.utc),
            "inTheMoney": False,
        }
    ])
    puts = Frame([
        {
            "contractSymbol": "SPY261016P00500000", "strike": 500,
            "bid": 0.0, "ask": 1.1, "lastPrice": 1.2,
            "volume": float("nan"), "openInterest": None, "impliedVolatility": float("nan"),
            "lastTradeDate": None, "inTheMoney": True,
        }
    ])
    options = ("2026-10-16", "2026-10-23")

    def option_chain(self, expiry):
        if expiry not in self.options:
            raise ValueError("No such expiration")
        return types.SimpleNamespace(calls=self.calls, puts=self.puts)

    def history(self, **kwargs):
        return types.SimpleNamespace(empty=True)


class PublicMarketDataTests(unittest.TestCase):
    def setUp(self):
        with data._cache_lock:
            data._cache.clear()

    def test_validate_symbol_and_expiry(self):
        self.assertEqual(data.normalize_request("spy", "2026-10-16"), ("SPY", "2026-10-16"))
        for symbol in ("../secret", "a b", "AAAA?x", ""):
            with self.subTest(symbol=symbol), self.assertRaises(ValueError):
                data.normalize_request(symbol)
        for expiry in ("2026-99-99", "yesterday", "../x"):
            with self.subTest(expiry=expiry), self.assertRaises(ValueError):
                data.normalize_request("SPY", expiry)

    def test_normalize_quotes_no_invented_market_data(self):
        rows, count, truncated = data.option_rows(FakeTicker.puts, 500)
        self.assertEqual(count, 1)
        self.assertFalse(truncated)
        self.assertIsNone(rows[0]["bid"])
        self.assertIsNone(rows[0]["ask"])
        self.assertIsNone(rows[0]["open_interest"])
        self.assertIsNone(rows[0]["iv"])
        self.assertEqual(rows[0]["quote_state"], "no_valid_bid_ask")

    def test_truncation_is_disclosed(self):
        frame = Frame([{"strike": float(i + 1), "bid": 1, "ask": 2} for i in range(500)])
        rows, total, truncated = data.option_rows(frame, 251.0)
        self.assertEqual(len(rows), data.MAX_ROWS_PER_SIDE)
        self.assertEqual(total, 500)
        self.assertTrue(truncated)

    def test_fake_yfinance_observation_caching_and_no_greeks(self):
        factory = unittest.mock.Mock(return_value=FakeTicker())
        with patch.dict(sys.modules, {"yfinance": types.SimpleNamespace(Ticker=factory)}):
            first = data.fetch_public_option_chain("spy")
            second = data.fetch_public_option_chain("SPY")
        self.assertEqual(first["market"], "US")
        self.assertEqual(first["expiry"], "2026-10-16")
        self.assertEqual(len(first["calls"]), 1)
        self.assertEqual(len(first["puts"]), 1)
        self.assertIsNone(first["spot_last_daily_close"])
        self.assertFalse(first["order_execution_enabled"])
        self.assertEqual(first["greeks_status"], "not_available")
        self.assertTrue(second["from_cache"])
        factory.assert_called_once()

    def test_missing_expiry_and_upstream_failure(self):
        with patch.dict(sys.modules, {"yfinance": types.SimpleNamespace(Ticker=lambda _: FakeTicker())}):
            with self.assertRaises(ValueError):
                data.fetch_public_option_chain("SPY", "2026-11-30")
        with patch.dict(sys.modules, {"yfinance": types.SimpleNamespace(Ticker=lambda _: (_ for _ in ()).throw(RuntimeError("Yahoo down")))}):
            with self.assertRaises(data.MarketDataUnavailable):
                data.fetch_public_option_chain("SPY")


class PublicWebRouteTests(HttpTests):
    """Reuses the HTTP fixture from original tests; network is mocked."""

    def test_public_options_read(self):
        payload = {
            "provider": "fake", "symbol": "SPY", "expiry": "2026-10-16",
            "calls": [], "puts": [], "observed_at_utc": "2026-10-08T00:00:00Z",
        }
        with patch("standalone_web.public_marketdata.fetch_public_option_chain", return_value=payload):
            with urlopen(self.url + "/api/v1/options?symbol=SPY") as response:
                out = json.load(response)
                self.assertTrue(out["ok"])
                self.assertEqual(out["data"]["symbol"], "SPY")

    def test_public_options_input_gate(self):
        for suffix in ("?symbol=../secret", "?symbol=SPY&unsafe=1", "?symbol=SPY&symbol=AAPL", ""):
            with self.subTest(suffix=suffix), self.assertRaises(HTTPError) as err:
                urlopen(self.url + "/api/v1/options" + suffix)
            self.assertEqual(err.exception.code, 400)

    def test_public_upstream_failure(self):
        with patch("standalone_web.public_marketdata.fetch_public_option_chain",
                   side_effect=data.MarketDataUnavailable("yahoo blocked")):
            with self.assertRaises(HTTPError) as err:
                urlopen(self.url + "/api/v1/options?symbol=SPY")
            self.assertEqual(err.exception.code, 503)


if __name__ == "__main__":
    unittest.main()
