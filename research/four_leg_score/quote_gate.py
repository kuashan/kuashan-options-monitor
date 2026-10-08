"""R1: quote-provenance gate for read-only four-leg option probability research.

This does not estimate probability, suggest trades, fetch data or change Web APIs.
The existing public yfinance observer lacks synchronized *quote* timestamps
and only supplies a daily underlying close: its output MUST fail this gate.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
from typing import Any, Mapping

from research.four_leg_score.engine import LEGS, MAX_OPTIONS_AGE, MAX_QUOTE_SKEW, MAX_SPOT_AGE

VERIFIED_SPOT_KIND = "verified_intraday_quote"


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _utc(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if result.utcoffset() is None:
        return None
    return result.astimezone(timezone.utc)


def assess_observation(
    snapshot: Mapping[str, Any], row: Mapping[str, Any], leg: str
) -> dict[str, Any]:
    """Classify data *eligibility*, never claim forecast accuracy.

    Expected in a potential future verified provider: snapshot.spot_current,
    spot_kind=verified_intraday_quote, spot_quote_at_utc, observed_at_utc;
    row.quote_at_utc, bid, ask, iv, strike. The actual Yahoo observer doesn't
    provide the extra quote facts and must not be auto-upgraded using
    last_trade_at or spot_last_daily_bar_at.
    """
    problems: list[str] = []
    if leg not in LEGS:
        raise ValueError("Unsupported leg")
    if not isinstance(snapshot, Mapping) or not isinstance(row, Mapping):
        raise TypeError("Snapshot and option row must be mappings")

    if snapshot.get("spot_kind") != VERIFIED_SPOT_KIND:
        problems.append("SPOT_NOT_VERIFIED_INTRADAY_QUOTE")
    spot = _number(snapshot.get("spot_current"))
    if spot is None or spot <= 0:
        problems.append("CURRENT_SPOT_MISSING")
    bid, ask, iv, strike = (_number(row.get(x)) for x in ("bid", "ask", "iv", "strike"))
    if bid is None or ask is None or bid <= 0 or ask < bid:
        problems.append("OPTION_BID_ASK_UNUSABLE")
    elif (ask - bid) / ((ask + bid) / 2) > 0.25:
        problems.append("OPTION_SPREAD_TOO_WIDE")
    if iv is None or iv <= 0 or iv > 10:
        problems.append("OPTION_IV_UNUSABLE")
    if strike is None or strike <= 0:
        problems.append("STRIKE_UNUSABLE")
    if not str(row.get("contract") or "").strip():
        problems.append("CONTRACT_ID_MISSING")
    if not str(snapshot.get("expiry") or "").strip():
        problems.append("EXPIRY_MISSING")

    received = _utc(snapshot.get("observed_at_utc"))
    underlying_at = _utc(snapshot.get("spot_quote_at_utc"))
    option_at = _utc(row.get("quote_at_utc"))
    if received is None:
        problems.append("OBSERVATION_TIME_MISSING_OR_INVALID")
    if underlying_at is None:
        problems.append("UNDERLYING_QUOTE_TIME_MISSING_OR_INVALID")
    if option_at is None:
        problems.append("OPTION_QUOTE_TIME_MISSING_OR_INVALID")
    if received is not None and underlying_at is not None:
        age = received - underlying_at
        if age < timedelta(0) or age > MAX_SPOT_AGE:
            problems.append("UNDERLYING_QUOTE_OUT_OF_WINDOW")
    if received is not None and option_at is not None:
        age = received - option_at
        if age < timedelta(0) or age > MAX_OPTIONS_AGE:
            problems.append("OPTION_QUOTE_OUT_OF_WINDOW")
    if underlying_at is not None and option_at is not None:
        if abs(underlying_at - option_at) > MAX_QUOTE_SKEW:
            problems.append("QUOTES_NOT_TIME_ALIGNED")

    # Distinguish readiness for a *theoretical* Q-model from empirical P
    # calibration, which cannot be inferred from any single fresh quote.
    ready = not problems
    return {
        "leg": leg,
        "quote_data_status": "THEORETICAL_INPUT_READY" if ready else "INSUFFICIENT",
        "quote_issues": problems,
        "theoretical_q_eligible": ready,
        "real_world_probability_calibrated": False,
        "actual_assignment_probability": None,
        "formal_opportunity_score_0_100": None,
        "formal_score_status": "PENDING_POINT_IN_TIME_HISTORY_AND_VALIDATION",
        "order_actions": [],
    }
