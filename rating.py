# -*- coding: utf-8 -*-
"""
单局评分与称号（MVP / SVP），参考官方 MVP 与 Max+ 思路：
  - 所有指标取“占本队总量的份额 x5”，均值恒为 1，跨英雄/跨定位可比
  - 角色按本队净资产排名连续加权：前排位偏经济/输出，后排位偏功能/参战
  - 死亡扣分、胜负加成；MVP 取胜方最高分，SVP 取败方最高分
  - schema 3 的缺失值（None）不参与计算，缺数据的选手不评 MVP/SVP 与标签
"""

# 位置基线：核心/辅助在大众对局中，单人占本队总量的典型份额 (核心, 辅助)。
# 定位：队内补刀前 3 = 核心，后 2 = 辅助。数值为 MOBA 通用经验假设，不取自本项目对局；
# 每项满足 3*核心 + 2*辅助 = 1.0（已用代码断言校验）。
BASE = {
    "dmg":   (0.25, 0.125),
    "part":  (0.20, 0.20),
    "eco":   (0.25, 0.125),
    "tower": (0.27, 0.095),
    "tank":  (0.22, 0.17),
    "stun":  (0.12, 0.32),
    "heal":  (0.06, 0.41),
    "ward":  (0.06, 0.41),
    "death": (0.20, 0.20),
}
# 权重按定位分两套，各自和为 1.0。本位不负责的指标权重为 0（不奖不罚）：
# 核心不要求插眼/治疗/控制；辅助不要求推塔/经济。
W_CORE = {"dmg": 0.28, "part": 0.22, "eco": 0.12, "tower": 0.08,
          "tank": 0.10, "stun": 0.10, "suputil": 0.00, "live": 0.10}
W_SUP = {"dmg": 0.15, "part": 0.30, "eco": 0.00, "tower": 0.00,
         "tank": 0.10, "stun": 0.10, "suputil": 0.15, "live": 0.20}
assert all(abs(3 * c + 2 * s - 1) < 1e-9 for c, s in BASE.values())
assert abs(sum(W_CORE.values()) - 1) < 1e-9 and abs(sum(W_SUP.values()) - 1) < 1e-9
BASE_FLOOR = 0.08   # 基线下限，防止低基线项(核心的眼/治疗)比值被放大
RATIO_CAP = 2.0     # 单项相对基线的比值上限
SCALE = 3.5         # 斜率：原始分每偏离典型水平 0.1 = 0.875 分

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


def _ratio(v, total, base):
    """本人占队份额 / 本位置典型份额，封顶；队内该项为 0 时记为典型水平。"""
    if total <= 0:
        return 1.0
    return min((v / total) / max(base, BASE_FLOOR), RATIO_CAP)


def rate_players(players, winner):
    out = {}
    for team in ("radiant", "dire"):
        ps = sorted((p for p in players if p["team"] == team and _complete(p)),
                    key=lambda p: (-p["last_hits"], -p["net_worth"]))
        if not ps:
            continue
        T = lambda k: sum(p[k] for p in ps)
        for rank, p in enumerate(ps):
            i = 0 if rank < 3 else 1
            r = lambda key, v, tot: _ratio(v, tot, BASE[key][i])
            dmg = r("dmg", p["hero_damage"], T("hero_damage"))
            part = r("part", p["kills"] + 0.7 * p["assists"],
                     T("kills") + 0.7 * T("assists"))
            eco = r("eco", p["net_worth"], T("net_worth"))
            tower = r("tower", p["tower_damage"], T("tower_damage"))
            tank = r("tank", p["hero_damage_taken"], T("hero_damage_taken"))
            stun = r("stun", p["stuns"], T("stuns"))
            suputil = (0.5 * r("heal", p["healing"], T("healing"))
                       + 0.5 * r("ward", p["wards_placed"] + p["wards_destroyed"],
                                 T("wards_placed") + T("wards_destroyed")))
            # 存活：死亡比典型越少越好，0 死=2.0，典型=1.0，两倍典型=0
            live = 2.0 - r("death", p["deaths"], T("deaths")) if T("deaths") else 1.0
            W = W_CORE if i == 0 else W_SUP
            out[p["pid"]] = (W["dmg"] * dmg + W["part"] * part + W["eco"] * eco
                             + W["tower"] * tower + W["tank"] * tank
                             + W["stun"] * stun + W["suputil"] * suputil
                             + W["live"] * live)
    # 各项均为“相对本位置典型水平”的比值，全项典型 -> raw=1.0 -> 6 分。
    # 败方封顶 9.9：满分只给胜方，败方最高 9.9；不影响败方内部排序与 SVP 归属
    res = {}
    for p in players:
        if p["pid"] not in out:
            continue
        cap = 10.0 if p["team"] == winner else 9.9
        res[p["pid"]] = round(max(0.0, min(cap, 6.0 + (out[p["pid"]] - 1.0) * SCALE * 2.5)), 1)
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

    # 秀系列（K/D 指标，只看击杀/死亡，不含助攻）：
    # 天之上 > 天秀 > 秀，互斥；缺字段不评
    for p in players:
        kills, deaths = p.get("kills"), p.get("deaths")
        if None in (kills, deaths):
            continue
        kd = kills / max(deaths, 1)
        if kd >= 15 and deaths == 0:
            p["kda_title"] = "天之上"
        elif kd >= 15:
            p["kda_title"] = "天秀"
        elif kd >= 10:
            p["kda_title"] = "秀"

    # 负面/特色称号：不互斥，一人可同时拿多个；但每个称号每场最多一人，
    # 取该项指标最突出者。展示顺序：瘤、莽、搞子、躺了在前，僵、硬固定最后
    cand = {"僵": [], "硬": [], "瘤": [], "莽": [], "搞子": [], "躺了": []}

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
            # 硬：承伤份额 >= 1.4 且死亡份额 <= 1.2（死太多算送不算扛）。
            # 中性偏正面，评分 <= 7.5 排除高分carry（其贡献已由评分/MVP体现）
            if taken_share >= 1.4 and death_share <= 1.2 and p["score"] <= 7.5:
                cand["硬"].append((taken_share, p["hero_damage_taken"], p["pid"]))
            # 瘤：经济份额 >= 1.3 但参战份额 <= 0.6，自己玩自己的
            if nw_share >= 1.3 and part_share <= 0.6 and p["score"] <= 5.0:
                cand["瘤"].append((nw_share, p["net_worth"], p["pid"]))
            # 莽：主动找架(参战份额>=1.2，不含死亡)但打不过(死亡>=8且死亡份额>=1.3)。
            # 中性偏负面，评分 <= 7.0 排除高评分carry。与"僵"(纯送低评分)区分
            if (part_share >= 1.2 and p["deaths"] >= 8 and death_share >= 1.3
                    and p["score"] <= 7.0):
                cand["莽"].append((part_share, p["deaths"], p["pid"]))
    # 搞子（败方）/ 躺了（胜方）：占了位置却没做到该做的事，纯数据，不看英雄。
    # 共同条件：核心位(补刀前3)伤害比<=0.5 或 辅助位(补刀后2)功能比<=0.4（相对本位典型）、
    #          评分<=3.5、本队评分垫底（天然唯一）
    # 搞子：所在队输了。躺了：所在队赢了，另需 参战<=0.8，且不是团控/抗伤型
    #       （控制比<0.8 且 承伤比<0.8），避免误伤斧王/斯拉达这类三号位
    for team in ("radiant", "dire"):
        ps = sorted((p for p in players if p["team"] == team and _complete(p)
                     and p["score"] is not None),
                    key=lambda p: (-p["last_hits"], -p["net_worth"]))
        if len(ps) < 2:
            continue
        T = lambda k: sum(p[k] for p in ps)
        denom = T("kills") + 0.7 * T("assists")
        low = min(p["score"] for p in ps)
        for rank, p in enumerate(ps):
            i = 0 if rank < 3 else 1
            rt = lambda key, v, tot: _ratio(v, tot, BASE[key][i])
            dmg = rt("dmg", p["hero_damage"], T("hero_damage"))
            stun = rt("stun", p["stuns"], T("stuns"))
            tank = rt("tank", p["hero_damage_taken"], T("hero_damage_taken"))
            func = 0.4 * stun + 0.6 * (
                0.5 * rt("heal", p["healing"], T("healing"))
                + 0.5 * rt("ward", p["wards_placed"] + p["wards_destroyed"],
                           T("wards_placed") + T("wards_destroyed")))
            useless = (i == 0 and dmg <= 0.5) or (i == 1 and func <= 0.4)
            if not (useless and p["score"] <= 3.5 and p["score"] == low):
                continue
            if team != winner:
                cand["搞子"].append((-p["score"], p["deaths"], p["pid"]))
            else:
                part = _share(p["kills"] + 0.7 * p["assists"], denom) if denom else 1.0
                if stun < 0.8 and tank < 0.8 and part <= 0.8:
                    cand["躺了"].append((-p["score"], p["deaths"], p["pid"]))
    by_pid = {p["pid"]: p for p in players}
    neg = set()
    for tag in ("僵", "硬", "瘤", "莽", "搞子", "躺了"):
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

    # 固定展示顺序：光明使者/左使/右使、敌塔师、瘤、莽、搞子、躺了，僵、硬固定最后
    for p in players:
        tags = []
        if left_pid is not None and p["pid"] == left_pid == right_pid:
            tags.append("光明使者")  # 左右同一人，合并
        else:
            if p["pid"] == left_pid:
                tags.append("光明左使")
            if p["pid"] == right_pid:
                tags.append("光明右使")
        if p["pid"] == tower_pid:
            tags.append("敌塔师")
        for tag in ("瘤", "莽", "搞子", "躺了", "僵", "硬"):
            if (p["pid"], tag) in neg:
                tags.append(tag)
        p["tags"] = tags

    loser = "dire" if winner == "radiant" else "radiant"
    for team, title in ((winner, "MVP"), (loser, "SVP")):
        ps = [p for p in players if p["team"] == team and p["pid"] in scores]
        if ps:
            # 同分依次比较：KDA、击杀+助攻、最后以 pid 兜底保证结果可复现
            def _tb(p):
                k, d, a = (p.get("kills") or 0), (p.get("deaths") or 0), (p.get("assists") or 0)
                return (p["score"], (k + a) / max(d, 1), k + a, -p["pid"])
            best = max(ps, key=_tb)
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
