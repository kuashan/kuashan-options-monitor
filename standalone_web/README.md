# Standalone Options Monitor Web MVP（独立 Web 只读版本）

## 边界

- 完全独立于 SiftAlpha V7、5s、SSSS，不共享其交易执行、配置或数据库。
- 原始 options-monitor 策略、账本、扫描与交易规则不改动。
- 原作者之前退役的旧 WebUI 不恢复；新功能全部放在 standalone_web 目录。
- 所有页面仅通过 om-agent 读取既有系统状态、决策快照、未平仓记录和期权收益。
- 不提供订单执行、自动扫描、手动下单、账户配置写入或 SQLite 写入接口。
- 当前底层券商主要为 Futu OpenD；IBKR 适配尚未实现。没有数据时显示缺失，不伪造行情。

## 本地运行（需 Python 3.12+）

从仓库根目录执行：

    python3.12 -m standalone_web.server --port 8765

打开 http://127.0.0.1:8765

Web 自身只用 Python 标准库；om-agent 仍需按原仓库要求先配置环境、账户和数据源。
未配置 OpenD 或不存在扫描/账本记录时，网页正常显示不可用或无数据，不会出现模拟资产信息。

### 只读接口

- GET /api/v1/health：仅检查 Web 服务本身。
- GET /api/v1/status?market=us：runtime_status。
- GET /api/v1/brief?market=us&account=lx：daily_decision_brief_read。
- GET /api/v1/positions?market=us&account=lx：option_positions_read（open）。
- GET /api/v1/performance?market=us&account=lx&period=mtd：option_performance_report。

market 仅支持 us/hk，period 仅支持 mtd/ytd。
账户标签可以省略，但底层部分查询可能要求指定；出错时必须显示真实错误。

## Oracle ARM 服务器部署原则（后续阶段，当前未部署）

1. 独立操作系统用户、独立目录、独立 Python 环境，不与 SiftAlpha V7 或其他策略共用数据库和进程。
2. Web 服务仅绑定 127.0.0.1:8765，不开放公网端口。
3. 手机远程访问通过带强身份认证的 HTTPS 反向代理或 Cloudflare Access；Web 组件本身没有登录系统，不得直接公网开放。
4. IBKR 需要单独设计只读适配器及数据校验，不能将 Futu 账户数据映射伪装成 IBKR 数据。
5. systemd、域名、证书、密钥、生产数据库和服务器配置都须独立授权后部署。现在不操作 Oracle 服务器。

## 测试

    python3.12 -m unittest discover -s standalone_web/tests -v

测试内容包括请求参数白名单、静态页面、健康端点、禁止非白名单工具与 POST 写入。
测试通过不代表已验证真实券商接入、实时行情或 Oracle ARM 环境。

## 里程碑

- M0：独立 Web 项目边界与只读界面、API 初版。
- M1：已有 Futu/SQLite 真数据环境验收；未配数据时显示缺失。
- M2：IBKR 只读数据适配独立研究与实现。
- M3：Oracle ARM 隔离部署、私网或零信任访问、备份回滚验收。

## M1：公开期权行情观察（Yahoo/yfinance）

本阶段优先实现不使用券商 API、无账户连接、无交易功能的 **美股期权链查询**。
选择 Yahoo Finance 的非官方开源访问库 `yfinance`，不是授权的专业交易行情。
该库开源并不意味着 Yahoo 行情数据开放许可；应遵循 Yahoo 使用条款，仅个人观察，**不得未经授权公开再分发数据**。

### 安装附加行情依赖

从仓库根目录运行（可使用专用虚拟环境）：

    python3.12 -m pip install -r standalone_web/requirements-marketdata.txt
    python3.12 -m standalone_web.server --port 8765

打开 http://127.0.0.1:8765，在「公开期权行情观察」中输入 SPY/AAPL/其他美股代码。
无需 Futu OpenD、无需 IBKR、无需 Yahoo API Key。

### 数据与限制

- GET /api/v1/options?symbol=SPY
- GET /api/v1/options?symbol=SPY&expiry=YYYY-MM-DD
- 提供可用到期日、Call/Put、行权价、有效双边报价、最近成交价、成交量、OI、IV、最后成交时间。
- 股票基准价格是 **最近日线收盘价**，不是实时股票行情。
- 报价时间没有官方统一时效保证。HTTP 返回的获取时间不等于数据源真实更新时间。
- 缺少买卖盘、bid=0、ask<bid、IV 不可用等情形会明确保留缺失状态，不计算中间价、年化利润或构造 Delta。
- 输出按接近现价最多 400 行/方向，显示来源总量与截断状态；接口 4 分钟成功缓存，失败不会伪造成旧报价。
- Yahoo 可能限流、阻断服务器机房 IP，或变更接口；需要在最终 Oracle 环境单独做联网验收，不允许回退到虚构数据。
- 港股期权尚未接入，不把香港股票现货数据当成期权链。
- 当前 Web 上的原始期权账本与现金/持仓面板仍属于既有 Futu 功能；没有 Futu 配置时可显示不可用，但不影响此公开行情观察模块。
- 不对用户开放公网端口，后续服务器使用身份验证代理访问。**没有登录模块，直接公网开放是不安全的。**

本阶段不提供期权推荐、Greeks 模拟值、策略自动交易、真实账户风险或券商持仓。
