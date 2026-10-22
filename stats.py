# -*- coding: utf-8 -*-
"""
一键统计：读取 matches 目录下的 match_*.json，按玩家汇总胜率 / GPM / XPM / 定位。

定位（核心 / 酱油）判定：
    每场比赛按「终局净资产」排名：
      - 全场 10 人排名：1 = 最有钱，10 = 最穷
      - 己方 5 人排名：1 = 队内最有钱，5 = 队内最穷
    队内排名 1~3 记为一场「核心」，4~5 记为「酱油」。
    多场比赛中核心占比 >= 50% 判为「核心」，否则「酱油」。
    同时输出全场/队内经济平均排名，排名越小越有钱。

可选：在脚本同目录新建 roles.json 手动指定定位，优先级高于自动判定，例如：
    {
      "76561198101454308": {"role": "核心"},
      "76561198096873883": {"role": "酱油"}
    }

用法:
    python stats.py                # 默认读取 桌面\\replay\\json
    python stats.py D:\\some\\dir   # 指定比赛 JSON 目录

输出（写在 JSON 目录的上一级，即 replay 根目录）:
    player_stats.csv   (Excel 可直接打开)
    player_stats.html  (浏览器查看)
"""

import csv
import glob
import html
import json
import os
import sys
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_MATCHES_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "replay", "json")


def load_matches(matches_dir):
    files = sorted(
        f for f in glob.glob(os.path.join(matches_dir, "match_*.json"))
        if not f.endswith("_raw.json")
    )
    matches = []
    for path in files:
        try:
            with open(path, encoding="utf-8") as fp:
                data = json.load(fp)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[跳过] {os.path.basename(path)}: {exc}")
            continue
        if len(data.get("players", [])) != 10 or data.get("duration", 0) <= 0:
            print(f"[跳过] {os.path.basename(path)}: 数据不完整")
            continue
        matches.append(data)
    return matches


def load_aliases():
    """读取 aliases.json，把多个账号/改名合并到同一显示名。

    格式（key 可以是玩家名或 SteamID，value 为合并后的显示名）：
        {"old zhu": "young zhu", "76561198087342825": "young zhu"}
    """
    path = os.path.join(SCRIPT_DIR, "aliases.json")
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fp:
            data = json.load(fp)
        return {str(k): str(v) for k, v in data.items()}
    except (OSError, json.JSONDecodeError, AttributeError) as exc:
        print(f"[警告] aliases.json 读取失败，忽略: {exc}")
        return {}


def load_role_overrides():
    path = os.path.join(SCRIPT_DIR, "roles.json")
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fp:
            data = json.load(fp)
        return {str(k): v for k, v in data.items()}
    except (OSError, json.JSONDecodeError, AttributeError) as exc:
        print(f"[警告] roles.json 读取失败，忽略: {exc}")
        return {}


def assign_ranks(match):
    """返回 {steamid: (全场10人排名, 队内5人排名)}，净资产越高排名越靠前。"""
    result = {}

    ranked_all = sorted(
        match["players"], key=lambda p: p.get("net_worth", 0), reverse=True
    )
    for i, p in enumerate(ranked_all):
        result.setdefault(str(p.get("steamid", "")), [None, None])[0] = i + 1

    for team in ("radiant", "dire"):
        members = [p for p in match["players"] if p.get("team") == team]
        members.sort(key=lambda p: p.get("net_worth", 0), reverse=True)
        for i, p in enumerate(members):
            result.setdefault(str(p.get("steamid", "")), [None, None])[1] = i + 1

    return {k: tuple(v) for k, v in result.items()}


def aggregate(matches):
    players = {}
    aliases = load_aliases()
    canonical_names = set(aliases.values())

    for match in matches:
        radiant_win = bool(match["radiant_win"])
        ranks = assign_ranks(match)

        for p in match["players"]:
            sid = str(p.get("steamid", ""))
            raw_name = p.get("name", "")
            canonical = aliases.get(raw_name) or aliases.get(sid)
            if not canonical and raw_name in canonical_names:
                canonical = raw_name
            if canonical:
                key = "alias:" + canonical
            else:
                key = sid or raw_name or "unknown"
            row = players.setdefault(key, {
                "steamids": [],
                "name": canonical or raw_name,
                "games": 0, "wins": 0, "core_games": 0,
                "gpm": [], "xpm": [],
                "kills": 0, "deaths": 0, "assists": 0,
                "last_hits": [], "net_worth": [], "hero_damage": [],
                "dmg_ratio": [],
                "heroes": defaultdict(int),
                "rank_all": [], "rank_team": [],
            })
            if sid and sid not in row["steamids"]:
                row["steamids"].append(sid)
            if raw_name and not canonical:
                row["name"] = raw_name

            row["games"] += 1
            won = (p.get("team") == "radiant") == radiant_win
            if won:
                row["wins"] += 1

            row["gpm"].append(p.get("gold_per_min", 0))
            row["xpm"].append(p.get("xp_per_min", 0))
            row["kills"] += p.get("kills", 0)
            row["deaths"] += p.get("deaths", 0)
            row["assists"] += p.get("assists", 0)
            row["last_hits"].append(p.get("last_hits", 0))
            net_worth = p.get("net_worth", 0)
            hero_damage = p.get("hero_damage", 0)
            row["net_worth"].append(net_worth)
            row["hero_damage"].append(hero_damage)
            row["dmg_ratio"].append(hero_damage / max(net_worth, 1))
            hero = (p.get("hero_name") or "").replace("CDOTA_Unit_Hero_", "")
            if hero:
                row["heroes"][hero] += 1

            if sid in ranks:
                rank_all, rank_team = ranks[sid]
                if rank_all:
                    row["rank_all"].append(rank_all)
                if rank_team:
                    row["rank_team"].append(rank_team)
                    if rank_team <= 3:
                        row["core_games"] += 1

    overrides = load_role_overrides()
    result = []
    for key, row in players.items():
        n = row["games"]
        avg = lambda xs: round(sum(xs) / len(xs), 1) if xs else 0.0
        mean = lambda xs: round(sum(xs) / len(xs), 2) if xs else 0.0
        kda = round((row["kills"] + row["assists"]) / max(row["deaths"], 1), 2)

        core_rate = row["core_games"] / n if n else 0.0
        role = "核心" if core_rate >= 0.5 else "酱油"

        ov = overrides.get(row["name"])
        if not ov:
            for s in row["steamids"]:
                ov = overrides.get(s)
                if ov:
                    break
        if ov and ov.get("role"):
            role = ov["role"]

        result.append({
            "玩家": row["name"],
            "SteamID": " / ".join(row["steamids"]),
            "场次": n,
            "胜": row["wins"],
            "负": n - row["wins"],
            "胜率": f"{row['wins'] / n * 100:.1f}%",
            "_winrate": row["wins"] / n,
            "定位": role,
            "核心率": f"{core_rate * 100:.0f}%",
            "_core_rate": core_rate,
            "全场经济平均排名": mean(row["rank_all"]),
            "队内经济平均排名": mean(row["rank_team"]),
            "平均GPM": avg(row["gpm"]),
            "平均XPM": avg(row["xpm"]),
            "KDA": kda,
            "平均K/D/A": (f"{row['kills'] / n:.1f}/{row['deaths'] / n:.1f}"
                          f"/{row['assists'] / n:.1f}"),
            "场均击杀": round(row["kills"] / n, 1),
            "场均死亡": round(row["deaths"] / n, 1),
            "场均助攻": round(row["assists"] / n, 1),
            "平均补刀": avg(row["last_hits"]),
            "平均净资产(K)": round(sum(row["net_worth"]) / n / 1000, 1),
            "场均英雄伤害(K)": round(sum(row["hero_damage"]) / n / 1000, 1),
            "伤害/经济": round(sum(row["dmg_ratio"]) / n, 2),
            "英雄池": len(row["heroes"]),
            "常用英雄": ", ".join(
                f"{h}({c})" for h, c in sorted(row["heroes"].items(), key=lambda x: -x[1])[:3]
            ),
        })

    result.sort(key=lambda r: (-r["_winrate"], -r["场次"], -r["平均GPM"]))
    return result


def write_csv(rows, path):
    cols = ["玩家", "SteamID", "场次", "胜", "负", "胜率", "定位", "核心率",
            "全场经济平均排名", "队内经济平均排名",
            "平均GPM", "平均XPM", "KDA", "平均K/D/A", "场均击杀", "场均死亡", "场均助攻", "平均补刀",
            "平均净资产(K)", "场均英雄伤害(K)", "伤害/经济", "英雄池", "常用英雄"]
    with open(path, "w", encoding="utf-8-sig", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r[k] for k in cols})


def write_html(rows, matches, path):
    best_gpm = max((r["平均GPM"] for r in rows), default=0)
    best_wr = max((r["_winrate"] for r in rows), default=0)

    def cls(row, key):
        if key == "gpm" and row["平均GPM"] == best_gpm:
            return "best"
        if key == "wr" and row["_winrate"] == best_wr:
            return "best"
        return ""

    body = []
    for i, r in enumerate(rows, 1):
        role_cls = "core" if r["定位"] == "核心" else "support"
        body.append(f"""<tr>
<td class="rank">{i}</td><td class="name">{html.escape(r['玩家'])}</td>
<td>{r['场次']}</td><td>{r['胜']}-{r['负']}</td>
<td class="{cls(r,'wr')}">{r['胜率']}</td>
<td class="role {role_cls}">{r['定位']}</td>
<td class="rate">{r['核心率']}</td>
<td>{r['全场经济平均排名']}</td><td>{r['队内经济平均排名']}</td>
<td class="{cls(r,'gpm')}">{r['平均GPM']}</td>
<td>{r['平均XPM']}</td>
<td>{r['KDA']}</td>
<td>{r['场均击杀']}/{r['场均死亡']}/{r['场均助攻']}</td>
<td>{r['平均补刀']}</td>
<td>{r['平均净资产(K)']:.1f}K</td>
<td>{r['场均英雄伤害(K)']:.1f}K</td>
<td>{r['伤害/经济']:.2f}</td>
<td class="heroes">{html.escape(r['常用英雄'])}</td>
</tr>""")

    doc = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>Dota 2 玩家统计</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{ margin: 0; padding: 32px; background: #14161b; color: #e6e8ec;
         font-family: "Microsoft YaHei", "Segoe UI", sans-serif; }}
  h1 {{ font-size: 22px; font-weight: 600; margin: 0 0 6px; }}
  .sub {{ color: #8a90a0; font-size: 13px; margin-bottom: 20px; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
  th, td {{ padding: 10px 12px; text-align: right; white-space: nowrap;
           border-bottom: 1px solid #242832; }}
  th {{ color: #8a90a0; font-weight: 500; position: sticky; top: 0;
        background: #14161b; font-size: 12px; }}
  td.name, th:nth-child(2) {{ text-align: left; font-weight: 600; }}
  td.rank {{ color: #5b6070; }}
  td.role {{ font-weight: 700; }}
  td.role.core {{ color: #7ee0a1; }}
  td.role.support {{ color: #c8a5ff; }}
  td.rate {{ color: #8a90a0; font-size: 12px; }}
  td.heroes {{ text-align: left; color: #a6acbb; max-width: 300px;
               overflow: hidden; text-overflow: ellipsis; }}
  tbody tr:hover {{ background: #1b1e26; }}
  td.best {{ color: #7ee0a1; font-weight: 700; }}
  .cards {{ display: flex; gap: 12px; margin-bottom: 20px; flex-wrap: wrap; }}
  .card {{ background: #1b1e26; border: 1px solid #242832; border-radius: 10px;
           padding: 12px 18px; min-width: 120px; }}
  .card .k {{ color: #8a90a0; font-size: 12px; }}
  .card .v {{ font-size: 20px; font-weight: 700; margin-top: 4px; }}
</style></head><body>
<h1>Dota 2 玩家统计</h1>
<div class="sub">共 {len(matches)} 场比赛 · 按胜率降序 · 定位依据：队内净资产排名 1–3 为核心，4–5 为酱油</div>
<div class="cards">
  <div class="card"><div class="k">比赛场次</div><div class="v">{len(matches)}</div></div>
  <div class="card"><div class="k">玩家数</div><div class="v">{len(rows)}</div></div>
  <div class="card"><div class="k">最高胜率</div><div class="v">{best_wr*100:.1f}%</div></div>
  <div class="card"><div class="k">最高平均 GPM</div><div class="v">{best_gpm}</div></div>
</div>
<table>
<thead><tr>
<th>#</th><th>玩家</th><th>场次</th><th>胜-负</th><th>胜率</th>
<th>定位</th><th>核心率</th><th>全场排名</th><th>队内排名</th>
<th>GPM</th><th>XPM</th><th>KDA</th><th>平均K/D/A</th><th>补刀</th>
<th>净资产(K)</th><th>英雄伤害(K)</th><th>伤害/经济</th><th>常用英雄</th>
</tr></thead>
<tbody>
{''.join(body)}
</tbody></table>
</body></html>"""
    with open(path, "w", encoding="utf-8") as fp:
        fp.write(doc)


def main():
    matches_dir = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MATCHES_DIR
    if not os.path.isdir(matches_dir):
        print(f"目录不存在: {matches_dir}")
        return 1
    out_dir = os.path.dirname(os.path.abspath(matches_dir))

    matches = load_matches(matches_dir)
    if not matches:
        print(f"没有找到有效的 match_*.json: {matches_dir}")
        return 1

    rows = aggregate(matches)
    csv_path = os.path.join(out_dir, "player_stats.csv")
    html_path = os.path.join(out_dir, "player_stats.html")
    write_csv(rows, csv_path)
    write_html(rows, matches, html_path)

    print(f"共 {len(matches)} 场比赛，{len(rows)} 名玩家\n")
    header = (f"{'玩家':<16}{'场次':>4}{'胜率':>8}{'定位':>6}{'核心率':>7}"
              f"{'全场排名':>8}{'队内排名':>8}{'GPM':>8}{'XPM':>8}{'KDA':>8}{'K/D/A':>18}{'伤害/经济':>10}")
    print(header)
    print("-" * len(header))
    for r in rows:
        print(f"{r['玩家'][:14]:<16}{r['场次']:>4}{r['胜率']:>8}{r['定位']:>6}{r['核心率']:>7}"
              f"{r['全场经济平均排名']:>8}{r['队内经济平均排名']:>8}"
              f"{r['平均GPM']:>8}{r['平均XPM']:>8}{r['KDA']:>8}{r['平均K/D/A']:>18}"
              f"{r['伤害/经济']:>10.2f}")
    print(f"\n已生成:\n  {csv_path}\n  {html_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
