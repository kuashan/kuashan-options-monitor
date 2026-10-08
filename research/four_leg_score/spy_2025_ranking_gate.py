"""SPY 2025 four-leg ranking gate: compare two pre-specified strikes, no score.

Only use known entry-date bid/ask and simple payoff scenarios. Prefer an option
only when it is Pareto-superior in both potential reward and adverse risk.
Otherwise ABSTAIN instead of inventing weights. The 2025 outcomes are read
only AFTER this rule is specified. No orders, no probabilities, no brokerage.
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
from research.four_leg_score.spy_three_regime_payoff import expiry_pl, FEE_PER_SHARE

FILES["spy/options_2025.parquet"] = (58_216_546, "133bf1d95c3479149bf4771bc8b3fd8b625064ce")
YEAR = 2025
TOL = 1e-9


def known_at_entry(leg: str, strike: float, bid: float, ask: float, spot: float) -> tuple[float, float]:
    """(favorable-scenario net payoff or credit, adverse-scenario net payoff).

    Scenario magnitudes are pre-specified, not calibrated:
    long: +10% spot for call, -10% for put (favorable);
          long risk is 100% debit loss.
    short: reward is net entry credit; adverse expiry spot +20% call/-20% put.
    """
    if leg in ("long_call", "long_put"):
        debit = ask + FEE_PER_SHARE
        favorable_spot = spot * (1.10 if leg == "long_call" else 0.90)
        return expiry_pl(leg,strike,favorable_spot,bid,ask), -debit
    if leg in ("short_call","short_put"):
        credit = bid-FEE_PER_SHARE
        adverse_spot = spot * (1.20 if leg == "short_call" else 0.80)
        return credit, expiry_pl(leg,strike,adverse_spot,bid,ask)
    raise ValueError("Unsupported option leg")


def compare(leg: str, atm: tuple[float,float,float,float],
            otm: tuple[float,float,float,float]) -> str:
    """Compare K/bid/ask/S, tradeoff means an explicit no-rank decision."""
    a=known_at_entry(leg,*atm)
    b=known_at_entry(leg,*otm)
    if all(x >= y-TOL for x,y in zip(a,b)) and any(x>y+TOL for x,y in zip(a,b)):
        return "ATM_DOMINATES"
    if all(y >= x-TOL for x,y in zip(a,b)) and any(y>x+TOL for x,y in zip(a,b)):
        return "OTM_DOMINATES"
    if all(abs(x-y)<=TOL for x,y in zip(a,b)):
        return "TIE"
    return "TRADEOFF_ABSTAIN"


def summarize(observations: list[tuple[float,float,float,float]],leg: str) -> dict:
    if not observations:
        return {"n":0}
    x=sorted(v[0] for v in observations)
    n=len(x)
    tail_n=max(1,math.ceil(n*.05))
    if leg.startswith("long"):
        norm=[pl/(quote+FEE_PER_SHARE) for pl,quote,k,spot in observations]
        scale="PAID_PREMIUM"
    elif leg=="short_put":
        norm=[pl/strike for pl,quote,strike,spot in observations]
        scale="GROSS_CASH_RESERVE_STRIKE"
    else:
        norm=None
        scale="NONE_FOR_UNBOUNDED_NAKED_SHORT_CALL"
    return {
        "n":n,
        "wins":sum(pl>0 for pl in x),
        "win_fraction":round(sum(pl>0 for pl in x)/n,6),
        "average_usd_per_underlying_share":round(statistics.mean(x),6),
        "worst_5pct_mean_usd_per_share":round(statistics.mean(x[:tail_n]),6),
        "mean_pnl_divided_by_stock_price":round(statistics.mean(
            pl/spot for pl,quote,strike,spot in observations),6),
        "capital_reference":scale,
        "mean_return_on_own_reference":round(statistics.mean(norm),6) if norm is not None else None,
    }


def run() -> None:
    with tempfile.TemporaryDirectory(prefix="spy-2025-rank-") as folder:
        dir=Path(folder)
        op,spot_file=dir/"options_2025.parquet",dir/"underlying_prices.parquet"
        fetch_verified("spy/options_2025.parquet",op)
        fetch_verified("spy/underlying_prices.parquet",spot_file)
        db=duckdb.connect(":memory:")
        db.execute(f"CREATE VIEW o AS SELECT * FROM read_parquet('{op.as_posix()}')")
        db.execute(f"""CREATE VIEW u AS
                   SELECT CAST("date" AS DATE) dt,CAST("close" AS DOUBLE) spot_close
                   FROM read_parquet('{spot_file.as_posix()}')""")
        # Same exact frozen 2022-24 pipeline: first Wednesday, DTE 20-45,
        # positive bid, <=25% spread, IV 3-200%, strike/spot 0.85-1.15,
        # closest ATM and 5%-OTM quoted contract per entry+expiry+side.
        db.execute("""
            CREATE TEMP TABLE dates AS
            SELECT DATE_TRUNC('month',dt) AS calendar_month, MIN(dt) AS entry
            FROM (SELECT DISTINCT CAST("date" AS DATE) dt FROM o)
            WHERE EXTRACT(DOW FROM dt)=3 GROUP BY 1
        """)
        db.execute("""
            CREATE TEMP TABLE eligible AS
            SELECT CAST(o."date" AS DATE) entry,
              CAST(o.expiration AS DATE) expiry,
              LOWER(CAST(o."type" AS VARCHAR)) side,
              CAST(o.contract_id AS VARCHAR) contract_id,
              CAST(o.strike AS DOUBLE) strike,
              CAST(o.bid AS DOUBLE) bid,
              CAST(o.ask AS DOUBLE) ask,
              CAST(o.implied_volatility AS DOUBLE) iv,
              CAST(u.spot_close AS DOUBLE) spot
            FROM o JOIN dates d ON CAST(o."date" AS DATE)=d.entry
            JOIN u ON u.dt=CAST(o."date" AS DATE)
            WHERE DATE_DIFF('day',CAST(o."date" AS DATE),CAST(o.expiration AS DATE))
                BETWEEN 20 AND 45
              AND CAST(o.expiration AS DATE)<=DATE '2025-12-31'
              AND LOWER(CAST(o."type" AS VARCHAR)) IN ('call','put')
              AND u.spot_close>0
              AND o.strike BETWEEN 0.85*u.spot_close AND 1.15*u.spot_close
              AND o.bid>0 AND o.ask>=o.bid
              AND (o.ask-o.bid)/((o.ask+o.bid)/2)<=0.25
              AND o.implied_volatility BETWEEN 0.03 AND 2.0
              AND isfinite(o.implied_volatility)
        """)
        db.execute("""
            CREATE TEMP TABLE chosen AS
            WITH targets AS (
               SELECT e.*, t.bucket,
                      CASE WHEN t.bucket='ATM' THEN e.spot
                           WHEN e.side='call' THEN 1.05*e.spot
                           ELSE 0.95*e.spot END AS desired_strike
               FROM eligible e
               CROSS JOIN (VALUES ('ATM'),('OTM_5PCT')) t(bucket)
            ), numbered AS (
               SELECT *,
                      ABS(strike-desired_strike)/spot AS target_gap,
                      ROW_NUMBER() OVER (
                        PARTITION BY entry,expiry,side,bucket
                        ORDER BY ABS(strike-desired_strike),strike,contract_id
                      ) rn
               FROM targets
            )
            SELECT * FROM numbered
            WHERE rn=1 AND (
              bucket='ATM' AND target_gap<=0.01
              OR bucket='OTM_5PCT' AND target_gap<=0.02
            )
        """)
        # Use terminal STOCK close as an end-of-day proxy. This source has
        # neither actual exercise records nor synchronized option quote times.
        raw=db.execute("""
            WITH finals AS (
              SELECT c.expiry,MAX_BY(u.spot_close,u.dt) s_terminal,
                     MAX(u.dt) close_date
              FROM (SELECT DISTINCT expiry FROM chosen) c
              LEFT JOIN u
                ON u.dt BETWEEN c.expiry-INTERVAL '4 days' AND c.expiry
              GROUP BY c.expiry
            )
            SELECT c.entry,c.expiry,c.side,c.bucket,c.strike,c.bid,c.ask,
                   c.spot,f.s_terminal,f.close_date
            FROM chosen c JOIN finals f ON f.expiry=c.expiry
            WHERE f.s_terminal>0
            ORDER BY c.entry,c.expiry,c.side,c.bucket
        """).fetchall()
        pair_index=defaultdict(dict)
        dates=set()
        expiry_dates=set()
        close_mismatch=0
        for entry,expiry,side,bucket,k,bid,ask,spot,terminal,close_date in raw:
            key=(str(entry),str(expiry),side)
            if bucket in pair_index[key]:
                raise AssertionError("Duplicate bucket within key")
            pair_index[key][bucket]=(k,bid,ask,spot,terminal)
            if close_date!=expiry:
                close_mismatch+=1
        result={}
        for side in ("call","put"):
            side_result={}
            for direction in ("long","short"):
                leg=f"{direction}_{side}"
                buckets={"ATM":[],"OTM_5PCT":[]}
                choices=defaultdict(int)
                dominates=[]
                pair_count=0
                for (entry,expiry,s),options in pair_index.items():
                    if s!=side or set(options)!={"ATM","OTM_5PCT"}:
                        continue
                    pair_count+=1
                    a=options["ATM"]; b=options["OTM_5PCT"]
                    # Research outputs require the identical contract universe
                    # for every ranked policy.
                    vals={}
                    for label,q in (("ATM",a),("OTM_5PCT",b)):
                        k,bid,ask,spot,terminal=q
                        pl=expiry_pl(leg,k,terminal,bid,ask)
                        paid=ask if direction=="long" else bid
                        vals[label]=(pl,paid,k,spot)
                        buckets[label].append(vals[label])
                    decision=compare(leg,a[:4],b[:4])
                    choices[decision]+=1
                    if decision=="ATM_DOMINATES":
                        dominates.append(("ATM",vals["ATM"],vals["OTM_5PCT"]))
                    elif decision=="OTM_DOMINATES":
                        dominates.append(("OTM_5PCT",vals["OTM_5PCT"],vals["ATM"]))
                    dates.add(entry);expiry_dates.add(expiry)
                dominant_vals=[x[1] for x in dominates]
                rejected_vals=[x[2] for x in dominates]
                side_result[leg]={
                    "pair_count":pair_count,
                    "decisions":dict(sorted(choices.items())),
                    "decisive_coverage":round(len(dominates)/pair_count,6) if pair_count else 0,
                    "fixed_ATM":summarize(buckets["ATM"],leg),
                    "fixed_OTM_5PCT":summarize(buckets["OTM_5PCT"],leg),
                    "dominant_only":summarize(dominant_vals,leg),
                    "opposite_of_dominant_same_pairs":summarize(rejected_vals,leg),
                    "no_forced_choice_for_tradeoff":True,
                }
            result[side]=side_result
        n=min(result["call"]["long_call"]["pair_count"],result["put"]["long_put"]["pair_count"])
        if n<20 or len(dates)<8:
            raise AssertionError("Not enough 2025 EOD candidate pairs; do not lower filters")
        report={
            "experiment":"SPY_2025_TWO_CHOICE_PARETO_RANKING_GATE",
            "source":"anahatsingh-ui/options-dataset-hist pinned 37f6c456fe1a4775c875673fb8ef907d5cd2fd66",
            "data_year":2025,
            "historical_outcome_not_exercise_or_actual_fill":True,
            "option_quote_exact_timestamp_unverified":True,
            "ranking_objectives":"Long: favorable +/-10% expiry net payoff and lower premium max-loss; Short: net credit and +/-20% adverse expiry payoff; NO tradeoff weights",
            "historical_fee_per_share":FEE_PER_SHARE,
            "n_unique_entry_dates":len(dates),
            "n_unique_expiry_dates":len(expiry_dates),
            "stock_close_date_mismatch_rows":close_mismatch,
            "coupled_outcomes_and_high_sample_correlation":True,
            "formal_score":None,
            "order_actions":[],
            "legs":result,
        }
        Path("spy_2025_ranking_gate_result.json").write_text(
            json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
        print("SPY_2025_RANKING_GATE_JSON="+json.dumps({
            "entry_dates":len(dates),"expiry_dates":len(expiry_dates),
            "close_mismatch":close_mismatch,
            "legs":result
        },ensure_ascii=False),flush=True)
        print("SPY_2025_RANKING_GATE_COMPLETE_NO_SCORE",flush=True)


if __name__=="__main__":
    run()
