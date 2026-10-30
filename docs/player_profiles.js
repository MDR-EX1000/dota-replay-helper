/* Local replay player profiles. Layout references: DOTABUFF and OpenDota; no remote player API. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.ReplayProfiles = factory();
})(typeof window !== "undefined" ? window : globalThis, function () {
  "use strict";
  const VIEWS = {overview: "概览", matches: "比赛记录", heroes: "英雄统计", peers: "队友", opponents: "对手"};
  const TITLES = {mvp: "MVP", svp: "SVP", wealth: "富豪", kills: "破敌", towers: "破军", support: "偏将", denies: "补王"};
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
  // 标记共用口径：把“有他在场”的场次胜率，与“没他在场”的场次胜率相比（排除自己稀释的口径偏差）。
  // 同队口径：好基友（同队胜率明显更高）/ 冤家（明显更低）。
  // 对阵口径：安全带（对阵胜率明显更高，是好打的对手）/ 克星（明显更低，是难打的对手）。
  // 门槛（经验值，非统计显著性检验）：有他在场 >= MARK_MIN_WITH 场，没他在场 >= MARK_MIN_WITHOUT 场，
  // 胜率差 >= MARK_MIN_GAP 个百分点，并满足绝对胜率：高方 >= 55%，低方 <= 45%（避免“自身只有 27%，40% 就叫好”）。
  // 每类最多 MARK_MAX 个，按差值排名 1/2/3；不满足就没有，不硬凑。同一人不可能同时落入“好”和“坏”两类
  const MARK_MIN_WITH = 5, MARK_MIN_WITHOUT = 3, MARK_MIN_GAP = 20, MARK_MAX = 3;
  const MARK_HIGH_RATE = 55, MARK_LOW_RATE = 45;
  // 对阵口径“没他在场”的场次通常更少、更不稳，所以下限更高
  const MARK_MIN_WITHOUT_VS = 4;
  function relationMarks(records, versus) {
    const known = records.filter(r => r.won !== null && ["radiant","dire"].includes(r.player.team));
    const present = new Map();
    for (const r of known) for (const peer of r.match.players || []) {
      if (!peer.id || peer.id === r.player.id || !["radiant","dire"].includes(peer.team)) continue;
      if (versus ? peer.team === r.player.team : peer.team !== r.player.team) continue;
      if (!present.has(peer.id)) present.set(peer.id, new Set());
      present.get(peer.id).add(r.match.id);
    }
    const rate = rows => rows.filter(r => r.won).length / rows.length * 100;
    const minWithout = versus ? MARK_MIN_WITHOUT_VS : MARK_MIN_WITHOUT;
    const scored = [];
    for (const [id, matchIds] of present) {
      const withHim = known.filter(r => matchIds.has(r.match.id));
      const without = known.filter(r => !matchIds.has(r.match.id));
      if (withHim.length < MARK_MIN_WITH || without.length < minWithout) continue;
      scored.push({id, gap: rate(withHim) - rate(without), together: withHim.length,
        togetherRate: rate(withHim), apartRate: rate(without)});
    }
    const pick = list => list.slice(0, MARK_MAX).map((x, i) => ({...x, rank: i}));
    const stable = (a, b) => b.together - a.together || a.id.localeCompare(b.id);
    return {
      high: pick(scored.filter(x => x.gap >= MARK_MIN_GAP && x.togetherRate >= MARK_HIGH_RATE).sort((a, b) => b.gap - a.gap || stable(a, b))),
      low: pick(scored.filter(x => x.gap <= -MARK_MIN_GAP && x.togetherRate <= MARK_LOW_RATE).sort((a, b) => a.gap - b.gap || stable(a, b)))
    };
  }
  function buddyMarks(records) {
    const t = relationMarks(records, false), o = relationMarks(records, true);
    return {buddies: t.high, rivals: t.low, safety: o.high, nemesis: o.low};
  }
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
    for (const r of records) {
      for (const title of r.player.titles || []) if (Object.prototype.hasOwnProperty.call(honors, title.key)) honors[title.key]++;
      // MVP/SVP 由评分系统写入 player.title（字符串），不在 titles 数组里
      if (r.player.title === "MVP") honors.mvp++;
      else if (r.player.title === "SVP") honors.svp++;
    }
    return {player, records, ...recordSummary(records), heroes: heroStats(records), peers: peerStats(records), opponents: opponentStats(records), marks: buddyMarks(records), honors,
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
    const state = {id:null, view:"overview", hero:"all", result:"all", page:1, query:"", sort:"", dir:"desc"};
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
    const MARK_ICONS = {
      good: '<svg class="rp-mark-ico" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 21 C5 15.5 2 12 2 8.2 C2 5.4 4.2 3.5 6.8 3.5 C9 3.5 10.8 4.8 12 6.6 C13.2 4.8 15 3.5 17.2 3.5 C19.8 3.5 22 5.4 22 8.2 C22 12 19 15.5 12 21Z" fill="currentColor"/></svg>',
      bad: '<svg class="rp-mark-ico" viewBox="0 0 24 24" aria-hidden="true"><path transform="translate(-1.3 0)" d="M12 21 C5 15.5 2 12 2 8.2 C2 5.4 4.2 3.5 6.8 3.5 C9 3.5 10.8 4.8 12 6.6 L10.8 10 L13.2 12.2 L11.2 15.6 Z" fill="currentColor"/><path transform="translate(1.3 0)" d="M12 6.6 C13.2 4.8 15 3.5 17.2 3.5 C19.8 3.5 22 5.4 22 8.2 C22 12 19 15.5 12 21 L11.2 15.6 L13.2 12.2 L10.8 10 Z" fill="currentColor"/></svg>',
      nemesis: '<svg class="rp-mark-ico" viewBox="0 0 24 24" aria-hidden="true"><path d="M3.2 21.4 L13.4 9.4" stroke="currentColor" stroke-width="2.1" stroke-linecap="round"/><path d="M10.6 12.8 C8.4 8.6 10.2 4.2 15 2.6 C14.4 5 14.8 6.8 16.6 8.4 C14.8 8.4 13.6 9.6 12.6 11.2 Z" fill="currentColor"/><path d="M13.2 10.2 C16 8 19.6 8.2 22 10.4 C19.8 10.8 18.4 11.8 17.8 13.4 C16.4 12 14.8 11.6 13.2 12.4 Z" fill="currentColor"/><circle cx="14.6" cy="6.6" r="0.9" fill="#0b0d12" opacity=".75"/><circle cx="17.6" cy="10.6" r="0.9" fill="#0b0d12" opacity=".75"/><path d="M20.6 3.4 L19 6 L21 6.2 L19.6 8.4" stroke="currentColor" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round" fill="none" opacity=".9"/></svg>',
      safety: '<svg class="rp-mark-ico" viewBox="0 0 24 24" aria-hidden="true"><path d="M3.6 2 H8 L20.4 15.2 H16.4 Z" fill="currentColor" opacity=".88"/><path d="M1.8 18 H22.2 V21.8 H1.8 Z" fill="currentColor" opacity=".88"/><rect x="9.4" y="12.4" width="7.4" height="6.8" rx="1.5" fill="currentColor"/><rect x="11.1" y="14.1" width="4" height="3.4" rx=".7" fill="#0b0d12" opacity=".6"/><path d="M13.1 12.4 V9.8" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>'
    };
    const MARK_NAMES = {good: "好基友", bad: "冤家", nemesis: "克星", safety: "安全带"};
    const MARK_CTX = {good: ["同队", "不同队"], bad: ["同队", "不同队"], nemesis: ["交手", "未交手"], safety: ["交手", "未交手"]};
    // 好基友/冤家/克星/安全带：按差值排名 1/2/3，颜色逐名变淡，悬停显示依据
    function markBadge(mark) {
      if (!mark) return "";
      const name = MARK_NAMES[mark.kind], [near, far] = MARK_CTX[mark.kind];
      const tip = `${name}（第 ${mark.rank + 1} 名）：${near} ${mark.together} 场胜率 ${mark.togetherRate.toFixed(0)}%，${far}胜率 ${mark.apartRate.toFixed(0)}%，差 ${mark.gap > 0 ? "+" : ""}${mark.gap.toFixed(0)} 个百分点`;
      return `<span class="rp-mark m${mark.rank} ${mark.kind}" title="${esc(tip)}">${MARK_ICONS[mark.kind]}${name}</span>`;
    }
    // 队友/对手表排序：sort=games|winRate，dir=desc|asc；未选择排序时保持默认顺序。
    // 胜率为空（结果全未知）的行始终排最后；同值时沿用默认顺序，保证稳定
    function sortRelations(rows) {
      if (!["games", "winRate"].includes(state.sort)) return rows;
      const sign = state.dir === "asc" ? 1 : -1;
      return rows.map((row, i) => ({row, i})).sort((a, b) => {
        const x = a.row[state.sort], y = b.row[state.sort];
        if (x == null && y == null) return a.i - b.i;
        if (x == null) return 1;
        if (y == null) return -1;
        return (x - y) * sign || a.i - b.i;
      }).map(item => item.row);
    }
    function sortHeader(key, label) {
      const active = state.sort === key;
      const arrow = active ? (state.dir === "asc" ? " ▲" : " ▼") : "";
      return `<th><button type="button" class="rp-sort ${active ? "active" : ""}" data-sort="${key}" aria-label="按${esc(label)}排序">${esc(label)}${arrow}</button></th>`;
    }
    function relationsView(profile, opponents = false) {
      const rows = sortRelations(opponents ? profile.opponents : profile.peers);
      const markOf = new Map();
      const sets = opponents ? [["nemesis", profile.marks.nemesis], ["safety", profile.marks.safety]]
                             : [["good", profile.marks.buddies], ["bad", profile.marks.rivals]];
      for (const [kind, list] of sets) for (const x of list) markOf.set(x.id, {...x, kind});
      return `<section class="rp-card"><div class="rp-section-head"><h3>${opponents ? "对手交手记录" : "共同出场的队友"}</h3><span>${opponents ? "仅统计敌方玩家 · 胜率以本玩家为视角" : "仅统计同队比赛"} · 点击表头可排序</span></div>${rows.length ? `<div class="rp-table-wrap"><table class="rp-table"><thead><tr><th>玩家</th>${sortHeader("games", opponents ? "交手场次" : "同队场次")}<th>胜 / 负</th>${sortHeader("winRate", opponents ? "对抗胜率" : "同队胜率")}<th>最近${opponents ? "交手" : "同队"}</th></tr></thead><tbody>${rows.map(p=>`<tr><td>${link(p.player)}${markBadge(markOf.get(p.player.id))}</td><td>${p.games}</td><td>${p.wins} / ${p.losses}${p.unknown ? "（未知 " + p.unknown + "）" : ""}</td><td>${percent(p.winRate)}</td><td>${esc(p.lastSeen)}</td></tr>`).join("")}</tbody></table></div>` : `<div class="rp-empty">暂无${opponents ? "对手交手" : "同队"}记录</div>`}</section>`;
    }
    function updateHash() {
      const query = new URLSearchParams({player:state.id,view:state.view});
      if (state.view === "matches") {
        query.set("hero",state.hero); query.set("result",state.result); query.set("page",String(state.page));
      }
      if ((state.view === "peers" || state.view === "opponents") && state.sort) {
        query.set("sort",state.sort); query.set("dir",state.dir);
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
      detail.querySelectorAll("[data-sort]").forEach(button=>button.addEventListener("click",()=>{
        const key=button.dataset.sort;
        if (state.sort===key) state.dir = state.dir==="desc" ? "asc" : "desc"; else {state.sort=key; state.dir="desc";}
        updateHash();
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
        state.sort = ["games","winRate"].includes(query.get("sort")) ? query.get("sort") : "";
        state.dir = query.get("dir") === "asc" ? "asc" : "desc";
        const player = players.find(p=>p.id===state.id);
        current = player ? buildProfile(player,matches) : null;
        if (current && state.hero !== "all" && !current.heroes.some(h => h.key === state.hero)) state.hero = "all";
        directory(); render();
      },
      get id() { return state.id; }
    };
  }
  return {buildProfile, buddyMarks, heroStats, peerStats, opponentStats, filterRecords, average, kda, heroImage, itemIcons, mount};
});
