# 四种单腿期权：机构实践与最小有效因子研究（2026-10-08）

**状态**：RESEARCHED / 因子选择属研究假设 / 正式 0–100 评分 NOT VALIDATED / WEB NOT MODIFIED / NO TRADING。

**研究基准**：原 main=a478cea87f26c1c6667f51031c6a2178bcc808f4；当前 research/four-leg-score-v1 审计基准 a009796adef9861c312cfc16d54cd5e6112dbc24。本次只增加研究记录，不修改已提交的研究引擎、Web、交易模块。

## 一、机构资料导出的原则

1. 交易台的定价、风险限额、流动性成本、情景模拟和模型验证分别解决不同问题，不能将所有 Greeks、IV、技术指标直接加权为“安全程度”。
2. 风险中性概率 Q 是市场定价下的分布，不是实际发生概率 P；Delta 主要是价格敏感度，用 1−abs(Delta) 替代实际“不指派概率”错误。
3. OCC 的 STANS 用价格、隐含波动率等风险因子的联合分布和 99% Expected Shortfall 评估保证金风险；CME SPAN 用价格×波动率×到期时间扫描、短期权最低风险值。这证明独立尾部风险约束有必要，但个人分析器不可声称等效清算所模型。
4. Cboe 指数期权历史研究显示卖波动率可能获得波动率风险溢价；OptionMetrics 的 2026 研究说明极端时期隐含波动率对未来实际波动的低估会十分严重。所以 IV 大、权利金高，不代表卖方一定划算。
5. 任何因子在未经过时间顺序的样本外增量验证前只能列为候选，不能给固定正向加权。

## 二、因子清单——做减法

| 因子 | 决议 | 实质与去重 |
|---|---|---|
| S/K/T、合约类型、行权方式、调整后交割物和乘数 | REQUIRED INPUT | 四方向盈亏模型必须有，合约乘数不能猜为 100 |
| 同步的标的价格/期权 Bid Ask/对应时间戳 | HARD GATE | 缺价、交叉报价、不能验证同时性，则评分不可用；期权 lastTradeDate 不是 bid/ask 更新时间 |
| 手续费/价差 | CORE | 买按 Ask、卖按 Bid；成交量和 OI 只能辅助判断，不重复算多个流动性分 |
| 到期价内/价外概率 Q 与到期盈利概率 Q | DISPLAY, NOT BOTH SCORED | 都来自相同价格分布但阈值不同；它们与 Delta、OTM 百分比、IV 强相关 |
| 实际 P 分布下净预期收益/风险单位 | CORE CANDIDATE | 真正衡量收益能否补偿风险；P 未校准时不得伪造期望收益 |
| 极端亏损、压力情景、Expected Shortfall | CORE CANDIDATE | 尾部风险不能被高胜率覆盖；无经验证的 P 分布时只能输出确定性压力情景，不伪称概率化 ES |
| 期限匹配的事前预测 RV 与 IV 的差 | CHALLENGER | 对卖方/买方方向有不同经济解释；过去 RV 不是未来 RV，需要前向验证；先不与 IV Rank 叠加 |
| IV smile / skew、OIPD surface | CONDITIONAL | 足够多有效行权价、无套利拟合/时间一致后作为第二概率估计，不强制全部合约拟合 |
| Delta、Gamma、Vega、Theta | DIAGNOSTICS | 展示风险敏感度、参与持有期间情景重估，不能和衍生出的概率/IV再分别加分 |
| OI、Volume | SUPPORTING | 辅助质量证据，非独立收益因子；0 与缺失有别 |
| 财报/分红/除息日 | EVENT GATE | 对 Long 可能是风险偏好的来源，对 Short 可带来跳空/提前行权；不一刀切“财报减20分” |
| IV Rank / IV percentile | OBSERVE ONLY | 历史 IV 数据需求高，与 IV/IV−RV 重叠 |
| RSI/MACD/SMA、季节性、趋势 | OBSERVATION CHALLENGER | 必须证明对净收益/概率校准有新增有效信息才可晋级 |
| GEX/情绪/Put Call 比 | REJECT V1 | 当前四单腿数据路径和预测价值不充分；避免加噪 |
| 年化权利金收益最大化 | REJECT AS SOLE RANK | 极短 DTE 的年化夸张、忽略成本与尾部 |
| 1−abs(Delta)=不被指派概率 | REJECT | 美式短期权可提前指派，不等于到期价外概率 |

## 三、四个方向分别处理（不得用一个未分方向的公式）

| 模式 | 重点收益指标 | 风险边界 |
|---|---|---|
| Long Call | 买 Ask 的真实成本、盈亏平衡、P(到期盈利)、右尾收益情景 | 最大亏损为已付权利金+费；低 POP 仍可能有正经济期望 |
| Long Put | 买 Ask、盈亏平衡、跌幅情景及 Put skew 溢价 | 最大亏损为已付成本；高 IV 带来贵权利金/跌后 IV 变化 |
| Short Put | 卖 Bid 的净权利金、所需担保、下跌压力损失、Q 到期 OTM 与盈利概率 | 股价跌到 0 可产生接近 K−净权利金的每股亏损；当前无账号不能声称资金已足额担保 |
| Short Call | 卖 Bid、到期两种概率、上涨冲击损失 | 裸卖 Call 理论亏损无上限。Covered Call 是持股+卖 Call 的**组合**，当前公开行情模式不能假定持股 |

## 四、最小有效模型架构

- 第 0 层 Data Gate：输入真实性、最新程度、合约规格、事件和报价可执行性。失败即 DATA_INSUFFICIENT，无正式评分。
- 第 1 层 Probability Q：Black–Scholes 单 IV 基线；仅当跨行权价报价足够可靠时，用 OIPD volatility smile/surface 独立对照。不任意平均模型概率。
- 第 2 层 Profit & Risk：真实 Bid/Ask、费用和方向性到期 P/L；持有中 S/IV/T 的价格冲击情景；分开披露尾部无界风险。
- 第 3 层 Probability P：独立建模，必须历史回测、滚动前向校准；美式提前指派另需真实事件标签，否则不可估计。
- 第 4 层 Score：最初只测试 3 个核心候选：净收益相对风险预算、尾部风险、流动性摩擦。第 4 个备选为前向预测的 IV−RV 价值因子。分 Long/Short Call/Put 单独验证并制定评分映射；完全不采用直接拼接十个仓库原权重。
- 显示层保留 P_Q(OTM)、P_Q(Profit)、Greeks、IV/skew 等解释，但**不把展示因子误当独立贡献项**。

## 五、什么证据才允许因子进入正式评分

1. 获取可信的历史逐日/逐时**期权链**及对应标的、报价时间、交易费用、执行价、股息、财报、公司行动；仅有股票历史价不能还原当日 Put/Call 收益。
2. 依照时间滚动训练/验证/测试，重叠到期样本做 embargo，分层比较 7/14/30/45/60 DTE、涨跌/高低 IV、不同股票行业与年份。
3. 概率 Q 与新 P 的 Brier/log loss、校准曲线、样本计数和概率段置信区间；实际指派不能用“到期价内”替换事件标签。
4. 综合评分的净收益、最大回撤、尾部损失、流动性成本及相对最简基线的增量；每加一个因子做消融、置换与跨市场状态稳健性检验。
5. 若新增因子不能在未见样本改善或对缺失数据过度敏感，则 REJECT。必要时维持“未评分、仅显示客观数据”的状态。
6. 对研究版本冻结算法和 source provenance；未经实际数据验证的 0–100 与“安全百分比”不得展示为正式结果。

## 六、查阅的权威资料（来源）

- OCC：期权提前指派 https://www.optionseducation.org/referencelibrary/faq/options-assignment
- OIC：Delta 解释 https://www.optionseducation.org/advancedconcepts/delta
- OCC：STANS Margin Methodology https://www.theocc.com/risk-management/margin-methodology
- CME：SPAN 方法（中文） https://www.cmegroup.cn/clearing/span-methodology-overview/
- CME：SPAN 清算模型参考 https://www.cmegroup.com/solutions/risk-management.html
- CFA：Risk-Neutral Distributions https://rpc.cfainstitute.org/research/foundation/2004/option-implied-risk-neutral-distributions-and-risk-aversion
- CFA：Options Strategies https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/options-strategies
- Cboe：Put Writing VRP https://www.cboe.com/insights/posts/white-paper-shows-volatility-risk-premium-facilitated-higher-risk-adjusted-returns-for-put-index
- OptionMetrics：Forward Implied vs Realized (2026) https://optionmetrics.com/blog/how-accurate-is-implied-volatility/
- Cboe：Options Liquidity https://www.cboe.com/insights/posts/order-types-and-off-screen-liquidity-what-you-see-isnt-always-what-you-get
- Review of Finance：bid/ask transaction cost in option returns https://academic.oup.com/rof/article/27/1/289/6510952
- Federal Reserve 2026 修订版（取代 SR11-7）：https://www.federalreserve.gov/frrs/guidance/supervisory-guidance-on-model-risk-management.htm
- Annual Review of Statistics 2026：Proper Scoring Rules https://doi.org/10.1146/annurev-statistics-042424-050626

**工程结论**：本轮只研究、记录、做因子减法；不改动现有研究计算引擎、Web 观察页面、Oracle 服务和交易逻辑。正式下一阶段是数据质量与概率模型独立对比，而不是直接上线 0–100 分。
