# Options Monitor V1 — Final Scope and Model Freeze（正式交付说明）

状态：FOUR-LEG WEB IMPLEMENTED / V1 RULE SCORE IMPLEMENTED / HISTORICAL PROBABILITY CALIBRATION NOT VALIDATED / NO BROKER / NO ORDERS。

## 本次一次性交付三项

### 1. 排除没有增量证据的因子

过去研究覆盖 SPY 2022、2023、2024、2025：
- Black–Scholes 风险中性（Q）到期价外概率与 Delta 近似比较：均保留为独立诊断，不能冒充真实世界（P）盈利率或不会被美式期权提前指派的概率。
- 固定 Black–Scholes / Delta 50:50 概率组合：研究中未全面超过最佳单一基准，所以不加入 V1 分数。
- 固定 20 日趋势修正：2023 未见样本中 Call、Put 的概率 Brier 均比简单模型更差，故排除该规则。
- IV Rank、OTM%、Gamma、Theta、Vega、技术指标：尚无独立增量净收益证据，而且多项来源于相同的价格/时间/波动率曲面。V1 不重复计分。
- 单看胜率、最高权利金、主观十因子加权：排除作为唯一收益/风险排名目标。2022 卖 Put 与 2024 卖 Call 的历史样本存在高盈利频率、负平均净收益的反例。
- 2025 ATM vs OTM5 的两个情景无权重 Pareto 排名，所有对照发生收益与尾部风险取舍，故不作为自动唯一推荐规则。
- 本次“排除”指 V1 方案，没有把未研究的所有因子宣称为“科学无效”。

### 2. V1 已冻结的 0–100 规则型参考评分

保留三个量，并使用最弱项限制，完全不训练权重：

输入：股票最近一根日 K 收盘价 S、期权行权价 K、Bid、Ask、隐含波动率 IV、剩余日历天数 T。数据源仅 Yahoo/yfinance 的非官方公开期权链。计算使用的交易成本是假设每股入场费 0.01 美元、示意无风险利率 0%、连续股息率 0%；不是当前市场上的可执行利率/实际费用。

- 买入按 Ask，卖出按 Bid；到期每股净收益 = 内在价值减买入权利金费用，或净卖出权利金减到期内在价值。
- 有利价格情景：股票相对 S 沿该期权方向变化 10%。
- 不利价格情景：股票相对 S 逆该期权方向变化 20%。
- 收益风险平衡 R = max(0,PL有利) / [max(0,PL有利)+max(0,-PL不利)]。若分母零，R 为零。
- 不利情景风险存活因子 D = max(0, 1 - max(0,-PL不利)/(0.20*S))。
- 买卖价差质量因子 L = max(0, 1 - [(Ask-Bid)/Mid]/0.25)。

综合规则参考评分：Score = round(100 * min(R, D, L))。

三个量均属于情景假设，存在相关性（R、D 都使用相同的不利收益场景），绝不声称独立预测因子或实际收益统计。弱项约束不需要假设“成功率权重”。不发布已验证机会评分（formal_opportunity_score_0_100 始终为 null），不将 Score 解释成真实命中率、推荐买卖或概率。

数据缺损或可疑时拒绝评分：没有现价、Bid/Ask 无效、IV 无效、已到期/当天到期、Bid/Ask 相对价差超过 25% 或卖方无法扣除示意费用，则 score_0_100 为 null，给出明确原因。

裸卖 Short Call：理论最大亏损无上限，不能建立与其他腿可比的有限资金风险分母，故 **不产生数值综合参考分**，仍完整显示净权利金、到期概率 Q、盈亏平衡、有限情景净收益和无限风险警示。不假设已有正股覆盖。Short Put 不假定现金已担保，实际资金与保证金信息不可用。

### 3. 四方向 Web 统一实现

已替换旧隐藏账户视图，提供四个标签：Long Call、Long Put、Short Call、Short Put。
- 标的、到期日、公开市场期权链读取。
- 列表展示有效报价、行权价、IV、到期盈亏平衡、风险中性 Q 理论盈利概率、不利 20% 场景损失、0–100 规则参考分（可用时）。
- 合约详情显示净入场现金流、有利/不利到期 P/L、最大理论损失（无限损失）、三个因子得分条、计算限制和数据质量说明。
- 排序按行权价或参考分；不是实际交易建议。按接近现价 ±15% 筛选或查看可用行。
- 无券商账户接入、无买卖订单接口、无自动交易。GET /api/v1/options 返回原始期权链并分别追加 analyses.long_call、analyses.short_call、analyses.long_put、analyses.short_put。GET /api/v1/health 继续可用；所有其它 /api/v1/* 路由仍为 403，POST 未支持。
- 美股期权 Yahoo 仅是公共观察源；股票现价实际上来自最新日线收盘、不是同期盘中报价；期权 Bid/Ask 无同步报价时间。所有含分数的结果明确标为 UNCALIBRATED_RULE_REFERENCE_DAILY_CLOSE。

## 本地运行

从独立仓库根目录（Python 3.12 及以上）依次执行：

    python3 -m pip install -r standalone_web/requirements-marketdata.txt
    python3 -m standalone_web.server --port 8765

访问 http://127.0.0.1:8765

静态页面无需构建 Node/npm。实际源可能受网络、地理位置、Yahoo 限流影响。未部署 Oracle；Web 绑定 127.0.0.1 且不含登录模块，因此 **不得直接公开到公网**。若将来需要手机或域名访问，必须先由用户另外授权有身份认证的代理部署。

## 验收与不应再推进的内容

验收 CI：.github/workflows/options-monitor-v1-final-ci.yml
- 四个腿、理论引擎、研究质量门槛、净收益/资金与尾部风险原有回归。
- 四方向评分公式、拒绝无效行情、裸卖无限亏损、Web HTTP 返回、静态四标签、禁止账户/交易 API、Python/JS 语法。
- 只保留明确的 Bug 修复，不再无限开启 R2/R3/... 研究、不随意加更多因子。
- 真实 Oracle/手机网络部署与真实 Yahoo 数据联通是 **未执行的不同交付任务**；本次仅保证独立仓库 V1 代码、静态 Web、API 与离线验收。
- 明确 NOT VALIDATED：真实世界概率校准、真实期权可成交 NBBO、实际美式期权提前指派概率、预测获利精度、系统性的策略投资收益。

V1 产品和规则评分按上述边界冻结。
