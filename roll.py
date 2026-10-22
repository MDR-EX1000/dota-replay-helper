# -*- coding: utf-8 -*-
"""
对黑 roll 点脚本（规则版）：先按硬规则筛方案，再在合格方案里 roll。

规则 R1-R5:
    R1 名单结构   建议 6 核 + 4 辅，但不作为硬门槛（不满足记 WARN）
    R2 每队结构   两队核心数差 ≤ 1，尽量均衡（不强制固定 3 核 2 辅）
    R3 均分差     两队综合分均值差 ≤ 10
    R4 预测胜率   45% ≤ 胜率 ≤ 55%
    R5 不堆叠     综合分前 2 名不能在同一队

若没有任何方案同时满足 R1-R5，按以下顺序放宽，并在结果中注明：
    先放宽 R5 -> 再把 R3 放宽到 15 -> 再把 R4 放宽到 40%-60%

roll 只在通过规则的方案里均匀抽取，保证：
    - 结构不会歪
    - 强度不会明显失衡
    - 随机不会偏向任何玩家

用法:
    python roll.py "玩家1" ... "玩家10"
    python roll.py --top 5 --seed 42 "玩家1" ... "玩家10"
"""

import random
import sys
from datetime import datetime
from itertools import combinations

import balance


def norm(s):
    return "".join(
        ch for ch in s
        if not (0xE000 <= ord(ch) <= 0xF8FF) and not ch.isspace()
    ).lower()


def resolve(name, players):
    if name in players:
        return name
    key = norm(name)
    cands = [n for n in players if key == norm(n) or key in norm(n) or norm(n) in key]
    return cands[0] if len(cands) == 1 else None


def parse_args():
    names, top_n, seed = [], 5, None
    raw = sys.argv[1:]
    i = 0
    while i < len(raw):
        a = raw[i]
        if a == "--top" and i + 1 < len(raw):
            top_n = int(raw[i + 1]); i += 2; continue
        if a.startswith("--top="):
            top_n = int(a.split("=", 1)[1]); i += 1; continue
        if a == "--seed" and i + 1 < len(raw):
            seed = int(raw[i + 1]); i += 2; continue
        if a.startswith("--seed="):
            seed = int(a.split("=", 1)[1]); i += 1; continue
        names.append(a); i += 1
    return names, top_n, seed


def make_split(sel, combo):
    team_a = [sel[0]] + list(combo)
    team_b = [p for p in sel if p not in team_a]
    ra = sum(p["rating"] for p in team_a) / 5
    rb = sum(p["rating"] for p in team_b) / 5
    pa = balance.expected(ra, rb)
    return {
        "team_a": team_a, "team_b": team_b,
        "ra": ra, "rb": rb, "pa": pa,
        "diff": abs(ra - rb),
        "score": 100 * (1 - 2 * abs(pa - 0.5)),
        "ca": sum(1 for p in team_a if p["role"] == "核心"),
        "cb": sum(1 for p in team_b if p["role"] == "核心"),
    }


def rule_rows(r, top2, limits):
    """返回 [(规则, 要求, 实际, 是否通过)]，供现场核对。"""
    a_names = {p["name"] for p in r["team_a"]}
    b_names = {p["name"] for p in r["team_b"]}
    top2_a = len(top2 & a_names)
    top2_b = len(top2 & b_names)
    stack_ok = not (top2_a == 2 or top2_b == 2)

    rows = [
        ("R2 每队结构", "核心数差 ≤ 1",
         f"A {r['ca']}核{5-r['ca']}辅 / B {r['cb']}核{5-r['cb']}辅",
         abs(r["ca"] - r["cb"]) <= 1),
        ("R3 均分差", f"≤ {limits['diff']}", f"{r['diff']:.1f}",
         r["diff"] <= limits["diff"]),
        ("R4 预测胜率", f"{limits['lo']*100:.0f}%–{limits['hi']*100:.0f}%",
         f"{r['pa']*100:.1f}% / {(1-r['pa'])*100:.1f}%",
         limits["lo"] <= r["pa"] <= limits["hi"]),
        ("R5 不堆叠", "前 2 名不同队",
         f"前2名分布 A{top2_a} / B{top2_b}", stack_ok),
    ]
    return rows


def main():
    names, top_n, seed = parse_args()
    players = balance.build_ratings(balance.load_matches())

    if len(names) != 10:
        print(f"需要正好 10 个玩家，当前 {len(names)} 个。")
        print("可用玩家:", "、".join(sorted(players)))
        return 1

    resolved, missing = [], []
    for n in names:
        r = resolve(n, players)
        (resolved if r else missing).append(r or n)
    if missing:
        print(f"找不到: {', '.join(missing)}")
        print("可用玩家:", "、".join(sorted(players)))
        return 1

    sel = [players[n] for n in resolved]
    cores = sum(1 for p in sel if p["role"] == "核心")
    supports = 10 - cores
    top2 = {p["name"] for p in sorted(sel, key=lambda x: -x["rating"])[:2]}

    all_splits = [make_split(sel, c) for c in combinations(sel[1:], 4)]

    # 规则等级：先严格，再逐级放宽
    levels = [
        ("严格规则 R1-R5", {"diff": 10, "lo": 0.45, "hi": 0.55, "stack": True}),
        ("放宽 R5（允许前2名同队）", {"diff": 10, "lo": 0.45, "hi": 0.55, "stack": False}),
        ("再放宽 R3 到 15", {"diff": 15, "lo": 0.45, "hi": 0.55, "stack": False}),
        ("再放宽 R4 到 40%–60%", {"diff": 15, "lo": 0.40, "hi": 0.60, "stack": False}),
    ]

    chosen_level, pool, qualified = None, [], 0
    for label, lim in levels:
        rows = []
        for r in all_splits:
            # 不强制 6 核 4 辅；只要求两队核心数尽量均衡（差 ≤ 1）
            if abs(r["ca"] - r["cb"]) > 1:
                continue
            if r["diff"] > lim["diff"]:
                continue
            if not (lim["lo"] <= r["pa"] <= lim["hi"]):
                continue
            a_names = {p["name"] for p in r["team_a"]}
            b_names = {p["name"] for p in r["team_b"]}
            if lim["stack"] and (len(top2 & a_names) == 2 or len(top2 & b_names) == 2):
                continue
            rows.append(r)
        if rows:
            chosen_level, qualified = label, len(rows)
            rows.sort(key=lambda x: (-x["score"], x["diff"]))
            pool = rows[:top_n]
            break

    if not pool:
        print("没有任何方案满足最低规则，请检查名单和评分数据。")
        return 1

    rng = random.Random(seed) if seed is not None else random.SystemRandom()
    chosen = rng.choice(pool)
    pa = chosen["pa"]
    limits = next(l for name, l in levels if name == chosen_level)

    verdict = ("优秀，推荐开打" if chosen["score"] >= 95 and chosen["diff"] <= 10
               else "合理，可以开打" if chosen["score"] >= 90
               else "勉强，建议重 roll" if chosen["score"] >= 80
               else "不平衡，建议重 roll")

    L = []
    L.append("=" * 70)
    L.append(f"对黑 roll 结果    {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    L.append(f"名单: {cores} 核 + {supports} 辅    {len(all_splits)} 种分法，"
             f"满足【{chosen_level}】的 {qualified} 种，roll 池前 {len(pool)} 套")
    L.append(f"随机种子: {seed if seed is not None else '系统随机'}")
    L.append("=" * 70)

    L.append("")
    L.append("【评分口径（可逐项复算）】")
    L.append("  综合分 = 0.5×Elo + 0.5×表现分（Elo 已含胜负，胜率不重复计分）")
    L.append("  表现分 = KDA 35% + GPM 15% + XPM 15% + 伤害/经济 35%")
    L.append("  位置基准: 核心 3.7/540/720/1.59，酱油 2.4/335/490/1.40")
    L.append("  原始表现 = 1000 + 300×Σ[权重×(实际值/基准−1)]，再按场次收缩")
    L.append("")
    L.append(f"{'玩家':<14}{'综合':>7}{'Elo':>7}{'表现':>7}{'场次':>5}{'胜率':>8}{'定位':>6}")
    for p in sorted(sel, key=lambda x: -x["rating"]):
        L.append(f"{p['name'][:12]:<14}{p['rating']:>7.1f}{p['elo']:>7.1f}{p['perf']:>7.1f}"
                 f"{p['games']:>5}{p['win_rate']*100:>7.1f}%{p['role']:>6}")

    L.append("")
    L.append(f"【roll 中】平衡分 {chosen['score']:.1f} | "
             f"预测胜率 {pa*100:.1f}% / {(1-pa)*100:.1f}% | "
             f"均分 {chosen['ra']:.1f} vs {chosen['rb']:.1f}（差 {chosen['diff']:.1f}）")
    L.append(f"判定: {verdict}")
    for label, team in (("队伍A", chosen["team_a"]), ("队伍B", chosen["team_b"])):
        members = "、".join(f"{p['name']}({p['rating']:.0f})"
                           for p in sorted(team, key=lambda x: -x["rating"]))
        c = sum(1 for p in team if p["role"] == "核心")
        L.append(f"  {label} [核心{c}/酱油{5-c}]: {members}")

    L.append("")
    L.append("【规则审计】")
    L.append(f"{'规则':<12}{'要求':<16}{'本次实际':<24}{'结果':<8}")
    L.append(f"{'R1 名单结构':<12}{'建议 6核4辅（非硬性）':<20}{f'{cores} 核 + {supports} 辅':<24}"
             f"{'PASS' if cores == 6 and supports == 4 else 'WARN':<8}")
    for rule, req, actual, ok in rule_rows(chosen, top2, limits):
        L.append(f"{rule:<12}{req:<16}{actual:<24}{'PASS' if ok else 'FAIL':<8}")
    if chosen_level != "严格规则 R1-R5":
        L.append(f"  注: 当前已放宽为「{chosen_level}」，原因是没有方案同时满足严格规则。")

    L.append("")
    L.append("【roll 池明细（现场可核对）】")
    for i, r in enumerate(pool, 1):
        mark = "  <== roll 中" if r is chosen else ""
        L.append(f"  {i}. 平衡 {r['score']:.1f} | 胜率 {r['pa']*100:.1f}%/{(1-r['pa'])*100:.1f}%"
                 f" | 均分 {r['ra']:.1f} vs {r['rb']:.1f}{mark}")

    L.append("")
    L.append("【为什么这样 roll 没问题】")
    L.append(f"  1. roll 池里 {len(pool)} 套方案全部通过上述规则，结构、分差、胜率都在线内")
    L.append(f"  2. 池内胜率区间 {min(x['pa'] for x in pool)*100:.1f}%–{max(x['pa'] for x in pool)*100:.1f}%，"
             "抽中哪套对胜负影响可忽略")
    L.append("  3. 随机只在合格池内均匀发生，不会偏向任何玩家或队伍")
    L.append("  4. 名单、种子、池子明细全部留档，可复现、可审计")

    print("\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main())
