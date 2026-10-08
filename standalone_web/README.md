# Options Monitor V1 — 独立四方向期权分析 Web

**状态：V1 代码和界面交付。仅个人只读观察，不交易、不读取账户、不依赖 V7 / 5s / SSSS。**

完整因子取舍、冻结公式、研究证据和验收边界请阅读：

[OPTIONS_V1_FINAL.md](OPTIONS_V1_FINAL.md)

## 已支持

- 四种单腿方向：买入 Call、买入 Put、卖出 Call、卖出 Put。
- 公开美股/ETF 期权链：代码、到期日、Bid/Ask、IV、成交量、OI；由 Yahoo Finance 非官方 yfinance 提供，不需要券商或用户 API Key。
- 四个方向分别展示盈亏平衡、入场净权利金/成本、理论风险中性 Q 到期盈利和价外概率、固定价格压力情景与风险边界。
- 三因子最弱项综合 **0–100 规则参考分**：收益情景平衡、不利 20% 情景损失尺度、Bid/Ask 价差；拒绝无效行情，裸卖 Call 无限风险不生成数值分。
- 可选择到期日、按行权价或参考分排序，查看单张合约的完整分项解释；桌面和手机布局自适应。
- 只有只读 GET /api/v1/options 和 GET /api/v1/health；其它账户/持仓/订单 API 403，POST 不支持。

**不要误读评分：它不是经历史校准的获利率、指派概率、真实成交价或买卖建议。** Yahoo 当前股票价格为最近日线收盘，缺少与期权报价同步的时间戳；模型使用示意利率 0、示意股息率 0、费用每股 $0.01。没有合格报价或已到期时不打分。

## 安装和本地启动（Python 3.12+）

在仓库根目录执行：

    python3 -m pip install -r standalone_web/requirements-marketdata.txt
    python3 -m standalone_web.server --port 8765

浏览器打开：

    http://127.0.0.1:8765

若 Yahoo 限流、当前网络无法访问或该合约无有效 Bid/Ask，页面会解释原因，不生成虚构行情。服务只绑定 127.0.0.1，**不能绕开登录认证直接向公网开放**。

## 最终验收

    python3 -m pip install 'duckdb>=1.1,<2'
    python3 -m unittest discover -s research/four_leg_score -p 'test_*.py' -v
    python3 -m unittest discover -s standalone_web/tests -p 'test_*.py' -v
    node --check standalone_web/static/app.js

GitHub Actions：.github/workflows/options-monitor-v1-final-ci.yml

这次只修改了独立 Web 和新增相关验收文件；未合并 main、未部署 Oracle、未连接券商或运行真实下单。远程服务部署与数据源的实时可用性不是此源码验收已经完成的内容。

**阶段边界：V1 FROZEN。** 新指标研究和多年度参数再调优不属于本次交付。
