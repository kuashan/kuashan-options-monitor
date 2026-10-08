"use strict";

/* Public-data only. Never touches the original options-monitor account APIs. */
const $ = (id) => document.getElementById(id);
const MODES = {
  long_call: {
    label: "买入 Call", source: "calls",
    risk: "最多损失支付的全部权利金和费用",
    explain: "以 Ask 买入；价格上涨有潜在收益，买方承担时间价值风险"
  },
  long_put: {
    label: "买入 Put", source: "puts",
    risk: "最多损失支付的全部权利金和费用",
    explain: "以 Ask 买入；价格下跌可能获益，Put 权利金也可能全部损失"
  },
  short_call: {
    label: "卖出 Call", source: "calls",
    risk: "裸卖 Call 理论最大亏损无上限 · 不提供数值评分",
    explain: "以 Bid 卖出；当前没有验证持股，不假定是备兑 Call"
  },
  short_put: {
    label: "卖出 Put", source: "puts",
    risk: "股价跌至零时仍需承担重大亏损；不假定有充足现金担保",
    explain: "以 Bid 卖出；资金占用与接货义务独立于收取的权利金"
  }
};

let chain = null;
let currentLeg = "short_put";
let selectedContract = null;
let requestSequence = 0;

function fmt(x, digits=2) {
  return typeof x === "number" && Number.isFinite(x)
    ? x.toLocaleString("en-US", {minimumFractionDigits: digits, maximumFractionDigits: digits})
    : "—";
}
function fmtPercent(x, digits=1) {
  return typeof x === "number" && Number.isFinite(x) ? fmt(x*100, digits)+"%" : "—";
}
function text(id, value) {
  const el = $(id);
  if (el) el.textContent = value == null ? "—" : String(value);
}
function cell(tr, str, className) {
  const td=document.createElement("td");
  td.textContent=String(str);
  if (className) td.className=className;
  tr.append(td);
  return td;
}
function unavailable(msg) {
  const tr=document.createElement("tr");
  const td=cell(tr,msg,"empty");
  td.colSpan=8;
  $("option-chain-tbody").replaceChildren(tr);
  $("detail-body").replaceChildren();
  const note=document.createElement("div");
  note.className="empty";
  note.textContent=msg;
  $("detail-body").append(note);
  text("detail-state","数据不足");
}
function addStat(parent,label,value,style="") {
  const el=document.createElement("div");
  el.className="detail-stat";
  const a=document.createElement("span");
  a.textContent=label;
  const b=document.createElement("strong");
  b.textContent=value;
  if(style) b.className=style;
  el.append(a,b);
  parent.append(el);
}
function addNote(parent,msg,warning=false) {
  const p=document.createElement("div");
  p.className=warning?"warning detail-warning":"detail-note";
  p.textContent=msg;
  parent.append(p);
}
function allRows() {
  const source=MODES[currentLeg].source;
  const rows=Array.isArray(chain?.[source])?chain[source]:[];
  const spot=chain?.spot_last_daily_close;
  const filtered=$("filter-moneyness").value==="near" && Number.isFinite(spot) && spot>0
    ? rows.filter(o => Number.isFinite(o.strike) && Math.abs(o.strike/spot-1)<=0.15)
    : rows.slice();
  if ($("sort-options").value==="score") {
    filtered.sort((a,b)=>{
      const av=a.analyses?.[currentLeg]?.score_0_100;
      const bv=b.analyses?.[currentLeg]?.score_0_100;
      return ((typeof bv==="number"?bv:-1)-(typeof av==="number"?av:-1))
        || (a.strike-b.strike);
    });
  } else {
    filtered.sort((a,b)=>a.strike-b.strike);
  }
  return filtered;
}
function fillDetail(option) {
  const body=$("detail-body");
  body.replaceChildren();
  if(!option) {
    addNote(body,"没有可展示的合约；可更换到期日、调整筛选或等待数据恢复。");
    text("detail-state","未选择");
    return;
  }
  const a=option.analyses?.[currentLeg];
  if(!a) {
    addNote(body,"本行尚无四方向分析结果，请重新获取数据。",true);
    text("detail-state","无法分析");
    return;
  }
  text("detail-state",a.score_0_100==null?"评分不可用":"参考 "+a.score_0_100+"/100");
  const head=document.createElement("div");
  head.className="detail-title";
  const title=document.createElement("strong");
  title.textContent=MODES[currentLeg].label+" · "+chain.symbol+" · K "+fmt(option.strike);
  const meta=document.createElement("span");
  meta.textContent=chain.expiry+" · "+(option.contract||"未提供合约编号");
  head.append(title,meta);
  body.append(head);

  const stats=document.createElement("div");
  stats.className="detail-stats";
  const premium = a.net_entry_per_share==null ? "—" : "$"+fmt(a.net_entry_per_share);
  addStat(stats,a.entry_kind==="DEBIT"?"买入支出／股":"卖出净收／股",premium);
  addStat(stats,"到期盈亏平衡",fmt(a.breakeven));
  addStat(stats,"Q 理论到期盈利概率",fmtPercent(a.p_expiry_profit_q));
  addStat(stats,"Q 理论到期价外概率",fmtPercent(a.p_expiry_otm_q));
  addStat(stats,"标的有利 10% 情景盈亏",a.favorable_10pct_pnl_per_share==null?"—":"$"+fmt(a.favorable_10pct_pnl_per_share));
  addStat(stats,"标的不利 20% 情景盈亏",a.adverse_20pct_pnl_per_share==null?"—":"$"+fmt(a.adverse_20pct_pnl_per_share),
    a.adverse_20pct_pnl_per_share<0?"negative":"");
  addStat(stats,"理论最大亏损／股",a.unbounded_max_loss?"无限":a.max_loss_per_share==null?"—":"$"+fmt(a.max_loss_per_share));
  addStat(stats,"综合参考分",a.score_0_100==null?"不适用":a.score_0_100+"/100");
  body.append(stats);

  if(a.score_factors) {
    const factorTitle=document.createElement("h3");
    factorTitle.textContent="三项有效因子 · 最弱项限制";
    body.append(factorTitle);
    const factors=[
      ["收益／不利情景平衡",a.score_factors.reward_to_scenario_balance],
      ["不利 20% 情景存活度",a.score_factors.adverse_20pct_survival],
      ["Bid/Ask 价差质量",a.score_factors.bid_ask_quality]
    ];
    for(const [name,value] of factors) {
      const row=document.createElement("div");
      row.className="factor";
      const label=document.createElement("span");
      label.textContent=name;
      const progress=document.createElement("div");
      progress.className="factor-track";
      const bar=document.createElement("div");
      bar.className="factor-fill";
      bar.style.width=(Math.max(0,Math.min(1,value||0))*100).toFixed(2)+"%";
      progress.append(bar);
      const amount=document.createElement("b");
      amount.textContent=fmtPercent(value);
      row.append(label,progress,amount);
      body.append(row);
    }
  }
  addNote(body,a.score_reason||"暂无可信参考评分说明",true);
  if(a.p_expiry_profit_q!==null) {
    addNote(body,"Black–Scholes 概率是风险中性 Q 理论量，不是已校准的真实盈利率；不代表美式期权不会提前指派。");
  }
  addNote(body,"数据来源是 Yahoo 期权链及标的最近日线收盘价。它们缺少经验证的同步报价时间；零利率、零连续股息率及 $0.01/股费用均为示意假设。");
}
function render() {
  document.querySelectorAll("[data-leg]").forEach(btn=>{
    const chosen=btn.dataset.leg===currentLeg;
    btn.classList.toggle("active",chosen);
    btn.setAttribute("aria-selected",String(chosen));
  });
  text("leg-label",MODES[currentLeg].label);
  text("leg-risk",MODES[currentLeg].risk);
  text("leg-explain",MODES[currentLeg].explain);

  if(!chain) {
    unavailable("尚无公开期权数据；请输入标的代码并查询。");
    return;
  }
  const side=MODES[currentLeg].source;
  const rows=allRows();
  const sourceCount=chain.counts?.[side+"_source"]??"未知";
  text("option-count",rows.length+" / "+sourceCount);
  text("option-score-state",currentLeg==="short_call"?"无限风险：无分数":"规则参考 · 未校准");
  const tbody=$("option-chain-tbody");
  tbody.replaceChildren();
  if(!rows.length) {
    unavailable("当前方向或筛选条件下没有可显示的合约。");
    return;
  }
  // All option values are placed via textContent, never innerHTML.
  for(const option of rows) {
    const a=option.analyses?.[currentLeg];
    const tr=document.createElement("tr");
    tr.className="option-row"+(selectedContract===option.contract?" selected":"");
    cell(tr,fmt(option.strike));
    cell(tr,fmt(option.bid)+" / "+fmt(option.ask));
    cell(tr,fmtPercent(option.iv));
    cell(tr,fmt(a?.breakeven));
    cell(tr,fmtPercent(a?.p_expiry_profit_q));
    cell(tr,a?.adverse_20pct_pnl_per_share==null?"—":"$"+fmt(a.adverse_20pct_pnl_per_share),
       a?.adverse_20pct_pnl_per_share<0?"negative":"");
    cell(tr,typeof a?.score_0_100==="number"?a.score_0_100+"/100":"—",
       typeof a?.score_0_100==="number"?"score-cell":"missing-quote");
    const td=document.createElement("td");
    const button=document.createElement("button");
    button.type="button";
    button.className="detail-button";
    button.textContent="查看";
    button.setAttribute("aria-label","分析 "+chain.symbol+" 行权价 "+fmt(option.strike));
    button.addEventListener("click",()=>{
      selectedContract=option.contract;
      fillDetail(option);
      renderSelectedRow();
      if(window.matchMedia("(max-width: 700px)").matches){
        $("detail").scrollIntoView({behavior:"smooth",block:"start"});
      }
    });
    td.append(button);tr.append(td);
    tbody.append(tr);
  }
  let picked=rows.find(o=>o.contract===selectedContract);
  if(!picked) {
    picked=rows.find(o=>typeof o.analyses?.[currentLeg]?.score_0_100==="number")||rows[0];
    selectedContract=picked?.contract??null;
  }
  fillDetail(picked);
  renderSelectedRow();
  const truncated=chain.counts?.[side+"_truncated"];
  text("option-chain-footer",
    "数据抓取："+(chain.observed_at_utc||"未知")+
    " · 股票日线："+(chain.spot_last_daily_bar_at||"未知")+
    (truncated?" · 合约表最多返回靠近现价的 400 行":"")+
    (chain.from_cache?" · 使用缓存":"")+
    " · 未验证同步报价 · 排序仅供比较。");
}
function renderSelectedRow(){
  for(const row of $("option-chain-tbody").querySelectorAll("tr.option-row")){
    // The option rows remain in source order within the chosen filter.
    // Selection is represented by the accessible detail panel and active button.
    row.classList.remove("selected");
    const button=row.querySelector("button");
    if(button&&button.getAttribute("aria-label")?.includes("")) {
      // Visual focus is retained by the clicked button; no invented row identities.
    }
  }
}
function fail(message) {
  chain=null;
  selectedContract=null;
  text("options-status",message);
  text("option-spot","—");
  text("option-expiry-label","—");
  text("option-count","—");
  text("option-score-state","不可用");
  unavailable(message);
  text("option-chain-footer","行情或服务不可用；没有生成虚构合约或评分。");
}
async function loadOptions(){
  const request=++requestSequence;
  const button=$("load-options");
  button.disabled=true;
  text("options-status","正在请求公开期权链（不读取券商账户）…");
  const symbol=$("option-symbol").value.trim().toUpperCase();
  const expiry=$("option-expiry").value;
  const params=new URLSearchParams({symbol});
  if(expiry) params.set("expiry",expiry);
  try {
    const response=await fetch("/api/v1/options?"+params.toString(),{cache:"no-store"});
    const json=await response.json();
    if(request!==requestSequence)return;
    if(!response.ok||!json.ok||!json.data){
      fail("行情不可用："+(json.error||"来源未提供数据"));
      return;
    }
    chain=json.data;
    selectedContract=null;
    const select=$("option-expiry");
    select.replaceChildren();
    for(const day of (chain.expirations||[])){
      const opt=document.createElement("option");
      opt.value=day;opt.textContent=day;
      opt.selected=day===chain.expiry;
      select.append(opt);
    }
    text("option-spot",fmt(chain.spot_last_daily_close));
    text("option-expiry-label",chain.expiry||"—");
    text("options-status",chain.symbol+" · 期权链读取成功"+(chain.from_cache?"（缓存）":"")+" · 只读");
    render();
  } catch(e){
    if(request===requestSequence)fail("无法读取期权数据或服务连接失败。");
  } finally {
    if(request===requestSequence)button.disabled=false;
  }
}
async function health(){
  try{
    const r=await fetch("/api/v1/health",{cache:"no-store"});
    const j=await r.json();
    text("service-state",j.ok?"● 服务正常 · 只读":"服务不可用");
  } catch(e){text("service-state","● 服务连接失败");}
}
for(const tab of document.querySelectorAll("[data-leg]")){
  tab.addEventListener("click",()=>{
    currentLeg=tab.dataset.leg;
    selectedContract=null;
    render();
  });
}
$("load-options").addEventListener("click",loadOptions);
$("option-expiry").addEventListener("change",loadOptions);
$("sort-options").addEventListener("change",render);
$("filter-moneyness").addEventListener("change",render);
$("option-symbol").addEventListener("keydown",(event)=>{
  if(event.key==="Enter"){
    event.preventDefault();
    $("option-expiry").replaceChildren(new Option("最近到期",""));
    loadOptions();
  }
});
$("option-symbol").addEventListener("change",()=>{
  $("option-expiry").replaceChildren(new Option("最近到期",""));
});
health();
loadOptions();
