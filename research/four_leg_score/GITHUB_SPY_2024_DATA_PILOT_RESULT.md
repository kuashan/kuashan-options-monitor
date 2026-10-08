# SPY 2024 GitHub 历史期权数据：实物核验结果

**2026-10-09（北京时间）** | **状态：DATASET STRUCTURE VERIFIED / EOD RESEARCH FEASIBLE / FORECAST CALIBRATION NOT STARTED**

## 已验证的数据源

- 源仓库：https://github.com/anahatsingh-ui/options-dataset-hist
- 固定源码 commit：37f6c456fe1a4775c875673fb8ef907d5cd2fd66
- 数据：spy/options_2024.parquet（56,948,550 bytes，Git blob SHA 8e0b7ca48dffa92fe93ceeffefdfce8557eab74a）
- 股票：spy/underlying_prices.parquet（252,066 bytes，Git blob SHA 4c22934a77ba09ced10fd1c413b5d8c9e0cb4a8d）
- CI：https://github.com/kuashan/kuashan-options-monitor/actions/runs/37805963809
- 复现实验：research/four_leg_score/github_data_pilot.py（仅研究分支，不接入现有 Web）

GitHub Actions 中通过真实 HTTPS 下载数据、校验大小和 Git blob SHA、使用 DuckDB 查询真实 Parquet 内容。SHA 一致证实下载字节等于当前 GitHub 固定 commit 的 blob，**不等于独立证明每条行情来自原始交易所。**

## 2024 年完整文件统计（实际执行结果）

| 指标 | 值 |
|---|---:|
| 期权合约-日期记录 | 2,292,800 |
| 实际交易日期 | 253 |
| 最早期权交易日 | 2024-01-02 |
| 最晚期权交易日 | 2024-12-31 |
| Call 行数 | 1,146,400 |
| Put 行数 | 1,146,400 |
| 无效/不可用 Bid Ask（bid<=0、ask<bid、缺失） | 106,797（约 4.66%） |
| IV 缺失/非正/非有限值 | 0 |
| Delta 缺失/非有限值 | 0 |
| Strike 缺失/非法 | 0 |
| 日期缺失或 expiry<date | 0 |
| 合约 ID 缺失 | 0 |
| underlying 价格文件内有效交易日 | 6,570 |
| 期权记录按日无法匹配到有效标的 close | 2 |
| 精确期权盘中 Quote Timestamp | 不提供 |

备注：数据提供方没有具名原始交易所/feed、仅声明 EOD 数据；包含 IV/Greeks 并不证明其值均可靠，尤其需对 0DTE、深度实值、高 IV 和不合理价差做过滤。不可把原始价差与模型估算价格混淆。对 EOD 日线允许按同日 quote date + close 研究，但时点精度/交易执行不确定性要在报告中披露。

## 与前次 R1 结论的关系

原有 Yahoo 当前行情接口缺少历史全链；**现在找到独立公开的历史 Parquet，足够为研究提供历史期权链素材**。此源没有 Quote Time，因此**不能通过盘中实时同步门槛**；未来针对 EOD 研究应独立建立按交易日对齐的验证口径，不要篡改盘中 quote_gate.py 使不完整实时数据错误 PASS。

## 决议：不扩大开发

- **PASS**：存在实际 GitHub 历史期权数据、Call/Put、Bid Ask、IV、Greeks、行权价、日期、标的收盘价，并具备 2024 年完整 253 交易日与 2.29M 行。
- **REJECT**：此前笼统“GitHub 没有可研究的历史期权链，必须购买数据”的判断。
- **PENDING**：跨年份真实性与报价质量（市场源不具名）、按 DTE/流动性过滤、原始价格与标的时点精度、分红/行权方式、合约调整、无历史指派事件记录。
- **NOT RUN**：未进行历史真实世界 P 概率校准、正式综合评分、任何交易、Oracle 部署或 Web 改动。
- **NEXT（只在用户要求继续时）**：只用 SPY 2024 数据做一个固定 20–45 DTE、有效报价、按 expiry 结果统计的最小基线验证；不训练十因子、不加入 AAPL/QQQ/IWM，不扩展通用数据管道。报告样本数、不同到期概率区间的真实命中率与基线 Brier，并说明日终报价同步尚未证明。

该研究只供个人分析，外部开源仓库代码及数据未经复制进默认分支或公开 Web。
