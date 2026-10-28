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
                   KDA 40% / GPM 15% / XPM 15% / 伤害-经济比 30%
                 位置基准：
                   核心 KDA 3.7 / GPM 540 / XPM 720 / 伤害经济比 1.59
                   酱油 KDA 2.4 / GPM 335 / XPM 490 / 伤害经济比 1.40
                 原始表现 = 1000 + 500 × Σ[权重 × (实际值/基准值 − 1)]
                 场次收缩：1000 + (原始表现−1000) × n/(n+5)
    MMR 分     : 3000 MMR = 1000 分；每 1000 MMR 差 = 33.3 分
                 MMR分 = 1000 + (MMR − 3000) / 30
    综合分     : 0.4 × Elo + 0.3 × 表现分 + 0.3 × MMR分
                 未登记 MMR 默认按 2000 计算
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
MATCHES_DIR = os.path.join(SCRIPT_DIR, "json")

K_FACTOR = 32
BASE = 1000.0
START_ELO = BASE


DEFAULT_BASELINES = {
    "核心": {"kda": 3.7, "gpm": 540.0, "xpm": 720.0, "dmg_gold": 1.59},
    "酱油": {"kda": 2.4, "gpm": 335.0, "xpm": 490.0, "dmg_gold": 1.40},
}


def load_baselines():
    """读取 baselines.json；缺失或格式错误时使用默认值。"""
    path = os.path.join(SCRIPT_DIR, "baselines.json")
    if not os.path.isfile(path):
        return DEFAULT_BASELINES
    try:
        with open(path, encoding="utf-8") as fp:
            data = json.load(fp)
        result = {}
        for role, default in DEFAULT_BASELINES.items():
            row = data.get(role, {})
            result[role] = {}
            for key, dv in default.items():
                v = row.get(key, dv)
                result[role][key] = float(v) if float(v) > 0 else dv
        return result
    except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
        print(f"[警告] baselines.json 读取失败，使用默认基准: {exc}")
        return DEFAULT_BASELINES


def load_mmr():
    path = os.path.join(SCRIPT_DIR, "mmr.json")
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fp:
            return {str(k): v for k, v in json.load(fp).items()}
    except (OSError, json.JSONDecodeError):
        return {}


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


def build_ratings(matches):
    import stats
    from player_data import IdentityResolver
    matches = sorted(matches, key=lambda m: (m.get("start_time", 0), str(m.get("match_id", ""))))
    rows = stats.aggregate(matches)
    # Use exactly the same explicit legacy mappings and account groups as statistics.
    resolver = IdentityResolver(matches, load_aliases(), stats.load_legacy_identities())
    elo = defaultdict(lambda: START_ELO)
    for match in matches:
        if not isinstance(match.get("radiant_win"), bool):
            continue
        teams = {team: [resolver.resolve(p, match, i)[0] for i, p in enumerate(match["players"])
                        if p.get("team") == team] for team in ("radiant", "dire")}
        if any(len(team) != 5 for team in teams.values()):
            continue
        if len(set(teams["radiant"] + teams["dire"])) != 10:
            continue
        ra, rb = (sum(elo[k] for k in teams[t]) / 5 for t in ("radiant", "dire"))
        ea = expected(ra, rb)
        for team, result, probability in (("radiant", float(match["radiant_win"]), ea),
                                           ("dire", float(not match["radiant_win"]), 1-ea)):
            for key in teams[team]:
                elo[key] += K_FACTOR * (result-probability)
    baselines = load_baselines()
    players = {}
    for row in rows:
        key = row["_identity"]
        ready = row["_rating_ready"]
        perf = BASE
        if ready:
            b = baselines[row["定位"]]
            values = row["_rating_inputs"]
            score = (.40*(values["kda"]/b["kda"]-1) + .15*(values["gpm"]/b["gpm"]-1)
                     + .15*(values["xpm"]/b["xpm"]-1) + .30*(values["dmg_gold"]/b["dmg_gold"]-1))
            perf = max(BASE-500, min(BASE+500, BASE+500*score*row["场次"]/(row["场次"]+5)))
        mmr_num = row["_mmr"] if row["_mmr"] is not None else 2000
        mmr_rating = BASE+(mmr_num-3000)/30
        provisional = row["场次"] < 2 or not ready
        rating = BASE if provisional else .4*elo[key]+.3*perf+.3*mmr_rating
        players[key] = {"id": row["_id"], "name": row["玩家"], "identity_status": row["_identity_status"],
            "elo": round(elo[key], 1), "perf": round(perf, 1), "mmr": mmr_num,
            "mmr_rating": round(mmr_rating, 1), "rating": round(rating, 1),
            "provisional": provisional, "role": row["定位"], "games": row["场次"],
            "win_rate": row["_winrate"], "gpm": row["平均GPM"], "xpm": row["平均XPM"],
            "kda": row["KDA"], "kd": row["平均K/D/A"], "samples": row["_samples"]}
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
    print(f"{'玩家':<18}{'综合':>7}{'Elo':>7}{'表现':>7}{'MMR':>6}{'定位':>6}{'场次':>5}"
          f"{'胜率':>8}{'KDA':>7}{'平均K/D/A':>18}{'GPM':>7}{'XPM':>7}")
    print("-" * 115)
    for p in sorted(players.values(), key=lambda x: -x["rating"]):
        mark = "*" if p.get("provisional") else ""
        print(f"{p['name'][:16] + mark:<18}{p['rating']:>7.1f}{p['elo']:>7.1f}{p['perf']:>7.1f}"
              f"{str(p['mmr']):>6}{p['role']:>6}{p['games']:>5}{p['win_rate']*100:>7.1f}%"
              f"{str(p['kda'] if p['kda'] is not None else '-'):>7}{p['kd']:>18}{str(p['gpm']):>7}{str(p['xpm']):>7}")
    if any(p.get("provisional") for p in players.values()):
        print(f"* 场次少于 2 场、身份待确认或评分数据不完整，综合分暂按 {BASE:.0f} 处理")


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
            if key == norm(players[n]["name"]) or key in norm(players[n]["name"]) or norm(players[n]["name"]) in key
        ]
        if len(candidates) == 1:
            resolved.append(candidates[0])
        else:
            missing.append(name)
    if missing:
        print(f"\n找不到这些玩家: {', '.join(missing)}")
        print("可用玩家:", ", ".join(sorted(p["name"] for p in players.values())))
        return 1

    if len(set(resolved)) != 10:
        print("名单中包含重复账号。")
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
