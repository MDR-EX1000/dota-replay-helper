# -*- coding: utf-8 -*-
"""
5v5 对黑分队器：用 Elo + 表现分给 10 人分两队，枚举所有组合并按平衡度排序。

用法:
    python balance.py                          # 只显示当前评分
    python balance.py "玩家A" "玩家B" ... (10个)  # 生成分队方案
    python balance.py --top 10 "玩家A" ...       # 显示前 10 套方案

评分:
    Elo        : 初始 1000，K=32，按比赛时间顺序逐场更新
    表现分     : 绝对数值 + 位置基准，不做百分位排名。
                 核心/酱油统一权重：
                   KDA 35% / GPM 15% / XPM 15% / 伤害-经济比 35%
                 位置基准：
                   核心 KDA 3.7 / GPM 540 / XPM 720 / 伤害经济比 1.59
                   酱油 KDA 2.4 / GPM 335 / XPM 490 / 伤害经济比 1.40
                 原始表现 = 1000 + 500 × Σ[权重 × (实际值/基准值 − 1)]
                 场次收缩：1000 + (原始表现−1000) × n/(n+5)
    综合分     : 0.5 × Elo + 0.5 × 表现分
                 （Elo 已包含胜负信息，胜率只展示，不重复计分）

分队:
    10 人分成 5v5 共 C(10,5)/2 = 126 种。
    队伍分 = 5 人综合分均值。
    胜率   = 1 / (1 + 10^((R_B - R_A)/400))
    平衡分 = 100 * (1 - 2*|胜率 - 50%|)     # 100 分为完全五五开
    结构约束：两队核心数差 ≤ 1（不强制固定 3 核 2 辅）。
"""

import glob
import json
import os
import sys
from collections import defaultdict
from itertools import combinations

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MATCHES_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "replay", "json")

K_FACTOR = 32
BASE = 1000.0
START_ELO = BASE


def load_aliases():
    path = os.path.join(SCRIPT_DIR, "aliases.json")
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fp:
            return {str(k): str(v) for k, v in json.load(fp).items()}
    except (OSError, json.JSONDecodeError):
        return {}


def load_matches():
    matches = []
    for p in glob.glob(os.path.join(MATCHES_DIR, "match_*.json")):
        if p.endswith("_raw.json"):
            continue
        try:
            with open(p, encoding="utf-8") as fp:
                d = json.load(fp)
        except (OSError, json.JSONDecodeError):
            continue
        if len(d.get("players", [])) == 10 and d.get("duration", 0) > 0:
            matches.append(d)
    matches.sort(key=lambda d: d.get("start_time", 0))
    return matches


def identity(player, aliases, canonicals):
    raw = player.get("name", "")
    sid = str(player.get("steamid", ""))
    name = aliases.get(raw) or aliases.get(sid)
    if not name and raw in canonicals:
        name = raw
    return name or raw or sid, raw, sid


def build_ratings(matches):
    aliases = load_aliases()
    canonicals = set(aliases.values())

    elo = defaultdict(lambda: START_ELO)
    agg = {}

    for d in matches:
        teams = {"radiant": [], "dire": []}
        for p in d["players"]:
            key, raw, sid = identity(p, aliases, canonicals)
            teams[p["team"]].append(key)

            row = agg.setdefault(key, {
                "raw": raw, "steamids": set(),
                "games": 0, "wins": 0, "core_games": 0,
                "gpm": [], "xpm": [], "lh": [], "dmg_ratio": [],
                "kills": 0, "deaths": 0, "assists": 0,
            })
            row["steamids"].add(sid)
            row["games"] += 1
            won = (p["team"] == "radiant") == bool(d["radiant_win"])
            row["wins"] += won
            row["gpm"].append(p.get("gold_per_min", 0))
            row["xpm"].append(p.get("xp_per_min", 0))
            row["kills"] += p.get("kills", 0)
            row["deaths"] += p.get("deaths", 0)
            row["assists"] += p.get("assists", 0)
            row["lh"].append(p.get("last_hits", 0))
            hero_damage = p.get("hero_damage", 0)
            net_worth = p.get("net_worth", 0)
            row["dmg_ratio"].append(hero_damage / max(net_worth, 1))

        ra = sum(elo[k] for k in teams["radiant"]) / 5
        rb = sum(elo[k] for k in teams["dire"]) / 5
        ea = 1 / (1 + 10 ** ((rb - ra) / 400))
        sa = 1.0 if d["radiant_win"] else 0.0
        for k in teams["radiant"]:
            elo[k] += K_FACTOR * (sa - ea)
        for k in teams["dire"]:
            elo[k] += K_FACTOR * ((1 - sa) - (1 - ea))

    # 队内净资产排名 -> 核心率
    for d in matches:
        for team in ("radiant", "dire"):
            members = sorted(
                [p for p in d["players"] if p["team"] == team],
                key=lambda p: p.get("net_worth", 0), reverse=True,
            )
            for i, p in enumerate(members):
                key, _, _ = identity(p, aliases, canonicals)
                if i < 3:
                    agg[key]["core_games"] += 1

    # 定位与场均数据
    for k, r in agg.items():
        r["role"] = "核心" if r["core_games"] / max(r["games"], 1) >= 0.5 else "酱油"
        r["core_rate"] = r["core_games"] / max(r["games"], 1)
        r["win_rate"] = r["wins"] / max(r["games"], 1)
        r["avg_gpm"] = sum(r["gpm"]) / r["games"]
        r["avg_xpm"] = sum(r["xpm"]) / r["games"]
        r["avg_kda"] = (r["kills"] + r["assists"]) / max(r["deaths"], 1)
        r["avg_lh"] = sum(r["lh"]) / r["games"]
        r["avg_dmg_gold"] = sum(r["dmg_ratio"]) / r["games"]

    # 绝对值 + 位置基准，不做百分位；四项权重固定
    # 每项: (取值函数, 基准值, 权重)
    MODELS = {
        "核心": [
            (lambda r: r["avg_kda"], 3.7, 0.35),        # 战斗
            (lambda r: r["avg_gpm"], 540.0, 0.15),       # 经济
            (lambda r: r["avg_xpm"], 720.0, 0.15),       # 等级
            (lambda r: r["avg_dmg_gold"], 1.59, 0.35),   # 伤害/经济
        ],
        "酱油": [
            (lambda r: r["avg_kda"], 2.4, 0.35),
            (lambda r: r["avg_gpm"], 335.0, 0.15),
            (lambda r: r["avg_xpm"], 490.0, 0.15),
            (lambda r: r["avg_dmg_gold"], 1.40, 0.35),
        ],
    }
    perf = {}
    for k, r in agg.items():
        score = 0.0
        for getter, base, weight in MODELS[r["role"]]:
            score += weight * (getter(r) / base - 1.0)
        raw = BASE + 500.0 * score
        n = r["games"]
        shrink = n / (n + 5.0)
        perf[k] = max(BASE - 500.0, min(BASE + 500.0, BASE + (raw - BASE) * shrink))

    players = {}
    for k, r in agg.items():
        rating = 0.5 * elo[k] + 0.5 * perf[k]
        provisional = r["games"] < 2
        if provisional:
            rating = BASE
        players[k] = {
            "name": k,
            "elo": round(elo[k], 1),
            "perf": round(perf[k], 1),
            "rating": round(rating, 1),
            "provisional": provisional,
            "role": r["role"],
            "games": r["games"],
            "win_rate": r["win_rate"],
            "gpm": round(r["avg_gpm"], 1),
            "xpm": round(r["avg_xpm"], 1),
            "kda": round(r["avg_kda"], 2),
            "kd": (f"{r['kills'] / r['games']:.1f}/{r['deaths'] / r['games']:.1f}"
                   f"/{r['assists'] / r['games']:.1f}"),
        }
    return players


def expected(a, b):
    return 1 / (1 + 10 ** ((b - a) / 400))


def generate(players, top_n):
    """按核心数尽量均衡（两队差 ≤1）筛选，再按平衡分排序。"""
    names = sorted(players)
    first, rest = names[0], names[1:]
    results = []
    for combo in combinations(rest, 4):
        team_a = [players[first]] + [players[n] for n in combo]
        team_b = [players[n] for n in rest if n not in combo]
        cores_a = sum(1 for p in team_a if p["role"] == "核心")
        cores_b = sum(1 for p in team_b if p["role"] == "核心")
        if abs(cores_a - cores_b) > 1:
            continue
        ra = sum(p["rating"] for p in team_a) / 5
        rb = sum(p["rating"] for p in team_b) / 5
        pa = expected(ra, rb)
        balance = 100 * (1 - 2 * abs(pa - 0.5))
        results.append({
            "score": balance, "balance": balance, "penalty": 0,
            "team_a": team_a, "team_b": team_b, "ra": ra, "rb": rb, "pa": pa,
            "cores_a": cores_a, "cores_b": cores_b,
        })
    results.sort(key=lambda r: (-r["score"], abs(r["ra"] - r["rb"])))
    return results[:top_n]


def print_ratings(players):
    print(f"{'玩家':<18}{'综合':>7}{'Elo':>7}{'表现':>7}{'定位':>6}{'场次':>5}"
          f"{'胜率':>8}{'KDA':>7}{'平均K/D/A':>18}{'GPM':>7}{'XPM':>7}")
    print("-" * 108)
    for p in sorted(players.values(), key=lambda x: -x["rating"]):
        mark = "*" if p.get("provisional") else ""
        print(f"{p['name'][:16] + mark:<18}{p['rating']:>7.1f}{p['elo']:>7.1f}{p['perf']:>7.1f}"
              f"{p['role']:>6}{p['games']:>5}{p['win_rate']*100:>7.1f}%"
              f"{p['kda']:>7.2f}{p['kd']:>18}{p['gpm']:>7.1f}{p['xpm']:>7.1f}")
    if any(p.get("provisional") for p in players.values()):
        print(f"* 场次少于 2 场，综合分暂按 {BASE:.0f} 处理")


def main():
    args = []
    top_n = 5
    raw = sys.argv[1:]
    i = 0
    while i < len(raw):
        a = raw[i]
        if a == "--top" and i + 1 < len(raw):
            try:
                top_n = int(raw[i + 1])
            except ValueError:
                pass
            i += 2
            continue
        if a.startswith("--top="):
            try:
                top_n = int(a.split("=", 1)[1])
            except ValueError:
                pass
            i += 1
            continue
        if a.startswith("--"):
            i += 1
            continue
        args.append(a)
        i += 1

    players = build_ratings(load_matches())
    print_ratings(players)

    if not args:
        print("\n把要上场的 10 个玩家名作为参数传入即可生成分队，例如：")
        print('  python balance.py "玩家1" "玩家2" ... "玩家10"')
        return 0
    if len(args) != 10:
        print(f"\n需要正好 10 个玩家，当前给了 {len(args)} 个。")
        return 1

    def norm(s):
        # 去掉私用区字符（如刀塔名里的 ）和空白，便于模糊匹配
        return "".join(
            ch for ch in s
            if not (0xE000 <= ord(ch) <= 0xF8FF) and not ch.isspace()
        ).lower()

    resolved = []
    missing = []
    for name in args:
        if name in players:
            resolved.append(name)
            continue
        key = norm(name)
        candidates = [
            n for n in players
            if key == norm(n) or key in norm(n) or norm(n) in key
        ]
        if len(candidates) == 1:
            resolved.append(candidates[0])
        else:
            missing.append(name)
    if missing:
        print(f"\n找不到这些玩家: {', '.join(missing)}")
        print("可用玩家:", ", ".join(sorted(players)))
        return 1

    args = resolved
    selected = {n: players[n] for n in args}
    core_count = sum(1 for p in selected.values() if p["role"] == "核心")
    support_count = len(args) - core_count
    print(f"\n{len(args)} 人分队，{core_count} 核 + {support_count} 辅，"
          f"按两队核心数差 ≤1 均衡，前 {top_n} 套：")

    results = generate(selected, top_n)

    if results and results[0]["balance"] < 90:
        print("[警告] 最优方案平衡分 < 90（预测胜率超出 45%–55% 合格线），"
              "当前名单可能无法做到合格平衡。")

    for i, r in enumerate(results, 1):
        cores_a, cores_b = r["cores_a"], r["cores_b"]
        print(f"\n方案 {i}  平衡分 {r['score']:.1f}  "
              f"预测胜率 {r['pa']*100:.1f}% / {(1-r['pa'])*100:.1f}%  "
              f"队伍均分 {r['ra']:.1f} vs {r['rb']:.1f}"
              + (f"  角色惩罚 -{r['penalty']:.0f}" if r["penalty"] else ""))
        for label, team, cores, avg in (
            ("A", r["team_a"], cores_a, r["ra"]),
            ("B", r["team_b"], cores_b, r["rb"]),
        ):
            members = "、".join(f"{p['name']}({p['rating']:.0f})" for p in sorted(team, key=lambda x: -x["rating"]))
            print(f"  队伍{label} [{avg:.1f} | 核心{cores}/酱油{5-cores}]: {members}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
