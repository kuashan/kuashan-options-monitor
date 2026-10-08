"""Minimal three-regime SPY EOD four-single-leg expiration-payoff study.

NO live market, broker, account, simulated option quotes, trading, score or model
fitting. Market-data origin / exact synchronized quote timestamps unverified.
Entry: observed ask for long, bid for short; terminal option intrinsic based on
underlying close (not actual exercise, assignment, or fill). Per-share units.
"""
from __future__ import annotations

from collections import defaultdict
import json
import math
from pathlib import Path
import statistics
import tempfile

import duckdb
from research.four_leg_score.github_data_pilot import fetch_verified, FILES

# Frozen upstream source SHA: 37f6c456fe1a4775c875673fb8ef907d5cd2fd66
FILES["spy/options_2022.parquet"] = (57_070_606, "f0a15b8263b7650147bfa62bce2cd44d59ef17a5")
FILES["spy/options_2023.parquet"] = (47_343_699, "ead8adeee0689d26e49f5b39f6d5536443931ac3")

YEARS = (2022, 2023, 2024)
DTE_MIN, DTE_MAX = 20, 45
IV_MIN, IV_MAX = 0.03, 2.0
MAX_SPREAD_MID = 0.25
STRIKE_BOUNDS = (0.85, 1.15)
FEE_PER_SHARE = 0.01  # purely illustrative: $1/100 shares, no fees for settlement
BUCKETS = ("ATM", "OTM_5PCT")
LEGS = ("long_call", "long_put", "short_call", "short_put")


def expiry_pl(leg: str, strike: float, terminal_spot: float, bid: float, ask: float,
              fee: float = FEE_PER_SHARE) -> float:
    if leg not in LEGS:
        raise ValueError("Unknown leg")
    if not all(math.isfinite(float(v)) for v in (strike,terminal_spot,bid,ask,fee)):
        raise ValueError("Invalid numbers")
    if strike <= 0 or terminal_spot < 0 or bid < 0 or ask < bid or fee < 0:
        raise ValueError("Invalid option payoff inputs")
    intrinsic = (max(terminal_spot-strike,0.0) if leg.endswith("call")
                 else max(strike-terminal_spot,0.0))
    return (intrinsic-ask-fee) if leg.startswith("long") else (bid-intrinsic-fee)


def _stats(observations: list[tuple[float, float, float, float]]) -> dict:
    """P/L, initial entry quote, strike and initial spot; NOT independent observations."""
    if not observations:
        return {"n":0}
    pl=sorted(x[0] for x in observations)
    n=len(pl)
    tail_size=max(1,math.ceil(n*0.05))
    def quantile(frac:float) -> float:
        return pl[int(round((n-1)*frac))]
    def fmt(x:float) -> float:
        return round(x,5)
    return {
        "n":n,
        "profit_frequency":fmt(sum(x>0 for x in pl)/n),
        "mean_pnl_per_underlying_share_usd":fmt(statistics.mean(pl)),
        "median_pnl":fmt(statistics.median(pl)),
        "p05_pnl":fmt(quantile(0.05)),
        "p95_pnl":fmt(quantile(0.95)),
        "worst_5pct_mean_pnl":fmt(statistics.mean(pl[:tail_size])),
        "observed_min_pnl":fmt(pl[0]),
        "observed_max_pnl":fmt(pl[-1]),
        "avg_entry_option_quote":fmt(statistics.mean(x[1] for x in observations)),
        "mean_strike":fmt(statistics.mean(x[2] for x in observations)),
        "mean_entry_spot":fmt(statistics.mean(x[3] for x in observations)),
    }


def run() -> None:
    with tempfile.TemporaryDirectory(prefix="spy-3regime-payoff-") as temp:
        root=Path(temp)
        underlying=root/"underlying_prices.parquet"
        fetch_verified("spy/underlying_prices.parquet",underlying)
        db=duckdb.connect(":memory:")
        db.execute(f"""CREATE VIEW underlying AS
            SELECT CAST("date" AS DATE) dt, CAST("close" AS DOUBLE) spot_close
            FROM read_parquet('{underlying.as_posix()}')""")
        results={}
        for year in YEARS:
            file=root/f"options_{year}.parquet"
            fetch_verified(f"spy/options_{year}.parquet",file)
            db.execute(f"CREATE OR REPLACE VIEW o AS SELECT * FROM read_parquet('{file.as_posix()}')")
            # first Wednesday of each month, frozen across years
            db.execute("""
              CREATE OR REPLACE TEMP TABLE selected_dates AS
              SELECT DATE_TRUNC('month', dt) month, MIN(dt) entry
              FROM (SELECT DISTINCT CAST("date" AS DATE) dt FROM o)
              WHERE EXTRACT(DOW FROM dt)=3 GROUP BY 1
            """)
            # Do all quote filtering BEFORE nearest-to-target selection to
            # avoid unavailable contracts being chosen. Two predeclared
            # moneyness buckets, one contract per entry x expiry x call/put.
            db.execute(f"""
              CREATE OR REPLACE TEMP TABLE eligible AS
              SELECT
                  CAST(o."date" AS DATE) entry,
                  CAST(o.expiration AS DATE) expiry,
                  LOWER(CAST(o."type" AS VARCHAR)) side,
                  CAST(o.contract_id AS VARCHAR) contract_id,
                  CAST(o.strike AS DOUBLE) strike,
                  CAST(o.bid AS DOUBLE) bid,
                  CAST(o.ask AS DOUBLE) ask,
                  CAST(o.implied_volatility AS DOUBLE) iv,
                  CAST(u.spot_close AS DOUBLE) spot,
                  DATE_DIFF('day', CAST(o."date" AS DATE), CAST(o.expiration AS DATE)) dte
              FROM o
              JOIN selected_dates d ON CAST(o."date" AS DATE)=d.entry
              JOIN underlying u ON u.dt=CAST(o."date" AS DATE)
              WHERE DATE_DIFF('day',CAST(o."date" AS DATE),CAST(o.expiration AS DATE))
                      BETWEEN {DTE_MIN} AND {DTE_MAX}
                AND CAST(o.expiration AS DATE) <= DATE '{year}-12-31'
                AND LOWER(CAST(o."type" AS VARCHAR)) IN ('call','put')
                AND u.spot_close > 0
                AND o.strike BETWEEN u.spot_close * {STRIKE_BOUNDS[0]} AND u.spot_close * {STRIKE_BOUNDS[1]}
                AND o.bid > 0 AND o.ask >= o.bid
                AND (o.ask-o.bid)/((o.ask+o.bid)/2) <= {MAX_SPREAD_MID}
                AND o.implied_volatility BETWEEN {IV_MIN} AND {IV_MAX}
                AND isfinite(o.implied_volatility)
            """)
            db.execute("""
              CREATE OR REPLACE TEMP TABLE selected AS
              WITH targets AS (
                SELECT e.*, b.bucket,
                       CASE WHEN b.bucket = 'ATM' THEN e.spot
                            WHEN e.side='call' THEN e.spot*1.05
                            ELSE e.spot*0.95 END target_strike
                FROM eligible e
                CROSS JOIN (VALUES ('ATM'),('OTM_5PCT')) AS b(bucket)
              ), rank_selection AS (
                SELECT *,
                       ABS(strike-target_strike)/spot AS target_gap,
                       ROW_NUMBER() OVER(
                         PARTITION BY entry,expiry,side,bucket
                         ORDER BY ABS(strike-target_strike),strike,contract_id
                       ) choice
                FROM targets
              )
              SELECT * FROM rank_selection
              WHERE choice=1
                AND (bucket = 'ATM' AND target_gap <=0.01
                     OR bucket='OTM_5PCT' AND target_gap<=0.02)
            """)
            # Use expiration-date underlying CLOSE as a **proxy** for
            # settlement, not option settlement or American exercise.
            rows=db.execute("""
              WITH ending AS (
                SELECT e.expiry,
                       MAX_BY(u.spot_close,u.dt) final_spot,
                       MAX(u.dt) final_day
                FROM (SELECT DISTINCT expiry FROM selected) e
                LEFT JOIN underlying u
                  ON u.dt BETWEEN e.expiry-INTERVAL '4 days' AND e.expiry
                GROUP BY e.expiry
              )
              SELECT e.entry,e.expiry,e.side,e.bucket,e.contract_id,
                     e.strike,e.bid,e.ask,e.spot,x.final_spot,x.final_day
              FROM selected e
              JOIN ending x ON x.expiry=e.expiry
              WHERE x.final_spot IS NOT NULL AND x.final_spot>0
            """).fetchall()
            seen=set()
            groups=defaultdict(list)
            dates=set()
            expiries=set()
            bad_dupes=0
            terminal_lags=defaultdict(int)
            for entry,expiry,side,bucket,contract,strike,bid,ask,spot,final_spot,final_day in rows:
                identity=(entry,expiry,side,bucket)
                if identity in seen:
                    bad_dupes+=1
                seen.add(identity)
                dates.add(str(entry));expiries.add(str(expiry))
                terminal_lags[(expiry-final_day).days]+=1
                for leg in ("long_"+side,"short_"+side):
                    price=ask if leg.startswith("long") else bid
                    pl=expiry_pl(leg,strike,final_spot,bid,ask)
                    groups[(bucket,leg)].append((pl,price,strike,spot))
            if bad_dupes:
                raise AssertionError(f"Duplicated candidate group count {bad_dupes}")
            if len(dates)<8 or len(rows)<80 or any(
                len(groups[(bucket,leg)])<10 for bucket in BUCKETS for leg in LEGS
            ):
                raise AssertionError(f"Insufficient data year={year}; dates={len(dates)} rows={len(rows)}")
            all_bucket={}
            for bucket in BUCKETS:
                all_bucket[bucket]={}
                for leg in LEGS:
                    all_bucket[bucket][leg]=_stats(groups[(bucket,leg)])
                # Synthetic payoff identities for paired long/short same
                # contract: their sum is always -(ask-bid)-2*fee.
                for side in ("call","put"):
                    lo=groups[(bucket,"long_"+side)]
                    sh=groups[(bucket,"short_"+side)]
                    for (lp,lquote,_,_),(sp,squote,_,_) in zip(lo,sh):
                        if abs(lp+sp-((squote-lquote)-2*FEE_PER_SHARE))>1e-8:
                            raise AssertionError("Long/short per-contract P/L conservation failed")
            result={
                "year":year,"entry_dates":len(dates),"expiry_dates":len(expiries),
                "call_and_put_contract_records":len(rows),
                "bucket_counts":{bucket:len(groups[(bucket,"long_call")])+len(groups[(bucket,"long_put")]) for bucket in BUCKETS},
                "last_spot_proxy_lag_days":dict(sorted(terminal_lags.items())),
                "groups":all_bucket,
            }
            results[str(year)]=result
            print("EOD_PAYOFF_YEAR_JSON="+json.dumps(result,ensure_ascii=False),flush=True)
            del file
        final={
            "research":"SPY_2022_2023_2024_FIRST_WEDNESDAY_FOUR_LEGS_TWO_PREDECLARED_MONEYNESS_BUCKETS",
            "status":"EOD_PAYOFF_PROXY_NOT_ACTUAL_FILLED_TRADES",
            "source_repo":"anahatsingh-ui/options-dataset-hist",
            "source_commit":"37f6c456fe1a4775c875673fb8ef907d5cd2fd66",
            "fees_per_underlying_share_usd":FEE_PER_SHARE,
            "fee_model":"one illustrative entry fee only; no early close/exercise/assignment/financing/slippage beyond quoted spread",
            "quote_selection":"buy at ask; sell at bid, NOT mid",
            "option_settlement":"intrinsic at last underlying close <= expiry within four calendar days",
            "no_intraday_quote_timestamps":True,
            "source_feed_not_independently_verified":True,
            "broker_assignments_not_observed":True,
            "payoffs_are_correlated_not_independent_trials":True,
            "theoretical_short_call_max_loss":"UNBOUNDED",
            "theoretical_short_put_max_loss":"strike minus net entry credit per underlying share",
            "no_formal_score_or_factor_fit":True,
            "year_results":results,
        }
        Path("spy_three_regime_payoff_result.json").write_text(
            json.dumps(final,indent=2,ensure_ascii=False),encoding="utf-8"
        )
        print("SPY_THREE_REGIME_PAYOFF_PILOT_COMPLETE",flush=True)


if __name__=="__main__":
    run()
