"""Frozen 2022 vs 2024 SPY EOD OTM comparison: BS-Q, Delta, pre-fixed 50/50 blend.

12 first-Wednesday entry snapshots per year. No parameter fitting, no P/L, exercise,
or real-world assignment. Historical market provenance and quote timestamps
remain unverified. The score used here is a proper forecast diagnostic
(Brier loss), never an opportunity recommendation score.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
import json
import math
from pathlib import Path
import tempfile

import duckdb
from research.four_leg_score.github_data_pilot import fetch_verified, FILES

# Upstream 2022 Git blob verified by SHA after download; 2024 remains pinned as before.
FILES["spy/options_2022.parquet"] = (57_070_606, "f0a15b8263b7650147bfa62bce2cd44d59ef17a5")

RATE = 0.04  # same frozen illustrative rate for BOTH years; historical yield curves not represented
DIVIDEND = 0.01  # fixed illustrative continuous dividend yield
IV_MIN, IV_MAX = 0.03, 2.0
DTE_MIN, DTE_MAX = 20, 45
MAX_SPREAD_RATIO = 0.25
MONEYNESS_MIN, MONEYNESS_MAX = 0.85, 1.15


def cdf(x: float) -> float:
    return math.erfc(-x / math.sqrt(2)) / 2


def bs_otm_prob(spot: float, strike: float, dte: int, iv: float, side: str, rate: float = RATE) -> float:
    t = dte / 365
    d2 = (math.log(spot / strike) + (rate - DIVIDEND - iv * iv / 2) * t) / (iv * math.sqrt(t))
    return cdf(d2) if side == "put" else cdf(-d2)


def _summary(data: list[tuple[float, float, str, str]], limit: int = 0) -> dict:
    if not data:
        return {"count": 0}
    n = len(data)
    pred = sum(x[0] for x in data) / n
    realized = sum(x[1] for x in data) / n
    brier = sum((x[0] - x[1]) ** 2 for x in data) / n
    months = {}
    groups = defaultdict(list)
    for row in data:
        groups[row[3]].append(row)
    for month, values in sorted(groups.items()):
        months[month] = {
            "n": len(values),
            "brier": round(sum((p - y) ** 2 for p, y, _, _ in values) / len(values), 6),
            "realized": round(sum(y for _, y, _, _ in values) / len(values), 5),
        }
    bins = []
    for lo, hi in ((0.0,0.1),(0.1,0.2),(0.2,0.3),(0.3,0.4),(0.4,0.5),
                   (0.5,0.6),(0.6,0.7),(0.7,0.8),(0.8,0.9),(0.9,1.0)):
        sample = [x for x in data if lo <= x[0] < hi or hi == 1.0 and x[0] == 1.0]
        bins.append({
            "range": f"{lo:.1f}-{hi:.1f}",
            "count": len(sample),
            "predicted": round(sum(x[0] for x in sample) / len(sample), 5) if sample else None,
            "actual_otm": round(sum(x[1] for x in sample) / len(sample), 5) if sample else None,
        })
    return {"count": n, "avg_predicted": round(pred, 6), "actual_otm_rate": round(realized, 6),
            "brier": round(brier, 6), "months": months, "bins": bins}


def run_year(year: int) -> None:
    assert year in (2022, 2024)
    with tempfile.TemporaryDirectory(prefix=f"spy-{year}-cal-") as temp:
        root = Path(temp)
        opt, under = root / f"options_{year}.parquet", root / "underlying_prices.parquet"
        fetch_verified(f"spy/options_{year}.parquet", opt)
        fetch_verified("spy/underlying_prices.parquet", under)
        db = duckdb.connect(":memory:")
        db.execute(f"CREATE VIEW options AS SELECT * FROM read_parquet('{opt.as_posix()}')")
        db.execute(f"CREATE VIEW stock AS SELECT CAST(\"date\" AS DATE) AS dt, CAST(close AS DOUBLE) AS close FROM read_parquet('{under.as_posix()}')")
        # The archive's 4:00 PM daily snapshot time is a *claim* without per-row quote timestamps.
        # Capture suspicious mechanical templating before any inference.
        diagnostics = db.execute("""
          SELECT
            COUNT(*) AS count,
            COUNT(DISTINCT contract_id) AS distinct_contracts,
            COUNT(DISTINCT "date") AS unique_dates,
            APPROX_QUANTILE(implied_volatility, [0.01, 0.50, 0.99]) AS iv_quantiles,
            APPROX_QUANTILE(CAST(volume AS DOUBLE), [0.10, 0.50, 0.90]) AS volume_quantiles,
            COUNT(*) FILTER (WHERE bid <= 0 OR ask <= 0 OR ask < bid) AS invalid_quotes,
            COUNT(*) FILTER (WHERE implied_volatility > 2) AS extremely_high_iv,
            COUNT(*) FILTER (WHERE bid > 0 AND ask >= bid AND ask-bid < 0.00001) AS zero_spread,
            COUNT(*) FILTER (WHERE "date" = expiration) AS same_day_expiry
          FROM options
        """).fetchone()
        print(f"INPUT_DIAGNOSTICS_YEAR_{year}="+json.dumps({
            "rows": diagnostics[0], "contracts": diagnostics[1], "dates": diagnostics[2],
            "iv_q_01_50_99": diagnostics[3], "vol_q_10_50_90": diagnostics[4],
            "invalid_quote": diagnostics[5], "high_iv_gt_2": diagnostics[6],
            "zero_spread": diagnostics[7], "zero_dte_rows": diagnostics[8],
        }), flush=True)
        db.execute("""
          CREATE TEMP TABLE selected_dates AS
          SELECT DATE_TRUNC('month', dt) AS month, MIN(dt) AS entry_date
          FROM (SELECT DISTINCT CAST("date" AS DATE) AS dt FROM options)
          WHERE EXTRACT(DOW FROM dt) = 3
          GROUP BY 1
        """)
        # Same-day stock close matched on date. Outcomes restricted to expiries in 2024,
        # and use latest stock close at/before expiration (<=4 calendar days).
        db.execute(f"""
          CREATE TEMP TABLE selected AS
          SELECT
            CAST(o."date" AS DATE) AS entry_date,
            CAST(o.expiration AS DATE) AS expiry,
            CAST(o."type" AS VARCHAR) AS side,
            CAST(o.strike AS DOUBLE) AS strike,
            CAST(o.bid AS DOUBLE) AS bid,
            CAST(o.ask AS DOUBLE) AS ask,
            CAST(o.implied_volatility AS DOUBLE) AS iv,
            CAST(o.delta AS DOUBLE) AS delta,
            CAST(s.close AS DOUBLE) AS spot,
            DATE_DIFF('day', CAST(o."date" AS DATE), CAST(o.expiration AS DATE)) AS dte
          FROM options o
          JOIN selected_dates d ON CAST(o."date" AS DATE) = d.entry_date
          JOIN stock s ON s.dt = CAST(o."date" AS DATE)
          WHERE LOWER(CAST(o."type" AS VARCHAR)) IN ('call','put')
            AND CAST(o.expiration AS DATE) <= DATE '{year}-12-31'
            AND DATE_DIFF('day', CAST(o."date" AS DATE), CAST(o.expiration AS DATE)) BETWEEN 20 AND 45
        """)
        db.execute("""
          CREATE TEMP TABLE terminal AS
          SELECT e.expiry, MAX_BY(s.close, s.dt) AS expiry_spot, MAX(s.dt) AS outcome_day
          FROM (SELECT DISTINCT expiry FROM selected) e
          LEFT JOIN stock s
            ON s.dt BETWEEN e.expiry - INTERVAL '4 days' AND e.expiry
          GROUP BY e.expiry
        """)
        total = db.execute("SELECT COUNT(*) FROM selected").fetchone()[0]
        excluded_missing_entry = db.execute("SELECT COUNT(*) FROM selected WHERE spot IS NULL OR spot <= 0").fetchone()[0]
        excluded_missing_outcome = db.execute("""
          SELECT COUNT(*) FROM selected a LEFT JOIN terminal t ON a.expiry = t.expiry
          WHERE t.expiry_spot IS NULL OR t.expiry_spot <= 0
        """).fetchone()[0]
        # No hidden IV scale conversion. IV in decimal as documented; impossible values excluded.
        rows = db.execute("""
          SELECT a.entry_date, a.expiry, a.side, a.strike, a.bid, a.ask, a.iv,
                 a.delta, a.spot, a.dte, t.expiry_spot, t.outcome_day
          FROM selected a
          JOIN terminal t ON a.expiry = t.expiry
          WHERE a.spot > 0 AND t.expiry_spot > 0
            AND a.strike BETWEEN a.spot * ? AND a.spot * ?
            AND a.bid > 0 AND a.ask >= a.bid
            AND (a.ask - a.bid) / ((a.ask + a.bid)/2) <= ?
            AND a.iv BETWEEN ? AND ?
            AND isfinite(a.iv) AND isfinite(a.delta)
        """, [MONEYNESS_MIN, MONEYNESS_MAX, MAX_SPREAD_RATIO, IV_MIN, IV_MAX]).fetchall()
        metrics = defaultdict(lambda: {"bs": [], "delta": [], "blend": [], "bs_zero_rate": []})
        dates: set[str] = set()
        expiries: set[str] = set()
        counts = defaultdict(int)
        for entry, expiry, side, strike, bid, ask, iv, delta, spot, dte, s_terminal, outcome_day in rows:
            side = side.lower()
            # Half-close convention: equality on strike is economically ATM, not OTM.
            if s_terminal == strike:
                counts["exact_atm_outcome_excluded"] += 1
                continue
            actual_otm = float(s_terminal > strike) if side == "put" else float(s_terminal < strike)
            p = bs_otm_prob(spot, strike, dte, iv, side)
            p_delta = max(0., min(1., 1.-abs(delta)))
            month = str(entry)[:7]
            dates.add(str(entry)); expiries.add(str(expiry))
            metrics[side]["bs"].append((p, actual_otm, side, month))
            metrics[side]["delta"].append((p_delta, actual_otm, side, month))
            # One pre-specified simple combination, no coefficient training or tuning.
            metrics[side]["blend"].append(((p+p_delta)/2,actual_otm,side,month))
            metrics[side]["bs_zero_rate"].append((bs_otm_prob(spot,strike,dte,iv,side,0.),actual_otm,side,month))
            counts["rows_used"] += 1
        report = {
            "experiment": f"SPY_{year}_EOD_OTM_Q_AND_FIXED_HALF_BLEND_NO_TRAINING",
            "year": year,
            "data_citation": "anahatsingh-ui/options-dataset-hist 37f6c456fe1a4775c875673fb8ef907d5cd2fd66",
            "quotes_verified_exact_timestamp": False,
            "original_market_feed_independently_proven": False,
            "sample_days_method": f"first trading Wednesday each month; 20-45 calendar DTE; expiry <={year}-12-31",
            "observations_not_independent_due_to_shared_underlying_and_expiry": True,
            "stock_expiry_close_proxy_not_actual_assignment_or_exercise_record": True,
            "stock_expiry_close_may_differ_from_option_settlement_value": True,
            "model": "Black-Scholes risk-neutral Q, per-row IV decimal; r=0.04 q=0.01 same illustrative both years; delta from archive; 0-rate sensitivity; fixed 50/50 ensemble diagnostic",
            "missing_historical_interest_dividend_curves": True,
            "filters": {"bid_gt":0, "spread_pct_max":25, "iv_range":[IV_MIN,IV_MAX], "strike_vs_spot":[MONEYNESS_MIN,MONEYNESS_MAX]},
            "before_filters_rows": total,
            "after_filters_rows": counts["rows_used"],
            "entry_dates": len(dates), "expiry_dates":len(expiries),
            "missing_entry":excluded_missing_entry, "missing_outcome":excluded_missing_outcome,
            "excluded_exact_atm":counts["exact_atm_outcome_excluded"],
            "call":{k:_summary(v) for k,v in metrics["call"].items()},
            "put":{k:_summary(v) for k,v in metrics["put"].items()},
            "no_real_world_calibration_claim": True,
            "no_assignment_probability_claim": True,
            "no_opportunity_score": True,
        }
        (Path.cwd() / f"spy_{year}_calibration_compare.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"CALIBRATION_PILOT_JSON_YEAR_{year}="+json.dumps({
            "rows_pre":total, "rows_post":counts["rows_used"],
            "entry_dates":len(dates), "expiry_dates":len(expiries),
            "call":{k:{a:v[a] for a in ("count","avg_predicted","actual_otm_rate","brier")} for k,v in metrics["call"] and {k:_summary(v) for k,v in metrics["call"].items()}.items()},
            "put":{k:{a:v[a] for a in ("count","avg_predicted","actual_otm_rate","brier")} for k,v in metrics["put"] and {k:_summary(v) for k,v in metrics["put"].items()}.items()},
        },sort_keys=True),flush=True)
        print(f"HIGH_CONFIDENCE_BINS_JSON_YEAR_{year}="+json.dumps({
            side: [b for b in report[side]["bs"]["bins"] if b["range"] in ("0.8-0.9","0.9-1.0")]
            for side in ("call","put")
        },sort_keys=True),flush=True)
        print(f"MONTHLY_BRIER_JSON_YEAR_{year}="+json.dumps({
            side: {"bs": report[side]["bs"]["months"],"delta": report[side]["delta"]["months"], "blend": report[side]["blend"]["months"]}
            for side in ("call","put")
        },sort_keys=True),flush=True)
        if len(dates) < 8 or counts["rows_used"] < 100:
            raise AssertionError("Not enough filtered option observations to draw even pilot diagnostics")
        print(f"SPY_{year}_CALIBRATION_COMPARISON_PASS_NO_FORMAL_SCORE",flush=True)


if __name__ == "__main__":
    for year in (2022, 2024):
        run_year(year)
    print("TWO_YEAR_FROZEN_BASELINES_COMPLETE_NO_TRAINING",flush=True)
