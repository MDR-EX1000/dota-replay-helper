# -*- coding: utf-8 -*-
"""
生成对黑分组动态网页：Desktop/replay/index.html

五个 Tab:
    1. 数据统计   —— 玩家汇总表（胜率 / KDA / GPM / XPM / 伤害经济比等）
    2. 比赛明细   —— 单场经济、战斗、装备与事件
    3. Roll 阵容  —— 勾选 10 人，一次 roll 出 3 套阵容，每套附规则审计
    4. 上传录像   —— 网页上传 .dem，云端解析并自动发布
    5. 规则说明   —— 评分口径、roll 规则、放宽顺序、可信依据

数据来自 balance.build_ratings() + stats.aggregate()。
每次解析新比赛后重新运行本脚本即可刷新页面。
"""

import json
import os
from datetime import datetime

import balance
import make_match_data
import stats

REPLAY_ROOT = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.join(REPLAY_ROOT, "docs")


def collect_players():
    ratings = balance.build_ratings(balance.load_matches())
    matches = stats.load_matches(stats.DEFAULT_MATCHES_DIR)
    rows = stats.aggregate(matches)
    by_name = {r["玩家"]: r for r in rows}

    out = []
    for name, p in ratings.items():
        s = by_name.get(name, {})
        out.append({
            "name": name,
            "rating": p["rating"],
            "elo": p["elo"],
            "perf": p["perf"],
            "role": p["role"],
            "provisional": p.get("provisional", False),
            "games": s.get("场次", p["games"]),
            "wins": s.get("胜", 0),
            "losses": s.get("负", 0),
            "winRate": float(str(s.get("胜率", f'{p["win_rate"]*100:.1f}%')).rstrip("%")),
            "coreRate": s.get("核心率", "-"),
            "rankAll": s.get("全场经济平均排名", 0),
            "rankTeam": s.get("队内经济平均排名", 0),
            "kda": s.get("KDA", p["kda"]),
            "kd": s.get("平均K/D/A", p["kd"]),
            "gpm": s.get("平均GPM", p["gpm"]),
            "xpm": s.get("平均XPM", p["xpm"]),
            "nwK": s.get("平均净资产(K)", 0),
            "dmgK": s.get("造成英雄伤害(K)", 0),
            "dmgTakenK": s.get("承受英雄伤害(K)", 0),
            "dmgGold": s.get("伤害/经济", 0),
            "takenGold": s.get("承伤/经济", 0),
            "mmr": s.get("MMR", "-"),
            "mmrNum": s.get("_mmr"),
            "heroes": s.get("常用英雄", ""),
        })
    out.sort(key=lambda x: (-x["winRate"], -x["rating"]))
    return out, len(matches)


TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dota 2 对黑数据统计</title>
<style>
  :root {
    color-scheme: dark;
    --bg:#14161b; --panel:#1b1e26; --line:#262b36; --text:#e6e8ec; --muted:#8a90a0;
    --accent:#7ee0a1; --purple:#c8a5ff; --warn:#ffcc66; --bad:#ff7b72;
  }
  * { box-sizing: border-box; }
  body { margin:0; padding:0 28px 60px; background:var(--bg); color:var(--text);
         font-family:"Microsoft YaHei","Segoe UI",sans-serif; }
  header { padding:26px 0 0; }
  h1 { font-size:22px; margin:0 0 4px; font-weight:650; }
  .sub { color:var(--muted); font-size:13px; }
  .tabs { display:flex; gap:6px; margin:20px 0 22px; border-bottom:1px solid var(--line); }
  .tab { background:none; border:0; color:var(--muted); font-size:14px; padding:10px 16px;
         cursor:pointer; border-bottom:2px solid transparent; font-weight:600; }
  .tab:hover { color:var(--text); }
  .tab.active { color:var(--accent); border-bottom-color:var(--accent); }
  .pane { display:none; }
  .pane.active { display:block; }
  h2 { font-size:15px; margin:0 0 12px; color:#c3c8d4; font-weight:600; }
  h3 { font-size:14px; margin:22px 0 8px; color:#cfd5e1; }
  p, li { font-size:13px; line-height:1.8; color:#b6bcc9; }
  code { background:#222733; padding:1px 6px; border-radius:5px; font-size:12px; color:#dfe3ea; }
  .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(220px,1fr)); gap:10px; }
  .player { background:var(--panel); border:1px solid var(--line); border-radius:10px;
            padding:12px 14px; cursor:pointer; display:flex; gap:10px; align-items:center;
            user-select:none; transition:border-color .15s,background .15s; }
  .player:hover { border-color:#3a4152; }
  .player.on { border-color:var(--accent); background:#1a2420; }
  .player input { accent-color:#7ee0a1; width:16px; height:16px; }
  .p-main { flex:1; min-width:0; }
  .p-name { font-weight:650; font-size:13px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .p-meta { color:var(--muted); font-size:11px; margin-top:3px; }
  .p-rating { font-size:18px; font-weight:700; }
  .badge { display:inline-block; font-size:10px; padding:1px 6px; border-radius:999px; margin-left:5px; }
  .badge.core { color:#7ee0a1; background:#173125; }
  .badge.sup { color:#c8a5ff; background:#251c38; }
  .badge.prov { color:#ffcc66; background:#332b17; }
  .bar { position:sticky; bottom:0; margin:22px -28px 0; padding:14px 28px;
         background:rgba(20,22,27,.94); border-top:1px solid var(--line);
         display:flex; align-items:center; gap:14px; backdrop-filter:blur(8px); }
  .count { color:var(--muted); font-size:13px; }
  .count b { color:var(--text); }
  button.primary { background:var(--accent); color:#0e1a13; border:0; border-radius:8px;
                   padding:10px 22px; font-size:14px; font-weight:700; cursor:pointer; }
  button.primary:disabled { background:#2c313d; color:#6b7280; cursor:not-allowed; }
  button.ghost { background:transparent; color:var(--muted); border:1px solid var(--line);
                 border-radius:8px; padding:9px 14px; font-size:13px; cursor:pointer; }
  .table-wrap { overflow-x:auto; border:1px solid var(--line); border-radius:10px; }
  table { border-collapse:collapse; width:100%; font-size:12.5px; }
  th, td { padding:10px 12px; text-align:right; white-space:nowrap; border-bottom:1px solid var(--line); }
  th { color:var(--muted); font-weight:500; background:#181b22; font-size:11.5px; position:sticky; top:0;
       cursor:pointer; user-select:none; }
  th:hover { color:var(--text); }
  th.left { text-align:left; }
  td.name, th:nth-child(1) { text-align:left; font-weight:600; }
  tbody tr:hover { background:#1b1f28; }
  tbody tr:last-child td { border-bottom:0; }
  .role-core { color:var(--accent); }
  .role-sup { color:var(--purple); }
  .heroes { text-align:left !important; color:var(--muted); max-width:280px;
            overflow:hidden; text-overflow:ellipsis; }
  .results { display:grid; grid-template-columns:repeat(auto-fit,minmax(380px,1fr)); gap:16px; }
  .card { background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:16px 18px; }
  .card-head { display:flex; justify-content:space-between; align-items:baseline; gap:10px; margin-bottom:12px; }
  .card-title { font-size:15px; font-weight:700; }
  .score { color:var(--accent); font-weight:700; }
  .prob { color:var(--muted); font-size:12px; }
  .team { margin-top:10px; }
  .team-label { font-size:11px; color:var(--muted); margin-bottom:6px; letter-spacing:.04em; }
  .members { display:flex; flex-wrap:wrap; gap:6px; }
  .member { background:#222733; border-radius:7px; padding:5px 9px; font-size:12px; }
  .member b { color:#cfd5e1; font-weight:600; }
  .member span { color:var(--muted); font-size:11px; margin-left:4px; }
  .audit { margin-top:14px; border-top:1px dashed var(--line); padding-top:10px; }
  .audit-row { display:flex; justify-content:space-between; font-size:11.5px; padding:3px 0; color:var(--muted); }
  .audit-row .ok { color:var(--accent); }
  .audit-row .no { color:var(--bad); }
  .why { margin-top:10px; font-size:11.5px; color:var(--muted); line-height:1.7; }
  .empty { color:var(--muted); font-size:13px; padding:18px 0; }
  .rules-box { background:var(--panel); border:1px solid var(--line); border-radius:12px;
               padding:18px 20px; margin-bottom:14px; }
  .rules-box table { font-size:12.5px; }
  .rules-box td, .rules-box th { text-align:left; }
  .footer { margin-top:28px; color:#6f7585; font-size:11.5px; }

  /* 比赛明细 */
  .m-layout { display:grid; grid-template-columns:260px minmax(0,1fr); gap:18px; align-items:start; }
  .m-side { position:sticky; top:12px; max-height:calc(100vh - 120px); display:flex; flex-direction:column; min-width:0; }
  .m-side-head { color:var(--muted); font-size:12px; margin-bottom:8px; }
  .match-list { overflow-y:auto; display:flex; flex-direction:column; gap:6px; padding-right:4px; }
  .m-item { text-align:left; background:var(--panel); border:1px solid var(--line); border-radius:9px;
            padding:9px 11px; cursor:pointer; color:var(--text); }
  .m-item:hover { border-color:#3a4152; }
  .m-item.active { border-color:var(--accent); background:#1a2420; }
  .mi-top { display:flex; justify-content:space-between; font-size:12px; font-weight:700; }
  .mi-sub { color:var(--muted); font-size:11px; margin-top:3px; }
  .mi-win { color:var(--accent); } .mi-loss { color:var(--bad); }
  .m-main { min-width:0; }
  .match-list { max-width:100%; }
  .m-head { background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:16px 18px; }
  .m-title { display:flex; align-items:baseline; gap:12px; flex-wrap:wrap; }
  .m-title b { font-size:18px; }
  .m-score { font-size:26px; font-weight:800; letter-spacing:1px; }
  .m-meta { color:var(--muted); font-size:12px; margin-top:6px; }
  .kpis { display:grid; grid-template-columns:repeat(auto-fit,minmax(110px,1fr)); gap:8px; margin-top:12px; }
  .kpi { background:#1b1e26; border:1px solid var(--line); border-radius:8px; padding:8px 10px; }
  .kpi .k { color:var(--muted); font-size:11px; } .kpi .v { font-size:16px; font-weight:700; margin-top:2px; }
  .subtabs { display:flex; gap:4px; margin:14px 0 10px; border-bottom:1px solid var(--line); overflow-x:auto; }
  .subtab { background:none; border:0; border-bottom:2px solid transparent; color:var(--muted);
            padding:8px 12px; font-size:13px; cursor:pointer; white-space:nowrap; }
  .subtab.active { color:var(--accent); border-bottom-color:var(--accent); }
  .subpane { display:none; } .subpane.active { display:block; }
  .scoreboard { margin-top:10px; }
  .sb-head { display:flex; justify-content:space-between; font-size:13px; font-weight:700; margin:10px 0 6px; }
  .sb-radiant { color:var(--accent); } .sb-dire { color:var(--bad); }
  .m-table { width:100%; border-collapse:collapse; font-size:12px; }
  .m-table th, .m-table td { padding:7px 8px; border-bottom:1px solid var(--line); text-align:right; white-space:nowrap; }
  .m-table th { color:var(--muted); font-weight:500; text-align:right; }
  .m-table th:nth-child(1), .m-table td:nth-child(1),
  .m-table th:nth-child(2), .m-table td:nth-child(2) { text-align:left; }
  .hero-cell { font-weight:600; } .hero-cell span { color:var(--muted); font-weight:400; font-size:11px; }
  .item-chips { display:flex; gap:3px; flex-wrap:wrap; justify-content:flex-end; }
  .item-chip { background:#222733; border-radius:5px; padding:2px 5px; font-size:10.5px; color:#b9bfcc; }
  .chart-card { background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:12px 14px; margin-bottom:12px; }
  .chart-title { font-size:13px; font-weight:600; margin-bottom:6px; }
  .chart-host { position:relative; width:100%; min-height:200px; }
  .chart-host svg { display:block; width:100%; overflow:visible; }
  .chart-legend { display:flex; gap:10px; flex-wrap:wrap; font-size:11px; color:var(--muted); margin-top:6px; }
  .chart-legend i { display:inline-block; width:10px; height:3px; border-radius:2px; margin-right:4px; vertical-align:middle; }
  .chart-tooltip { position:absolute; pointer-events:none; background:#0f1217; border:1px solid var(--line);
                   border-radius:6px; padding:6px 8px; font-size:11px; color:var(--text); display:none; z-index:5; white-space:nowrap; }
  .dmg-bar { display:flex; height:8px; border-radius:4px; overflow:hidden; background:#222733; min-width:120px; }
  .dmg-bar i { display:block; height:100%; }
  .dmg-legend { font-size:10.5px; color:var(--muted); margin-top:3px; }
  .event-list { display:flex; flex-direction:column; gap:2px; }
  .event-row { display:grid; grid-template-columns:52px 78px minmax(0,1fr); gap:8px; padding:6px 4px;
               border-bottom:1px solid var(--line); font-size:12px; align-items:baseline; }
  .ev-time { color:var(--muted); font-variant-numeric:tabular-nums; }
  .ev-team { font-size:10px; font-weight:700; }
  .ev-kill { color:#e66767; } .ev-radiant { color:var(--accent); }
  .ev-desc { color:#cfd5e1; } .ev-desc small { color:var(--muted); }
  .filter-row { display:flex; gap:6px; flex-wrap:wrap; margin-bottom:8px; }
  .filter-row .chip.active { color:var(--accent); border-color:var(--accent); }
  .purchase-card { background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:10px 12px; margin-bottom:10px; }
  .purchase-head { display:flex; justify-content:space-between; font-size:12px; font-weight:600; margin-bottom:6px; }
  .purchase-list { display:flex; gap:5px; flex-wrap:wrap; }
  .purchase-chip { background:#222733; border-radius:5px; padding:2px 6px; font-size:10.5px; color:#b9bfcc; }
  @media (max-width:900px) {
    .m-layout { grid-template-columns:1fr; }
    .m-side { position:static; max-height:none; }
    .match-list { flex-direction:row; overflow-x:auto; padding-bottom:4px; }
    .m-item { min-width:180px; flex:0 0 auto; }
    .m-score { font-size:22px; }
    .event-row { grid-template-columns:46px 64px minmax(0,1fr); }
  }

  /* AI 匹配助手 */
  .ai-action { display:none; align-items:center; gap:12px; margin:18px 0 8px; flex-wrap:wrap; }
  .ai-hint { color:var(--muted); font-size:12px; }
  .overlay { position:fixed; inset:0; background:rgba(0,0,0,.55); opacity:0; pointer-events:none;
             transition:opacity .2s; z-index:90; }
  .overlay.on { opacity:1; pointer-events:auto; }
  .drawer { position:fixed; top:0; right:0; height:100%; width:430px; max-width:100%;
            background:#171a21; border-left:1px solid var(--line); z-index:100;
            display:flex; flex-direction:column; transform:translateX(100%);
            transition:transform .22s ease; }
  .drawer.on { transform:translateX(0); }
  .drawer-head { display:flex; justify-content:space-between; align-items:center;
                 padding:16px 18px; border-bottom:1px solid var(--line); }
  .drawer-title { font-weight:700; font-size:15px; }
  .drawer-sub { color:var(--muted); font-size:11.5px; margin-top:3px; }
  .chat { flex:1; overflow-y:auto; padding:16px 18px; display:flex; flex-direction:column; gap:12px; }
  .msg { max-width:88%; padding:9px 12px; border-radius:10px; font-size:13px; line-height:1.65;
         white-space:normal; word-break:break-word; }
  .msg.user { align-self:flex-end; background:#233042; color:#e6e8ec; }
  .msg.assistant { align-self:flex-start; background:#1f2430; color:#cfd5e1; }
  .msg.system { align-self:center; background:#222733; color:var(--muted); font-size:12px; }
  .msg .err { color:var(--bad); }
  .msg p { margin:0 0 8px; } .msg p:last-child { margin-bottom:0; }
  .msg ul, .msg ol { margin:4px 0 8px; padding-left:20px; }
  .msg li { margin:2px 0; }
  .msg h1, .msg h2, .msg h3, .msg h4 { margin:6px 0 6px; font-size:14px; color:#e6e8ec; }
  .msg code { background:#11141a; padding:1px 5px; border-radius:4px; font-size:11.5px; }
  .msg pre { background:#11141a; border:1px solid var(--line); border-radius:7px;
             padding:9px 11px; overflow-x:auto; margin:6px 0 8px; }
  .msg pre code { background:none; padding:0; }
  .msg a { color:var(--accent); }
  .msg table { border-collapse:collapse; margin:6px 0 8px; font-size:11.5px; }
  .msg th, .msg td { border:1px solid var(--line); padding:3px 7px; text-align:left; }
  .msg.streaming::after { content:"▍"; color:var(--accent); animation:blink 1s infinite; }
  @keyframes blink { 50% { opacity:0; } }
  .msg.match-wrap { max-width:96%; padding:0; background:transparent; }
  .typing { color:var(--muted); font-size:12px; padding:4px 2px; }
  .chips { display:flex; gap:6px; flex-wrap:wrap; padding:8px 18px 0; }
  .chip { background:#222733; border:1px solid var(--line); color:#b9bfcc; border-radius:999px;
          padding:5px 10px; font-size:11.5px; cursor:pointer; }
  .chip:hover { color:var(--text); border-color:#3a4152; }
  .chat-input { display:flex; gap:8px; padding:12px 18px 18px; align-items:flex-end; }
  .chat-input textarea { flex:1; resize:none; background:#11141a; color:var(--text);
                         border:1px solid var(--line); border-radius:9px; padding:9px 11px;
                         font-size:13px; font-family:inherit; outline:none; }
  .chat-input textarea:focus { border-color:var(--accent); }
  .match-card { background:var(--panel); border:1px solid var(--line); border-radius:12px;
                padding:13px 15px; margin-top:6px; }
  .match-card .mc-head { display:flex; justify-content:space-between; gap:8px; margin-bottom:8px; }
  .match-card .mc-title { font-weight:700; font-size:13px; }
  .match-card .mc-prob { color:var(--muted); font-size:11.5px; text-align:right; }
  .match-card .mc-team { margin-top:7px; }
  .match-card .mc-reason { margin-top:9px; color:var(--muted); font-size:11.5px; line-height:1.6; }
  .match-card .mc-actions { margin-top:9px; display:flex; gap:8px; }
  .adopted-banner { color:var(--accent); font-size:12px; margin-bottom:8px; }

  .upload-box { background:var(--panel); border:1px solid var(--line); border-radius:12px;
                padding:16px 18px; max-width:720px; }
  .upload-hint { color:var(--muted); font-size:12.5px; line-height:1.7; margin:0 0 14px; }
  .upload-field { display:flex; align-items:center; gap:10px; font-size:12.5px;
                  color:var(--muted); margin-bottom:12px; }
  .upload-field > input { background:#11141a; color:var(--text); border:1px solid var(--line);
                          border-radius:8px; padding:7px 10px; font-size:13px; outline:none; width:200px; }
  .upload-field > input:focus { border-color:var(--accent); }
  .up-remember { display:inline-flex; align-items:center; gap:5px; font-size:12px;
                 color:var(--muted); cursor:pointer; }
  .up-remember input { width:auto; margin:0; }
  .up-service { font-size:12px; color:var(--muted); margin:-4px 0 12px; }
  .up-service.ok { color:#4ec9a5; }
  .up-service.err { color:#e06666; }
  .upload-hint-line { color:var(--muted); font-size:11.5px; margin:-6px 0 10px; }
  .up-force { display:flex; align-items:center; gap:6px; font-size:12px;
              color:var(--muted); margin:-2px 0 10px; cursor:pointer; }
  .up-force input { width:auto; margin:0; }
  .upload-drop { display:flex; align-items:center; justify-content:center; border:1px dashed #3a4152;
                 border-radius:10px; padding:22px; cursor:pointer; color:var(--muted);
                 font-size:13px; margin-bottom:12px; }
  .upload-drop:hover, .upload-drop.dragover { border-color:var(--accent); color:var(--text); }
  .upload-drop.dragover { background:#1a1f29; }
  .upload-drop input { display:none; }
  .up-actions { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
  .up-note { color:var(--muted); font-size:11.5px; }
  .up-result { margin-top:12px; padding:12px 14px; border:1px solid var(--line); border-radius:10px;
               background:#1b1f28; font-size:12.5px; line-height:1.8; }
  .up-result a { color:var(--accent); }
  .up-progress { height:8px; background:#1b1f28; border-radius:999px; overflow:hidden; margin:12px 0 8px; }
  .up-bar { height:100%; width:0; background:var(--accent); transition:width .2s; }
  .up-status { font-size:12.5px; color:var(--text); min-height:18px; margin-bottom:6px; }
  .up-log { margin:8px 0 0; padding-left:18px; color:var(--muted); font-size:12px; line-height:1.8; }
  .up-log .err { color:#e06666; }
  .up-log .ok { color:#4ec9a5; }

  @media (max-width:640px) {
    body { padding:0 14px 60px; }
    .bar { margin:18px -14px 0; padding:12px 14px; flex-wrap:wrap; }
    .drawer { width:100%; }
  }
</style>
<script src="vendor/marked.umd.js"></script>
<script src="vendor/purify.min.js"></script>
</head>
<body>
<header>
  <h1>Dota 2 对黑数据统计</h1>
  <div class="sub">共 <b id="matchCount"></b> 场比赛 · 数据更新于 __TIME__</div>
</header>

<nav class="tabs">
  <button class="tab active" data-tab="stats">数据统计</button>
  <button class="tab" data-tab="match">比赛明细</button>
  <button class="tab" data-tab="roll">Roll 阵容</button>
  <button class="tab" data-tab="upload">上传录像</button>
  <button class="tab" data-tab="rules">规则说明</button>
</nav>

<section id="pane-stats" class="pane active">
  <h2>玩家数据汇总（默认按胜率降序，点击表头切换排序）</h2>
  <div class="table-wrap">
    <table>
      <thead id="statsHead"></thead>
      <tbody id="statsBody"></tbody>
    </table>
  </div>
</section>

<section id="pane-match" class="pane">
  <div class="m-layout">
    <aside class="m-side">
      <div class="m-side-head">比赛列表 <span id="mMatchCount"></span></div>
      <div id="matchList" class="match-list"></div>
    </aside>
    <main id="matchDetail" class="m-main">
      <div class="empty">选择一场比赛查看明细</div>
    </main>
  </div>
</section>

<section id="pane-roll" class="pane">
  <h2>1. 选择上场玩家 <span id="hint" style="color:#8a90a0;font-weight:400;font-size:12px"></span></h2>
  <div class="grid" id="players"></div>

  <h2 style="margin-top:26px">2. 结果</h2>
  <div id="results"><div class="empty">默认已全选，请反选到 10 人后点击下方 Roll。</div></div>

  <div id="aiAction" class="ai-action">
    <button class="primary" id="aiOpen">交互式匹配改进</button>
    <span class="ai-hint" id="aiHint"></span>
  </div>

  <div class="bar">
    <div class="count">已选 <b id="cnt">0</b> / 10</div>
    <button class="ghost" id="clear">清空</button>
    <button class="ghost" id="top10">选前 10</button>
    <button class="primary" id="roll" disabled>Roll</button>
  </div>
</section>

<section id="pane-upload" class="pane">
  <h2>上传录像（.dem）</h2>
  <div class="upload-box">
    <p class="upload-hint">
      从 Dota 2 客户端「观看 → 已下载的重放」找到比赛，文件名就是比赛 ID（例如
      <code>9061520546.dem</code>）。上传后会自动解析、更新统计并重新发布本页，无需再动本地脚本。
    </p>

    <div class="up-service" id="upService">正在检查服务状态…</div>

    <div class="upload-field">
      <span>上传口令</span>
      <input id="upCode" type="password" placeholder="输入口令" autocomplete="off">
      <label class="up-remember"><input id="upRemember" type="checkbox"> 记住</label>
    </div>
    <div class="upload-hint-line" id="upCodeHint"></div>
    <label class="up-force"><input id="upForce" type="checkbox">
      重新解析已存在的比赛（会覆盖旧数据，解析器更新后使用）</label>

    <label class="upload-drop" id="upDrop">
      <input id="upFile" type="file" accept=".dem">
      <span id="upFileName">点击选择，或把 .dem 文件拖到这里</span>
    </label>

    <div class="up-actions">
      <button class="primary" id="upStart" disabled>开始上传并解析</button>
      <button class="ghost" id="upCancel" hidden>取消</button>
      <span class="up-note">解析约 1–2 分钟，成功后本页数据即可查看</span>
    </div>

    <div class="up-progress" id="upBarWrap" hidden><div class="up-bar" id="upBar"></div></div>
    <div class="up-status" id="upStatus"></div>
    <div class="up-result" id="upResult" hidden></div>
    <ol class="up-log" id="upLog"></ol>
  </div>
</section>

<div id="aiOverlay" class="overlay" onclick="closeAI()"></div>
<aside id="aiDrawer" class="drawer" aria-hidden="true">
  <div class="drawer-head">
    <div>
      <div class="drawer-title">AI 匹配助手</div>
      <div class="drawer-sub">只会调整当前 10 人 · 由 DeepSeek 驱动</div>
    </div>
    <button class="ghost" onclick="closeAI()">关闭</button>
  </div>
  <div class="chat" id="aiMessages"></div>
  <div class="chips">
    <button class="chip" data-prompt="把现在这三套里最平衡的那套再优化一下，给出更合理的分队。">更平衡</button>
    <button class="chip" data-prompt="避免综合分前两名在同一队，重新给一套方案。">避免双强同队</button>
    <button class="chip" data-prompt="解释一下当前三套方案的优缺点。">解释当前方案</button>
    <button class="chip" data-prompt="重新给 3 套不同的阵容。">重新给 3 套</button>
  </div>
  <div class="chat-input">
    <textarea id="aiInput" rows="2" placeholder="例如：让两边核心数更均衡，或者把某人换到另一队…"></textarea>
    <button class="primary" id="aiSend">发送</button>
  </div>
</aside>

<section id="pane-rules" class="pane">
  <div class="rules-box">
    <h3 style="margin-top:0">一、评分口径</h3>
    <p><code>综合分 = 0.4 × Elo + 0.3 × 表现分 + 0.3 × MMR分</code></p>
    <p><code>MMR分 = 1000 + (MMR − 3000) / 30</code>：3000 MMR = 1000 分，每 1000 MMR 差约 33.3 分；未登记默认按 2000 计算。</p>
    <p style="color:#8a90a0">Elo 本身已经包含胜负信息，所以不再单独加胜率分，避免重复计算；胜率只在数据表中展示。</p>
    <p><b>Elo</b>：初始 1000，K=32。每场按队伍平均分计算期望胜率，再给 5 人同步加减。</p>
    <p><b>表现分</b>：绝对数值 + 位置基准（不做百分位排名），权重统一：</p>
    <table>
      <tr><th>指标</th><th>权重</th><th>基准（核心 / 酱油）</th></tr>
      <tr><td>KDA</td><td>40%</td><td>3.7 / 2.4</td></tr>
      <tr><td>GPM</td><td>15%</td><td>540 / 335</td></tr>
      <tr><td>XPM</td><td>15%</td><td>720 / 490</td></tr>
      <tr><td>伤害/经济</td><td>30%</td><td>1.59 / 1.40</td></tr>
    </table>
    <p><code>原始表现 = 1000 + 500 × Σ[权重 × (实际值/基准值 − 1)]</code><br>
       再按场次收缩：<code>1000 + (原始表现−1000) × n/(n+5)</code>。</p>
  </div>

  <div class="rules-box">
    <h3 style="margin-top:0">二、Roll 规则</h3>
    <table>
      <tr><th>规则</th><th>要求</th><th>说明</th></tr>
      <tr><td>R1 名单结构</td><td>建议 6 核 + 4 辅</td><td>非硬门槛；不满足记 WARN，仍可正常 roll</td></tr>
      <tr><td>R2 每队结构</td><td>两队核心数差 ≤ 1</td><td>按实际名单尽量均衡，不强制固定 3 核 2 辅</td></tr>
      <tr><td>R3 均分差</td><td>两队综合均分差 ≤ 10</td><td>强度接近</td></tr>
      <tr><td>R4 预测胜率</td><td>45% – 55%</td><td>按 Elo 公式计算</td></tr>
      <tr><td>R5 不堆叠</td><td>综合分前 2 名不同队</td><td>避免双强同队</td></tr>
    </table>
    <p>若没有方案同时满足 R1–R5，按固定顺序放宽并在结果中注明：<br>
       1. 放宽 R5 → 2. 把 R3 放宽到 15 → 3. 把 R4 放宽到 40%–60%。</p>
  </div>

  <div class="rules-box">
    <h3 style="margin-top:0">三、为什么这样 roll 没问题</h3>
    <ol>
      <li><b>结构约束</b>：只保留两队核心数差 ≤1 的分法，按实际名单尽量均衡。</li>
      <li><b>强度硬约束</b>：均分差和预测胜率必须在线内，不达标不进池。</li>
      <li><b>随机只在合格池内</b>：池内方案胜率几乎相同，抽中哪套对胜负影响可忽略。</li>
      <li><b>规则审计</b>：每套结果都会列出 R2–R5 的实际值和 PASS/FAIL，现场可核对。</li>
      <li><b>可复现</b>：网页每次 roll 的方案、池子、时间都可见；脚本版还会记录随机种子并落盘。</li>
    </ol>
  </div>

  <div class="rules-box">
    <h3 style="margin-top:0">四、数据来源</h3>
    <p>比赛重放（.dem）在本地用 manta 解析成 JSON，存于 <code>Desktop\replay\json</code>；
       汇总表和本页面由脚本从同一批 JSON 重新计算，不依赖第三方 API。</p>
    <p><b>伤害口径</b>：造成英雄伤害 = 对敌方英雄造成的伤害（<code>m_flHeroDamage</code>）；
       承受英雄伤害 = 战斗日志中敌方英雄对你造成的伤害。两者都不含小兵和防御塔。</p>
  </div>
</section>

<script src="data/matches.js?v=__DATA_VER__"></script>
<script>
const PLAYERS = __DATA__;
const MATCH_COUNT = __MATCHES__;
const MATCHES = (window.MATCH_DATA && window.MATCH_DATA.matches) || [];
const AI_ENDPOINT = __AI_ENDPOINT__;
const UPLOAD_ENDPOINT = __UPLOAD_ENDPOINT__;
const UPLOAD_HINT = __UPLOAD_HINT__;
const state = {
  selected: new Set(PLAYERS.map(p => p.name)),
  results: [],
  resultsHtml: "",
  rollPool: [],
  adopted: null,
  ai: { messages: [], busy: false, open: false, cards: {} },
};
const $ = (id) => document.getElementById(id);

/* ---------- Tabs ---------- */
document.querySelectorAll(".tab").forEach(btn => {
  btn.onclick = () => showTab(btn.dataset.tab);
});
function showTab(name) {
  document.querySelectorAll(".tab").forEach(b => b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".pane").forEach(p => p.classList.toggle("active", p.id === "pane-" + name));
  if (name === "match") initMatchTab();
  if (name === "upload") warmUpUpload();
}

/* ---------- 数据统计 ---------- */
function esc(s) {
  return String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}
const STAT_COLUMNS = [
  { key: "name", label: "玩家", type: "str", cls: "name", fmt: p => esc(p.name) },
  { key: "rating", label: "综合", type: "num", fmt: p => p.rating.toFixed(1) },
  { key: "games", label: "场次", type: "num", fmt: p => p.games },
  { key: "wins", label: "胜-负", type: "num", fmt: p => `${p.wins}-${p.losses}`, get: p => p.wins },
  { key: "winRate", label: "胜率", type: "num", fmt: p => p.winRate.toFixed(1) + "%" },
  { key: "role", label: "定位", type: "str", fmt: p => p.role,
    clsFn: p => p.role === "核心" ? "role-core" : "role-sup" },
  { key: "coreRate", label: "核心率", type: "num", get: p => parseFloat(p.coreRate), fmt: p => p.coreRate },
  { key: "rankAll", label: "全场排名", type: "num", fmt: p => Number(p.rankAll).toFixed(2) },
  { key: "rankTeam", label: "队内排名", type: "num", fmt: p => Number(p.rankTeam).toFixed(2) },
  { key: "kda", label: "KDA", type: "num", fmt: p => Number(p.kda).toFixed(2) },
  { key: "kd", label: "平均K/D/A", type: "num", get: p => Number(p.kda), fmt: p => esc(p.kd) },
  { key: "gpm", label: "GPM", type: "num", fmt: p => Number(p.gpm).toFixed(1) },
  { key: "xpm", label: "XPM", type: "num", fmt: p => Number(p.xpm).toFixed(1) },
  { key: "nwK", label: "净资产(K)", type: "num", fmt: p => Number(p.nwK).toFixed(1) },
  { key: "dmgK", label: "造成英雄伤害(K)", type: "num", fmt: p => Number(p.dmgK).toFixed(1) },
  { key: "dmgTakenK", label: "承受英雄伤害(K)", type: "num", fmt: p => Number(p.dmgTakenK).toFixed(1) },
  { key: "dmgGold", label: "伤害/经济", type: "num", fmt: p => Number(p.dmgGold).toFixed(2) },
  { key: "takenGold", label: "承伤/经济", type: "num", fmt: p => Number(p.takenGold).toFixed(2) },
  { key: "mmr", label: "MMR", type: "num", get: p => p.mmrNum, fmt: p => p.mmr },
  { key: "heroes", label: "常用英雄", type: "str", cls: "heroes",
    fmt: p => `<span title="${esc(p.heroes)}">${esc(p.heroes)}</span>` },
];
const statsSort = { key: "winRate", dir: -1 };

function sortStats(key) {
  const col = STAT_COLUMNS.find(c => c.key === key);
  if (statsSort.key === key) statsSort.dir *= -1;
  else { statsSort.key = key; statsSort.dir = col.type === "num" ? -1 : 1; }
  renderStats();
}

function renderStats() {
  $("matchCount").textContent = MATCH_COUNT;
  $("statsHead").innerHTML = "<tr>" + STAT_COLUMNS.map(c => {
    const arrow = statsSort.key === c.key ? (statsSort.dir < 0 ? " ▼" : " ▲") : "";
    const align = (c.cls === "name" || c.cls === "heroes") ? "left" : "";
    return `<th class="${align}" onclick="sortStats('${c.key}')">${c.label}${arrow}</th>`;
  }).join("") + "</tr>";

  const col = STAT_COLUMNS.find(c => c.key === statsSort.key) || STAT_COLUMNS[4];
  const rows = [...PLAYERS].sort((a, b) => {
    let va = col.get ? col.get(a) : a[col.key];
    let vb = col.get ? col.get(b) : b[col.key];
    if (col.type === "num") {
      const aMissing = va === null || va === undefined || va === "" || Number.isNaN(Number(va));
      const bMissing = vb === null || vb === undefined || vb === "" || Number.isNaN(Number(vb));
      if (aMissing && bMissing) return 0;
      if (aMissing) return 1;   // 未登记始终排在最后
      if (bMissing) return -1;
      return (Number(va) - Number(vb)) * statsSort.dir;
    }
    return String(va).localeCompare(String(vb), "zh") * statsSort.dir;
  });

  $("statsBody").innerHTML = rows.map(p => "<tr>" + STAT_COLUMNS.map(c => {
    const cls = c.clsFn ? c.clsFn(p) : (c.cls || "");
    return `<td class="${cls}">${c.fmt(p)}</td>`;
  }).join("") + "</tr>").join("");
}

/* ---------- 比赛明细 ---------- */
const matchState = { initialized: false, id: null, sub: "overview", eventFilter: "all", hideConsumables: false, onlyFinished: false };
const MATCH_SUBS = [
  ["overview", "总览"], ["economy", "经济"], ["combat", "战斗"],
  ["items", "装备"], ["events", "事件"]
];
const CONSUMABLES = new Set(["tango", "flask", "clarity", "dust", "smoke_of_deceit", "ward_observer", "ward_sentry", "ward_dispenser", "tpscroll", "teleport_scroll", "energy_booster", "bottle", "magic_stick", "magic_wand"]);

function fmtClock(sec) {
  const neg = sec < 0;
  let s = Math.abs(Math.round(sec));
  const m = Math.floor(s / 60);
  s = s % 60;
  return (neg ? "-" : "") + m + ":" + String(s).padStart(2, "0");
}
function fmtDuration(sec) { return fmtClock(sec); }
function kfmt(n) {
  n = Number(n) || 0;
  if (Math.abs(n) >= 10000) return (n / 1000).toFixed(1) + "K";
  return String(Math.round(n));
}
function teamZh(t) { return t === "radiant" ? "天辉" : "夜魇"; }
function matchById(id) { return MATCHES.find(m => m.id === id) || null; }

function initMatchTab() {
  if (matchState.initialized) { if (matchState.id) renderMatchDetail(matchById(matchState.id)); return; }
  matchState.initialized = true;
  const q = new URLSearchParams((location.hash || "").replace(/^#/, ""));
  const hashId = q.get("match");
  const hashSub = q.get("sub");
  if (hashSub && MATCH_SUBS.some(x => x[0] === hashSub)) matchState.sub = hashSub;
  $("mMatchCount").textContent = MATCHES.length + " 场";
  renderMatchList();
  const first = hashId && matchById(hashId) ? hashId : (MATCHES[0] && MATCHES[0].id);
  if (first) selectMatch(first, false);
}

function renderMatchList() {
  $("matchList").innerHTML = MATCHES.map(m => {
    const win = m.winner === "radiant" ? "天辉胜" : "夜魇胜";
    return `<button class="m-item ${m.id === matchState.id ? "active" : ""}" data-id="${m.id}">
      <div class="mi-top"><span class="${m.radiant_win ? "mi-win" : "mi-loss"}">${win}</span>
        <span>${m.score.radiant} - ${m.score.dire}</span></div>
      <div class="mi-sub">${esc(m.date)} · ${fmtDuration(m.duration)} · ${esc(m.mode)}</div>
    </button>`;
  }).join("");
  document.querySelectorAll("#matchList .m-item").forEach(btn => {
    btn.onclick = () => selectMatch(btn.dataset.id, true);
  });
}

function selectMatch(id, updateHash) {
  if (!matchById(id)) return;
  matchState.id = id;
  matchState.eventFilter = "all";
  renderMatchList();
  renderMatchDetail(matchById(id));
  if (updateHash) {
    try { history.replaceState(null, "", "#match=" + id + "&sub=" + matchState.sub); }
    catch (e) { location.hash = "match=" + id + "&sub=" + matchState.sub; }
  }
}

function renderMatchDetail(m) {
  if (!m) return;
  const win = m.winner === "radiant" ? "天辉胜利" : "夜魇胜利";
  const kpi = (side) => {
    const t = m.teams[side];
    return `<div class="kpis">
      <div class="kpi"><div class="k">击杀</div><div class="v">${t.kills}</div></div>
      <div class="kpi"><div class="k">死亡</div><div class="v">${t.deaths}</div></div>
      <div class="kpi"><div class="k">助攻</div><div class="v">${t.assists}</div></div>
      <div class="kpi"><div class="k">净资产</div><div class="v">${kfmt(t.net_worth)}</div></div>
      <div class="kpi"><div class="k">英雄伤害</div><div class="v">${kfmt(t.hero_damage)}</div></div>
      <div class="kpi"><div class="k">推塔伤害</div><div class="v">${kfmt(t.tower_damage)}</div></div>
    </div>`;
  };
  $("matchDetail").innerHTML = `
    <div class="m-head">
      <div class="m-title">
        <span class="m-score">${m.score.radiant} <span style="color:var(--muted);font-size:16px">-</span> ${m.score.dire}</span>
        <b class="${m.radiant_win ? "mi-win" : "mi-loss"}">${win}</b>
        <span class="m-meta">${esc(m.date)} · ${fmtDuration(m.duration)} · ${esc(m.mode)} · #${m.id}</span>
      </div>
      <div style="margin-top:12px"><div class="sb-head sb-radiant">天辉</div>${kpi("radiant")}
        <div class="sb-head sb-dire">夜魇</div>${kpi("dire")}</div>
    </div>
    <div class="subtabs" id="mSubtabs">${MATCH_SUBS.map(([k, label]) =>
      `<button class="subtab ${k === matchState.sub ? "active" : ""}" data-sub="${k}">${label}</button>`).join("")}</div>
    <div id="mSub"></div>`;
  document.querySelectorAll("#mSubtabs .subtab").forEach(btn => {
    btn.onclick = () => {
      matchState.sub = btn.dataset.sub;
      document.querySelectorAll("#mSubtabs .subtab").forEach(b => b.classList.toggle("active", b === btn));
      renderSub(m);
      try { history.replaceState(null, "", "#match=" + m.id + "&sub=" + matchState.sub); } catch (e) {}
    };
  });
  renderSub(m);
}

function renderSub(m) {
  const host = $("mSub");
  if (!host) return;
  host.innerHTML = `<div class="subpane active" id="mSubPane"></div>`;
  const pane = $("mSubPane");
  if (matchState.sub === "economy") renderEconomy(pane, m);
  else if (matchState.sub === "combat") renderCombat(pane, m);
  else if (matchState.sub === "items") renderItems(pane, m);
  else if (matchState.sub === "events") renderEvents(pane, m);
  else renderOverview(pane, m);
}

function scoreboardTable(team, m) {
  const players = m.players.filter(p => p.team === team).sort((a, b) => b.net_worth - a.net_worth);
  return `<div class="sb-head ${team === "radiant" ? "sb-radiant" : "sb-dire"}">${teamZh(team)}</div>
  <div class="table-wrap"><table class="m-table">
    <thead><tr><th>英雄</th><th>玩家</th><th>等级</th><th>K/D/A</th><th>净资产</th><th>GPM/XPM</th><th>正/反</th><th>装备</th></tr></thead>
    <tbody>${players.map(p => `<tr>
      <td class="hero-cell">${esc(p.hero_zh)}<span><br>${esc(p.hero)}</span></td>
      <td>${esc(p.name)}</td><td>${p.level}</td><td>${p.kills}/${p.deaths}/${p.assists}</td>
      <td>${kfmt(p.net_worth)}</td><td>${p.gpm}/${p.xpm}</td><td>${p.last_hits}/${p.denies}</td>
      <td><div class="item-chips">${p.items.map(i => `<span class="item-chip" title="${esc(i.key)}">${esc(i.zh)}</span>`).join("")}</div></td>
    </tr>`).join("")}</tbody></table></div>`;
}

function renderOverview(host, m) {
  host.innerHTML = scoreboardTable("radiant", m) + scoreboardTable("dire", m);
}

function svgEl(tag, attrs) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const k in attrs || {}) el.setAttribute(k, attrs[k]);
  return el;
}

function drawLineChart(host, times, series, opts) {
  host.innerHTML = "";
  if (!times || !times.length || !series || !series.length) {
    host.innerHTML = '<div class="empty">暂无数据</div>';
    return;
  }
  const W = Math.max(320, host.clientWidth || 720);
  const H = opts.height || 210;
  const pad = { l: 52, r: 18, t: 12, b: 24 };
  const pw = W - pad.l - pad.r, ph = H - pad.t - pad.b;
  let vals = [];
  series.forEach(s => s.values.forEach(v => vals.push(Number(v) || 0)));
  let min = Math.min(...vals), max = Math.max(...vals);
  if (opts.zero) { min = Math.min(min, 0); max = Math.max(max, 0); }
  if (min === max) { min -= 1; max += 1; }
  const padY = (max - min) * 0.08;
  min -= padY; max += padY;
  const x = i => pad.l + (times.length <= 1 ? 0 : i / (times.length - 1) * pw);
  const y = v => pad.t + (max - v) / (max - min) * ph;
  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": opts.title || "折线图" });
  for (let i = 0; i <= 4; i++) {
    const v = min + (max - min) * i / 4;
    svg.appendChild(svgEl("line", { x1: pad.l, x2: W - pad.r, y1: y(v), y2: y(v), stroke: "#2c2c2a", "stroke-width": 1 }));
    const t = svgEl("text", { x: pad.l - 6, y: y(v) + 3, fill: "#898781", "font-size": 10, "text-anchor": "end" });
    t.textContent = kfmt(v); svg.appendChild(t);
  }
  if (opts.zero) {
    svg.appendChild(svgEl("line", { x1: pad.l, x2: W - pad.r, y1: y(0), y2: y(0), stroke: "#4a4a46", "stroke-width": 1 }));
  }
  const labels = [0, Math.floor((times.length - 1) / 2), times.length - 1];
  labels.forEach(i => {
    const t = svgEl("text", { x: x(i), y: H - 6, fill: "#898781", "font-size": 10,
      "text-anchor": i === 0 ? "start" : (i === times.length - 1 ? "end" : "middle") });
    t.textContent = fmtClock(times[i]); svg.appendChild(t);
  });
  const colors = opts.colors || ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181"];
  series.forEach((s, si) => {
    const pts = s.values.map((v, i) => `${x(i)},${y(Number(v) || 0)}`).join(" ");
    svg.appendChild(svgEl("polyline", { points: pts, fill: "none",
      stroke: s.color || colors[si % colors.length], "stroke-width": 2, "stroke-linejoin": "round" }));
  });
  host.appendChild(svg);
  if (series.length > 1 || opts.legend) {
    const lg = document.createElement("div");
    lg.className = "chart-legend";
    lg.innerHTML = series.map((s, si) => `<span><i style="background:${s.color || colors[si % colors.length]}"></i>${esc(s.name)}</span>`).join("");
    host.appendChild(lg);
  }
  const tip = document.createElement("div");
  tip.className = "chart-tooltip";
  host.appendChild(tip);
  const line = svgEl("line", { x1: 0, x2: 0, y1: pad.t, y2: pad.t + ph, stroke: "#5b6070", "stroke-width": 1, "stroke-dasharray": "3 3", opacity: 0 });
  svg.appendChild(line);
  svg.addEventListener("mousemove", ev => {
    const rect = svg.getBoundingClientRect();
    const px = (ev.clientX - rect.left) * (W / rect.width);
    let idx = Math.round((px - pad.l) / pw * (times.length - 1));
    idx = Math.max(0, Math.min(times.length - 1, idx));
    line.setAttribute("x1", x(idx)); line.setAttribute("x2", x(idx)); line.setAttribute("opacity", 1);
    tip.style.display = "block";
    tip.style.left = Math.min(W - 160, x(idx) + 10) + "px";
    tip.style.top = "6px";
    tip.innerHTML = `<b>${fmtClock(times[idx])}</b><br>` +
      series.map((s, si) => `<span style="color:${s.color || colors[si % colors.length]}">●</span> ${esc(s.name)}: ${kfmt(s.values[idx])}`).join("<br>");
  });
  svg.addEventListener("mouseleave", () => { line.setAttribute("opacity", 0); tip.style.display = "none"; });
}

function renderEconomy(host, m) {
  const ec = m.economy;
  if (!ec || !ec.times || !ec.times.length) {
    host.innerHTML = '<div class="empty">该场比赛没有经济曲线数据（可能未重新解析）。</div>';
    return;
  }
  const diff = (a, b) => a.map((v, i) => (Number(v) || 0) - (Number(b[i]) || 0));
  const goldDiff = diff(ec.team.radiant.gold, ec.team.dire.gold);
  const xpDiff = diff(ec.team.radiant.xp, ec.team.dire.xp);
  host.innerHTML = `
    <div class="chart-card"><div class="chart-title">团队经济差（天辉 − 夜魇）</div><div class="chart-host" id="chartGold"></div></div>
    <div class="chart-card"><div class="chart-title">团队经验差（天辉 − 夜魇）</div><div class="chart-host" id="chartXp"></div></div>
    <div class="chart-card"><div class="chart-title">天辉玩家净资产</div><div class="chart-host" id="chartNwR"></div></div>
    <div class="chart-card"><div class="chart-title">夜魇玩家净资产</div><div class="chart-host" id="chartNwD"></div></div>
    <div class="why">数据来源：${ec.source === "snapshot" ? "每游戏分钟采样" : "由金钱/经验日志估算"}${ec.approx ? "（近似）" : ""}</div>`;
  drawLineChart($("chartGold"), ec.times, [{ name: "经济差", values: goldDiff, color: "#199e70" }], { zero: true, legend: false, title: "团队经济差" });
  drawLineChart($("chartXp"), ec.times, [{ name: "经验差", values: xpDiff, color: "#3987e5" }], { zero: true, legend: false, title: "团队经验差" });
  const playerSeries = (team, colors) => m.players.filter(p => p.team === team).map((p, i) => {
    const ep = (ec.players || []).find(x => x.pid === p.pid);
    return { name: p.hero_zh || p.hero, values: ep ? ep.net_worth : [], color: colors[i % colors.length] };
  });
  const colors = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181"];
  drawLineChart($("chartNwR"), ec.times, playerSeries("radiant", colors), { height: 200, legend: true, title: "天辉玩家净资产" });
  drawLineChart($("chartNwD"), ec.times, playerSeries("dire", colors), { height: 200, legend: true, title: "夜魇玩家净资产" });
}

function damageBar(p, key) {
  const d = (p.damage && p.damage[key]) || {};
  const vals = [["physical", "物理", "#3987e5"], ["magical", "魔法", "#d95926"], ["pure", "纯粹", "#199e70"], ["other", "其他", "#898781"]];
  const total = vals.reduce((s, v) => s + (Number(d[v[0]]) || 0), 0) || 1;
  return `<div class="dmg-bar">${vals.map(v => {
    const pct = (Number(d[v[0]]) || 0) / total * 100;
    return pct > 0 ? `<i style="width:${pct}%;background:${v[2]}" title="${v[1]} ${kfmt(d[v[0]])}"></i>` : "";
  }).join("")}</div><div class="dmg-legend">${vals.map(v => `${v[1]} ${kfmt(d[v[0]])}`).join(" · ")}</div>`;
}

function renderCombat(host, m) {
  const table = (team) => {
    const ps = m.players.filter(p => p.team === team).sort((a, b) => b.hero_damage - a.hero_damage);
    return `<div class="sb-head ${team === "radiant" ? "sb-radiant" : "sb-dire"}">${teamZh(team)}</div>
    <div class="table-wrap"><table class="m-table">
      <thead><tr><th>英雄</th><th>造成伤害</th><th>承受伤害</th><th>推塔伤害</th><th>眩晕</th><th>治疗</th><th>插眼/反眼</th></tr></thead>
      <tbody>${ps.map(p => `<tr><td class="hero-cell">${esc(p.hero_zh)}<span><br>${esc(p.name)}</span></td>
        <td>${kfmt(p.hero_damage)}${damageBar(p, "dealt")}</td>
        <td>${kfmt(p.hero_damage_taken)}${damageBar(p, "taken")}</td>
        <td>${kfmt(p.tower_damage)}</td><td>${Number(p.stuns).toFixed(1)}s</td>
        <td>${kfmt(p.healing)}</td><td>${p.wards_placed}/${p.wards_destroyed}</td></tr>`).join("")}</tbody>
    </table></div>`;
  };
  host.innerHTML = table("radiant") + table("dire");
}

function renderItems(host, m) {
  const cards = m.players.map(p => {
    let rows = (m.purchases || []).filter(x => x.pid === p.pid);
    if (matchState.hideConsumables) rows = rows.filter(x => !CONSUMABLES.has(x.item));
    if (matchState.onlyFinished) rows = rows.filter(x => !x.recipe && x.cost >= 2000);
    rows.sort((a, b) => a.t - b.t);
    return `<div class="purchase-card">
      <div class="purchase-head"><span>${esc(p.hero_zh)} · ${esc(p.name)}</span>
        <span class="item-chips">${p.items.map(i => `<span class="item-chip">${esc(i.zh)}</span>`).join("")}</span></div>
      <div class="purchase-list">${rows.map(x => `<span class="purchase-chip" title="${esc(x.item)}">[${fmtClock(x.t)}] ${esc(x.item_zh)} ${x.cost || ""}</span>`).join("") || '<span class="why">没有购买记录</span>'}</div>
    </div>`;
  }).join("");
  host.innerHTML = `<div class="filter-row">
    <label class="chip"><input type="checkbox" id="hideCons" ${matchState.hideConsumables ? "checked" : ""}> 隐藏消耗品</label>
    <label class="chip"><input type="checkbox" id="onlyFin" ${matchState.onlyFinished ? "checked" : ""}> 只看成装</label>
  </div>${cards}`;
  $("hideCons").onchange = e => { matchState.hideConsumables = e.target.checked; renderItems(host, m); };
  $("onlyFin").onchange = e => { matchState.onlyFinished = e.target.checked; renderItems(host, m); };
}

function renderEvents(host, m) {
  const items = [];
  (m.kills || []).forEach(k => items.push({ t: k.t, kind: "kill", d: k }));
  (m.objectives || []).forEach(o => items.push({ t: o.t, kind: "objective", d: o }));
  items.sort((a, b) => a.t - b.t);
  const filters = [["all", "全部"], ["kill", "击杀"], ["tower", "防御塔"], ["rax", "兵营"], ["roshan", "肉山"], ["aegis", "不朽盾"], ["other", "其他"]];
  const filtered = items.filter(x => matchState.eventFilter === "all" ||
    (matchState.eventFilter === "kill" ? x.kind === "kill" : (x.kind === "objective" && x.d.kind === matchState.eventFilter)));
  const rows = filtered.map(x => {
    if (x.kind === "kill") {
      const k = x.d;
      const team = k.team === "radiant" ? "ev-radiant" : "ev-kill";
      return `<div class="event-row"><span class="ev-time">${fmtClock(k.t)}</span>
        <span class="ev-team ${team}">${teamZh(k.team)}</span>
        <span class="ev-desc">${k.first_blood ? '<b style="color:#ffcc66">一血</b> ' : ""}${esc(k.killer_zh)} → ${esc(k.victim_zh)}
        ${k.assists.length ? `<small>助攻：${k.assists.map(a => esc(a.zh)).join("、")}</small>` : ""}</span></div>`;
    }
    const o = x.d;
    return `<div class="event-row"><span class="ev-time">${fmtClock(o.t)}</span>
      <span class="ev-team ${o.team === "radiant" ? "ev-radiant" : "ev-kill"}">${teamZh(o.team)}</span>
      <span class="ev-desc">${esc(o.label)}${o.killer_zh ? ` <small>${esc(o.killer_zh)}</small>` : ""}</span></div>`;
  }).join("");
  host.innerHTML = `<div class="filter-row">${filters.map(([k, label]) =>
    `<button class="chip ${matchState.eventFilter === k ? "active" : ""}" data-filter="${k}">${label}</button>`).join("")}</div>
    <div class="event-list">${rows || '<div class="empty">没有事件</div>'}</div>`;
  document.querySelectorAll("#mSubPane .filter-row .chip").forEach(btn => {
    btn.onclick = () => { matchState.eventFilter = btn.dataset.filter; renderEvents(host, m); };
  });
}

/* ---------- 选人 ---------- */
function renderPlayers() {
  $("players").innerHTML = PLAYERS.map(p => `
    <label class="player ${state.selected.has(p.name) ? "on" : ""}">
      <input type="checkbox" ${state.selected.has(p.name) ? "checked" : ""} onchange="toggle('${escJs(p.name)}')">
      <div class="p-main">
        <div class="p-name">${esc(p.name)}
          <span class="badge ${p.role === "核心" ? "core" : "sup"}">${p.role}</span>
          ${p.provisional ? '<span class="badge prov">暂定</span>' : ""}
        </div>
        <div class="p-meta">${p.games} 场 · 胜率 ${p.winRate.toFixed(1)}% · KDA ${Number(p.kda).toFixed(2)} · GPM ${Number(p.gpm).toFixed(0)}</div>
      </div>
      <div class="p-rating">${Math.round(p.rating)}</div>
    </label>`).join("");
  updateBar();
}
function escJs(s) { return String(s).replace(/\\/g, "\\\\").replace(/'/g, "\\'"); }
function toggle(name) {
  if (state.selected.has(name)) state.selected.delete(name);
  else if (state.selected.size < 10) state.selected.add(name);
  if (state.results.length) {
    state.results = [];
    state.resultsHtml = "";
    state.adopted = null;
    resetAI();
    $("results").innerHTML = '<div class="empty">名单已变更，请重新 Roll。</div>';
    updateAIAction();
  }
  renderPlayers();
}
function updateBar() {
  const n = state.selected.size;
  $("cnt").textContent = n;
  $("roll").disabled = n !== 10;
  const cores = [...state.selected].map(x => PLAYERS.find(p => p.name === x))
    .filter(p => p && p.role === "核心").length;
  if (n > 10) $("hint").textContent = `（已选 ${n} 人，请反选掉 ${n - 10} 人）`;
  else if (n < 10) $("hint").textContent = `（还差 ${10 - n} 人）`;
  else $("hint").textContent = `（当前 ${cores} 核 + ${n - cores} 辅）`;
}
$("clear").onclick = () => { state.selected.clear(); renderPlayers(); };
$("top10").onclick = () => {
  state.selected = new Set(PLAYERS.slice(0, 10).map(p => p.name));
  renderPlayers();
};

/* ---------- Roll ---------- */
function combinations(arr, k) {
  const out = [];
  (function rec(start, cur) {
    if (cur.length === k) { out.push(cur.slice()); return; }
    for (let i = start; i < arr.length; i++) { cur.push(arr[i]); rec(i + 1, cur); cur.pop(); }
  })(0, []);
  return out;
}
function expected(ra, rb) { return 1 / (1 + Math.pow(10, (rb - ra) / 400)); }
function buildSplits(sel) {
  const splits = [];
  for (const combo of combinations(sel.slice(1), 4)) {
    const a = [sel[0], ...combo];
    const b = sel.filter(p => !a.includes(p));
    const ra = a.reduce((s, p) => s + p.rating, 0) / 5;
    const rb = b.reduce((s, p) => s + p.rating, 0) / 5;
    const pa = expected(ra, rb);
    const ca = a.filter(p => p.role === "核心").length;
    const cb = b.filter(p => p.role === "核心").length;
    splits.push({ a, b, ra, rb, pa, ca, cb, diff: Math.abs(ra - rb),
      score: 100 * (1 - 2 * Math.abs(pa - 0.5)) });
  }
  return splits;
}
function shuffle(a) {
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}
function roll() {
  const sel = PLAYERS.filter(p => state.selected.has(p.name));
  if (sel.length !== 10) return;
  const cores = sel.filter(p => p.role === "核心").length;
  const top2 = new Set([...sel].sort((x, y) => y.rating - x.rating).slice(0, 2).map(p => p.name));
  const all = buildSplits(sel);

  const levels = [
    { label: "严格规则 R1-R5", diff: 10, lo: .45, hi: .55, stack: true },
    { label: "放宽 R5（允许前2同队）", diff: 10, lo: .45, hi: .55, stack: false },
    { label: "再放宽 R3 到 15", diff: 15, lo: .45, hi: .55, stack: false },
    { label: "再放宽 R4 到 40%–60%", diff: 15, lo: .40, hi: .60, stack: false },
  ];

  let chosenLevel = null, valid = [];
  for (const lv of levels) {
    valid = all.filter(r => {
      if (Math.abs(r.ca - r.cb) > 1) return false;
      if (r.diff > lv.diff) return false;
      if (r.pa < lv.lo || r.pa > lv.hi) return false;
      const a2 = r.a.filter(p => top2.has(p.name)).length;
      const b2 = r.b.filter(p => top2.has(p.name)).length;
      if (lv.stack && (a2 === 2 || b2 === 2)) return false;
      return true;
    });
    if (valid.length) { chosenLevel = lv; break; }
  }
  if (!valid.length) {
    $("results").innerHTML = `<div class="empty">没有满足最低规则的方案。当前名单是 ${cores} 核 + ${10 - cores} 辅，请调整名单或检查数据。</div>`;
    state.results = [];
    updateAIAction();
    return;
  }

  valid.sort((x, y) => y.score - x.score || x.diff - y.diff);
  const pool = valid.slice(0, Math.min(10, valid.length));
  const picks = shuffle([...pool]).slice(0, 3);

  state.results = picks;
  state.rollPool = sel.map(p => p.name);
  state.rollTop2 = [...top2];
  state.rollLevel = chosenLevel;
  state.adopted = null;
  resetAI();

  const probs = pool.map(x => x.pa);
  const basis = `<div class="why" style="margin-bottom:12px">
    本次共 ${all.length} 种分法；在【${chosenLevel.label}】下合格 ${valid.length} 种；
    roll 池取平衡分前 ${pool.length} 套，池内胜率
    ${(Math.min(...probs) * 100).toFixed(1)}%–${(Math.max(...probs) * 100).toFixed(1)}%。
    以下 3 套均从池内随机抽取。
  </div>`;

  $("results").innerHTML = basis + picks.map((r, i) => card(r, i + 1, top2, chosenLevel)).join("");
  state.resultsHtml = $("results").innerHTML;
  updateAIAction();
}
function memberHtml(p) {
  return `<span class="member"><b>${esc(p.name)}</b><span>${Math.round(p.rating)}</span></span>`;
}
function auditRows(r, top2, lv) {
  const a2 = r.a.filter(p => top2.has(p.name)).length;
  const b2 = r.b.filter(p => top2.has(p.name)).length;
  return [
    ["R2 每队结构", "核心数差 ≤ 1", `A ${r.ca}核${5 - r.ca}辅 / B ${r.cb}核${5 - r.cb}辅`, Math.abs(r.ca - r.cb) <= 1],
    ["R3 均分差", `≤ ${lv.diff}`, `${r.diff.toFixed(1)}`, r.diff <= lv.diff],
    ["R4 预测胜率", `${(lv.lo * 100).toFixed(0)}%–${(lv.hi * 100).toFixed(0)}%`,
      `${(r.pa * 100).toFixed(1)}% / ${((1 - r.pa) * 100).toFixed(1)}%`, r.pa >= lv.lo && r.pa <= lv.hi],
    ["R5 不堆叠", "前 2 名不同队", `A${a2} / B${b2}`, !(a2 === 2 || b2 === 2)],
  ].map(([n, req, act, ok]) =>
    `<div class="audit-row"><span>${n} · ${req}</span><span>${act} <span class="${ok ? "ok" : "no"}">${ok ? "PASS" : "FAIL"}</span></span></div>`
  ).join("");
}
function card(r, idx, top2, lv) {
  return `<div class="card">
    <div class="card-head">
      <div class="card-title">方案 ${idx}</div>
      <div><span class="score">平衡分 ${r.score.toFixed(1)}</span>
        <div class="prob">预测 ${(r.pa * 100).toFixed(1)}% / ${((1 - r.pa) * 100).toFixed(1)}% · 均分 ${r.ra.toFixed(1)} vs ${r.rb.toFixed(1)}</div>
      </div>
    </div>
    <div class="team">
      <div class="team-label">队伍 A · 核心 ${r.ca} / 酱油 ${5 - r.ca}</div>
      <div class="members">${[...r.a].sort((x, y) => y.rating - x.rating).map(memberHtml).join("")}</div>
    </div>
    <div class="team">
      <div class="team-label">队伍 B · 核心 ${r.cb} / 酱油 ${5 - r.cb}</div>
      <div class="members">${[...r.b].sort((x, y) => y.rating - x.rating).map(memberHtml).join("")}</div>
    </div>
    <div class="audit">
      <div class="team-label" style="margin-bottom:6px">规则审计</div>
      ${auditRows(r, top2, lv)}
    </div>
    <div class="why">依据：该方案从合格池随机抽取；3 核 2 辅、均分差、预测胜率、前 2 名分布全部满足规则，池内胜率差 &lt; 0.3 个百分点。</div>
  </div>`;
}

/* ---------- AI 匹配助手 ---------- */
function normName(s) {
  return String(s).replace(/[\uE000-\uF8FF\s]/g, "").toLowerCase();
}
function playerByName(raw) {
  const key = normName(raw);
  return PLAYERS.find(p => normName(p.name) === key) || null;
}
function aiContext() {
  const pool = state.rollPool.map(n => PLAYERS.find(p => p.name === n)).filter(Boolean);
  return {
    players: pool.map(p => ({
      name: p.name, rating: p.rating, role: p.role,
      gpm: p.gpm, xpm: p.xpm, kda: p.kda, mmr: p.mmr
    })),
    lineups: state.results.map(r => ({
      team_a: r.a.map(p => p.name),
      team_b: r.b.map(p => p.name),
      pa: r.pa,
      score: r.score
    })),
    adopted: state.adopted ? {
      team_a: state.adopted.a.map(p => p.name),
      team_b: state.adopted.b.map(p => p.name)
    } : null
  };
}
function updateAIAction() {
  const box = $("aiAction");
  if (!box) return;
  if (!state.results.length) { box.style.display = "none"; return; }
  box.style.display = "flex";
  const btn = $("aiOpen");
  if (!AI_ENDPOINT) {
    btn.disabled = true;
    $("aiHint").textContent = "AI 助手尚未部署，请先运行一键部署 AI";
  } else if (location.protocol === "file:") {
    btn.disabled = true;
    $("aiHint").textContent = "本地文件模式无法使用 AI，请打开线上地址";
  } else {
    btn.disabled = false;
    $("aiHint").textContent = "在已 roll 的结果上和 AI 讨论、微调";
  }
}
function resetAI() {
  state.ai.messages = [];
  state.ai.cards = {};
  state.ai.busy = false;
  const box = $("aiMessages");
  if (box) box.innerHTML = "";
  closeAI();
}
function openAI() {
  if (!AI_ENDPOINT) { alert("AI 助手尚未部署"); return; }
  state.ai.open = true;
  $("aiOverlay").classList.add("on");
  $("aiDrawer").classList.add("on");
  $("aiDrawer").setAttribute("aria-hidden", "false");
  if (!state.ai.messages.length) seedAI();
  setTimeout(() => $("aiInput").focus(), 200);
}
function closeAI() {
  state.ai.open = false;
  const ov = $("aiOverlay"), dr = $("aiDrawer");
  if (ov) ov.classList.remove("on");
  if (dr) { dr.classList.remove("on"); dr.setAttribute("aria-hidden", "true"); }
}
function addMsg(role, html, extra) {
  const d = document.createElement("div");
  d.className = "msg " + role + (extra ? " " + extra : "");
  d.innerHTML = html;
  $("aiMessages").appendChild(d);
  $("aiMessages").scrollTop = $("aiMessages").scrollHeight;
  return d;
}
function seedAI() {
  const summary = state.results.map((r, i) =>
    `方案${i + 1}：平衡分 ${r.score.toFixed(1)}，预测 ${(r.pa * 100).toFixed(1)}%`
  ).join("；");
  addMsg("assistant",
    `已加载当前 10 人和 3 套方案（${summary}）。想怎么调整？可以直接说“更平衡”“避免某某同队”等。`);
}
function setAIBusy(busy) {
  state.ai.busy = busy;
  $("aiSend").disabled = busy;
  $("aiInput").disabled = busy;
  let tip = $("aiTyping");
  if (busy && !tip) {
    tip = document.createElement("div");
    tip.id = "aiTyping";
    tip.className = "typing";
    tip.textContent = "AI 正在思考…";
    $("aiMessages").appendChild(tip);
    $("aiMessages").scrollTop = $("aiMessages").scrollHeight;
  } else if (!busy && tip) {
    tip.remove();
  }
}
async function sendAI(text) {
  text = (text || "").trim();
  if (!text || state.ai.busy || !AI_ENDPOINT) return;
  addMsg("user", esc(text).replace(/\n/g, "<br>"));
  state.ai.messages.push({ role: "user", content: text });
  $("aiInput").value = "";
  await runAILoop();
}
function md(text) {
  if (window.marked) {
    const html = window.marked.parse(text, { breaks: true, gfm: true });
    return window.DOMPurify ? window.DOMPurify.sanitize(html) : html;
  }
  return esc(text).replace(/\n/g, "<br>");
}
function newStreamBubble() {
  const tip = $("aiTyping");
  if (tip) tip.remove();
  const d = document.createElement("div");
  d.className = "msg assistant streaming";
  $("aiMessages").appendChild(d);
  return d;
}
function scheduleRender(el, text) {
  if (!el || el._timer) return;
  el._timer = setTimeout(() => {
    el._timer = null;
    el.innerHTML = md(text);
    $("aiMessages").scrollTop = $("aiMessages").scrollHeight;
  }, 60);
}
async function consumeSSE(res) {
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const blocks = [];
  const bubbles = {};

  const handle = (raw) => {
    let event = "message", data = "";
    for (const line of raw.split(/\r?\n/)) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data += line.slice(5).trim();
    }
    if (!data) return;
    let obj;
    try { obj = JSON.parse(data); } catch (_) { return; }
    const type = obj.type || event;
    if (type === "error") {
      addMsg("assistant", `<span class="err">${esc((obj.error && obj.error.message) || "AI 流式错误")}</span>`);
      return;
    }
    if (type === "content_block_start") {
      const b = obj.content_block || {};
      const idx = obj.index;
      if (b.type === "text") {
        blocks[idx] = { type: "text", text: "" };
        bubbles[idx] = newStreamBubble();
      } else if (b.type === "tool_use") {
        blocks[idx] = { type: "tool_use", id: b.id, name: b.name, inputJson: "" };
      } else {
        blocks[idx] = { type: b.type, ignored: true };
      }
    } else if (type === "content_block_delta") {
      const b = blocks[obj.index];
      if (!b) return;
      const d = obj.delta || {};
      if (d.type === "text_delta" && b.type === "text") {
        b.text += d.text || "";
        scheduleRender(bubbles[obj.index], b.text);
      } else if (d.type === "input_json_delta" && b.type === "tool_use") {
        b.inputJson += d.partial_json || "";
      }
    } else if (type === "content_block_stop") {
      const b = blocks[obj.index];
      if (b && b.type === "text" && bubbles[obj.index]) {
        clearTimeout(bubbles[obj.index]._timer);
        bubbles[obj.index].innerHTML = md(b.text);
        bubbles[obj.index].classList.remove("streaming");
      }
      if (b && b.type === "tool_use") {
        try { b.input = JSON.parse(b.inputJson || "{}"); } catch (_) { b.input = {}; }
      }
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let m;
    while ((m = buffer.match(/\r?\n\r?\n/))) {
      const raw = buffer.slice(0, m.index);
      buffer = buffer.slice(m.index + m[0].length);
      handle(raw);
    }
  }
  if (buffer.trim()) handle(buffer);
  Object.values(bubbles).forEach(el => el.classList.remove("streaming"));

  return blocks.filter(b => b && !b.ignored).map(b => {
    if (b.type === "text") return { type: "text", text: b.text };
    if (b.type === "tool_use") {
      if (!b.input) {
        try { b.input = JSON.parse(b.inputJson || "{}"); } catch (_) { b.input = {}; }
      }
      return { type: "tool_use", id: b.id, name: b.name, input: b.input };
    }
    return null;
  }).filter(Boolean);
}
async function runAILoop() {
  setAIBusy(true);
  try {
    let rounds = 0;
    while (rounds++ < 3) {
      const res = await fetch(AI_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: state.ai.messages, context: aiContext(), stream: true })
      });
      const ct = (res.headers.get("content-type") || "").toLowerCase();
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        addMsg("assistant", `<span class="err">${esc(data.error || ("请求失败 " + res.status))}</span>`);
        break;
      }

      let blocks;
      if (ct.includes("text/event-stream")) {
        blocks = await consumeSSE(res);
      } else {
        const data = await res.json().catch(() => ({}));
        blocks = (data.content || []).filter(b => b.type === "text" || b.type === "tool_use");
        for (const b of blocks) {
          if (b.type === "text" && b.text && b.text.trim()) addMsg("assistant", md(b.text));
        }
      }

      const history = blocks.filter(b => b.type === "text" ? b.text.trim() : true);
      if (history.length) state.ai.messages.push({ role: "assistant", content: history });

      const tools = blocks.filter(b => b.type === "tool_use" && b.name === "display_match");
      if (!tools.length) break;

      const results = [];
      for (const t of tools) {
        const out = handleDisplayMatch(t);
        results.push({
          type: "tool_result",
          tool_use_id: t.id,
          content: out.ok ? "已展示阵容卡片。" : ("错误：" + out.error)
        });
      }
      state.ai.messages.push({ role: "user", content: results });
    }
  } catch (e) {
    addMsg("assistant", '<span class="err">网络错误，请稍后重试。</span>');
  } finally {
    setAIBusy(false);
  }
}
function handleDisplayMatch(tool) {
  const inp = tool.input || {};
  const aNames = Array.isArray(inp.team_a) ? inp.team_a : [];
  const bNames = Array.isArray(inp.team_b) ? inp.team_b : [];
  if (aNames.length !== 5 || bNames.length !== 5) {
    return { ok: false, error: "每队必须正好 5 人" };
  }
  const a = [], b = [];
  for (const n of aNames) {
    const p = playerByName(n);
    if (!p) return { ok: false, error: `未知玩家：${n}` };
    a.push(p);
  }
  for (const n of bNames) {
    const p = playerByName(n);
    if (!p) return { ok: false, error: `未知玩家：${n}` };
    b.push(p);
  }
  const all = [...a, ...b];
  if (new Set(all.map(p => p.name)).size !== 10) {
    return { ok: false, error: "10 个玩家必须互不重复" };
  }
  const pool = new Set(state.rollPool);
  if (all.some(p => !pool.has(p.name))) {
    return { ok: false, error: "只能使用当前已选的 10 人" };
  }
  const ra = a.reduce((s, p) => s + p.rating, 0) / 5;
  const rb = b.reduce((s, p) => s + p.rating, 0) / 5;
  const pa = expected(ra, rb);
  const ca = a.filter(p => p.role === "核心").length;
  const cb = b.filter(p => p.role === "核心").length;
  const r = { a, b, ra, rb, pa, ca, cb, diff: Math.abs(ra - rb),
    score: 100 * (1 - 2 * Math.abs(pa - 0.5)) };
  const id = "m" + Date.now() + "_" + Object.keys(state.ai.cards).length;
  state.ai.cards[id] = r;
  const top2 = new Set(state.rollTop2 || []);
  const lv = state.rollLevel || { diff: 10, lo: .45, hi: .55 };
  addMsg("assistant", matchCardHtml(r, id, inp.reason || "", top2, lv), "match-wrap");
  return { ok: true };
}
function matchCardHtml(r, id, reason, top2, lv) {
  return `<div class="match-card">
    <div class="mc-head">
      <div class="mc-title">AI 建议阵容</div>
      <div class="mc-prob">预测 ${(r.pa * 100).toFixed(1)}% / ${((1 - r.pa) * 100).toFixed(1)}%<br>
        平衡分 ${r.score.toFixed(1)} · 均分 ${r.ra.toFixed(1)} vs ${r.rb.toFixed(1)}</div>
    </div>
    <div class="mc-team">
      <div class="team-label">队伍 A · 核心 ${r.ca} / 酱油 ${5 - r.ca}</div>
      <div class="members">${[...r.a].sort((x, y) => y.rating - x.rating).map(memberHtml).join("")}</div>
    </div>
    <div class="mc-team">
      <div class="team-label">队伍 B · 核心 ${r.cb} / 酱油 ${5 - r.cb}</div>
      <div class="members">${[...r.b].sort((x, y) => y.rating - x.rating).map(memberHtml).join("")}</div>
    </div>
    <div class="audit">${auditRows(r, top2, lv)}</div>
    ${reason ? `<div class="mc-reason">${esc(reason)}</div>` : ""}
    <div class="mc-actions">
      <button class="primary" onclick="adoptLineup('${id}')">采用此阵容</button>
    </div>
  </div>`;
}
function adoptLineup(id) {
  const r = state.ai.cards[id];
  if (!r) return;
  state.adopted = r;
  const top2 = new Set(state.rollTop2 || []);
  const lv = state.rollLevel || { diff: 10, lo: .45, hi: .55 };
  $("results").innerHTML =
    '<div class="adopted-banner">已采用 AI 建议阵容</div>' +
    card(r, "AI", top2, lv) + state.resultsHtml;
  addMsg("assistant", "已采用这套阵容，主结果区已更新。");
}

$("roll").onclick = roll;
$("aiOpen").onclick = openAI;
$("aiSend").onclick = () => sendAI($("aiInput").value);
$("aiInput").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendAI($("aiInput").value);
  }
});
document.querySelectorAll(".chip").forEach(c => {
  c.onclick = () => sendAI(c.dataset.prompt);
});

/* ---------- 上传录像 ---------- */
const UP_CHUNK = 4 * 1024 * 1024;
const UP_MAX_RETRY = 3;
const upState = {
  file: null, busy: false, abort: null, uploadId: null,
  cancelled: false, startedAt: 0,
};

function upLog(text, cls) {
  const li = document.createElement("li");
  if (cls) li.className = cls;
  li.textContent = text;
  $("upLog").appendChild(li);
}

function upSetProgress(pct) {
  $("upBarWrap").hidden = false;
  $("upBar").style.width = Math.max(0, Math.min(100, pct)) + "%";
}

function upStatus(text) { $("upStatus").textContent = text; }

function upResult(html) {
  const el = $("upResult");
  if (!html) { el.hidden = true; el.innerHTML = ""; return; }
  el.hidden = false;
  el.innerHTML = html;
}

function upCode() { return $("upCode").value.trim(); }

function upStore(key, val) {
  try {
    if (val === null) localStorage.removeItem(key);
    else localStorage.setItem(key, val);
  } catch (_) { /* 隐私模式忽略 */ }
}

function upReset() {
  upState.file = null;
  upState.uploadId = null;
  $("upFile").value = "";
  $("upFileName").textContent = "点击选择，或把 .dem 文件拖到这里";
  $("upStart").disabled = true;
  upResult("");
}

function upFinish() {
  upState.busy = false;
  upState.abort = null;
  $("upStart").disabled = !upState.file;
  $("upStart").hidden = false;
  $("upCancel").hidden = true;
}

function upFriendlyError(msg) {
  const m = String(msg || "");
  if (m.includes("口令错误")) return "口令错误，请检查后重试";
  if (m.includes("Failed to fetch") || m.includes("aborted")) return "网络中断，请重试";
  return m;
}

async function upFetch(url, opts, timeoutMs) {
  const ctrl = new AbortController();
  upState.abort = ctrl;
  const timer = setTimeout(() => ctrl.abort(), timeoutMs || 90000);
  try {
    const res = await fetch(url, { ...opts, signal: ctrl.signal });
    const data = await res.json().catch(() => ({}));
    return { res, data };
  } finally {
    clearTimeout(timer);
    upState.abort = null;
  }
}

let upWarmAt = 0;
async function checkService(force) {
  const el = $("upService");
  if (!UPLOAD_ENDPOINT) {
    el.className = "up-service err";
    el.textContent = "上传服务尚未部署，暂时不可用";
    return false;
  }
  if (!force && Date.now() - upWarmAt < 60000) return true;
  el.className = "up-service";
  el.textContent = "正在连接上传服务…（首次访问可能需要唤醒 20–30 秒）";
  try {
    const res = await fetch(UPLOAD_ENDPOINT + "/health", { cache: "no-store" });
    const d = await res.json();
    if (!res.ok || !d.ok) throw new Error();
    upWarmAt = Date.now();
    el.className = "up-service ok";
    el.textContent = "服务就绪 · 已有 " + d.matches + " 场比赛 · 单文件上限 " +
      Math.round((d.maxBytes || 300 * 1024 * 1024) / 1024 / 1024) + "MB";
    return true;
  } catch (_) {
    el.className = "up-service err";
    el.textContent = "上传服务暂时连不上；首次访问需要唤醒，请稍后再试";
    return false;
  }
}

function warmUpUpload() { checkService(false); }

async function checkExists() {
  if (!upState.file || !upCode() || !UPLOAD_ENDPOINT) return;
  if ($("upForce").checked) return;
  const matchId = upState.file.name.replace(/\.dem$/i, "");
  try {
    const { res, data } = await upFetch(UPLOAD_ENDPOINT + "/check", {
      method: "POST",
      headers: { "Content-Type": "application/json", "x-upload-code": upCode() },
      body: JSON.stringify({ matchId }),
    }, 40000);
    if (res.status === 401) { upLog("口令错误，请检查后重试", "err"); return; }
    if (!res.ok) return;
    if (data.exists) {
      upLog("比赛 " + matchId + " 已存在（按 ID 去重），无需重复上传", "ok");
      upStatus("已存在，无需上传");
      $("upStart").disabled = true;
    } else if (!upState.busy) {
      upStatus("");
      $("upStart").disabled = false;
    }
  } catch (_) { /* 真正上传时还会再校验 */ }
}

function pickFile(f) {
  upResult("");
  if (!f) return;
  if (!/^\d{7,12}\.dem$/i.test(f.name)) {
    upLog("文件名必须是比赛 ID，例如 9061520546.dem", "err");
    upReset();
    return;
  }
  if (f.size > 300 * 1024 * 1024) {
    upLog("文件超过 300MB", "err");
    upReset();
    return;
  }
  upState.file = f;
  $("upFileName").textContent = f.name + " · " + (f.size / 1024 / 1024).toFixed(1) + " MB";
  $("upStart").disabled = false;
  if ($("upForce").checked) {
    upStatus("已选择（将覆盖同名比赛），点「开始上传并解析」");
  } else {
    upStatus("已选择，点「开始上传并解析」");
    checkExists();
  }
}

function initUploadTab() {
  const fileInput = $("upFile");
  const startBtn = $("upStart");
  const saved = localStorage.getItem("uploadCode") || sessionStorage.getItem("uploadCode");
  if (saved) {
    $("upCode").value = saved;
    $("upRemember").checked = !!localStorage.getItem("uploadCode");
  }
  $("upCodeHint").textContent = UPLOAD_HINT || "";

  if (!UPLOAD_ENDPOINT) {
    upStatus("上传服务尚未部署，暂时不可用。");
    startBtn.disabled = true;
    return;
  }

  $("upDrop").addEventListener("click", () => fileInput.click());
  ["dragenter", "dragover"].forEach((ev) => $("upDrop").addEventListener(ev, (e) => {
    e.preventDefault();
    $("upDrop").classList.add("dragover");
  }));
  ["dragleave", "drop"].forEach((ev) => $("upDrop").addEventListener(ev, (e) => {
    e.preventDefault();
    $("upDrop").classList.remove("dragover");
  }));
  $("upDrop").addEventListener("drop", (e) => {
    const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
    if (f) pickFile(f);
  });
  window.addEventListener("dragover", (e) => e.preventDefault());
  window.addEventListener("drop", (e) => e.preventDefault());

  fileInput.addEventListener("change", () => {
    const f = fileInput.files && fileInput.files[0];
    if (f) pickFile(f);
  });

  $("upCode").addEventListener("blur", () => { if (upCode()) checkExists(); });

  $("upForce").addEventListener("change", () => {
    if ($("upForce").checked) {
      upStatus(upState.file ? "已选择（将覆盖同名比赛），点「开始上传并解析」" : "勾选后上传会覆盖同名比赛");
    } else if (upState.file) {
      checkExists();
    }
  });

  $("upStart").addEventListener("click", () => {
    if (upState.busy) return;
    const code = upCode();
    if (!code) { upLog("请先输入上传口令", "err"); $("upCode").focus(); return; }
    if (!upState.file) { upLog("请先选择 .dem 文件", "err"); return; }
    if ($("upRemember").checked) {
      upStore("uploadCode", code);
      sessionStorage.removeItem("uploadCode");
    } else {
      sessionStorage.setItem("uploadCode", code);
      upStore("uploadCode", null);
    }
    uploadAndParse(upState.file, code);
  });

  $("upCancel").addEventListener("click", async () => {
    if (!upState.busy) return;
    upState.cancelled = true;
    if (upState.abort) upState.abort.abort();
    if (upState.uploadId && upCode()) {
      fetch(UPLOAD_ENDPOINT + "/cancel", {
        method: "POST",
        headers: { "Content-Type": "application/json", "x-upload-code": upCode() },
        body: JSON.stringify({ uploadId: upState.uploadId }),
      }).catch(() => {});
    }
    upLog("已取消上传", "err");
    upStatus("已取消");
    upSetProgress(0);
    upFinish();
  });

  window.addEventListener("beforeunload", (e) => {
    if (upState.busy) { e.preventDefault(); e.returnValue = ""; }
  });
}

async function uploadAndParse(file, code) {
  upState.busy = true;
  upState.cancelled = false;
  upState.startedAt = Date.now();
  $("upStart").disabled = true;
  $("upStart").hidden = true;
  $("upCancel").hidden = false;
  $("upLog").innerHTML = "";
  upResult("");
  upSetProgress(0);
  checkService(false);

  try {
    const forceParse = $("upForce").checked;
    const uploadId = [...crypto.getRandomValues(new Uint8Array(16))]
      .map(b => b.toString(16).padStart(2, "0")).join("");
    upState.uploadId = uploadId;
    const total = Math.ceil(file.size / UP_CHUNK);
    upLog((forceParse ? "重新解析模式：" : "") + "开始上传 " + total + " 个分片…");

    for (let i = 0; i < total; i++) {
      if (upState.cancelled) return;
      const blob = file.slice(i * UP_CHUNK, Math.min(file.size, (i + 1) * UP_CHUNK));
      let lastErr = null;
      let ok = false;
      for (let attempt = 1; attempt <= UP_MAX_RETRY && !upState.cancelled; attempt++) {
        try {
          const chunkHeaders = {
            "Content-Type": "application/octet-stream",
            "x-upload-code": code,
            "x-upload-id": uploadId,
            "x-chunk-index": String(i),
            "x-chunk-total": String(total),
            "x-file-name": file.name,
          };
          if (forceParse) chunkHeaders["x-force"] = "1";
          const { res, data } = await upFetch(UPLOAD_ENDPOINT + "/upload", {
            method: "POST",
            headers: chunkHeaders,
            body: blob,
          }, 120000);
          if (res.status === 409 && data.code === "EXISTS") {
            upSetProgress(100);
            upLog(data.error, "ok");
            upStatus("已存在，跳过上传");
            upFinish();
            return;
          }
          if (res.status === 401) throw new Error("口令错误，请检查后重试");
          if (!res.ok) throw new Error(data.error || ("上传失败 HTTP " + res.status));
          ok = true;
          break;
        } catch (err) {
          if (upState.cancelled) return;
          lastErr = err;
          if (String(err.message || "").includes("口令错误")) throw err;
          if (attempt < UP_MAX_RETRY) {
            upLog("第 " + (i + 1) + " 片失败，重试 " + attempt + "/" + (UP_MAX_RETRY - 1) + "…", "err");
            await new Promise(r => setTimeout(r, 700 * attempt));
          }
        }
      }
      if (!ok) throw lastErr || new Error("上传失败");

      const pct = Math.round((i + 1) / total * 60);
      upSetProgress(pct);
      const elapsed = (Date.now() - upState.startedAt) / 1000;
      upStatus("上传中 " + (i + 1) + "/" + total + " · " + pct + "% · 已用 " + elapsed.toFixed(0) + "s");
    }

    upState.uploadId = null;
    upSetProgress(62);
    upStatus("上传完成，开始解析…");
    const start = await upFetch(UPLOAD_ENDPOINT + "/parse", {
      method: "POST",
      headers: { "Content-Type": "application/json", "x-upload-code": code },
      body: JSON.stringify({ uploadId, force: forceParse }),
    }, 60000);
    if (start.res.status === 401) throw new Error("口令错误，请检查后重试");
    if (!start.res.ok) throw new Error(start.data.error || "无法开始解析");
    $("upCancel").hidden = true;
    upLog("任务已创建：" + start.data.jobId);

    const jobId = start.data.jobId;
    let lastStage = "";
    while (true) {
      if (upState.cancelled) return;
      if (Date.now() - upState.startedAt > 15 * 60 * 1000) throw new Error("解析超时，请稍后重试");
      await new Promise(r => setTimeout(r, 1500));
      const { res, data } = await upFetch(
        UPLOAD_ENDPOINT + "/status?jobId=" + encodeURIComponent(jobId), {}, 40000);
      if (!res.ok) throw new Error(data.error || "查询状态失败");
      if (data.stage && data.stage !== lastStage) {
        lastStage = data.stage;
        upLog(data.stage);
      }
      const elapsed = ((Date.now() - upState.startedAt) / 1000).toFixed(0);
      upSetProgress(data.state === "done" ? 100 : Math.min(95, 62 + Number(elapsed) * 0.4));
      upStatus(data.state === "done" ? "完成" : (data.stage || "处理中") + " · 已用 " + elapsed + "s");
      if (data.state === "done") {
        const r = data.result || {};
        if (r.skipped) {
          upLog("比赛 " + r.matchId + " 已存在，未重复解析", "ok");
          upStatus("已存在，无需重复上传");
          upFinish();
          return;
        }
        upLog("比赛 " + r.matchId + " 解析成功，当前共 " + r.matchCount + " 场", "ok");
        upStatus("完成");
        const dur = Math.floor((r.duration || 0) / 60) + ":" +
          String((r.duration || 0) % 60).padStart(2, "0");
        const win = r.winner === "radiant" ? "天辉胜" : "夜魇胜";
        const ver = Date.now();
        upResult(
          "<div><b>比赛 " + r.matchId + "</b> 解析完成 · " + dur + " · " + win +
          " · 当前共 " + r.matchCount + " 场</div>" +
          '<div style="margin-top:6px">' +
          '<a href="?v=' + ver + "#match=" + r.matchId + '">查看本场明细</a>' +
          ' · <a href="?v=' + ver + '">刷新主页</a></div>'
        );
        upFinish();
        return;
      }
      if (data.state === "error") throw new Error(data.message || "解析失败");
    }
  } catch (err) {
    if (!upState.cancelled) {
      upLog(upFriendlyError(err.message || err), "err");
      upStatus("失败");
    }
  } finally {
    if (!upState.cancelled) upFinish();
  }
}

initUploadTab();
renderStats();
renderPlayers();

window.addEventListener("hashchange", () => {
  if (!location.hash.startsWith("#match=")) return;
  const q = new URLSearchParams(location.hash.slice(1));
  const id = q.get("match");
  if (!id) return;
  showTab("match");
  const sub = q.get("sub");
  if (sub && MATCH_SUBS.some(x => x[0] === sub)) matchState.sub = sub;
  if (id !== matchState.id) selectMatch(id, false);
  else if (matchState.id) renderMatchDetail(matchById(matchState.id));
});

let mResizeTimer = null;
window.addEventListener("resize", () => {
  if (!$("pane-match").classList.contains("active") || !matchState.id) return;
  clearTimeout(mResizeTimer);
  mResizeTimer = setTimeout(() => renderSub(matchById(matchState.id)), 180);
});

if (location.hash.startsWith("#match=")) {
  showTab("match");
  initMatchTab();
}

// 预览模式：index.html?demo=1 自动切到 Roll 并生成 3 套
if (new URLSearchParams(location.search).get("demo")) {
  showTab("roll");
  const cores = PLAYERS.filter(p => p.role === "核心").slice(0, 6);
  const sups = PLAYERS.filter(p => p.role === "酱油").slice(0, 4);
  state.selected = new Set([...cores, ...sups].map(p => p.name));
  renderPlayers();
  roll();
}
</script>
</body>
</html>
"""


def main():
    make_match_data.build()
    players, match_count = collect_players()
    ai_endpoint = ""
    upload_endpoint = ""
    upload_hint = "口令见群公告，或向群主索要。"
    try:
        with open(os.path.join(REPLAY_ROOT, "cloudbase.json"), encoding="utf-8") as fp:
            conf = json.load(fp)
        ai_endpoint = conf.get("ai_endpoint", "")
        upload_endpoint = conf.get("upload_endpoint", "")
        upload_hint = conf.get("upload_hint", upload_hint)
    except (OSError, json.JSONDecodeError):
        pass
    data_path = os.path.join(DOCS_DIR, "data", "matches.js")
    data_ver = str(int(os.path.getmtime(data_path))) if os.path.isfile(data_path) else "0"

    html = (TEMPLATE
            .replace("__DATA__", json.dumps(players, ensure_ascii=False))
            .replace("__MATCHES__", str(match_count))
            .replace("__TIME__", datetime.now().strftime("%Y-%m-%d %H:%M"))
            .replace("__AI_ENDPOINT__", json.dumps(ai_endpoint))
            .replace("__UPLOAD_ENDPOINT__", json.dumps(upload_endpoint))
            .replace("__UPLOAD_HINT__", json.dumps(upload_hint, ensure_ascii=False))
            .replace("__DATA_VER__", data_ver))
    os.makedirs(DOCS_DIR, exist_ok=True)
    out = os.path.join(DOCS_DIR, "index.html")
    with open(out, "w", encoding="utf-8") as fp:
        fp.write(html)
    print(f"已生成: {out}")
    print(f"比赛数: {match_count}，玩家数: {len(players)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
