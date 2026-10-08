# SPY 2025 四种单腿期权：最小排名准入实验

**状态：PILOT CLOSED / 31 TESTS PASS / RANK RULE NOT PROMOTED / FORMAL SCORE NOT ENABLED。**

## 研究边界与远端审计

- 开始前真实 HEAD：`main=a478cea87f26c1c6667f51031c6a2178bcc808f4`，上轮研究 `research/spy-four-leg-capital-risk-v1=774ee0b99681d4b964603596d254255c97ce855e`。本轮只在 `research/spy-2025-ranking-gate-v1` 实施。
- 使用前轮未直接检验的年度 **SPY 2025**：公开镜像 `anahatsingh-ui/options-dataset-hist` 固定 commit `37f6c456fe1a4775c875673fb8ef907d5cd2fd66`。
- `spy/options_2025.parquet` 大小 58,216,546 bytes、Git blob SHA `133bf1d95c3479149bf4771bc8b3fd8b625064ce`；股票 `spy/underlying_prices.parquet` 大小 252,066 bytes、SHA `4c22934a77ba09ced10fd1c413b5d8c9e0cb4a8d`。GitHub Actions 中实际下载并校验了两文件。
- 实验脚本：`research/four_leg_score/spy_2025_ranking_gate.py`；测试：`research/four_leg_score/test_spy_2025_ranking_gate.py`；CI **PASS**：https://github.com/kuashan/kuashan-options-monitor/actions/runs/37812871030；制品 `spy-2025-ranking-gate-result` 存完整 JSON。
- 初次 CI 由于 DuckDB 保留字 `target` SQL 别名失败，但单元测试 31/31 已通过；仅重命名为 `desired_strike` 后重新运行成功，筛选及评估规则没有调整。

## 仅选择两个已冻结合约候选

严格重用前轮样本方法：每月第一个可用交易周三，剩余 20–45 个日历天、在同一年度到期；Bid>0、Ask≥Bid、相对中间价的价差≤25%、IV 为 3%–200%、K/S 为 85%–115%。每个入场日 × 到期日 × Call/Put 独立取最接近 ATM (K≈S) 和价外 5% (Call K≈1.05S，Put K≈0.95S) 的两张有效报价合约；择时和择合约只用已观察到的入场信息，不看未来收益。

- **买入 Call/Put**：因子 1 = 若到期价格朝有利方向变化 10% 的静态到期净盈亏；因子 2 = 亏损上限（买 Ask+每股 $0.01 示意费用），越低越好。
- **卖出 Call/Put**：因子 1 = 卖 Bid−每股 $0.01 示意费用净权利金；因子 2 = 到期股票朝不利方向变化 20% 的静态净盈亏，越高越好。
- 只有某候选在这两个指标上**均不差且至少一个更好**，才认定有 `ATM_DOMINATES` 或 `OTM_DOMINATES`；否则 `TRADEOFF_ABSTAIN`。没有权重、没有拟合参数、没有 0–100 分。
- 跨 Call/Put 的 favorable 与 adverse 情景用途不同；此方法只在同一 Leg、相同 entry+expiry 的两张合约间比较。**不能**当作四种方向的统一排序。
- 后验到期盈亏：Long 按 Ask、Short 按 Bid，并减每股 $0.01 示意费用；以同日正股收盘价计算期权到期内在价值，无法反映真实指派、保证金成本及盘中逐笔成交。

## 实际执行结果

- 观察日 **11** 个；不同到期日 **47** 个；所有入选合约都有与到期日同日匹配的股票收盘价代理（`stock_close_date_mismatch_rows=0`）。
- Call 每方向 **47** 对 ATM/OTM 5%，Put 每方向 **46** 对。每组 Long/Short 共用相同合约，对照数据高度相关，并非 186 次独立事件。

| 方向 | 固定 ATM 每股平均盈亏 | ATM 最差 5% 平均 | 固定 OTM5 每股平均盈亏 | OTM5 最差 5% 平均 | 两目标均优的组数 | 取舍/拒绝排名 |
|---|---:|---:|---:|---:|---:|---:|
| Long Call (47组) | +$1.3202 | -$15.1867 | -$0.6657 | -$2.4833 | 0 | 47/47 |
| Long Put (46组) | -$1.8217 | -$13.5067 | -$0.8039 | -$6.1300 | 0 | 46/46 |
| Short Call (47组) | -$1.6823 | -$20.9867 | +$0.6140 | -$4.5767 | 0 | 47/47 |
| Short Put (46组) | +$1.6917 | **-$48.0433** | +$0.7211 | **-$27.4400** | 0 | 46/46 |

单位美元／股。以上每张样本均假定从入场持有至到期；费用只包含明确的示意入场费，未模拟真实下单、结算、提前行权、利息、滑点与实际合约交割物；资金预算、权利金投入的百分比不能跨单腿直接比较。

### 盈利占比，仅供观察

| Leg | ATM | OTM5 |
|---|---:|---:|
| Long Call | 53.19% | 8.51% |
| Long Put | 23.91% | 10.87% |
| Short Call | 44.68% | 91.49% |
| Short Put | 76.09% | 89.13% |

高胜率不等于高期望收益，2025 年 OTM5 的卖 Call 仍有亏损尾部，卖 Put 的 ATM 平均收益较高但尾部亏损明显更大。

## 严格因子决策

1. **RETAIN as hard context / 风险边界**：真实 Bid/Ask 成本、Long 最大亏损、CSP 的现金担保需求、裸 Short Call 理论无限亏损、明确静态不利情景与样本尾部损失。
2. **REJECT as automatic single-score rank**：把“权利金最高”和“最差情景损失最小”强行求和。它们在这两种行权价之间通常是相互牵制的；本年度比较中 **0% 的候选对可以无权重、严格支配另一张**。
3. **NOT PROMOTED**：Pareto 规则未实际选择到合约，故无法据本实验声称提升盈亏/准确度；100% 拒绝排名不是投资模型的显著性结果，亦不意味着不存在其它有用排序因子。这反映的是**两个预定义收益/风险目标与两种行权价之间的结构性取舍**，不是统计概率校准。
4. **NEXT BOUNDARY**：下一轮如继续，必须明确**每个方向自己的风险预算/使用目的**，如最大可承担的每张美元亏损、Short Put 现金担保金额、Long 的投入权利金。然后在风险约束内比较有净经济价值的合约，**不再额外加入 RSI/IV Rank/无验证权重的 Greeks**。
5. **NO FALSE SAFETY**：对裸 Short Call 不推导有限资金回报率；对实际美式提前指派概率、实时同步 NBBO、经认证历史行情源和 0–100 机会分继续标记 NOT AVAILABLE / PENDING。

## 工程边界

本轮只新增 2025 排名研究脚本、6 项测试和本报告；既有研究回归总计 **31 项 PASS**，实数据研究运行 PASS。**main、独立 Web 页面、Oracle 服务器、实盘及 V7/5s/SSSS 均未变更。**

**最终状态：2025 PARETO RANKING PILOT CLOSED，强制排名方案 NOT PROMOTED，正式综合评分仍 NOT VALIDATED。**
