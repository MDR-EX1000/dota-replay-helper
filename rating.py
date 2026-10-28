# -*- coding: utf-8 -*-
"""
单局评分与称号（MVP / SVP），参考官方 MVP 与 Max+ 思路：
  - 所有指标取“占本队总量的份额 x5”，均值恒为 1，跨英雄/跨定位可比
  - 角色按本队净资产排名连续加权：前排位偏经济/输出，后排位偏功能/参战
  - 死亡扣分、胜负加成；MVP 取胜方最高分，SVP 取败方最高分
"""

# 净资产排名(0=最高) -> 核心度 1..0
CORE_W = [1.0, 0.9, 0.7, 0.3, 0.0]


def _share(v, total):
    return 5.0 * v / total if total > 0 else 1.0


def rate_players(players, winner):
    out = {}
    for team in ("radiant", "dire"):
        ps = sorted((p for p in players if p["team"] == team),
                    key=lambda p: -p["net_worth"])
        T = lambda k: sum(p[k] for p in ps)
        tk, td = T("kills"), T("deaths")
        for i, p in enumerate(ps):
            core = CORE_W[i] if i < 5 else 0.0
            sup = 1 - core
            dmg = _share(p["hero_damage"], T("hero_damage"))
            part = _share(p["kills"] + 0.7 * p["assists"],
                          tk + 0.7 * T("assists"))
            eco = _share(p["net_worth"], T("net_worth"))
            tower = min(_share(p["tower_damage"], T("tower_damage")), 3.0)
            tank = min(_share(p["hero_damage_taken"], T("hero_damage_taken")), 2.5)
            util = (_share(p["stuns"], T("stuns")) * 0.4
                    + _share(p["healing"], T("healing")) * 0.3
                    + _share(p["wards_placed"] + p["wards_destroyed"],
                             T("wards_placed") + T("wards_destroyed")) * 0.3)
            death = min(_share(p["deaths"], td), 2.5) if td else 1.0
            # 零死亡额外奖励有限；死亡多于均值才重罚；份额封顶 2.5 倍，
            # 避免低死亡局里唯一一次死亡被无限放大
            death_pen = 0.30 * death if death <= 1 else 0.30 + 0.35 * (death - 1)
            kda = (p["kills"] + p["assists"]) / max(p["deaths"], 1)
            kda_bonus = min(kda, 12) / 12 * 0.5

            raw = (0.26 * dmg + 0.24 * part
                   + 0.10 * eco
                   + 0.07 * tower
                   + 0.08 * tank
                   + 0.14 * util
                   + kda_bonus - death_pen)
            out[p["pid"]] = raw
    # 线性映射到 0-10：raw≈0.9 为 6 分
    res = {}
    for p in players:
        r = out[p["pid"]]
        s = 6.0 + (r - 0.9) * 5.0
        if p["team"] == winner:
            s += 0.3
        res[p["pid"]] = round(max(0.0, min(10.0, s)), 1)
    return res


def apply(players, winner):
    scores = rate_players(players, winner)
    for p in players:
        p["score"] = scores[p["pid"]]
        p["title"] = ""
        # KDA 称号：天之上 > 天秀 > 秀，互斥
        kda = (p["kills"] + p["assists"]) / max(p["deaths"], 1)
        if kda >= 15 and p["deaths"] == 0:
            p["kda_title"] = "天之上"
        elif kda >= 15:
            p["kda_title"] = "天秀"
        elif kda >= 10:
            p["kda_title"] = "秀"
        else:
            p["kda_title"] = ""
    # 负面/特色称号：不互斥，可同时获得；展示顺序固定为 僵、硬、瘤、莽
    for team in ("radiant", "dire"):
        ps = [p for p in players if p["team"] == team]
        T = lambda k: sum(p[k] for p in ps)
        tk, td = T("kills"), T("deaths")
        tt = T("hero_damage_taken")
        denom = tk + 0.7 * T("assists")
        for p in ps:
            death_share = _share(p["deaths"], td) if td else 1.0
            taken_share = _share(p["hero_damage_taken"], tt)
            nw_share = _share(p["net_worth"], T("net_worth"))
            part_share = _share(p["kills"] + 0.7 * p["assists"], denom) if denom else 1.0
            tags = []
            # 僵：死亡 >= 10 次且死亡份额 >= 1.6，评分垫底，对局负面影响大
            if p["deaths"] >= 10 and death_share >= 1.6 and p["score"] <= 4.5:
                tags.append("僵")
            # 硬：承伤份额 >= 1.4 且死亡份额 <= 1.2（死太多算送不算扛）
            if taken_share >= 1.4 and death_share <= 1.2 and p["score"] <= 5.5:
                tags.append("硬")
            # 瘤：经济份额 >= 1.3 但参战份额 <= 0.6，自己玩自己的
            if nw_share >= 1.3 and part_share <= 0.6 and p["score"] <= 5.0:
                tags.append("瘤")
            # 莽：交战份额 >= 1.1（输赢的架都算）、死亡 >= 8 且死亡份额 >= 1.3、
            # KDA < 1.2；不看评分和胜负，赢了也是莽
            engage_den = denom + td
            engage_share = (_share(p["kills"] + 0.7 * p["assists"] + p["deaths"], engage_den)
                            if engage_den else 1.0)
            kda = (p["kills"] + p["assists"]) / max(p["deaths"], 1)
            if (engage_share >= 1.1 and p["deaths"] >= 8
                    and death_share >= 1.3 and kda < 1.2):
                tags.append("莽")
            p["tags"] = tags
    loser = "dire" if winner == "radiant" else "radiant"
    for team, title in ((winner, "MVP"), (loser, "SVP")):
        ps = [p for p in players if p["team"] == team]
        if ps:
            best = max(ps, key=lambda p: (p["score"], p["kills"] + p["assists"]))
            best["title"] = title
    return players
