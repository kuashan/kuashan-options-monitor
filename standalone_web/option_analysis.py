"""Read-only four-leg V1 explanation and *uncalibrated* scenario reference scoring.

Precisely THREE score inputs: (1) favorable-vs-adverse payoff balance,
(2) survival of one adverse-price shock, (3) quoted bid/ask friction.
The combined score is their MINIMUM, not fitted weights. This is not an
empirical success probability, predicted return, execution signal or
cross-leg risk-adjusted performance. See OPTIONS_V1_FINAL.md.

No quote timestamps from Yahoo -> all scores are labelled INDICATIVE; the
formal historically calibrated opportunity score stays null. All other
features (IV, Greeks, OTM distance, momentum) are EXCLUDED from scoring.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import math
from typing import Any

from research.four_leg_score.engine import Snapshot, evaluate, expiry_payoff_per_share

MODEL = "V1_THREE_FACTOR_BOTTLENECK"
FEE_PER_SHARE = 0.01                # illustrative entry fee, not broker quote
RISK_FREE_RATE = 0.0                # illustrative only; NOT current yield curve
DIVIDEND_YIELD = 0.0                # illustrative only; NOT actual dividend forecast
FAVORABLE_MOVE = 0.10              # deterministic scenario, not a forecast
ADVERSE_MOVE = 0.20                # deterministic scenario, not a forecast
MAX_SPREAD_MID = 0.25              # research-only quality threshold
LEGS = ("long_call", "long_put", "short_call", "short_put")


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    v = float(value)
    return v if math.isfinite(v) else None


def _date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        d = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return d.astimezone(timezone.utc) if d.tzinfo else None
    except ValueError:
        return None


def _unavailable(leg: str, reason: str) -> dict[str, Any]:
    return {
        "leg": leg,
        "score_0_100": None,
        "score_status": "INPUT_BLOCKED",
        "score_reason": reason,
        "formal_opportunity_score_0_100": None,
        "actual_assignment_probability": None,
        "p_expiry_profit_q": None,
        "p_expiry_otm_q": None,
        "breakeven": None,
        "net_entry_per_share": None,
        "adverse_20pct_pnl_per_share": None,
        "favorable_10pct_pnl_per_share": None,
        "max_loss_per_share": None,
        "unbounded_max_loss": leg == "short_call",
        "score_factors": None,
        "order_actions": [],
    }


def analyze_option(
    leg: str,
    option: dict[str, Any],
    spot: float | None,
    expiry: str,
    observed_at_utc: str,
) -> dict[str, Any]:
    """Analyze a single public option without treating a daily close as live."""
    if leg not in LEGS:
        raise ValueError("unsupported leg")
    spot = _num(spot)
    strike = _num(option.get("strike"))
    bid = _num(option.get("bid"))
    ask = _num(option.get("ask"))
    iv = _num(option.get("iv"))
    observed = _time(observed_at_utc)
    expiration = _date(expiry)
    if observed is None or expiration is None:
        return _unavailable(leg, "缺少有效的抓取时间或到期日")
    # Calendar dates reflect expiration, not the actual precise 4pm ET
    # American-option exercise cutoff. Do not invent an intraday clock.
    dte = (expiration - observed.date()).days
    if dte <= 0:
        return _unavailable(leg, "到期日为今日或已过：不能使用日历日期假装剩余盘中时间")
    if spot is None or spot <= 0:
        return _unavailable(leg, "缺少有效的标的最近日线收盘价")
    if strike is None or strike <= 0 or bid is None or ask is None or bid <= 0 or ask < bid:
        return _unavailable(leg, "行权价或 Bid/Ask 双边报价无效")
    if iv is None or not (0 < iv <= 10):
        return _unavailable(leg, "IV 缺失或不合理")
    spread = (ask - bid) / ((ask + bid) / 2.0)
    if spread > MAX_SPREAD_MID:
        return _unavailable(leg, "Bid/Ask 价差超过 25%，不生成评分")
    if leg.startswith("short_") and bid <= FEE_PER_SHARE:
        return _unavailable(leg, "权利金不足以覆盖示意入场费用")

    x = Snapshot(
        leg=leg,
        underlying_price=spot,
        strike=strike,
        bid=bid,
        ask=ask,
        iv=iv,
        years_to_expiry=dte / 365.0,
        risk_free_rate=RISK_FREE_RATE,
        dividend_yield=DIVIDEND_YIELD,
        fee_per_share=FEE_PER_SHARE,
    )
    try:
        theory = evaluate(x)
        # The favorable/adverse scenarios are deliberately symmetrical
        # across the directional leg, and are NEVER assigned probabilities.
        favorable_up = leg in ("long_call", "short_put")
        favorable_spot = spot * (1 + FAVORABLE_MOVE if favorable_up else 1 - FAVORABLE_MOVE)
        adverse_spot = spot * (1 - ADVERSE_MOVE if favorable_up else 1 + ADVERSE_MOVE)
        favorable_pl = expiry_payoff_per_share(x, favorable_spot)
        adverse_pl = expiry_payoff_per_share(x, adverse_spot)
    except ValueError as exc:
        return _unavailable(leg, f"无法计算参考情景：{exc}")

    reward = max(favorable_pl, 0.0)
    bad_loss = max(-adverse_pl, 0.0)
    reward_balance = reward / (reward + bad_loss) if reward + bad_loss > 0 else 0.0
    stress_survival = max(0.0, 1.0 - bad_loss / (spot * ADVERSE_MOVE))
    liquidity = max(0.0, 1.0 - spread / MAX_SPREAD_MID)
    factors = {
        "reward_to_scenario_balance": round(reward_balance, 6),
        "adverse_20pct_survival": round(stress_survival, 6),
        "bid_ask_quality": round(liquidity, 6),
    }
    # No *finite* capital-risk denominator exists for an uncovered short
    # call, so do not present a numeric score as if its unlimited loss were capped.
    unbounded = leg == "short_call"
    score = None if unbounded else round(100 * min(factors.values()))
    net_entry = (ask + FEE_PER_SHARE) if leg.startswith("long_") else (bid - FEE_PER_SHARE)
    return {
        "leg": leg,
        "score_0_100": score,
        "score_status": (
            "UNBOUNDED_RISK_NO_COMPARABLE_SCORE" if unbounded
            else "UNCALIBRATED_RULE_REFERENCE_DAILY_CLOSE"
        ),
        "score_reason": (
            "裸卖 Call 理论亏损无上限；展示有限压力测试但不提供可比较分数"
            if unbounded else
            "仅以入场价差、10%有利情景与20%不利情景计算保守参考分；非胜率"
        ),
        "formal_opportunity_score_0_100": None,
        "actual_assignment_probability": None,
        "theoretical_measurement": "BLACK_SCHOLES_RISK_NEUTRAL_Q_NOT_REAL_WORLD",
        "p_expiry_profit_q": round(theory["p_expiry_profit_q"], 6),
        "p_expiry_otm_q": round(theory["p_expiry_otm_q"], 6),
        "breakeven": round(theory["breakeven"], 6),
        "net_entry_per_share": round(net_entry, 6),
        "entry_kind": "DEBIT" if leg.startswith("long_") else "CREDIT",
        "favorable_10pct_pnl_per_share": round(favorable_pl, 6),
        "adverse_20pct_pnl_per_share": round(adverse_pl, 6),
        "max_loss_per_share": theory["max_loss_per_share"],
        "unbounded_max_loss": unbounded,
        "spread_mid_ratio": round(spread, 6),
        "score_factors": factors,
        "assumptions": {
            "fee_per_share": FEE_PER_SHARE,
            "risk_free_rate": RISK_FREE_RATE,
            "dividend_yield": DIVIDEND_YIELD,
            "calendar_dte": dte,
            "spot_source": "LATEST_DAILY_BAR_NOT_SYNCHRONIZED_OR_LIVE",
            "option_quote_timestamp": "UNAVAILABLE",
            "scenarios_are_forecasts": False,
        },
        "order_actions": [],
    }


def analyze_chain(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Attach a research-only analysis to each call/put row, never mutate input."""
    if not isinstance(snapshot, dict):
        raise TypeError("snapshot must be a dict")
    result = dict(snapshot)
    for kind, legs in (
        ("calls", ("long_call", "short_call")),
        ("puts", ("long_put", "short_put")),
    ):
        result[kind] = []
        for option in snapshot.get(kind, []):
            row = dict(option)
            row["analyses"] = {
                leg: analyze_option(
                    leg, row, snapshot.get("spot_last_daily_close"),
                    str(snapshot.get("expiry") or ""),
                    str(snapshot.get("observed_at_utc") or ""),
                )
                for leg in legs
            }
            result[kind].append(row)
    result["model"] = {
        "name": MODEL,
        "score_kind": "UNCALIBRATED_SCENARIO_REFERENCE_NOT_EMPIRICAL_PROBABILITY",
        "formal_score_available": False,
        "retained_score_factors": [
            "favorable_vs_adverse_expiry_payoff_balance",
            "adverse_20pct_loss_vs_underlying_spot",
            "bid_ask_relative_spread",
        ],
        "excluded_from_score": [
            "delta_proxy", "iv_rank", "greeks_stacking", "20day_momentum",
            "naive_50_50_probability_blend", "unverified_assignment_probability",
        ],
        "risk_free_rate": RISK_FREE_RATE,
        "dividend_yield": DIVIDEND_YIELD,
        "illustrative_fee_per_share": FEE_PER_SHARE,
        "uses_synced_market_quotes": False,
        "requires_no_broker": True,
        "order_execution_enabled": False,
    }
    return result
