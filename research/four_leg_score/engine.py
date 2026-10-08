"""Four single-leg options: original, broker-free **research** calculation kernel.

Inputs are explicit assumptions, never silently fetched. No orders, no broker access,
no claims that market-implied risk-neutral probabilities are real-world forecasts.

The final 0-100 opportunity score is intentionally withheld until historical,
out-of-sample calibration exists. See AUDIT_AND_SCORE_SPEC.md.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import math
from typing import Literal

Leg = Literal["long_call", "long_put", "short_call", "short_put"]
LEGS: frozenset[str] = frozenset(("long_call", "long_put", "short_call", "short_put"))
MAX_SPOT_AGE = timedelta(minutes=30)  # research-only data-quality gate
MAX_OPTIONS_AGE = timedelta(minutes=30)
MAX_QUOTE_SKEW = timedelta(minutes=15)


@dataclass(frozen=True)
class Snapshot:
    leg: Leg
    underlying_price: float
    strike: float
    bid: float
    ask: float
    iv: float  # decimal annualized, e.g. 0.30 for 30%
    years_to_expiry: float
    risk_free_rate: float  # explicit decimal annualized
    dividend_yield: float  # explicit decimal continuous dividend yield
    fee_per_share: float = 0.0  # explicit assumed cash cost per underlying unit
    observed_at_utc: datetime | None = None
    underlying_quote_at_utc: datetime | None = None
    option_quote_at_utc: datetime | None = None
    # Last-trade timestamp is NOT a quote snapshot timestamp.
    verified_share_cover: bool = False


def norm_cdf(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def _valid_number(name: str, value: float, *, lower: float | None = None) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite numeric")
    if lower is not None and value < lower:
        raise ValueError(f"{name} must be >= {lower}")


def _ensure_inputs(x: Snapshot) -> None:
    if x.leg not in LEGS:
        raise ValueError("Leg must be one of the four supported single-leg types")
    for name in ("underlying_price", "strike", "bid", "ask", "iv", "years_to_expiry",
                 "risk_free_rate", "dividend_yield", "fee_per_share"):
        _valid_number(name, getattr(x, name))
    if x.underlying_price <= 0 or x.strike <= 0 or x.iv <= 0 or x.years_to_expiry <= 0:
        raise ValueError("Positive underlying, strike, IV and remaining time required")
    if x.iv > 10 or x.years_to_expiry > 15:
        raise ValueError("IV or time outside model guardrail")
    if not (-0.25 <= x.risk_free_rate <= 1) or not (-0.25 <= x.dividend_yield <= 1):
        raise ValueError("Rate/yield outside explicit guardrail")
    if x.bid < 0 or x.ask <= 0 or x.bid > x.ask or x.fee_per_share < 0:
        raise ValueError("Missing/crossed option market, or negative fees")
    if x.leg.startswith("short_") and x.bid <= x.fee_per_share:
        raise ValueError("No positive net short credit at executable bid")
    if x.leg.startswith("long_") and x.ask + x.fee_per_share <= 0:
        raise ValueError("No executable long option ask")
    if x.leg == "short_put" and x.bid - x.fee_per_share >= x.strike:
        raise ValueError("Put net credit >= strike; invalid payoff evidence")
    for name in ("observed_at_utc", "underlying_quote_at_utc", "option_quote_at_utc"):
        value = getattr(x, name)
        if value is not None and (not isinstance(value, datetime) or
                                  value.utcoffset() is None):
            raise ValueError(f"{name} must be timezone-aware when provided")


def d2_at(x: Snapshot, threshold: float) -> float:
    """BS risk-neutral terminal CDF threshold, NOT an objective forecast."""
    if threshold <= 0:
        return math.inf
    voltime = x.iv * math.sqrt(x.years_to_expiry)
    return (
        math.log(x.underlying_price / threshold)
        + (x.risk_free_rate - x.dividend_yield - 0.5 * x.iv**2) * x.years_to_expiry
    ) / voltime


def probability_above(x: Snapshot, threshold: float) -> float:
    if threshold <= 0:
        return 1.0
    return norm_cdf(d2_at(x, threshold))


def _quality(x: Snapshot) -> tuple[str, list[str]]:
    issues: list[str] = []
    if x.observed_at_utc is None or x.underlying_quote_at_utc is None or x.option_quote_at_utc is None:
        issues.append("MISSING_SYNCHRONIZED_QUOTE_TIMESTAMPS")
    else:
        u_age = x.observed_at_utc - x.underlying_quote_at_utc
        o_age = x.observed_at_utc - x.option_quote_at_utc
        if u_age < timedelta(0) or o_age < timedelta(0):
            issues.append("QUOTE_TIMESTAMP_IN_FUTURE")
        if u_age > MAX_SPOT_AGE or o_age > MAX_OPTIONS_AGE:
            issues.append("STALE_UNDERLYING_OR_OPTION_QUOTE")
        if abs(x.underlying_quote_at_utc - x.option_quote_at_utc) > MAX_QUOTE_SKEW:
            issues.append("UNSYNCHRONIZED_QUOTES")
    if x.bid == 0:
        issues.append("ZERO_BID")
    spread = (x.ask - x.bid) / ((x.ask + x.bid) / 2)
    if spread > 0.25:
        issues.append("WIDE_SPREAD_OVER_25_PERCENT")
    if x.leg == "short_call" and not x.verified_share_cover:
        issues.append("SHORT_CALL_UNCOVERED_UNBOUNDED_LOSS")
    return ("QUALITY_CHECK" if issues else "TIMESTAMP_CHECK_PASS", issues)


def expiry_payoff_per_share(x: Snapshot, terminal_spot: float) -> float:
    """Underlying-unit P/L at expiration, based on executable entry bid/ask."""
    _ensure_inputs(x)
    _valid_number("terminal_spot", terminal_spot, lower=0)
    option_type = "call" if x.leg.endswith("call") else "put"
    intrinsic = max(terminal_spot - x.strike, 0.0) if option_type == "call" else max(x.strike - terminal_spot, 0.0)
    if x.leg.startswith("long_"):
        return intrinsic - (x.ask + x.fee_per_share)
    return (x.bid - x.fee_per_share) - intrinsic


def evaluate(x: Snapshot) -> dict:
    """Expose separate pricing probability, payout/risk and verification status.

    Do not output final score/probability-of-no-assignment: both would imply
    empirical validation or an American-exercise model that is not present.
    """
    _ensure_inputs(x)
    is_call = x.leg.endswith("call")
    is_long = x.leg.startswith("long_")
    entry_cash = (x.ask + x.fee_per_share) if is_long else (x.bid - x.fee_per_share)
    breakeven = (
        x.strike + entry_cash if (is_call == is_long)
        else x.strike - entry_cash
    )
    # long call: K+debit; long put: K-debit
    # short call: K+credit; short put: K-credit
    if x.leg == "short_call":
        breakeven = x.strike + entry_cash
    if x.leg == "short_put":
        breakeven = x.strike - entry_cash

    p_above_strike = probability_above(x, x.strike)
    p_itm = p_above_strike if is_call else 1 - p_above_strike
    # Profit domain is above breakeven for long calls & short puts,
    # below breakeven for long puts & short calls.
    p_above_breakeven = probability_above(x, breakeven)
    profit_when_above = x.leg in ("long_call", "short_put")
    p_profit = p_above_breakeven if profit_when_above else 1 - p_above_breakeven

    if is_long:
        max_loss = entry_cash
        max_profit = math.inf if is_call else x.strike - entry_cash
    else:
        max_profit = entry_cash
        max_loss = math.inf if is_call else x.strike - entry_cash

    quality, issues = _quality(x)
    return {
        "leg": x.leg,
        "measurement": "BLACK_SCHOLES_RISK_NEUTRAL_NOT_REAL_WORLD",
        "model_status": "THEORETICAL_ONLY",
        "p_expiry_itm_q": p_itm,
        "p_expiry_otm_q": 1 - p_itm,
        "p_expiry_profit_q": p_profit,
        "breakeven": breakeven,
        "entry_credit_per_share": entry_cash if not is_long else None,
        "entry_debit_per_share": entry_cash if is_long else None,
        "max_gain_per_share": max_profit if math.isfinite(max_profit) else None,
        "max_loss_per_share": max_loss if math.isfinite(max_loss) else None,
        "unbounded_upside_gain": is_long and is_call,
        "unbounded_upside_loss": not is_long and is_call,
        "short_call_covered_assumption": x.verified_share_cover if x.leg == "short_call" else None,
        "quote_quality_state": quality,
        "data_warnings": issues,
        "risk_of_touch": None,
        "actual_assignment_probability": None,
        "real_world_probability_calibrated": False,
        "opportunity_score_0_100": None,
        "score_status": "PENDING_OUT_OF_SAMPLE_CALIBRATION",
        "order_actions": [],
    }
