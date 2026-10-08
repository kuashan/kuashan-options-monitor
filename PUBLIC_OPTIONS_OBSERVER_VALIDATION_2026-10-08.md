# Options Monitor · Public Options Observer V1
状态：IMPLEMENTED / OFFLINE TEST PASS / LIVE DATA SMOKE PASS / ORACLE DEPLOYMENT NOT STARTED
日期：2026-10-08

## 本轮范围

- 开源行情访问：yfinance -> 非官方 Yahoo Finance 公开数据；无用户自有 API Key。
- 美股期权链：SPY/AAPL 等可输入的美股或 ETF，支持到期日选择、Calls/Puts、Strike、Bid、Ask、Last、Volume、OI、IV、Last Trade Date。
- 最近日 K 收盘价标记为历史收盘价而非实时价；HTTP 抓取时间不等于成交时间。
- 不显示虚构的 Grekks、实时价、权利金或模拟交易。
- 旧 Futu/OpenD、账户、SQLite、绩效等接口在公开观察模式均拒绝访问 (HTTP 403)；页面默认不查询。
- 仅监听 loopback 127.0.0.1:8765，不提供公网身份验证。
- 当前不与 IBKR、V7、5s、SSSS 或任何自动交易系统联动。
- 原始 main 备份分支不改动，所有新增开发位于 feature/public-options-observer-v1。

## GitHub Actions 验证（真实证据）

Run: https://github.com/kuashan/kuashan-options-monitor/actions/runs/37795711091
已验证的代码提交：611f71d970f446c987911a0eff914bb3959f8907
结果：SUCCESS
- Unit tests: Ran 28 tests, OK
- Python syntax validation: PASS
- yfinance dependency installation: PASS
- Public live smoke: AVAILABLE
- SPY expiry: 2026-10-08
- Call rows returned: 119
- Put rows returned: 128

注意：以上数据只是一次访问结果，不能证明没有时延、没有报价缺失、长期可用或适合交易。Oracle Cloud 环境网络连接尚未验证。

## 运行方式

    python3.12 -m pip install -r standalone_web/requirements-marketdata.txt
    python3.12 -m standalone_web.server --port 8765

本机浏览器：http://127.0.0.1:8765

## 未完成（不得声称完成）

- 香港股票期权链正式接入与覆盖校验
- 期权 Greeks 专业数据源
- 数据许可证与外部分发授权（yfinance 软件开源，不意味着雅虎数据授权）
- 独立 Oracle ARM 主机端到端测试、安全入口、回滚与部署
- 实际浏览器端到端验收
- 交易及券商账户功能（不在本次需求范围）

## 结论

公开行情观察模块 V1 已实现，并通过隔离环境单元测试与 SPY 真正联网请求。
此里程碑不等同于已经在服务器投入运行。
