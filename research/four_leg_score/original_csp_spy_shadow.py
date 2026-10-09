"""Original MAIN Cash-Secured Put: bounded, explicit historical SHADOW ONLY.

Source of rule definitions: docs/candidate_strategy.md on original main
a478cea87f26c1c6667f51031c6a2178bcc808f4.
This script DOES NOT execute the original Candidate Engine, which fails closed
without OpenD account and market snapshots, tick size, actual fee schedule,
complete earnings calendar, contracts/multiplier and capital. No original
candidate is claimed executable or officially passed.

What can be tested: 7-60 DTE, K<=S and >=0.8*S, quote spread <=40%,
IV/term-matched historical RV >= 1.1 and IV-RV >= .05, annualized premium
>=10%, rank by nonannualized net premium return with <=.002 tie neighborhood.
Fee = illustrative $0.01/share, execution BID and unrounded MID scenarios.
Historical archive original feed/timestamps unverified. One candidate max
per first available Wednesday of month and SPY only.
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

FILES.update({
    "spy/options_2022.parquet": (57_070_606, "f0a15b8263b7650147bfa62bce2cd44d59ef17a5"),
    "spy/options_2023.parquet": (47_343_699, "ead8adeee0689d26e49f5b39f6d5536443931ac3"),
    "spy/options_2025.parquet": (58_216_546, "133bf1d95c3479149bf4771bc8b3fd8b625064ce"),
})
YEARS=(2022,2023,2024,2025)
FEE_PER_SHARE=.01             # shadow ONLY; not the full original Futu contract fee
NEAR_RETURN=.002
SPREAD_MAX=.40
MIN_IV_RV_RATIO=1.10
MIN_IV_RV_ABSOLUTE=.05
MIN_ANNUAL=.10
MIN_DTE,MAX_DTE=7,60
WARNING="NOT_ORIGINAL_EXECUTABLE_OR_FILLED_TRADES"


def _volatility_session_based(entry:date, expiry:date, trade_dates:list[date],
                              closes:list[float]) -> tuple[float|None,int]:
    """Available completed closes strictly before entry, never future prices."""
    # Known future exchange *calendar* is inferred from archive date rows and
    # can differ from historical OpenD session calendar. Price future NOT read.
    future_sessions=sum(1 for d in trade_dates if entry < d <= expiry)
    lookback=max(20,future_sessions)
    previous_prices=[close for d,close in zip(trade_dates,closes) if d < entry]
    if len(previous_prices)<lookback+1:
        return None,lookback
    p=previous_prices[-(lookback+1):]
    log_returns=[math.log(p[i]/p[i-1]) for i in range(1,len(p))]
    if len(log_returns)<2:
        return None,lookback
    return statistics.stdev(log_returns)*math.sqrt(252),lookback


def _summary(items:list[dict],price_type:str) -> dict:
    if not items:
        return {"n":0}
    pnls=sorted(x[f"pl_{price_type}"] for x in items)
    fraction=[int(x>0) for x in pnls]
    per_cash=[v / row["strike"] for v,row in zip(
        (r[f"pl_{price_type}"] for r in items),items
    )]
    return {
        "n":len(items),
        "profitable_at_expiration_fraction":round(statistics.mean(fraction),6),
        "mean_pnl_per_share":round(statistics.mean(pnls),6),
        "median_pnl_per_share":round(statistics.median(pnls),6),
        "minimum_pnl_per_share":round(pnls[0],6),
        "worst_5pct_mean_pnl_per_share":round(
            statistics.mean(pnls[:max(1,math.ceil(.05*len(pnls)))]),6
        ),
        "mean_pnl_over_strike_cash_fraction":round(statistics.mean(per_cash),6),
        "mean_estimated_entry_credit":round(statistics.mean(x[f"credit_{price_type}"] for x in items),6),
        "mean_strike":round(statistics.mean(x["strike"] for x in items),4),
        "mean_spot":round(statistics.mean(x["spot"] for x in items),4),
        "mean_dte":round(statistics.mean(x["dte"] for x in items),3),
        "mean_iv_minus_rv":round(statistics.mean(x["iv_minus_rv"] for x in items),6),
    }


def run():
    data={}
    with tempfile.TemporaryDirectory(prefix="original-csp-spy-shadow-") as folder:
        root=Path(folder)
        underlying=root/"underlying_prices.parquet"
        fetch_verified("spy/underlying_prices.parquet",underlying)
        db=duckdb.connect(":memory:")
        db.execute(f"""CREATE VIEW u AS SELECT CAST("date" AS DATE) dt,
                    CAST("close" AS DOUBLE) spot
                    FROM read_parquet('{underlying.as_posix()}')""")
        daily=db.execute("SELECT dt,spot FROM u WHERE spot>0 ORDER BY dt").fetchall()
        trade_dates=[row[0] for row in daily]
        closes=[row[1] for row in daily]
        for year in YEARS:
            option=root/f"options_{year}.parquet"
            fetch_verified(f"spy/options_{year}.parquet",option)
            db.execute(f"CREATE OR REPLACE VIEW o AS SELECT * FROM read_parquet('{option.as_posix()}')")
            db.execute("""
              CREATE OR REPLACE TEMP TABLE entry_dates AS
              SELECT DATE_TRUNC('month',dt) AS month_date,MIN(dt) AS entry
              FROM (SELECT DISTINCT CAST("date" AS DATE) dt FROM o)
              WHERE EXTRACT(DOW FROM dt)=3 GROUP BY 1
            """)
            # These are the public data fields that partially approximate
            # original OpenD contract snapshots; no synthetic greeks.
            raw=db.execute(f"""
              WITH e AS (
                SELECT CAST(o."date" AS DATE) entry,
                   CAST(o.expiration AS DATE) expiry,
                   CAST(o.strike AS DOUBLE) strike,
                   CAST(o.bid AS DOUBLE) bid,
                   CAST(o.ask AS DOUBLE) ask,
                   CAST(o.implied_volatility AS DOUBLE) iv,
                   CAST(o.open_interest AS DOUBLE) oi,
                   CAST(o.contract_id AS VARCHAR) contract,
                   CAST(u.spot AS DOUBLE) spot,
                   DATE_DIFF('day',CAST(o."date" AS DATE),CAST(o.expiration AS DATE)) dte
                FROM o JOIN entry_dates d ON CAST(o."date" AS DATE)=d.entry
                JOIN u ON u.dt=CAST(o."date" AS DATE)
                WHERE LOWER(CAST(o."type" AS VARCHAR))='put'
                  AND DATE_DIFF('day',CAST(o."date" AS DATE),CAST(o.expiration AS DATE))
                      BETWEEN {MIN_DTE} AND {MAX_DTE}
                  AND CAST(o.expiration AS DATE)<=DATE '{year}-12-31'
                  AND u.spot>0
                  AND o.strike BETWEEN .8*u.spot AND u.spot
                  AND o.bid>0 AND o.ask>=o.bid
                  AND (o.ask-o.bid)/((o.ask+o.bid)/2)<=.40
                  AND o.implied_volatility>0
                  AND isfinite(o.implied_volatility)
              )
              SELECT e.*, t.spot terminal_spot, t.last_date terminal_day
              FROM e
              JOIN (
                 SELECT expiry,MAX_BY(u.spot,u.dt) AS spot,MAX(u.dt) last_date
                 FROM (SELECT DISTINCT expiry FROM e) p
                 JOIN u ON u.dt BETWEEN p.expiry-INTERVAL '4 days' AND p.expiry
                 GROUP BY expiry
              ) t ON t.expiry=e.expiry
            """).fetchall()
            vol_lookup={}
            rejected=defaultdict(int)
            options_by_date=defaultdict(list)
            observation_dates=set()
            source_rows=len(raw)
            for entry,expiry,strike,bid,ask,iv,oi,contract,spot,dte,terminal,terminal_day in raw:
                observation_dates.add(entry.isoformat())
                key=(entry,expiry)
                if key not in vol_lookup:
                    vol_lookup[key]=_volatility_session_based(entry,expiry,trade_dates,closes)
                rv,lookback=vol_lookup[key]
                if rv is None or rv<=0:
                    rejected["missing_term_rv"]+=1
                    continue
                if iv/rv<MIN_IV_RV_RATIO or iv-rv<MIN_IV_RV_ABSOLUTE:
                    rejected["no_iv_over_rv_edge"]+=1
                    continue
                # Raw mid is a proxy for the original tick-rounded mid limit.
                # Exact price tick and Futu fee cannot be recovered.
                raw_mid=(bid+ask)/2.
                net_mid=raw_mid-FEE_PER_SHARE
                net_bid=bid-FEE_PER_SHARE
                if net_mid<=0 or strike<=net_mid:
                    rejected["nonpositive_net_mid_credit"]+=1
                    continue
                pr=net_mid/(strike-net_mid)
                if pr*365/dte<MIN_ANNUAL:
                    rejected["below_10pct_annualized_mid_proxy"]+=1
                    continue
                itm=max(strike-terminal,0.)
                row={
                    "entry":entry.isoformat(),"expiry":expiry.isoformat(),
                    "contract":contract,"strike":strike,"spot":spot,"dte":dte,
                    "iv":iv,"rv":rv,"iv_minus_rv":iv-rv,"iv_rv":iv/rv,
                    "spread_mid":(ask-bid)/raw_mid,
                    "oi":oi,
                    "net_mid_period_return":pr,
                    "net_assignment_discount":(spot-(strike-net_mid))/spot,
                    "credit_mid":net_mid,"credit_bid":net_bid,
                    "pl_mid":net_mid-itm,"pl_bid":net_bid-itm,
                    "outcome_stock_close_lag":(expiry-terminal_day).days,
                }
                options_by_date[entry.isoformat()].append(row)
            chosen=[]
            # Single SPY symbol: use original "maximize period net return,
            # <=.002 neighborhood, then discount/spread/OI/credit" priority.
            for entry,options in sorted(options_by_date.items()):
                peak=max(x["net_mid_period_return"] for x in options)
                near=[x for x in options if peak-x["net_mid_period_return"]<=NEAR_RETURN]
                near.sort(key=lambda x:(
                    -x["net_assignment_discount"],x["spread_mid"],
                    -(x["oi"] is not None),-(x["oi"] or 0),
                    -x["credit_mid"],x["contract"]
                ))
                chosen.append(near[0])
            # Full source can be used only when all original fields pass;
            # this experiment explicitly omits unavailable OpenD fields.
            result={
              "year":year,
              "source_rows_quotes_7_to_60_dte":source_rows,
              "dates_with_raw_contracts":len(observation_dates),
              "dates_with_partial_original_quote_and_volatility_gate":len(options_by_date),
              "hypothetical_selected_months":len(chosen),
              "rejected_after_quote":dict(rejected),
              "mid_proxy":_summary(chosen,"mid"),
              "bid_conservative_proxy":_summary(chosen,"bid"),
              "selected_proxy_per_entry":chosen,
              "original_strict_executable_candidates":None,
              "cannot_certify":"OPEN_D_MARKET_STATE,OPTION_SNAPSHOT_RECEIPTS,PRICE_TICK,STANDARD_CONTRACT,MULTIPLIER,EXACT_FEES,FX,CNY50_THRESHOLD,CASH_COLLATERAL,LEDGER,EARNINGS_CALENDAR,QFQ_RV_CALENDAR",
            }
            data[str(year)]=result
            print("ORIGINAL_CSP_SHADOW_YEAR_JSON="+json.dumps({
                "year":year,"source_rows":source_rows,
                "eligible_observation_dates":len(options_by_date),
                "hypothetical_selected_months":len(chosen),
                "mid_proxy":result["mid_proxy"],
                "bid_proxy":result["bid_conservative_proxy"],
                "rejections":result["rejected_after_quote"],
            },sort_keys=True),flush=True)
        doc={
            "result_status":WARNING,
            "original_main_source_sha":"a478cea87f26c1c6667f51031c6a2178bcc808f4",
            "original_strategy":"insurance_underwriting Cash-Secured Put, original candidate_strategy.md",
            "original_candidate_engine_not_executed":True,
            "unverified_market_data_provenance_and_exact_bid_ask_time":True,
            "ranking_uses_unrounded_mid_as_proxy":True,
            "model_fitted":False,
            "hindsight_calendar_only_for_trading_sessions":True,
            "rv_built_from_prices_strictly_prior_to_entry":True,
            "underlying_spot_same_date_eod_not_live":True,
            "never_claim_original_score_accuracy":True,
            "observations_not_independent_due_to_shared_SPY":True,
            "no_exact_broker_fee_and_fx_or_collateral":True,
            "fee_per_share_illustrative":FEE_PER_SHARE,
            "original_mid_limit_fill_unverified":True,
            "year_results":data,
        }
        Path("original_csp_spy_shadow_result.json").write_text(
            json.dumps(doc,ensure_ascii=False,indent=2),encoding="utf-8"
        )
        print("ORIGINAL_CSP_SHADOW_COMPLETE_NOT_1TO1",flush=True)


if __name__=="__main__":
    run()
