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
