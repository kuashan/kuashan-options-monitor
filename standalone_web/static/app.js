"use strict";

const byId = (id) => document.getElementById(id);
const views = ["status", "brief", "positions", "performance"];

function text(id, value) {
  byId(id).textContent = String(value ?? "—");
}

function formatValue(value) {
  if (value === null || value === undefined || value === "") return "未提供";
  if (typeof value === "boolean") return value ? "是" : "否";
  if (typeof value === "object") return JSON.stringify(value, null, 2);
  return String(value);
}

function addLine(parent, title, value) {
  const row = document.createElement("div");
  row.className = "keyval";
  const label = document.createElement("span");
  label.textContent = title;
  const detail = document.createElement("strong");
  detail.textContent = formatValue(value);
  row.append(label, detail);
  parent.append(row);
}

function showMessage(parent, value, isWarning = false) {
  const element = document.createElement("div");
  element.className = isWarning ? "notice" : "empty";
  element.textContent = value;
  parent.replaceChildren(element);
}

function showRaw(id, data) {
  text(id, data === null || data === undefined ? "暂无数据" : JSON.stringify(data, null, 2));
}

function issueReason(response) {
  const error = response?.error;
  if (typeof error === "string") return error;
  if (error && typeof error === "object") {
    return error.message || error.code || "数据源没有提供可用信息";
  }
  return "数据未就绪（检查配置、数据源与运行状态）";
}

async function load(view, query) {
  const params = new URLSearchParams(query);
  const response = await fetch("/api/v1/" + view + "?" + params.toString(), { cache: "no-store" });
  const body = await response.json();
  if (!response.ok) return { ok: false, error: body.error || "请求失败", data: null };
  return body;
}

function renderStatus(response) {
  const data = response.data;
  if (!response.ok || !data) {
    text("runtime-value", "不可用");
    text("runtime-caption", issueReason(response));
    return;
  }
  const summary = data.summary || {};
  const ok = summary.ok === true;
  text("runtime-value", ok ? "正常" : "待检查");
  text("runtime-caption", ok ? "运行快照通过检查" : "查看原始运行状态或检查系统配置");
}

function renderBrief(response) {
  const panel = byId("brief-panel");
  showRaw("brief-json", response.data);
  if (!response.ok || !response.data) {
    text("brief-value", "不可用");
    text("brief-caption", issueReason(response));
    showMessage(panel, issueReason(response), true);
    return;
  }
  const data = response.data;
  if (!data.available) {
    text("brief-value", "无快照");
    text("brief-caption", formatValue(data.reason));
    showMessage(panel, "当前账户或市场尚无可靠的每日决策快照。不会显示示例行情。");
    return;
  }
  text("brief-value", "可查看");
  text("brief-caption", "已有真实每日决策快照");
  panel.replaceChildren();
  const sections = Array.isArray(data.sections) ? data.sections : [data];
  addLine(panel, "覆盖范围", sections.length === 1 ? "1 个报告范围" : sections.length + " 个报告范围");
  addLine(panel, "可操作状态", data.effective_actionability || "未判定");
  for (const section of sections.slice(0, 4)) {
    const brief = section.brief || {};
    if (brief.market) addLine(panel, "市场", brief.market);
    if (brief.account) addLine(panel, "账户", brief.account);
    if (brief.market_trading_date) addLine(panel, "交易日期", brief.market_trading_date);
    if (Array.isArray(brief.data_gaps) && brief.data_gaps.length) {
      const warning = document.createElement("div");
      warning.className = "notice";
      warning.textContent = "此报告存在 " + brief.data_gaps.length + " 项数据缺口，建议先核对报告质量。";
      panel.append(warning);
    }
  }
}

function renderPositions(response) {
  const tbody = byId("positions-tbody");
  const data = response.data;
  if (!response.ok || !data || !Array.isArray(data.rows)) {
    text("position-value", "不可用");
    text("position-caption", issueReason(response));
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 6;
    td.className = "empty";
    td.textContent = issueReason(response);
    tr.append(td);
    tbody.replaceChildren(tr);
    return;
  }
  const rows = data.rows;
  text("position-value", rows.length);
  text("position-caption", "原始账本返回的未平仓记录数量");
  tbody.replaceChildren();
  if (!rows.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 6;
    td.className = "empty";
    td.textContent = "查询成功，账本中暂无符合条件的未平仓期权记录。";
    tr.append(td);
    tbody.append(tr);
  }
  for (const record of rows) {
    const tr = document.createElement("tr");
    const fields = [
      record.symbol, (record.side || "") + " " + (record.option_type || ""),
      record.strike, record.expiration_ymd, record.contracts_open, record.status
    ];
    for (const field of fields) {
      const td = document.createElement("td");
      td.textContent = formatValue(field);
      tr.append(td);
    }
    tbody.append(tr);
  }
  const exposure = data.evidence_scope || {};
  text("positions-footer", "持仓账本： " + formatValue(exposure.ledger_positions || "已查询") +
    " · 行情与交割状态可能独立于账本更新，请以来源时间为准");
}

function renderPerformance(response) {
  const panel = byId("performance-panel");
  showRaw("performance-json", response.data);
  if (!response.ok || !response.data) {
    showMessage(panel, issueReason(response), true);
    return;
  }
  const data = response.data;
  panel.replaceChildren();
  addLine(panel, "统计期间", data.period?.kind || "未提供");
  addLine(panel, "截止日期", data.period?.as_of_date || "未提供");
  const cashflow = data.option_net_cashflow || {};
  const cny = cashflow.cny_total;
  if (cny !== undefined) {
    addLine(panel, "累计净现金流（CNY 证据）", typeof cny === "object" ? "查看结构化报告" : cny);
  }
  const winRate = data.sell_option_win_rate;
  if (winRate !== undefined) {
    addLine(panel, "卖出期权胜率", typeof winRate === "object" ? "查看结构化报告" : winRate);
  }
  if (data.quality?.missing?.length) {
    const warning = document.createElement("div");
    warning.className = "notice";
    warning.textContent = "有 " + data.quality.missing.length + " 项收益计算证据缺失，详细数据见原始报告。";
    panel.append(warning);
  }
  if (!panel.children.length) showMessage(panel, "没有可展示的统计字段，请展开原始结构化报告。");
}

async function refresh() {
  const button = byId("refresh");
  button.disabled = true;
  text("load-status", "正在查询现有快照（不会触发扫描或交易）…");
  const query = {
    market: byId("market").value,
    account: byId("account").value.trim(),
    period: byId("period").value
  };
  const results = await Promise.all(views.map(async (view) => {
    try {
      return await load(view, query);
    } catch (error) {
      return { ok: false, data: null, error: "服务连接失败" };
    }
  }));
  renderStatus(results[0]);
  renderBrief(results[1]);
  renderPositions(results[2]);
  renderPerformance(results[3]);
  const successes = results.filter((result) => result.ok).length;
  text("load-status", successes + "/" + results.length + " 个只读查询可用");
  text("time-stamp", "本地刷新时间：" + new Date().toLocaleString("zh-CN"));
  button.disabled = false;
}

async function checkHealth() {
  try {
    const response = await fetch("/api/v1/health", { cache: "no-store" });
    const result = await response.json();
    text("service-state", result.ok ? "Web 服务可达 · 只读" : "Web 服务异常");
  } catch (error) {
    text("service-state", "Web 服务连接异常");
  }
}

byId("refresh").addEventListener("click", refresh);
byId("market").addEventListener("change", refresh);
byId("period").addEventListener("change", refresh);
for (const link of document.querySelectorAll(".nav-link")) {
  link.addEventListener("click", () => {
    document.querySelectorAll(".nav-link").forEach((item) => item.classList.remove("selected"));
    link.classList.add("selected");
  });
}
checkHealth();
refresh();


// Public-market observation is completely independent of Futu/OM accounts.
let publicChain = null;
let latestPublicRequest = 0;

function showPublicError(message) {
  publicChain = null;
  text("options-status", message);
  text("option-spot", "—");
  text("option-expiry-label", "—");
  text("option-count", "—");
  const tr = document.createElement("tr");
  const cell = document.createElement("td");
  cell.colSpan = 9;
  cell.className = "empty";
  cell.textContent = message;
  tr.append(cell);
  byId("option-chain-tbody").replaceChildren(tr);
  text("option-chain-footer", "当前数据不可用；没有使用虚构报价或自动回退到其他券商。");
}

function formatQuote(value, digits = 2) {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toLocaleString("en-US", { maximumFractionDigits: digits, minimumFractionDigits: digits })
    : "—";
}

function showPublicSide() {
  if (!publicChain) return;
  const side = byId("option-side").value;
  const rows = Array.isArray(publicChain[side]) ? publicChain[side] : [];
  const sourceCount = publicChain.counts?.[side + "_source"];
  const truncated = publicChain.counts?.[side + "_truncated"];
  text("option-count", String(rows.length) + " / " + (sourceCount ?? "未知"));
  const tbody = byId("option-chain-tbody");
  tbody.replaceChildren();
  if (!rows.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 9;
    td.className = "empty";
    td.textContent = "该到期日没有可显示的 " + side + " 合约。";
    tr.append(td);
    tbody.append(tr);
    return;
  }
  for (const option of rows) {
    const tr = document.createElement("tr");
    const fields = [
      formatQuote(option.strike),
      formatQuote(option.bid),
      formatQuote(option.ask),
      formatQuote(option.last),
      formatValue(option.volume),
      formatValue(option.open_interest),
      option.iv !== null ? formatQuote(option.iv * 100, 1) + "%" : "—",
      option.last_trade_at || "未知",
      option.quote_state === "valid_bid_ask" ? "有效双边报价" : "无有效双边报价",
    ];
    for (let i = 0; i < fields.length; i++) {
      const td = document.createElement("td");
      td.textContent = fields[i];
      if (i === 8 && option.quote_state !== "valid_bid_ask") td.className = "missing-quote";
      tr.append(td);
    }
    tbody.append(tr);
  }
  text("option-chain-footer",
    "数据抓取时间：" + publicChain.observed_at_utc +
    " · 最近日 K 日期：" + (publicChain.spot_last_daily_bar_at || "未知") +
    " · " + (publicChain.from_cache ? "命中约 4 分钟缓存" : "本次获取") +
    (truncated ? " · 已按接近现价选择前 400 张合约；其余未显示" : "") +
    " · 不可用于确认实时可成交报价。");
}

async function loadPublicOptions() {
  const requestId = ++latestPublicRequest;
  const button = byId("load-options");
  button.disabled = true;
  text("options-status", "正在读取公开期权链（无券商账户）…");
  const symbol = byId("option-symbol").value.trim().toUpperCase();
  const expiry = byId("option-expiry").value;
  const params = new URLSearchParams({ symbol });
  if (expiry) params.set("expiry", expiry);
  try {
    const response = await fetch("/api/v1/options?" + params, { cache: "no-store" });
    const body = await response.json();
    if (requestId !== latestPublicRequest) return;
    if (!response.ok || !body.ok || !body.data) {
      showPublicError("公开行情不可用：" + (body.error || "未知错误"));
      return;
    }
    publicChain = body.data;
    const select = byId("option-expiry");
    select.replaceChildren();
    for (const date of publicChain.expirations || []) {
      const option = document.createElement("option");
      option.value = date;
      option.textContent = date;
      option.selected = date === publicChain.expiry;
      select.append(option);
    }
    text("option-spot", formatQuote(publicChain.spot_last_daily_close));
    text("option-expiry-label", publicChain.expiry);
    text("option-provider", "Yahoo · yfinance");
    text("options-status", publicChain.symbol + " · " +
      "已获取" + (publicChain.from_cache ? "（缓存）" : "") +
      " · 非实时，报价时效不保证");
    showPublicSide();
  } catch (error) {
    if (requestId === latestPublicRequest) showPublicError("行情服务无法连接或解析失败。");
  } finally {
    if (requestId === latestPublicRequest) button.disabled = false;
  }
}

byId("load-options").addEventListener("click", loadPublicOptions);
byId("option-side").addEventListener("change", showPublicSide);
byId("option-expiry").addEventListener("change", loadPublicOptions);
byId("option-symbol").addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    byId("option-expiry").value = "";
    loadPublicOptions();
  }
});
byId("option-symbol").addEventListener("change", () => {
  const select = byId("option-expiry");
  select.replaceChildren(new Option("自动选择最近到期日", ""));
});
loadPublicOptions();
