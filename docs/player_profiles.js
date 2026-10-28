/* Local replay player profiles. Layout references: DOTABUFF and OpenDota; no remote player API. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.ReplayProfiles = factory();
})(typeof window !== "undefined" ? window : globalThis, function () {
  "use strict";
  const VIEWS = {overview: "概览", matches: "比赛记录", heroes: "英雄统计", peers: "队友", opponents: "对手"};
  const TITLES = {mvp: "MVP", wealth: "富豪", kills: "破敌", towers: "破军", support: "偏将", denies: "补王", soul: "英魂"};
  const valid = value => typeof value === "number" && Number.isFinite(value) && value >= 0;
  const esc = value => String(value == null ? "" : value).replace(/[&<>"']/g, c => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"}[c]));
  const number = (value, digits = 0) => value == null ? "暂无数据" : Number(value).toFixed(digits);
  const compact = value => value == null ? "暂无数据" : value >= 10000 ? (value / 1000).toFixed(1) + "K" : number(value);
  const percent = value => value == null ? "暂无数据" : number(value, 1) + "%";
  const playerHref = id => "#player=" + encodeURIComponent(id) + "&view=overview";
  const matchHref = id => "#match=" + encodeURIComponent(id) + "&sub=overview";
  const dateKey = match => valid(match.start) ? match.start : 0;

  function average(records, field) {
    const values = records.map(r => r.player[field]).filter(valid);
    return {value: values.length ? values.reduce((a, b) => a + b, 0) / values.length : null, samples: values.length};
  }
  function kda(records) {
    const rows = records.filter(r => ["kills", "deaths", "assists"].every(k => valid(r.player[k])));
    const totals = ["kills", "deaths", "assists"].map(k => rows.reduce((sum, r) => sum + r.player[k], 0));
    return {value: rows.length ? (totals[0] + totals[2]) / Math.max(totals[1], 1) : null,
      samples: rows.length, line: rows.length ? totals.map(v => number(v / rows.length, 1)).join(" / ") : "暂无数据"};
  }
  function recordSummary(records) {
    const known = records.filter(r => r.won !== null);
    const wins = known.filter(r => r.won).length;
    return {games: records.length, wins, losses: known.length - wins, unknown: records.length - known.length,
      winRate: known.length ? 100 * wins / known.length : null, kda: kda(records)};
  }
  function heroStats(records) {
    const groups = new Map();
    for (const record of records) {
      const key = record.player.hero || "unknown";
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(record);
    }
    return [...groups].map(([key, rows]) => ({key, name: rows[0].player.hero_zh || key,
      image: rows[0].player.hero_image || "", ...recordSummary(rows), gpm: average(rows, "gpm"),
      xpm: average(rows, "xpm"), last: rows[0].match.date || "时间未知"}))
      .sort((a, b) => b.games - a.games || b.wins - a.wins || a.key.localeCompare(b.key));
  }
  function relationshipStats(records, opponents = false) {
    const peers = new Map();
    for (const record of records) {
      const seen = new Set();
      for (const peer of record.match.players || []) {
        if (!peer.id || peer.id === record.player.id || !["radiant","dire"].includes(peer.team) || !["radiant","dire"].includes(record.player.team) ||
            (opponents ? peer.team === record.player.team : peer.team !== record.player.team) || seen.has(peer.id)) continue;
        seen.add(peer.id);
        if (!peers.has(peer.id)) peers.set(peer.id, {player: peer, records: []});
        peers.get(peer.id).records.push(record);
      }
    }
    return [...peers.values()].map(row => ({player: row.player, lastSeen: row.records[0].match.date || "时间未知", ...recordSummary(row.records)}))
      .sort((a, b) => b.games - a.games || b.wins - a.wins || a.player.id.localeCompare(b.player.id));
  }
  const peerStats = records => relationshipStats(records, false);
  const opponentStats = records => relationshipStats(records, true);
  function buildProfile(player, matches) {
    const records = [];
    for (const match of [...matches].sort((a, b) => dateKey(b) - dateKey(a) || String(b.id).localeCompare(String(a.id)))) {
      for (const p of match.players || []) {
        if (p.id !== player.id) continue;
        const known = ["radiant", "dire"].includes(match.winner) && ["radiant", "dire"].includes(p.team);
        records.push({match, player: p, won: known ? p.team === match.winner : null});
      }
    }
    const honors = Object.fromEntries(Object.keys(TITLES).map(key => [key, 0]));
    for (const r of records) for (const title of r.player.titles || []) if (Object.prototype.hasOwnProperty.call(honors, title.key)) honors[title.key]++;
    return {player, records, ...recordSummary(records), heroes: heroStats(records), peers: peerStats(records), opponents: opponentStats(records), honors,
      gpm: average(records, "gpm"), xpm: average(records, "xpm"),
      damage: average(records, "hero_damage"), healing: average(records, "healing"),
      lastSeen: records.length ? records[0].match.date || "时间未知" : "暂无比赛"};
  }
  function filterRecords(records, hero = "all", result = "all") {
    return records.filter(r => (hero === "all" || r.player.hero === hero) &&
      (result === "all" || (result === "win" && r.won === true) || (result === "loss" && r.won === false) || (result === "unknown" && r.won === null)));
  }
  function heroImage(row) {
    const image = /^https:\/\/(?:[a-z0-9-]+\.)*steamstatic\.com\//i.test(row.image || "") ? row.image : "";
    return `<span class="rp-hero-image" aria-hidden="true"><span>${esc(Array.from(row.name || "?")[0])}</span>${image ? `<img data-hero-image loading="lazy" alt="" src="${esc(image)}">` : ""}</span>`;
  }
  function heroCell(row) { return `<span class="rp-hero-label">${heroImage(row)}<span>${esc(row.name)}</span></span>`; }
  function duration(seconds) {
    return valid(seconds) ? Math.floor(seconds / 60) + ":" + String(Math.floor(seconds % 60)).padStart(2, "0") : "暂无数据";
  }
  function resultLabel(row) { return row.won === null ? "结果未知" : row.won ? "胜利" : "失败"; }
  function resultClass(row) { return row.won === null ? "rp-neutral" : row.won ? "rp-win" : "rp-loss"; }
  function badgeList(player) {
    return (player.titles || []).map(t => `<span class="rp-award" title="${esc(t.reason)}">${esc(t.name)}</span>`).join("") || '<span class="rp-muted">—</span>';
  }
  function itemIcons(player) {
    return `<div class="rp-items">${(player.items || []).slice(0,6).map(item => {
      const image = /^https:\/\/(?:[a-z0-9-]+\.)*steamstatic\.com\//i.test(item.image || "") ? item.image : "";
      const name = item.zh || item.key || "物品";
      return `<span class="rp-item" role="img" aria-label="${esc(name)}" title="${esc(name)}"><span>${esc(Array.from(name)[0])}</span>${image ? `<img data-item-image src="${esc(image)}" alt="" loading="lazy">` : ""}</span>`;
    }).join("") || '<span class="rp-muted">—</span>'}</div>`;
  }
  function matchesTable(records, limit) {
    const rows = limit ? records.slice(0, limit) : records;
    if (!rows.length) return '<div class="rp-empty">没有符合条件的比赛</div>';
    return `<div class="rp-table-wrap"><table class="rp-table"><thead><tr><th>英雄 / 比赛</th><th>结果</th><th>K / D / A</th><th>GPM / XPM</th><th>时长</th><th>终局装备</th><th>称号</th></tr></thead>
      <tbody>${rows.map(r => `<tr><td><a class="rp-match-link" href="${matchHref(r.match.id)}">${heroCell({name:r.player.hero_zh || r.player.hero, image:r.player.hero_image})}<small>${esc(r.match.date || "时间未知")} · #${esc(r.match.id)}</small></a></td>
        <td class="${resultClass(r)}">${resultLabel(r)}</td><td>${number(r.player.kills)} / ${number(r.player.deaths)} / ${number(r.player.assists)}</td>
        <td>${number(r.player.gpm)} / ${number(r.player.xpm)}</td><td>${duration(r.match.duration)}</td><td>${itemIcons(r.player)}</td><td class="rp-awards-cell">${badgeList(r.player)}</td></tr>`).join("")}</tbody></table></div>`;
  }
  function heroTable(rows) {
    if (!rows.length) return '<div class="rp-empty">暂无英雄记录</div>';
    return `<div class="rp-table-wrap"><table class="rp-table"><thead><tr><th>英雄</th><th>场次</th><th>胜率</th><th>KDA</th><th>GPM / XPM</th><th>最近出场</th></tr></thead>
      <tbody>${rows.map(row => `<tr><td>${heroCell(row)}</td><td>${row.games}</td><td>${percent(row.winRate)}</td><td title="有效样本 ${row.kda.samples}/${row.games} 场">${number(row.kda.value,2)}</td><td>${number(row.gpm.value)} / ${number(row.xpm.value)}</td><td>${esc(row.last)}</td></tr>`).join("")}</tbody></table></div>`;
  }

  function mount(options) {
    const {root, players, matches, avatarHtml} = options;
    const state = {id:null, view:"overview", hero:"all", result:"all", page:1, query:""};
    let current = null;
    root.innerHTML = `<div class="rp-layout"><aside class="rp-directory"><label for="profileSearch">玩家资料 <span>${players.length} 人</span></label>
      <input id="profileSearch" type="search" placeholder="搜索玩家昵称" autocomplete="off"><div id="profileList" class="rp-player-list"></div></aside>
      <main id="profileDetail" class="rp-detail" aria-live="polite"></main></div>`;
    const list = root.querySelector("#profileList"), detail = root.querySelector("#profileDetail");
    const link = p => `<a class="player-link player-identity" href="${playerHref(p.id)}">${avatarHtml(p)}<span>${esc(p.name)}</span></a>`;
    function directory() {
      const filtered = players.filter(p => p.name.toLocaleLowerCase().includes(state.query.toLocaleLowerCase()));
      list.innerHTML = filtered.map(p => `<a class="rp-player ${p.id === state.id ? "active" : ""}" href="${playerHref(p.id)}" ${p.id === state.id ? 'aria-current="page"' : ""}>
        ${avatarHtml(p)}<span><b>${esc(p.name)}</b><small>${p.games} 场 · ${esc(p.role)}</small></span></a>`).join("") || '<p class="rp-empty">没有匹配的玩家</p>';
    }
    root.querySelector("#profileSearch").addEventListener("input", e => { state.query = e.target.value; directory(); });
    function profileHeader(profile) {
      const p = profile.player;
      return `<header class="rp-header"><div class="rp-person">${avatarHtml(p)}<div><div class="rp-eyebrow">PLAYER PROFILE · 练习赛档案</div><h2>${esc(p.name)}</h2>
        <div class="rp-header-meta"><span>${esc(p.role)}</span>${p.provisional ? '<span class="rp-status">评分暂定</span>' : ""}${p.identity_status === "unresolved" ? '<span class="rp-status">身份待确认</span>' : ""}<span>最近出场 ${esc(profile.lastSeen)}</span></div></div></div>
        <div class="rp-rating"><small>对黑综合分</small><strong>${number(p.rating,1)}</strong><span>登记 MMR ${p.mmrNum == null ? "未登记" : number(p.mmrNum)}</span></div></header>
      <p class="rp-scope">数据范围：本项目已录入的 ${profile.games} 场练习赛 · 昵称取最新比赛记录，固定别名优先 · 非完整天梯战绩</p>
      <div class="rp-kpis">
        <div><small>胜率</small><strong>${percent(profile.winRate)}</strong><span>${profile.wins} 胜 / ${profile.losses} 负${profile.unknown ? " / " + profile.unknown + " 场结果未知" : ""}</span></div>
        <div><small>KDA</small><strong>${number(profile.kda.value,2)}</strong><span>场均 ${profile.kda.line}</span></div>
        <div><small>场均 GPM</small><strong>${number(profile.gpm.value)}</strong><span>有效样本 ${profile.gpm.samples}/${profile.games} 场</span></div>
        <div><small>场均 XPM</small><strong>${number(profile.xpm.value)}</strong><span>有效样本 ${profile.xpm.samples}/${profile.games} 场</span></div>
        <div><small>场均英雄伤害</small><strong>${compact(profile.damage.value)}</strong><span>有效样本 ${profile.damage.samples}/${profile.games} 场</span></div>
        <div><small>英雄池 / 称号</small><strong>${profile.heroes.length}<em> / ${Object.values(profile.honors).reduce((a,b)=>a+b,0)}</em></strong><span>使用英雄数 / 获得称号次数</span></div>
      </div>`;
    }
    function overview(profile) {
      const last = profile.records.slice(0,10);
      return `<div class="rp-overview"><div><section class="rp-card"><div class="rp-section-head"><h3>近期状态</h3><span>最近 ${last.length} 场</span></div>
        <div class="rp-form">${last.map(r=>`<a href="${matchHref(r.match.id)}" class="${resultClass(r)}" title="${esc((r.player.hero_zh || r.player.hero) + " · " + r.match.date + " · " + resultLabel(r))}">${r.won === null ? "?" : r.won ? "W" : "L"}</a>`).join("") || '<p class="rp-empty">暂无比赛</p>'}</div>
        <p class="rp-muted">从左至右为最新到最早，点击可查看对局。</p></section>
        <section class="rp-card"><div class="rp-section-head"><h3>最近比赛</h3><a href="${playerHref(state.id).replace("view=overview","view=matches")}">全部比赛 →</a></div>${matchesTable(profile.records,5)}</section></div>
        <div><section class="rp-card"><div class="rp-section-head"><h3>常用英雄</h3><a href="${playerHref(state.id).replace("view=overview","view=heroes")}">查看全部 →</a></div>
          ${profile.heroes.slice(0,4).map(h=>`<div class="rp-top-hero">${heroCell(h)}<span><b>${h.games} 场</b><small>${percent(h.winRate)} 胜率</small></span></div>`).join("") || '<p class="rp-empty">暂无英雄记录</p>'}</section>
        <section class="rp-card"><div class="rp-section-head"><h3>单场荣誉</h3><span>项目规则 v1</span></div><div class="rp-honors">${Object.entries(TITLES).map(([key,name])=>`<div class="${profile.honors[key] ? "earned" : ""}"><span>${esc(name)}</span><b>${profile.honors[key]}</b></div>`).join("")}</div><p class="rp-muted">同一场可获得多个称号；数据缺失的项目会暂停评选。</p></section></div></div>`;
    }
    function matchesView(profile) {
      const rows = filterRecords(profile.records, state.hero, state.result);
      const pages = Math.max(1,Math.ceil(rows.length/10));
      state.page = Math.min(pages,Math.max(1,state.page));
      return `<section class="rp-card"><div class="rp-filter-row"><label>英雄 <select id="profileHero"><option value="all">全部英雄</option>${profile.heroes.map(h=>`<option value="${esc(h.key)}" ${state.hero===h.key ? "selected" : ""}>${esc(h.name)}</option>`).join("")}</select></label>
        <label>结果 <select id="profileResult">${Object.entries({all:"全部结果",win:"胜利",loss:"失败",unknown:"结果未知"}).map(([key,name])=>`<option value="${key}" ${state.result===key ? "selected" : ""}>${name}</option>`).join("")}</select></label><span>找到 ${rows.length} / ${profile.records.length} 场</span></div>
        ${matchesTable(rows.slice((state.page-1)*10,state.page*10))}
        <div class="rp-pagination"><button data-page="${state.page-1}" ${state.page===1 ? "disabled" : ""}>上一页</button><span>第 ${state.page} / ${pages} 页</span><button data-page="${state.page+1}" ${state.page===pages ? "disabled" : ""}>下一页</button></div></section>`;
    }
    function relationsView(profile, opponents = false) {
      const rows = opponents ? profile.opponents : profile.peers;
      return `<section class="rp-card"><div class="rp-section-head"><h3>${opponents ? "对手交手记录" : "共同出场的队友"}</h3><span>${opponents ? "仅统计敌方玩家 · 胜率以本玩家为视角" : "仅统计同队比赛"}</span></div>${rows.length ? `<div class="rp-table-wrap"><table class="rp-table"><thead><tr><th>玩家</th><th>${opponents ? "交手场次" : "同队场次"}</th><th>胜 / 负</th><th>${opponents ? "对抗胜率" : "同队胜率"}</th><th>最近${opponents ? "交手" : "同队"}</th></tr></thead><tbody>${rows.map(p=>`<tr><td>${link(p.player)}</td><td>${p.games}</td><td>${p.wins} / ${p.losses}${p.unknown ? "（未知 " + p.unknown + "）" : ""}</td><td>${percent(p.winRate)}</td><td>${esc(p.lastSeen)}</td></tr>`).join("")}</tbody></table></div>` : `<div class="rp-empty">暂无${opponents ? "对手交手" : "同队"}记录</div>`}</section>`;
    }
    function updateHash() {
      const query = new URLSearchParams({player:state.id,view:state.view});
      if (state.view === "matches") {
        query.set("hero",state.hero); query.set("result",state.result); query.set("page",String(state.page));
      }
      window.location.hash = query.toString();
    }
    function render() {
      if (!current) {
        detail.innerHTML = '<section class="rp-card rp-empty">找不到该玩家。请从左侧选择已录入的玩家。</section>';
        return;
      }
      detail.innerHTML = profileHeader(current) + `<nav class="rp-tabs" aria-label="玩家资料分类">${Object.entries(VIEWS).map(([key,name])=>`<a href="#player=${encodeURIComponent(state.id)}&view=${key}" class="${state.view===key ? "active" : ""}" ${state.view===key ? 'aria-current="page"' : ""}>${name}</a>`).join("")}</nav>
        <div id="profileContent">${state.view==="heroes" ? `<section class="rp-card"><div class="rp-section-head"><h3>英雄使用记录</h3><span>按出场次数排序</span></div>${heroTable(current.heroes)}</section>` : state.view==="matches" ? matchesView(current) : state.view==="peers" ? relationsView(current) : state.view==="opponents" ? relationsView(current,true) : overview(current)}</div>`;
      detail.querySelectorAll("#profileHero, #profileResult").forEach(select=>select.addEventListener("change",()=>{
        state.hero=detail.querySelector("#profileHero").value; state.result=detail.querySelector("#profileResult").value; state.page=1; updateHash();
      }));
      detail.querySelectorAll("[data-page]").forEach(button=>button.addEventListener("click",()=>{state.page=Number(button.dataset.page);updateHash();}));
    }
    return {
      show(id, query = new URLSearchParams()) {
        state.id = id || (players[0] && players[0].id) || null;
        state.view = Object.prototype.hasOwnProperty.call(VIEWS, query.get("view")) ? query.get("view") : "overview";
        state.hero = query.get("hero") || "all";
        state.result = ["all","win","loss","unknown"].includes(query.get("result")) ? query.get("result") : "all";
        const page = Number(query.get("page") || 1);
        state.page = Number.isFinite(page) ? Math.max(1,Math.floor(page)) : 1;
        const player = players.find(p=>p.id===state.id);
        current = player ? buildProfile(player,matches) : null;
        if (current && state.hero !== "all" && !current.heroes.some(h => h.key === state.hero)) state.hero = "all";
        directory(); render();
      },
      get id() { return state.id; }
    };
  }
  return {buildProfile, heroStats, peerStats, opponentStats, filterRecords, average, kda, heroImage, itemIcons, mount};
});
