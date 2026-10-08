"""Public option-chain observation via yfinance (unofficial Yahoo Finance access).

Scope: US listed equity/ETF options only. Not a licensed market-data feed.
No broker, account, trading, portfolios, simulated prices or order execution.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
import re
import threading
import time
from typing import Any

SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.-]{0,14}$")
EXPIRY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MAX_ROWS_PER_SIDE = 400
CACHE_TTL_SECONDS = 240
_cache_lock = threading.Lock()
_cache: dict[tuple[str, str | None], tuple[float, dict[str, Any]]] = {}


class MarketDataUnavailable(Exception):
    """Raised when an external public data source cannot be trusted/queried."""


def normalize_request(symbol: str, expiry: str | None = None) -> tuple[str, str | None]:
    code = str(symbol or "").strip().upper()
    if not SYMBOL_RE.fullmatch(code):
        raise ValueError("Invalid US ticker symbol (for example AAPL, SPY or BRK-B)")
    if expiry:
        if not EXPIRY_RE.fullmatch(expiry):
            raise ValueError("Expiration must use YYYY-MM-DD")
        try:
            datetime.strptime(expiry, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("Invalid expiration date") from exc
    return code, expiry or None


def _finite(value: Any) -> float | None:
    if value is None:
        return None
    try:
        converted = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return converted if math.isfinite(converted) else None


def _integer(value: Any) -> int | None:
    number = _finite(value)
    if number is None or number < 0:
        return None
    return int(number)


def _date_time(value: Any) -> str | None:
    if value is None:
        return None
    try:
        if hasattr(value, "isoformat"):
            return value.isoformat()
        converted = str(value)
        return converted if converted and converted.lower() not in ("nan", "nat", "none") else None
    except (TypeError, ValueError):
        return None


def option_rows(frame: Any, spot: float | None) -> tuple[list[dict], int, bool]:
    """Normalize without inventing absent bid/ask, greeks or market timestamps."""
    if frame is None or not hasattr(frame, "iterrows"):
        return [], 0, False
    rows = []
    for _, record in frame.iterrows():
        strike = _finite(record.get("strike"))
        if strike is None or strike <= 0:
            continue
        bid, ask = _finite(record.get("bid")), _finite(record.get("ask"))
        # Treat zero or crossed quotes as invalid, not a tradable midpoint.
        tradable_quote = bid is not None and ask is not None and bid > 0 and ask >= bid
        iv = _finite(record.get("impliedVolatility"))
        row = {
            "contract": str(record.get("contractSymbol") or "")[:80],
            "strike": strike,
            "bid": bid if tradable_quote else None,
            "ask": ask if tradable_quote else None,
            "last": _finite(record.get("lastPrice")),
            "volume": _integer(record.get("volume")),
            "open_interest": _integer(record.get("openInterest")),
            "iv": iv if iv is not None and iv > 0 else None,
            "last_trade_at": _date_time(record.get("lastTradeDate")),
            "in_the_money": bool(record.get("inTheMoney")) if record.get("inTheMoney") is not None else None,
            "quote_state": "valid_bid_ask" if tradable_quote else "no_valid_bid_ask",
        }
        rows.append(row)
    total = len(rows)
    if spot is not None and spot > 0:
        # Show contracts nearest underlying spot; expose truncation explicitly.
        rows.sort(key=lambda r: (abs(r["strike"] - spot), r["strike"], r["contract"]))
        rows = rows[:MAX_ROWS_PER_SIDE]
        rows.sort(key=lambda r: (r["strike"], r["contract"]))
    else:
        rows.sort(key=lambda r: (r["strike"], r["contract"]))
        rows = rows[:MAX_ROWS_PER_SIDE]
    return rows, total, total > MAX_ROWS_PER_SIDE


def _stock_last_close(ticker: Any) -> tuple[float | None, str | None]:
    """Return latest daily bar close, NOT a live underlying quote."""
    try:
        history = ticker.history(period="5d", interval="1d", auto_adjust=False)
        if history is None or history.empty:
            return None, None
        last = history.iloc[-1]
        close = _finite(last.get("Close"))
        observed_at = _date_time(history.index[-1])
        return close, observed_at
    except Exception:
        return None, None


def fetch_public_option_chain(symbol: str, expiry: str | None = None) -> dict[str, Any]:
    """Fetch an observation snapshot from unofficial public Yahoo APIs.

    No key or broker account. Fail closed when Yahoo omits the chain.
    """
    symbol, expiry = normalize_request(symbol, expiry)
    key = symbol, expiry
    now = time.monotonic()
    with _cache_lock:
        cached = _cache.get(key)
        if cached and now - cached[0] < CACHE_TTL_SECONDS:
            return dict(cached[1], from_cache=True)

    try:
        import yfinance as yf  # Optional, isolated from the original Futu engine.
    except ImportError as exc:
        raise MarketDataUnavailable("yfinance not installed; see standalone_web/requirements-marketdata.txt") from exc

    try:
        ticker = yf.Ticker(symbol)
        expirations = list(ticker.options or ())
    except Exception as exc:
        raise MarketDataUnavailable("Yahoo expiration list unavailable (network, throttling or symbol)") from exc
    if not expirations:
        raise MarketDataUnavailable("No US option expirations returned for this ticker; coverage unavailable")
    selected = expiry or expirations[0]
    if selected not in expirations:
        raise ValueError("Expiration not currently available for this ticker")

    try:
        chain = ticker.option_chain(selected)
        if chain is None or chain.calls is None or chain.puts is None:
            raise MarketDataUnavailable("Yahoo option chain response is incomplete")
        spot, spot_at = _stock_last_close(ticker)
        calls, total_calls, truncated_calls = option_rows(chain.calls, spot)
        puts, total_puts, truncated_puts = option_rows(chain.puts, spot)
        if not calls and not puts:
            raise MarketDataUnavailable("Option chain returned no valid contracts")
    except MarketDataUnavailable:
        raise
    except Exception as exc:
        raise MarketDataUnavailable("Yahoo option chain unavailable (network, throttling or missing fields)") from exc

    snapshot = {
        "provider": "Yahoo Finance via yfinance (unofficial)",
        "symbol": symbol,
        "market": "US",
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_delay": "unknown; not guaranteed live",
        "expiry": selected,
        "expirations": expirations,
        "spot_last_daily_close": spot,
        "spot_last_daily_bar_at": spot_at,
        "spot_kind": "historical_daily_close_not_live",
        "calls": calls,
        "puts": puts,
        "counts": {
            "calls_returned": len(calls), "puts_returned": len(puts),
            "calls_source": total_calls, "puts_source": total_puts,
            "calls_truncated": truncated_calls, "puts_truncated": truncated_puts,
        },
        "greeks_status": "not_available",  # No fabricated Delta/Theta/Gamma.
        "account_connected": False,
        "order_execution_enabled": False,
        "from_cache": False,
    }
    with _cache_lock:
        if len(_cache) >= 64:
            _cache.clear()
        _cache[key] = time.monotonic(), snapshot
    return snapshot
