# R1 — 期权历史数据与报价一致性最小验证（2026-10-08）

**阶段状态：QUOTE GATE IMPLEMENTED；历史概率校准 BLOCKED_BY_DATA；正式评分未启用。**

审计远端起点：main a478cea87f26c1c6667f51031c6a2178bcc808f4；公开观察版 e86d40d8de77d2564f4befb9dd5457af68abb7ab；研究分支开始时 5ebf24f58b20df4434852a3f4604d47de8b4cad3。

## 数据来源的实际能力

| 数据来源 | 可用信息 | 本阶段判断 |
|---|---|---|
| 仓库现有 Yahoo / yfinance | 当前可用合约及 Bid/Ask、行权价、IV、OI、成交量；标的股价取最近一根**日线收盘** | 观察 PASS，正式概率评分 BLOCKED。期权 lastTradeDate 是成交时间，不是 Bid/Ask 的报价时间；拉取完成时间也不是行情时间 |
| Cboe 官方免费历史下载 | 历史期权成交量、Put/Call 比 | 不足以还原历史单张期权 Bid/Ask，因此不能用于真实净收益验证 |
| Cboe DataShop Option EOD Summary | 15:45 ET 和 EOD NBBO 快照，标的报价，价格及 OI；IV/Greeks 选配 | 历史价格证据合适，但属于需购买的数据产品。本阶段未购买 |
| Cboe DataShop Option Quotes | 分钟/自选间隔 NBBO、对应标的报价等 | 适合更细时间同步，数据成本与范围暂不必要 |
| OptionMetrics IvyDB US | 长期历史期权 EOD，Bid/Ask、IV/Greeks、标的与公司行动等 | 成熟机构级数据源，不是免费公共历史期权链 |
| 今后存储公开行情快照 | 只可积累从开始采集后的前瞻样本 | 无法补造以前的报价；若仍缺真实 quote 时间，也无法证明时间同步 |

查核依据：
- yfinance 期权接口源码：https://github.com/ranaroussi/yfinance/blob/main/yfinance/ticker.py
- Cboe 免费历史成交量：https://www.cboe.com/us/options/market_statistics/historical_data/
- Cboe 历史 EOD 商品：https://datashop.cboe.com/option-eod-summary
- Cboe 期权间隔报价：https://datashop.cboe.com/option-quote-intervals
- OptionMetrics IvyDB：https://optionmetrics.com/united-states/

特别禁止：用今天的期权价格加过去的股票价格伪造历史期权链；用理论定价替代历史真实成交价，却报告经真实交易数据验证的收益。

## 这轮唯一工程改动

新增 research/four_leg_score/quote_gate.py 与 research/four_leg_score/test_quote_gate.py，只在研究层评估数据是否**有资格进入理论概率模型**。

- 只有具备明确盘中标的现价、标的和期权报价各自的有效时间戳、合格 Bid/Ask、IV、合约身份及到期日，且报价时间不陈旧、不相互冲突，才输出 THEORETICAL_INPUT_READY。
- 缺少这些字段时返回 INSUFFICIENT 与具体原因；不能拿最近日 K 收盘价冒充现价，也不能拿 lastTradeDate 冒充报价更新时间。
- 采用既有研究核对窗口：单一报价距获取时间最多 30 分钟，两种报价时间差最多 15 分钟，价差超过 25% 不接受。它们是**研究用质量阈值**，不是行业标准或正式的盈利因子。
- 就算数据达到 THEORETICAL_INPUT_READY，正式机会评分仍然为 null；这只说明理论 Q 概率的输入具备基本条件，不代表价格源经交易所证明或概率经过历史校准。
- 当前 yfinance 观察版必定缺上述关键字段，四个方向一律 INSUFFICIENT。**研究层不偷偷补值，不改变现有行情页面。**

## 验收边界与结论

- 覆盖四种单腿，正常模拟数据仅允许理论 Q 输入资格，绝不生成正式 0–100 分或实际指派概率。
- 验证 Yahoo 结构性缺口、陈旧/未来/不一致时间戳、零报价/穿价/异常宽价差和缺失 IV 的拒绝行为。
- CI 继续运行既有四腿测试及 Web 观察版回归，不部署、不连券商、不改变服务器，也不加入新评分因子。
- R1 QUOTE GATE 可以在单测通过后 CLOSED；但 R1 HISTORICAL CALIBRATION 仍保持 BLOCKED_BY_DATA。暂不购买数据库，暂不架设庞大历史采集系统。
- 下一阶段须先获得真实、时间对齐的历史期权报价样本。用户确认后仅选 1–2 个标的做极小校准实验；无数据则不做未经证明的回测。

原始 main、公开观察 Web、V7/5s/SSSS 和 Oracle 均不修改。
