# Four Single-Leg Options: Ten-Repository Audit and Scoring Contract V1

**Status:** RESEARCH IMPLEMENTED (offline kernel) / FORMAL SCORE **NOT CALIBRATED** / WEB **NOT WIRED** / TRADING **NOT IN SCOPE**  
**Date:** 2026-10-08  
**Code base read first:** \`kuashan/kuashan-options-monitor\` main \`a478cea87f26c1c6667f51031c6a2178bcc808f4\`; observer branch \`e86d40d8de77d2564f4befb9dd5457af68abb7ab\`.  
**Research code:** \`research/four_leg_score/engine.py\`. This is an original independent implementation, not copy/paste of licensed algorithm source.

## 1. Scope and names (four directions, not four multi-leg strategies)

| Leg | Action | Intrinsic at expiry | Cash flow at entry (per share) | Profit breakeven | Maximum loss |
|---|---|---|---|---|---|
| Long Call | Buy a Call | max(S_T−K,0) | negative ask and fee | K + debit | debit |
| Long Put | Buy a Put | max(K−S_T,0) | negative ask and fee | K − debit | debit |
| Short Call | Sell a Call | −max(S_T−K,0) | positive bid less fee | K + credit | **Unbounded** for the standalone naked short call |
| Short Put | Sell a Put | −max(K−S_T,0) | positive bid less fee | K − credit | K−credit, per underlying share |

Contract multipliers are **not** guessed. Figures remain *per underlying unit* until actual deliverable and multiplier are validated. A Covered Call is **stock plus a short Call**, a separate combined exposure; it is not interchangeable with the naked standalone short Call. With no broker/account connection, the viewer cannot assert that the short Call is covered, or that a short Put is cash secured.

For American equity options, short positions may be assigned before expiration, with additional ex-dividend and operational risks. Do **not** label \`P(expiry OTM)\` as \`P(no assignment)\`. Source: [Options Industry Council – Assignment FAQ](https://www.optionseducation.org/referencelibrary/faq/options-assignment).

## 2. Evidence from ten repositories (inspected actual default-branch source files)

| # | GitHub / inspected HEAD | Verified implementation | Borrow as a concept | Must NOT silently import |
|---|---|---|---|---|
| 1 | [deid84/seasonal-screener](https://github.com/deid84/seasonal-screener), \`3cd2e183295c\` | \`options_analysis.py\` BSM Greeks and expected move, \`screener.py:174+\` seasonality+low-volatility-discount score; Yahoo/yfinance Web | Seasonality validation, earnings, normalized Greeks and observed IV/HV features | Seasonality/HV discount is not per-contract profit/no-assignment probability. Discount favors cheap options and must not be blindly applied to short sellers. MIT. |
| 2 | [alpacahq/options-wheel](https://github.com/alpacahq/options-wheel), \`369842928906\` | \`core/strategy.py:29-52\` score \`(1-abs(delta))*(250/(DTE+5))*(bid/strike)\`; one candidate per symbol. | Sensible Sell Put term/return filters, concentration by symbol | \`1−|delta|\` is a heuristic risk proxy, not a calibrated OTM or actual no-assignment probability. Automated trading and Alpaca credentials excluded. Apache-2.0. |
| 3 | [goldspanlabs/optopsy](https://github.com/goldspanlabs/optopsy), \`40bb8b2aa07e\` | \`optopsy/strategies/singles.py\` explicitly supports all four legs, \`optopsy/metrics.py\` win rate, VaR/CVaR and risk metrics, simulator. | Per-leg independent historical evaluation, worst tails, chronological simulations/fees | Past win rate is not this contract's future probability; historical options datasets required. **AGPL-3.0**: no code copying or packaging without license review. |
| 4 | [Ja-Ta/options-income-screener](https://github.com/Ja-Ta/options-income-screener), \`39b8dd41cf08\` | \`python_app/src/scoring/score_csp.py\` explicit 0–1 weighted 7-factor score, plus earnings, trend, spread/volume filters in \`cash_secured_puts.py\`; another simple 70% ROI/30% margin selector. | Transparently decomposed score categories, events penalties, liquidity filters | Author-set weights are not validated probabilities or proven optimum; historical IV Rank not directly available in Yahoo snapshots. Provider is Massive API. MIT. |
| 5 | [06prasadg/wheel-strategy-screener](https://github.com/06prasadg/wheel-strategy-screener), \`5f331b8ac49b\` | \`black_scholes.py\` D1/D2 and option Delta, \`wheel_simulator.py\` iterates price closes, simulated assignment rate | Track assignment events and strategies by outcome; walk-forward ledger concept | Simulated premiums from BS+historical vol, not historical executable option quotes; close-only assignment ignores early exercise and stock constituent bias. MIT. |
| 6 | [Marfusios/premium-tracker](https://github.com/Marfusios/premium-tracker), \`fe8062c81c62\` | \`components/Dashboard.tsx:144-161\` classifies short Put assignment as "likely" if ITM, otherwise uses P/L fallback; CSV portfolio dashboard | Visualization and explanation of exposure and collateral | This is binary moneyness, **not a probability estimator**. README claims MIT but repository root had no \`LICENSE\` blob in inspected tree and API metadata gave no SPDX license; **do not copy code until permission is confirmed**. |
| 7 | [rgaveiga/optionlab](https://github.com/rgaveiga/optionlab), \`8dc119ca03a1\` | \`optionlab/engine.py\` PoP, Greeks, ITM/touch; \`profit.py\` return-probability integration; \`black_scholes.py\` D1/D2 | Separate expiry ITM, touch and profit, with testable payoff conventions | \`put_itm_prob=exp(-qT)*N(-d2)\` includes dividend discount, so **not literally the bare probability** when q≠0; our own baseline uses \`N(-d2)\`. Touch assumptions are model-dependent. GPL-3.0; do not copy code. |
| 8 | [Open-Lemma/options-implied-probability](https://github.com/Open-Lemma/options-implied-probability), \`180748f6a78e\` | \`oipd/interface/probability.py:516-552\` explicitly implements \`prob_below\` and \`prob_above\` from CDF; vol surface + yfinance reader available | Strong candidate for optional **second** market-implied probability model, with density/smile and data-quality reports | Risk-neutral **market-implied** distribution, not real-world statistical chances; full curve may fail on sparse/crossed/stale Yahoo quotes. Apache-2.0. Benchmark before package adoption. |
| 9 | [Talha-Tariq/poptions](https://github.com/Talha-Tariq/poptions), \`658d8873a686\` | \`poptions/MonteCarlo.py\` GBM simulation and target-profit-hit percentages; \`ShortPut.py\` specific payoff | Optional expiry/exit objective Monte Carlo cross-check | Code explicitly excludes assignment, dividends, splits, fees and earnings; simulation hit percentage is not a forecast. MIT. |
| 10 | [bcdannyboy/spreadfinder](https://github.com/bcdannyboy/spreadfinder), \`4545b694050b\` | \`spreadfinder.py:805-815\` composite score; \`:850-955\` BSM/binomial, GBM/t-distribution/Heston sampling and expected value | Independent scenario and tail-model comparison, spread/slippage penalties | Built for a **two-leg bull Put spread** and Tradier credentials, not our four single legs; author-weighted score has no demonstrated calibration. No root \`LICENSE\` in inspected tree / no SPDX metadata; reuse concept, **not code**. |

**Result:** All ten inspected. Only 7 and 8 directly offer per-contract explicit price-distribution probabilities; 2 and 4 provide ranking heuristics, 3 provides four-leg historical evaluation, 9 and 10 provide scenario simulation. **None** of them can guarantee American short-option "no assignment 90%" from Yahoo data.

## 3. Model architecture: shared mathematics, four different payoff/risk objectives

A. **Quote/contract quality gate (before ranking).** Collect market+contract identity; quote timestamps for underlying *and* options (NOT \`lastTradeDate\` treated as a quote refresh); rights/deliverables/multiplier, bid/ask, IV, expiry timezone, dividends, rates, corporate actions, OI, liquidity and event calendar. No phantom prices, no assuming 100-share multiplier for adjusted contracts. When unable to synchronize, show \`DATA_UNVERIFIED\` and **no formal score**.

B. **Probability Q (model-implied / risk-neutral; benchmark).** Given \`S,K,T,sigma,r,q\`, define

\`\`\`
d2(B) = [ln(S/B) + (r - q - 0.5*sigma^2)*T] / (sigma*sqrt(T))
P_Q(S_T > B) = N(d2(B)),  P_Q(S_T < B) = N(-d2(B))
P_Q(put expiry OTM)  = P_Q(S_T >= K)
P_Q(call expiry OTM) = P_Q(S_T <= K)
\`\`\`

Probability of profit uses a *different* threshold: the leg's **executable bid/ask + fees** breakeven (see section 1); no artificial proxy \`1−abs(Delta)\`. It is NOT a true future frequency, assignment probability, or a probability that no earlier touch occurred.

C. **Second probability / uncertainty.** Independently compare single-IV Black–Scholes to OIPD smile/surface CDF *only when market-data quality is sufficient*. Monte Carlo can stress tails, jump/gap and volatility regimes. Report model disagreement, stale information, confidence ranges. If fitted surface/underlying time base fails, do not silently report a consensus probability. Do not average contradictory models by arbitrary weights.

D. **Risk, payoff, and data reliability.**
- Long Call: fixed debit loss, right-tail upside; POP alone may undervalue positively skewed long calls.
- Long Put: fixed debit loss, left-tail upside bounded by strike; put time decay and downside drift matter.
- Short Put: net credit vs capital at risk and downside tail, not only high \`P_Q(OTM)\`; still no verified cash capacity in observer mode.
- Short Call: naked option's unbounded right-tail loss; no "safe 90%" grade. If covered with shares, show **separate stock+short-call combined payoff** only with verified cover.
- Protect against high POP paired with rare catastrophic loss; historical expected shortfall (CVaR), drawdown, worse-case gap scenarios and executable spread are mandatory to final ranking.

E. **Opportunity score 0–100 (separate from probability).**
- Data quality gates **reject or withhold** a result, not award arbitrary positive points.
- Output interpretable components \`distribution_accuracy / reward_efficiency / tail_loss / liquidity / event_exposure\` **per leg** with declared directional semantics.
- Candidate weights and normalization MUST be fitted/selected on historical **training** data and independently verified out-of-sample by strategy type, market regime, expiration and symbol. Explicit score version and as-of provenance.
- Do **not** combine four legs into one ranking without a common risk budget and selected user objective; different payoff tails make equal numeric scores misleading.
- **At this phase** return \`opportunity_score_0_100: null\`, \`score_status: PENDING_OUT_OF_SAMPLE_CALIBRATION\`. This is a deliberate no-fake-score design, not missing code.

## 4. Historical validation gate before the final score can be surfaced

1. Archive immutable real-time (or correctly timestamped delayed) option bid/ask, OI/volume, spot, IV, expiry, corporate actions, dividends and rates; time-align all fields. For a historical backtest do NOT query today's option chain to reconstruct yesterday's bid.
2. Build point-in-time event samples for each leg, multiple expirations (7/14/30/45/60 DTE), moneyness and IV regimes across several years/symbols; prevent same event or symbol regimes from leaking across train/test.
3. Use rolling train/validate/test, with purged or embargoed overlapping maturities; compare baselines: delta proxy, BSM Q, OIPD Q, and event/historical feature model. Use Brier score, log-loss, calibration diagrams and binomial confidence intervals for expiry OTM / expiry-profit frequency.
4. Separately evaluate net premium (bid sell / ask buy), realistic spread, fee, worst-case gap, tail losses, EV under a fitted **real-world** distribution, CVaR, coverage limitations and turnover. OTM realized outcomes are **NOT** actual broker assignment records.
5. Test score ablations per feature, bootstrap robustness, cross-symbol/year splits, four separately pre-registered models; no weights hand-picked after viewing final test samples.
6. Admit a formal score only if calibrated, stable and superior to simple baselines on locked holdout; report sample count, model version, uncertainty and abstention coverage.
7. Model must never output a buy/sell order or instruct automatic trade. The observer is read-only.

## 5. What the currently available public Yahoo adapter can and cannot do

The independent \`standalone_web/public_marketdata.py\` currently provides bid/ask/last, IV, OI/volume, expirations and **the latest daily bar close** as spot. A last trade time on an option is **not** the live bid/ask timestamp. Neither the quote synchronization nor forward dividend schedule are reliable enough to call a 90% result "observed forecast". Therefore do not wire research probabilities to the production Web until quote provenance and options terminology tests pass.

Data obtained via \`yfinance\` is unofficial Yahoo access, with personal-use restrictions; an open-source library is **not** an open licensed market-data feed.

## 6. Engineering milestones

- **R0** (this branch): 10-repository audit, legal provenance, original pure Python four-leg *theoretical* probability/payoff kernel and offline tests. **No edits to primary candidate strategy, Web or broker paths.**
- **R1**: Data-quality provenance contract / cache with read-only market adapter; reject unsynchronized snapshots and adjusted deliverable ambiguity.
- **R2**: Independent OIPD comparison and OptionLab analytical benchmark, documented discrepancies; 4-leg payoff scenarios and optional volatility-stress simulation.
- **R3**: Historical point-in-time dataset, calibration, coefficient/version governance; real-world frequency tests and holdout reports.
- **R4**: Only after R3 passes, Web displays 4 tabs each containing separate \`Q expiry OTM\`, \`Q POP\`, \`Tail risk\`, \`Liquidity\`, \`Quality\`, then validated \`Score/100\` + explanation. No trading action ever enabled.

**No development of V7 / 5s / SSSS. No Oracle deployment performed.**
