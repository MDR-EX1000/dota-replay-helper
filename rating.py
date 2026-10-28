# -*- coding: utf-8 -*-
"""
单局评分与称号（MVP / SVP），参考官方 MVP 与 Max+ 思路：
  - 所有指标取“占本队总量的份额 x5”，均值恒为 1，跨英雄/跨定位可比
  - 角色按本队净资产排名连续加权：前排位偏经济/输出，后排位偏功能/参战
  - 死亡扣分、胜负加成；MVP 取胜方最高分，SVP 取败方最高分
  - schema 3 的缺失值（None）不参与计算，缺数据的选手不评 MVP/SVP 与标签
"""

# 净资产排名(0=最高) -> 核心度 1..0
CORE_W = [1.0, 0.9, 0.7, 0.3, 0.0]

# 评分/标签依赖的字段；任一缺失就不对该选手评分
FIELDS = (
    "kills", "deaths", "assists", "net_worth", "hero_damage",
    "tower_damage", "hero_damage_taken", "stuns", "healing",
    "wards_placed", "wards_destroyed",
)


def _complete(p):
    return all(p.get(field) is not None for field in FIELDS)


def _share(v, total):
    return 5.0 * v / total if total > 0 else 1.0


def rate_players(players, winner):
    out = {}
    for team in ("radiant", "dire"):
        ps = sorted((p for p in players if p["team"] == team and _complete(p)),
                    key=lambda p: -p["net_worth"])
        if not ps:
            continue
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
        if p["pid"] not in out:
            continue
        r = out[p["pid"]]
        s = 6.0 + (r - 0.9) * 5.0
        if p["team"] == winner:
            s += 0.3
        res[p["pid"]] = round(max(0.0, min(10.0, s)), 1)
    return res


def apply(players, winner, objectives=None):
    for p in players:
        p["score"] = None
        p["title"] = ""
        p["kda_title"] = ""
        p["tags"] = []

    if winner not in ("radiant", "dire"):
        return players

    scores = rate_players(players, winner)
    for p in players:
        if p["pid"] in scores:
            p["score"] = scores[p["pid"]]

    # KDA 称号：天之上 > 天秀 > 秀，互斥；缺字段不评
    for p in players:
        kills, deaths, assists = p.get("kills"), p.get("deaths"), p.get("assists")
        if None in (kills, deaths, assists):
            continue
        kda = (kills + assists) / max(deaths, 1)
        if kda >= 15 and deaths == 0:
            p["kda_title"] = "天之上"
        elif kda >= 15:
            p["kda_title"] = "天秀"
        elif kda >= 10:
            p["kda_title"] = "秀"

    # 负面/特色称号：不互斥，一人可同时拿多个；但每个称号每场最多一人，
    # 取该项指标最突出者。展示顺序固定为 僵、硬、瘤、莽
    cand = {"僵": [], "硬": [], "瘤": [], "莽": []}

    for team in ("radiant", "dire"):
        ps = [p for p in players if p["team"] == team and _complete(p)]
        if not ps:
            continue
        T = lambda k: sum(p[k] for p in ps)
        tk, td = T("kills"), T("deaths")
        tt = T("hero_damage_taken")
        denom = tk + 0.7 * T("assists")
        engage_den = denom + td
        for p in ps:
            death_share = _share(p["deaths"], td) if td else 1.0
            taken_share = _share(p["hero_damage_taken"], tt)
            nw_share = _share(p["net_worth"], T("net_worth"))
            part_share = _share(p["kills"] + 0.7 * p["assists"], denom) if denom else 1.0
            engage_share = (_share(p["kills"] + 0.7 * p["assists"] + p["deaths"], engage_den)
                            if engage_den else 1.0)
            kda = (p["kills"] + p["assists"]) / max(p["deaths"], 1)
            # 僵：死亡 >= 10 次且死亡份额 >= 1.6，评分垫底，对局负面影响大
            if p["deaths"] >= 10 and death_share >= 1.6 and p["score"] <= 4.5:
                cand["僵"].append((death_share, p["deaths"], p["pid"]))
            # 硬：承伤份额 >= 1.4 且死亡份额 <= 1.2（死太多算送不算扛）
            if taken_share >= 1.4 and death_share <= 1.2 and p["score"] <= 5.5:
                cand["硬"].append((taken_share, p["hero_damage_taken"], p["pid"]))
            # 瘤：经济份额 >= 1.3 但参战份额 <= 0.6，自己玩自己的
            if nw_share >= 1.3 and part_share <= 0.6 and p["score"] <= 5.0:
                cand["瘤"].append((nw_share, p["net_worth"], p["pid"]))
            # 莽：交战份额 >= 1.1（输赢的架都算）、死亡 >= 8 且死亡份额 >= 1.3、
            # KDA < 1.2；不看评分和胜负，赢了也是莽
            if (engage_share >= 1.1 and p["deaths"] >= 8
                    and death_share >= 1.3 and kda < 1.2):
                cand["莽"].append((engage_share, p["deaths"], p["pid"]))
    by_pid = {p["pid"]: p for p in players}
    neg = set()
    for tag in ("僵", "硬", "瘤", "莽"):
        if cand[tag]:
            best = max(cand[tag])  # 主指标最高者；并列时取绝对量更大者
            neg.add((best[2], tag))

    # 敌塔师：推塔伤害占全队 >= 60% 且绝对量 >= 8000，且亲手拆塔 >= 3 座
    # （塔的最后一击，objectives 里 kind=tower 的 killer），取推塔份额最高者
    def _norm(s):
        return (s or "").lower().replace("npc_dota_hero_", "").replace("_", "")
    towers_by_hero = {}
    for o in objectives or []:
        if o.get("kind") == "tower" and o.get("killer"):
            k = _norm(o["killer"])
            towers_by_hero[k] = towers_by_hero.get(k, 0) + 1
    tw = [(p["tower_damage"] / max(sum(q["tower_damage"] for q in players
           if q["team"] == p["team"] and _complete(q)), 1), p["tower_damage"], p["pid"])
          for p in players
          if _complete(p) and towers_by_hero.get(_norm(p["hero"]), 0) >= 3]
    tw = [x for x in tw if x[0] >= 0.6 and x[1] >= 8000]
    tower_pid = max(tw)[2] if tw else None

    # 光明左使：插假眼 >= 15 且全场最多（老数据无拆分字段时 obs_wards=0，自然不评）
    obs = [(p.get("obs_wards") or 0, p["pid"]) for p in players]
    left_pid = max(obs)[1] if obs and max(obs)[0] >= 15 else None

    # 光明右使：重排眼轻插真眼。排眼 >= 12 即候选（不看队内占比，
    # 多位酱油排眼积极不互相取消资格，但最终只授最高者），
    # 按 排眼x2 + 真眼x1 排序取最高
    dew = [((p["wards_destroyed"] or 0) * 2 + (p.get("sen_wards") or 0),
            p["wards_destroyed"] or 0, p["pid"]) for p in players]
    dew = [x for x in dew if x[1] >= 12]
    right_pid = max(dew)[2] if dew else None

    # 固定展示顺序：敌塔师、光明使者/左使/右使、僵、硬、瘤、莽
    for p in players:
        tags = []
        if p["pid"] == tower_pid:
            tags.append("敌塔师")
        if left_pid is not None and p["pid"] == left_pid == right_pid:
            tags.append("光明使者")  # 左右同一人，合并
        else:
            if p["pid"] == left_pid:
                tags.append("光明左使")
            if p["pid"] == right_pid:
                tags.append("光明右使")
        for tag in ("僵", "硬", "瘤", "莽"):
            if (p["pid"], tag) in neg:
                tags.append(tag)
        p["tags"] = tags

    loser = "dire" if winner == "radiant" else "radiant"
    for team, title in ((winner, "MVP"), (loser, "SVP")):
        ps = [p for p in players if p["team"] == team and p["pid"] in scores]
        if ps:
            best = max(ps, key=lambda p: (p["score"],
                                          (p.get("kills") or 0) + (p.get("assists") or 0)))
            best["title"] = title
    # 虽败犹荣：败方专属，不唯一、不限于 SVP。评分 >= 8.0（胜方顶尖水平）
    # 且 KDA >= 1.5（防短局/碾压局数据失真），输了但贡献重大即授予
    for p in players:
        if p["team"] == loser and p["score"] is not None:
            kda = (p["kills"] + p["assists"]) / max(p["deaths"], 1)
            p["honor"] = p["score"] >= 8.0 and kda >= 1.5
    for p in players:
        p.setdefault("honor", False)
    return players
