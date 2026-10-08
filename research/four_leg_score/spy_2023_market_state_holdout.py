"""Frozen 2023 SPY EOD test of ONE market-state factor; no parameter fitting.

Only 2023. Baselines: Black-Scholes Q, 1-|delta|. ONE challenger:
BS with 25% shrinkage of lagged 20-market-observation momentum in log drift.
Coefficient and lookback are predeclared, NOT optimized. All probabilities
are expiry OTM proxies, never actual no-assignment or investment scores.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import json
import math
import tempfile

import duckdb
from research.four_leg_score.github_data_pilot import fetch_verified, FILES

FILES["spy/options_2023.parquet"] = (47_343_699, "ead8adeee0689d26e49f5b39f6d5536443931ac3")

YEAR = 2023
RATE = 0.04               # keep historic pilot's illustrative fixed assumptions
DIVIDEND = 0.01
LOOKBACK_DAYS = 20        # strictly PRIOR option-observation dates, not future bars
MOMENTUM_SHRINK = 0.25   # single arbitrary FROZEN research hypothesis, not calibrated
SPREAD_LIMIT = 0.25
IV_LIMITS = (0.03, 2.0)
MONEYNESS = (0.85, 1.15)


def cdf(x: float) -> float:
    return math.erfc(-x / math.sqrt(2)) / 2.0


def prob_otm(spot: float, strike: float, t_days: int, iv: float,
             side: str, momentum20_log: float = 0.0) -> float:
    t = t_days / 365.0
    drift_shock = MOMENTUM_SHRINK * momentum20_log * t * 252 / LOOKBACK_DAYS
    d2 = (
        math.log(spot/strike)
        + (RATE-DIVIDEND-iv*iv/2)*t
        + drift_shock
    ) / (iv*math.sqrt(t))
    return cdf(d2) if side == "put" else cdf(-d2)


def metrics(rows: list[tuple[float, float, str]]) -> dict:
    n=len(rows)
    if not n:
        return {"n": 0, "brier": None, "pred": None, "otm": None}
    return {
        "n":n,
        "brier":round(sum((p-y)**2 for p,y,_ in rows)/n,8),
        "pred":round(sum(p for p,_,_ in rows)/n,8),
        "otm":round(sum(y for _,y,_ in rows)/n,8),
    }


def run() -> None:
    with tempfile.TemporaryDirectory(prefix="spy-2023-state-") as td:
        root=Path(td)
        option_file=root/"options_2023.parquet"
        spot_file=root/"underlying_prices.parquet"
        fetch_verified("spy/options_2023.parquet", option_file)
        fetch_verified("spy/underlying_prices.parquet",spot_file)
        db=duckdb.connect(":memory:")
        db.execute(f"CREATE VIEW o AS SELECT * FROM read_parquet('{option_file.as_posix()}')")
        db.execute(f"""CREATE VIEW px AS
            SELECT CAST("date" AS DATE) dt, CAST(close AS DOUBLE) spot
            FROM read_parquet('{spot_file.as_posix()}')""")

        # Sanity check: note that the SPY stock file contains far more daily
        # rows than market sessions. Weekend price CHANGES are a provenance flag.
        integrity=db.execute("""
            WITH daily AS (
              SELECT dt, spot, LAG(spot) OVER (ORDER BY dt) prior_spot
              FROM px WHERE dt BETWEEN DATE '2023-01-01' AND DATE '2023-12-31'
            )
            SELECT COUNT(*) AS year_days,
                   COUNT(*) FILTER (WHERE EXTRACT(DOW FROM dt) IN (0,6)) AS weekend_days,
                   COUNT(*) FILTER (
                       WHERE EXTRACT(DOW FROM dt) IN (0,6)
                         AND prior_spot IS NOT NULL AND ABS(spot-prior_spot)>0.00001
                   ) AS changing_weekends,
                   CAST(MAX_BY(spot,dt) AS DOUBLE) AS last_close
            FROM daily
        """).fetchone()
        db.execute("""
          CREATE TEMP TABLE selected_dates AS
            SELECT DATE_TRUNC('month', dt) AS month, MIN(dt) AS entry_date
            FROM (SELECT DISTINCT CAST("date" AS DATE) dt FROM o)
            WHERE EXTRACT(DOW FROM dt)=3 GROUP BY 1
        """)
        # Market-state history ONLY uses dates on which OPTION SNAPSHOTS exist.
        # It cannot access future bars, interpolated weekend prices, or target outcomes.
        db.execute("""
          CREATE TEMP TABLE prior20 AS
            SELECT dt, spot,
                   LAG(spot, 20) OVER (ORDER BY dt) AS prior_spot20
            FROM px WHERE dt IN (SELECT DISTINCT CAST("date" AS DATE) FROM o)
        """)
        db.execute("""
          CREATE TEMP TABLE filtered0 AS
            SELECT CAST(o."date" AS DATE) entry,
                   CAST(o.expiration AS DATE) expiry,
                   LOWER(CAST(o."type" AS VARCHAR)) side,
                   CAST(o.strike AS DOUBLE) strike,
                   CAST(o.bid AS DOUBLE) bid,
                   CAST(o.ask AS DOUBLE) ask,
                   CAST(o.implied_volatility AS DOUBLE) iv,
                   CAST(o.delta AS DOUBLE) delta,
                   p.spot spot, p.prior_spot20 prev20,
                   DATE_DIFF('day', CAST(o."date" AS DATE), CAST(o.expiration AS DATE)) dte
            FROM o
            JOIN selected_dates e ON CAST(o."date" AS DATE)=e.entry_date
            JOIN prior20 p ON p.dt=CAST(o."date" AS DATE)
            WHERE CAST(o.expiration AS DATE)<=DATE '2023-12-31'
              AND DATE_DIFF('day', CAST(o."date" AS DATE), CAST(o.expiration AS DATE))
                  BETWEEN 20 AND 45
              AND LOWER(CAST(o."type" AS VARCHAR)) IN ('call','put')
        """)
        db.execute("""
          CREATE TEMP TABLE settled AS
            SELECT e.expiry, MAX_BY(p.spot,p.dt) final_spot
            FROM (SELECT DISTINCT expiry FROM filtered0) e
            LEFT JOIN px p ON p.dt BETWEEN e.expiry - INTERVAL '4 days' AND e.expiry
            GROUP BY e.expiry
        """)
        rows=db.execute("""
          SELECT a.entry, a.expiry, a.side, a.strike, a.iv, a.delta, a.spot,
                 a.prev20, a.dte, s.final_spot
          FROM filtered0 a JOIN settled s ON s.expiry=a.expiry
          WHERE a.spot>0 AND a.prev20>0 AND s.final_spot>0
            AND a.strike BETWEEN a.spot * ? AND a.spot * ?
            AND a.bid>0 AND a.ask>=a.bid
            AND (a.ask-a.bid)/((a.ask+a.bid)/2)<=?
            AND a.iv BETWEEN ? AND ?
            AND isfinite(a.iv) AND isfinite(a.delta)
        """,[MONEYNESS[0],MONEYNESS[1],SPREAD_LIMIT,IV_LIMITS[0],IV_LIMITS[1]]).fetchall()
        outcomes=defaultdict(lambda: defaultdict(list))
        months=defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        entry_dates=set()
        expiry_dates=set()
        daily_sign=defaultdict(lambda:{"pos":0,"neg":0})
        for entry, expiry, side, strike, iv, delta, spot, prev20, dte, spot_t in rows:
            if spot_t==strike:
                continue
            y=float(spot_t>strike) if side=="put" else float(spot_t<strike)
            b=prob_otm(spot,strike,dte,iv,side)
            d=min(1.,max(0.,1.-abs(delta)))
            momentum=math.log(spot/prev20)
            m=prob_otm(spot,strike,dte,iv,side,momentum20_log=momentum)
            month=str(entry)[:7]
            entry_dates.add(str(entry))
            expiry_dates.add(str(expiry))
            daily_sign[month]["pos" if momentum>=0 else "neg"]+=1
            for label,p in (("bs",b),("delta",d),("momentum",m)):
                value=(p,y,str(entry))
                outcomes[side][label].append(value)
                months[side][month][label].append(value)
        if len(entry_dates)<8 or sum(len(outcomes[s]["bs"]) for s in ("call","put"))<100:
            raise RuntimeError("INSUFFICIENT_2023_HOLDOUT_DATA")
        aggregate={side:{label:metrics(outcomes[side][label]) for label in ("bs","delta","momentum")}
                   for side in ("call","put")}
        monthly={side:{month:{label:metrics(months[side][month][label]) for label in ("bs","delta","momentum")}
                      for month in sorted(months[side])} for side in ("call","put")}
        month_wins={
            side:{
                "momentum_vs_bs":sum(1 for v in monthly[side].values() if v["momentum"]["brier"]<v["bs"]["brier"]),
                "momentum_vs_delta":sum(1 for v in monthly[side].values() if v["momentum"]["brier"]<v["delta"]["brier"]),
                "months":len(monthly[side]),
            } for side in ("call","put")
        }
        # Tiny sample / highly correlated strikes: aggregate Brier alone is
        # NOT a confidence interval and does not prove robust improvement.
        improvement_both=all(
            aggregate[side]["momentum"]["brier"] < min(aggregate[side]["bs"]["brier"],aggregate[side]["delta"]["brier"])
            for side in ("call","put")
        )
        # Require majorities of independent observation MONTHS against both
        # baselines even to put into further observation; no automatic promotion.
        reliable_monthly=all(
            month_wins[s]["momentum_vs_bs"]>month_wins[s]["months"]/2
            and month_wins[s]["momentum_vs_delta"]>month_wins[s]["months"]/2
            for s in ("call","put")
        )
        quality_note="UNVERIFIED_SOURCE_EOD_SNAPSHOT; NO_EXACT_OPTION_QUOTE_TIME"
        if integrity[2]:
            quality_note+="; UNDERLYING_HAS_NONZERO_WEEKEND_PRICE_CHANGES"
        verdict=("FURTHER_VALIDATION_ONLY" if improvement_both and reliable_monthly
                 else "NOT_PROMOTED_ON_2023_HOLDOUT")
        report={
            "scope":"SPY 2023 fixed first-Wednesday 20-45 DTE only",
            "source":"anahatsingh-ui/options-dataset-hist 37f6c456fe1a4775c875673fb8ef907d5cd2fd66",
            "provenance_not_independently_verified":True,
            "stock_calendar_diagnostics":{"rows_2023":integrity[0],"weekends":integrity[1],
                                          "changing_weekends":integrity[2],"last_close_2023":integrity[3]},
            "quality_note":quality_note,
            "assumptions":{"r":RATE,"q":DIVIDEND,"momentum_observation_days":LOOKBACK_DAYS,
                           "fixed_drift_shrink":MOMENTUM_SHRINK,
                           "note":"hypothesis, coefficient not estimated or validated"},
            "entry_dates":len(entry_dates),"expiry_dates":len(expiry_dates),
            "filtered_rows":sum(len(outcomes[s]["bs"]) for s in ("call","put")),
            "aggregate":aggregate,
            "monthly":monthly,"monthly_comparison":month_wins,
            "market_state_sign_counts":daily_sign,
            "preliminary_factor_verdict":verdict,
            "formal_model_promoted":False,
            "historical_probability_is_not_broker_assignment":True,
            "historical_quotes_time_synchronized":False,
            "formal_opportunity_score":None,
        }
        output=Path("spy_2023_market_state_holdout.json")
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2,default=dict),encoding="utf-8")
        print("HOLDOUT_2023_RESULT="+json.dumps({
            "stock_calendar_diagnostics":report["stock_calendar_diagnostics"],
            "entry_dates":report["entry_dates"],"expiry_dates":report["expiry_dates"],
            "filtered_rows":report["filtered_rows"],
            "aggregate":aggregate,"monthly_comparison":month_wins,
            "verdict":verdict,"quality_note":quality_note
        }),flush=True)
        print("SPY_2023_HOLDOUT_COMPLETE_NO_FORMAL_SCORE",flush=True)


if __name__=="__main__":
    run()
