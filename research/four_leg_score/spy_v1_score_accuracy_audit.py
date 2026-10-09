"""Frozen V1 score on historical SPY 2022-25: audit, never tune.

Ranks paired *same-date same-expiry same-side* ATM vs 5%-OTM.
Calculations are EXACTLY the current V1 analyze_option() and expiry_payoff_per_share()
on archived actual Parquet quote fields. No lookahead features.
Outcome is a stock-close intrinsic-value proxy, NOT exercise / live fills.

IMPORTANT: 2025 appeared in prior factor research; it is not a blind holdout
for model selection. Score is NOT a probability, so no "score accuracy as %".
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
import json
import math
from pathlib import Path
import statistics
import tempfile

import duckdb

from research.four_leg_score.github_data_pilot import FILES, fetch_verified
from research.four_leg_score.engine import Snapshot, expiry_payoff_per_share
from standalone_web.option_analysis import (
    analyze_option, FEE_PER_SHARE, RISK_FREE_RATE, DIVIDEND_YIELD,
)

FILES.update({
    "spy/options_2022.parquet": (57_070_606, "f0a15b8263b7650147bfa62bce2cd44d59ef17a5"),
    "spy/options_2023.parquet": (47_343_699, "ead8adeee0689d26e49f5b39f6d5536443931ac3"),
    "spy/options_2025.parquet": (58_216_546, "133bf1d95c3479149bf4771bc8b3fd8b625064ce"),
})
YEARS = (2022, 2023, 2024, 2025)
LEGS = ("long_call", "long_put", "short_call", "short_put")
BUCKETS = ("ATM", "OTM_5PCT")


def _mean(xs):
    return round(statistics.mean(xs), 6) if xs else None


def _tail(xs):
    if not xs:
        return None
    n = max(1, math.ceil(len(xs)*0.05))
    return _mean(sorted(xs)[:n])


def _metrics(rows):
    """rows: [(score-or-None, pnl, normalized pnl, Q-theoretical p)]"""
    if not rows:
        return {"n": 0}
    valid_scores = [r[0] for r in rows if isinstance(r[0], int)]
    normalized = [r[2] for r in rows if r[2] is not None]
    return {
        "n": len(rows),
        "n_with_score": len(valid_scores),
        "n_score_zero": sum(s == 0 for s in valid_scores),
        "avg_score": _mean(valid_scores),
        "win_rate": _mean([int(r[1]>0) for r in rows]),
        "avg_pnl_usd_per_underlying_share": _mean([r[1] for r in rows]),
        "worst_5pct_pnl_usd_per_share": _tail([r[1] for r in rows]),
        "avg_normalized_pnl": _mean(normalized),
        "worst_5pct_normalized_pnl": _tail(normalized),
        "q_profit_brier": _mean([(r[3] - int(r[1]>0))**2 for r in rows if r[3] is not None]),
        "q_profit_mean": _mean([r[3] for r in rows if r[3] is not None]),
    }


def evaluate_pair(atm, otm, leg):
    """Both are (score, pnl, normalized P/L, probability Q), no future data used for picking."""
    a,b=atm[0],otm[0]
    if not isinstance(a,int) or not isinstance(b,int):
        return "BLOCKED", None
    if a == b:
        return "TIED", None
    high,low = (atm,otm) if a>b else (otm,atm)
    return "RANKED", (high,low)


def run():
    result={}
    with tempfile.TemporaryDirectory(prefix="frozen-v1-spy-accuracy-") as folder:
        root=Path(folder)
        px=root/"underlying_prices.parquet"
        fetch_verified("spy/underlying_prices.parquet",px)
        db=duckdb.connect(":memory:")
        db.execute(f"""CREATE VIEW u AS SELECT CAST("date" AS DATE) dt,
                     CAST("close" AS DOUBLE) spot FROM read_parquet('{px.as_posix()}')""")

        for year in YEARS:
            opt=root/f"options_{year}.parquet"
            fetch_verified(f"spy/options_{year}.parquet",opt)
            db.execute(f"CREATE OR REPLACE VIEW o AS SELECT * FROM read_parquet('{opt.as_posix()}')")
            db.execute("""
              CREATE OR REPLACE TEMP TABLE entry_dates AS
              SELECT DATE_TRUNC('month',dt) AS mth,MIN(dt) AS entry
              FROM (SELECT DISTINCT CAST("date" AS DATE) dt FROM o)
              WHERE EXTRACT(DOW FROM dt)=3
              GROUP BY 1
            """)
            db.execute(f"""
              CREATE OR REPLACE TEMP TABLE eligible AS
              SELECT CAST(o."date" AS DATE) entry,
                CAST(o.expiration AS DATE) expiry,
                LOWER(CAST(o."type" AS VARCHAR)) side,
                CAST(o.contract_id AS VARCHAR) contract_id,
                CAST(o.strike AS DOUBLE) strike,
                CAST(o.bid AS DOUBLE) bid,
                CAST(o.ask AS DOUBLE) ask,
                CAST(o.implied_volatility AS DOUBLE) iv,
                CAST(u.spot AS DOUBLE) spot
              FROM o
              JOIN entry_dates e ON CAST(o."date" AS DATE)=e.entry
              JOIN u ON u.dt=CAST(o."date" AS DATE)
              WHERE DATE_DIFF('day',CAST(o."date" AS DATE),CAST(o.expiration AS DATE))
                 BETWEEN 20 AND 45
                AND CAST(o.expiration AS DATE)<=DATE '{year}-12-31'
                AND LOWER(CAST(o."type" AS VARCHAR)) IN ('call','put')
                AND u.spot>0
                AND o.strike BETWEEN 0.85*u.spot AND 1.15*u.spot
                AND o.bid>0 AND o.ask>=o.bid
                AND (o.ask-o.bid)/((o.ask+o.bid)/2)<=0.25
                AND o.implied_volatility BETWEEN 0.03 AND 2
                AND isfinite(o.implied_volatility)
            """)
            db.execute("""
              CREATE OR REPLACE TEMP TABLE selected AS
              WITH targets AS (
                SELECT e.*, t.bucket,
                  CASE WHEN t.bucket='ATM' THEN e.spot
                       WHEN e.side='call' THEN e.spot*1.05
                       ELSE e.spot*0.95 END AS target_strike
                FROM eligible e CROSS JOIN
                (VALUES ('ATM'),('OTM_5PCT')) t(bucket)
              ), ranked AS (
                SELECT *,ABS(strike-target_strike)/spot AS target_gap,
                  ROW_NUMBER() OVER (
                    PARTITION BY entry,expiry,side,bucket
                    ORDER BY ABS(strike-target_strike),strike,contract_id
                  ) rank_choice
                FROM targets
              )
              SELECT * FROM ranked WHERE rank_choice=1
               AND ((bucket='ATM' AND target_gap<=0.01)
                 OR (bucket='OTM_5PCT' AND target_gap<=0.02))
            """)
            rows=db.execute("""
              WITH terminal AS (
                SELECT e.expiry, MAX_BY(u.spot,u.dt) final_spot,
                   MAX(u.dt) final_day
                FROM (SELECT DISTINCT expiry FROM selected) e
                LEFT JOIN u ON u.dt BETWEEN e.expiry-INTERVAL '4 days' AND e.expiry
                GROUP BY e.expiry
              )
              SELECT s.entry,s.expiry,s.side,s.bucket,
                s.strike,s.bid,s.ask,s.iv,s.spot,
                t.final_spot,t.final_day
              FROM selected s JOIN terminal t ON s.expiry=t.expiry
              WHERE t.final_spot>0
              ORDER BY s.entry,s.expiry,s.side,s.bucket
            """).fetchall()

            groups=defaultdict(dict)
            skipped=defaultdict(int)
            entry_days=set()
            expiry_days=set()
            for entry,expiry,side,bucket,strike,bid,ask,iv,spot,terminal,final_day in rows:
                # Do not invent a historical actual quote time: date/time here
                # is ONLY a deterministic DATE adapter for V1's date parsing.
                clock=f"{entry.isoformat()}T12:00:00+00:00"
                option={"strike":strike,"bid":bid,"ask":ask,"iv":iv}
                data={}
                for prefix in ("long","short"):
                    leg=f"{prefix}_{side}"
                    output=analyze_option(leg,option,spot,expiry.isoformat(),clock)
                    debit=ask+FEE_PER_SHARE
                    credit=bid-FEE_PER_SHARE
                    snap=Snapshot(
                        leg=leg,underlying_price=spot,strike=strike,bid=bid,ask=ask,iv=iv,
                        years_to_expiry=(expiry-entry).days/365,
                        risk_free_rate=RISK_FREE_RATE,dividend_yield=DIVIDEND_YIELD,
                        fee_per_share=FEE_PER_SHARE,
                    )
                    pnl=expiry_payoff_per_share(snap,terminal)
                    # Different denominators, compare ONLY SAME leg.
                    denominator = debit if prefix=="long" else (
                        strike if side=="put" else None
                    )
                    norm=pnl/denominator if denominator else None
                    if output["score_0_100"] is None:
                        skipped[output["score_status"]]+=1
                    data[leg] = (
                        output["score_0_100"],pnl,norm,output["p_expiry_profit_q"]
                    )
                key=(entry.isoformat(),expiry.isoformat(),side)
                if bucket in groups[key]:
                    raise AssertionError("Duplicate pair identifier")
                groups[key][bucket]=data
                entry_days.add(entry.isoformat())
                expiry_days.add(expiry.isoformat())
                if final_day != expiry:
                    skipped["expiry_stock_close_lag"]+=1

            metrics={}
            for leg in LEGS:
                paired_fixed={bucket:[] for bucket in BUCKETS}
                winning,losing=[],[]
                counts=defaultdict(int)
                for (_,_,side),buckets in groups.items():
                    if side!=leg.split("_")[1] or set(buckets)!={"ATM","OTM_5PCT"}:
                        continue
                    a=buckets["ATM"][leg]
                    b=buckets["OTM_5PCT"][leg]
                    paired_fixed["ATM"].append(a)
                    paired_fixed["OTM_5PCT"].append(b)
                    state,pair=evaluate_pair(a,b,leg)
                    counts[state]+=1
                    if pair is not None:
                        winning.append(pair[0])
                        losing.append(pair[1])
                        counts["right_if_more_profit_usd"]+=int(pair[0][1]>pair[1][1])
                        counts["right_if_more_profit_normalized"]+=int(
                            pair[0][2]>pair[1][2]
                        ) if pair[0][2] is not None else 0
                        counts["equal_profit_usd"]+=int(pair[0][1]==pair[1][1])
                total=len(paired_fixed["ATM"])
                selection_count=len(winning)
                metrics[leg]={
                    "pair_count":total,
                    "score_differentiated_pairs":selection_count,
                    "score_tied_pairs":counts["TIED"],
                    "blocked_pairs":counts["BLOCKED"],
                    "score_coverage_fraction":round(selection_count/total,6) if total else None,
                    "rank_correct_fraction_higher_realized_usd_pnl":round(
                        counts["right_if_more_profit_usd"]/selection_count,6) if selection_count else None,
                    "rank_correct_fraction_higher_realized_normalized_pnl":round(
                        counts["right_if_more_profit_normalized"]/selection_count,6
                    ) if selection_count and leg!="short_call" else None,
                    "ties_in_realized_profit":counts["equal_profit_usd"],
                    "fixed_ATM":_metrics(paired_fixed["ATM"]),
                    "fixed_OTM_5PCT":_metrics(paired_fixed["OTM_5PCT"]),
                    "higher_scored_contract_same_pairs":_metrics(winning),
                    "lower_scored_contract_same_pairs":_metrics(losing),
                }

            year_record={
                "year":year,
                "entry_dates":len(entry_days),
                "expiry_dates":len(expiry_days),
                "full_option_records_selected_before_pair_match":len(rows),
                "no_exact_option_quote_timestamp":True,
                "synthetic_clock_is_only_date_parser_not_quote_time":True,
                "quote_source_market_provenance_unverified":True,
                "risk_free_and_dividend_assumptions":[0.,0.],
                "sample_matched_price_lags_or_errors":dict(skipped),
                "legs":metrics,
            }
            result[str(year)]=year_record
            compact={}
            for leg,z in metrics.items():
                compact[leg]={
                    "n":z["pair_count"],
                    "differentiated":z["score_differentiated_pairs"],
                    "tied":z["score_tied_pairs"],
                    "rank_right_usd":z["rank_correct_fraction_higher_realized_usd_pnl"],
                    "rank_right_normalized":z["rank_correct_fraction_higher_realized_normalized_pnl"],
                    "atm_win":z["fixed_ATM"]["win_rate"],
                    "otm_win":z["fixed_OTM_5PCT"]["win_rate"],
                    "higher_win":z["higher_scored_contract_same_pairs"]["win_rate"],
                    "lower_win":z["lower_scored_contract_same_pairs"]["win_rate"],
                    "higher_pnl":z["higher_scored_contract_same_pairs"]["avg_pnl_usd_per_underlying_share"],
                    "lower_pnl":z["lower_scored_contract_same_pairs"]["avg_pnl_usd_per_underlying_share"],
                    "q_brier_ATM":z["fixed_ATM"]["q_profit_brier"],
                    "q_brier_OTM":z["fixed_OTM_5PCT"]["q_profit_brier"],
                }
            print("V1_ACCURACY_YEAR_JSON="+json.dumps({
                "year":year,
                "entry_dates":len(entry_days),"expiry_dates":len(expiry_days),
                "selected_contract_rows":len(rows),"legs":compact
            },sort_keys=True),flush=True)
            if len(entry_days)<8 or min(z["pair_count"] for z in metrics.values())<30:
                raise AssertionError(f"Insufficient SPY paired data for {year}")
        report={
            "study":"FROZEN_OPTIONS_MONITOR_V1_SCORE_SPY_2022_TO_2025",
            "calibration_or_weight_tuning_performed":False,
            "score_is_probability":False,
            "original_v1_scoring_source":"standalone_web/option_analysis.py (unchanged)",
            "source_upstream_commit":"37f6c456fe1a4775c875673fb8ef907d5cd2fd66",
            "fee_per_share_usd":FEE_PER_SHARE,
            "years":list(YEARS),
            "year_2025_is_not_blind_to_prior_research":True,
            "label":"expiry intrinsic from historical stock close, NOT actual option exercise",
            "rank_test":"ATM vs 5%-OTM same entry, expiry and leg; unoptimized score selects higher",
            "normalization":"long P/L per debit; short put P/L per cash secured strike; short call undefined",
            "confidence":"no independence across same-spot strikes / expiries; not a reliable live accuracy guarantee",
            "data":result,
        }
        Path("spy_v1_score_accuracy_audit.json").write_text(
            json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8"
        )
        print("SPY_V1_SCORE_ACCURACY_AUDIT_COMPLETE_NO_TUNING",flush=True)


if __name__=="__main__":
    run()
