"""11-inspired single-match titles. Undocumented rules are project rules, v1."""
from player_data import metric

VERSION = "11-inspired-v1"
RULES = [
    "参考 11 平台经典七称号；以下公式、适用阵营、并列及缺失处理为本项目 v1 规则。",
    "仅评选双方各 5 人、时长超过 3 分钟且胜负已知的比赛。一人可获得多个称号。",
    "MVP 为胜方综合分第一，英魂为败方综合分第一；各仅一人。",
    "综合分 = 100 ×（30% KDA + 25% 英雄伤害 + 15% 推塔伤害 + 10% 眩晕秒数 + 10% 治疗 + 10% 辅助分）。",
    "KDA = (击杀 + 助攻) / (死亡 + 1)。各指标除以全场最高值，最高值为 0 时该项计 0 分。",
    "辅助分 = 助攻 + 2 × 插眼数 + 3 × 排眼数。偏将按辅助分评选。",
    "富豪按全场净资产，破敌按胜方击杀，破军按全场正补塔数，补王按全场反补数评选。",
    "基础称号并列最高可同时获得；最高值为 0 不颁发，正补塔全员相同时不颁发破军。",
    "MVP/英魂同分时依次比较 KDA、击杀、较少死亡、较小比赛内编号，使用未四舍五入的分数。",
    "只计敌方塔最后一击；小兵击塔、反补不计入。可明确归属的蛇棒计入暗影萨满，无法归属的召唤物会使破军暂不评选。",
    "某称号依赖的数据有缺失时，在其完整比较范围内暂停该项评选；真实 0 值保留。",
    "净资产、击杀、反补等直接统计适用于 v2 旧数据；旧解析器合成的 0 无法仅凭结果恢复，需重解析核实。",
]
DEFINITIONS = [("mvp", "MVP", "MVP", 3), ("wealth", "富豪", "富", 1),
               ("kills", "破敌", "破", 1), ("towers", "破军", "军", 1),
               ("support", "偏将", "助", 1), ("denies", "补王", "补", 1),
               ("soul", "英魂", "魂", 1)]
DEFS = {key: (name, short, points) for key, name, short, points in DEFINITIONS}
MVP_FIELDS = ("kills", "deaths", "assists", "hero_damage", "tower_damage", "stuns",
              "healing", "wards_placed", "wards_destroyed")


def norm(token):
    return str(token or "").lower().replace("npc_dota_hero_", "").replace("cdota_unit_hero_", "").replace("_", "")


def tower_counts(players, objectives):
    if not isinstance(objectives, list):
        return None
    counts = {p["pid"]: 0 for p in players}
    for event in objectives:
        if event.get("kind") != "tower":
            continue
        target, team = event.get("target", ""), event.get("team", "")
        owner = "radiant" if "goodguys" in target else "dire" if "badguys" in target else None
        if event.get("denied") or (owner and team == owner):
            continue
        if team not in ("radiant", "dire"):
            return None
        killer = norm(event.get("killer"))
        if any(part in killer for part in ("creep", "siege", "tower")):
            continue
        if killer.startswith("npcdotashadowshamanward"):
            killer = "shadowshaman"
        candidates = [p for p in players if p["team"] == team and norm(p["hero"]) == killer]
        if len(candidates) != 1:
            return None
        counts[candidates[0]["pid"]] += 1
    return counts


def assign_titles(players, raw_match):
    result = {"version": VERSION, "rules": RULES, "unavailable": [], "eligible": False}
    for p in players:
        p["titles"] = []
        p["title_score"] = None
        p["tower_kills"] = None
    def unavailable(key, reason):
        result["unavailable"].append({"key": key, "name": DEFS[key][0], "reason": reason})
    duration = metric(raw_match, "duration")
    if (len(players) != 10 or any(sum(p["team"] == t for p in players) != 5 for t in ("radiant", "dire"))
            or duration is None or duration <= 180 or not isinstance(raw_match.get("radiant_win"), bool)):
        for key in DEFS:
            unavailable(key, "需双方各 5 人、时长超过 3 分钟且胜负已知")
        return result
    result["eligible"] = True
    winner = "radiant" if raw_match["radiant_win"] else "dire"
    def award(p, key, value, reason):
        name, short, points = DEFS[key]
        p["titles"].append({"key": key, "name": name, "short": short,
                            "points": points, "value": round(value, 3), "reason": reason})
    def best(key, candidates, field, description, require_difference=False):
        if any(p.get(field) is None for p in candidates):
            unavailable(key, description + "数据不完整")
            return
        maximum = max(p[field] for p in candidates)
        if maximum <= 0 or (require_difference and len({p[field] for p in candidates}) == 1):
            unavailable(key, "所有选手正补塔数相同" if require_difference else "该项最高值为 0")
            return
        winners = [p for p in candidates if p[field] == maximum]
        for p in winners:
            award(p, key, maximum, "%s最高：%s%s" % (description, round(maximum, 2), "（并列）" if len(winners) > 1 else ""))
    best("wealth", players, "net_worth", "全场净资产")
    best("kills", [p for p in players if p["team"] == winner], "kills", "胜方击杀")
    best("denies", players, "denies", "全场反补")
    for p in players:
        p["support_score"] = (p["assists"] + 2*p["wards_placed"] + 3*p["wards_destroyed"]
                              if all(p.get(k) is not None for k in ("assists", "wards_placed", "wards_destroyed")) else None)
    best("support", players, "support_score", "全场辅助分（助攻 + 2×插眼 + 3×排眼）")
    counts = tower_counts(players, raw_match.get("objectives"))
    if counts is None:
        unavailable("towers", "推塔事件缺失或存在无法归属的最后一击")
    else:
        for p in players:
            p["tower_kills"] = counts[p["pid"]]
        best("towers", players, "tower_kills", "全场正补塔数", True)
    if any(p.get(k) is None for p in players for k in MVP_FIELDS):
        for key in ("mvp", "soul"):
            unavailable(key, "综合分依赖的全场数据不完整")
    else:
        for p in players:
            p["_kda"] = (p["kills"]+p["assists"])/(p["deaths"]+1)
        weights = {"_kda": .30, "hero_damage": .25, "tower_damage": .15,
                   "stuns": .10, "healing": .10, "support_score": .10}
        maxima = {k: max(p[k] for p in players) for k in weights}
        scores = {p["pid"]: 100*sum(w*p[k]/maxima[k] if maxima[k] else 0 for k, w in weights.items()) for p in players}
        for p in players:
            p["title_score"] = round(scores[p["pid"]], 2)
        for key, team in (("mvp", winner), ("soul", "dire" if winner == "radiant" else "radiant")):
            p = max((p for p in players if p["team"] == team),
                    key=lambda p: (scores[p["pid"]], p["_kda"], p["kills"], -p["deaths"], -p["pid"]))
            award(p, key, scores[p["pid"]], "%s综合分第一：%.2f（项目自拟 v1）" % ("胜方" if key == "mvp" else "败方", scores[p["pid"]]))
        for p in players:
            p.pop("_kda", None)
    for p in players:
        p["titles"].sort(key=lambda t: list(DEFS).index(t["key"]))
    return result
