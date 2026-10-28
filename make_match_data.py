# -*- coding: utf-8 -*-
"""
生成比赛明细数据：json/match_*.json -> docs/data/matches.js

只输出公开字段，绝不包含 SteamID。
"""

import json
import os
import re
import rating
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
JSON_DIR = os.path.join(ROOT, "json")
OUT_DIR = os.path.join(ROOT, "docs", "data")
OUT_FILE = os.path.join(OUT_DIR, "matches.js")

MODE_ZH = {
    1: "全英雄选择", 2: "队长模式", 3: "随机征召", 4: "单一征召",
    5: "全阵营随机", 11: "中路模式", 12: "最少选择", 16: "队长征召",
    18: "技能征召", 20: "全随机死亡竞赛", 21: "1v1 中路", 22: "全英雄选择",
    23: "快速模式",
}


def load_json(name, default):
    path = os.path.join(ROOT, name)
    try:
        with open(path, encoding="utf-8") as fp:
            return json.load(fp)
    except (OSError, json.JSONDecodeError):
        return default


ALIASES = load_json("aliases.json", {})
HERO_ZH = load_json("hero_names_zh.json", {})
ITEM_ZH = load_json("item_names_zh.json", {})
ITEM_ALIASES = load_json("item_aliases.json", {})
ITEM_IDS = load_json("item_ids.json", {})
ITEM_COSTS = load_json("item_costs.json", {})
ABILITY_ZH = load_json("ability_names_zh.json", {})


def norm_hero(s):
    s = (s or "").lower()
    s = s.replace("cdota_unit_hero_", "").replace("npc_dota_hero_", "")
    return s.replace("_", "")


def hero_zh(token):
    return HERO_ZH.get(norm_hero(token), token or "")


def item_key(raw):
    k = (raw or "").lower()
    if k.startswith("item_"):
        k = k[5:]
    return ITEM_ALIASES.get(k, k)


def item_zh(key):
    return ITEM_ZH.get(key) or key.replace("_", " ").title()


def ability_zh(key):
    return ABILITY_ZH.get(key) or key.replace("_", " ").title()


def unit_label(token):
    if not token:
        return ""
    if norm_hero(token) in HERO_ZH:
        return hero_zh(token)
    t = token.lower()
    if "tower" in t:
        return "防御塔"
    if "creep" in t or "melee" in t or "ranged" in t:
        return "小兵"
    if "roshan" in t:
        return "肉山"
    return token


def objective_label(kind, target, lane, tier):
    lane_zh = {"top": "上路", "mid": "中路", "bot": "下路"}.get(lane, "")
    if kind == "tower":
        owner = "天辉" if "goodguys" in target else "夜魇"
        tier_zh = {1: "一塔", 2: "二塔", 3: "三塔", 4: "四塔"}.get(tier, "塔")
        return f"{owner}{lane_zh}{tier_zh}"
    if kind == "rax":
        owner = "天辉" if "goodguys" in target else "夜魇"
        return f"{owner}{lane_zh}兵营"
    if kind == "fort":
        return "遗迹"
    if kind == "shrine":
        return "圣坛"
    if kind == "roshan":
        return "肉山"
    if kind == "aegis":
        return "不朽盾"
    if kind == "tormentor":
        return "痛苦魔方"
    return target


def team_totals(players, team):
    ps = [p for p in players if p["team"] == team]
    return {
        "kills": sum(p["kills"] for p in ps),
        "deaths": sum(p["deaths"] for p in ps),
        "assists": sum(p["assists"] for p in ps),
        "net_worth": sum(p["net_worth"] for p in ps),
        "hero_damage": sum(p["hero_damage"] for p in ps),
        "hero_damage_taken": sum(p["hero_damage_taken"] for p in ps),
        "tower_damage": sum(p["tower_damage"] for p in ps),
        "healing": sum(p["healing"] for p in ps),
        "stuns": round(sum(p["stuns"] for p in ps), 1),
        "wards_placed": sum(p["wards_placed"] for p in ps),
        "wards_destroyed": sum(p["wards_destroyed"] for p in ps),
    }


def transform_match(m):
    aliases = ALIASES
    canonical = set(aliases.values())

    def player_name(p):
        raw = p.get("name", "")
        sid = str(p.get("steamid", ""))
        n = aliases.get(raw) or aliases.get(sid)
        if not n and raw in canonical:
            n = raw
        return n or raw or sid

    players_out = []
    for p in m.get("players", []):
        hero = norm_hero(p.get("hero") or p.get("hero_name", ""))
        items = []
        for raw in p.get("items", []):
            k = item_key(raw)
            items.append({"key": k, "zh": item_zh(k)})
        abilities = []
        for a in p.get("abilities", []):
            k = a.get("name", "")
            if k:
                abilities.append({"key": k, "zh": ability_zh(k), "level": a.get("level", 0)})
        players_out.append({
            "pid": p.get("player_id", 0),
            "slot": p.get("player_slot", 0),
            "team": p.get("team", ""),
            "name": player_name(p),
            "hero": hero,
            "hero_zh": hero_zh(hero),
            "level": p.get("level", 0),
            "kills": p.get("kills", 0),
            "deaths": p.get("deaths", 0),
            "assists": p.get("assists", 0),
            "net_worth": p.get("net_worth", 0),
            "gpm": p.get("gold_per_min", 0),
            "xpm": p.get("xp_per_min", 0),
            "last_hits": p.get("last_hits", 0),
            "denies": p.get("denies", 0),
            "hero_damage": p.get("hero_damage", 0),
            "hero_damage_taken": p.get("hero_damage_taken", 0),
            "tower_damage": p.get("tower_damage", 0),
            "healing": p.get("hero_healing", 0),
            "stuns": p.get("stuns", 0),
            "wards_placed": p.get("observer_sentry_wards", 0),
            "wards_destroyed": p.get("wards_destroyed", 0),
            "items": items,
            "abilities": abilities,
            "damage": p.get("damage"),
        })

    rating.apply(players_out, "radiant" if m.get("radiant_win") else "dire")

    score = {
        "radiant": sum(p["kills"] for p in players_out if p["team"] == "radiant"),
        "dire": sum(p["kills"] for p in players_out if p["team"] == "dire"),
    }

    kills = []
    for k in m.get("kills", []):
        killer = k.get("killer", "")
        victim = k.get("victim", "")
        assists = [{"key": a, "zh": unit_label(a)} for a in k.get("assists", []) if a and a != killer]
        kills.append({
            "t": round(k.get("t", 0), 1),
            "killer": killer,
            "killer_zh": unit_label(killer),
            "victim": victim,
            "victim_zh": unit_label(victim),
            "assists": assists,
            "team": k.get("killer_team", ""),
            "inflictor": ability_zh(k["inflictor"]) if k.get("inflictor") else "",
            "first_blood": bool(k.get("first_blood")),
        })

    objectives = []
    for o in m.get("objectives", []):
        kind = o.get("kind", "")
        target = o.get("target", "")
        lane = o.get("lane", "")
        tier = o.get("tier", 0)
        objectives.append({
            "t": round(o.get("t", 0), 1),
            "kind": kind,
            "team": o.get("team", ""),
            "label": objective_label(kind, target, lane, tier),
            "killer": o.get("killer", ""),
            "killer_zh": unit_label(o.get("killer", "")),
            "lane": lane,
            "tier": tier,
            "denied": bool(o.get("denied")),
        })

    purchases = []
    for pu in m.get("purchases", []):
        item_id = pu.get("item_id")
        key = ITEM_IDS.get(str(item_id), "")
        if not key:
            continue
        key = ITEM_ALIASES.get(key, key)
        purchases.append({
            "t": round(pu.get("t", 0), 1),
            "pid": pu.get("player_id", 0),
            "hero": pu.get("hero", ""),
            "hero_zh": hero_zh(pu.get("hero", "")),
            "item": key,
            "item_zh": item_zh(key),
            "cost": ITEM_COSTS.get(key, 0),
            "recipe": key.startswith("recipe_"),
        })

    economy = None
    ec = m.get("economy")
    if ec and ec.get("times"):
        times = ec["times"]
        nw = ec.get("net_worth", [])
        xp = ec.get("xp", [])
        by_team = {"radiant": {"gold": [], "xp": []}, "dire": {"gold": [], "xp": []}}
        for idx in range(len(times)):
            for team in ("radiant", "dire"):
                vals_nw = [p for p in players_out if p["team"] == team]
                g = sum(nw[p["pid"]][idx] for p in vals_nw if p["pid"] < len(nw) and idx < len(nw[p["pid"]]))
                x = sum(xp[p["pid"]][idx] for p in vals_nw if p["pid"] < len(xp) and idx < len(xp[p["pid"]]))
                by_team[team]["gold"].append(g)
                by_team[team]["xp"].append(x)
        economy = {
            "source": ec.get("source", "snapshot"),
            "approx": bool(ec.get("approx")),
            "times": times,
            "team": by_team,
            "players": [
                {"pid": p["pid"], "net_worth": nw[p["pid"]] if p["pid"] < len(nw) else [],
                 "xp": xp[p["pid"]] if p["pid"] < len(xp) else []}
                for p in players_out
            ],
        }

    start = m.get("start_time", 0)
    return {
        "id": str(m.get("match_id", "")),
        "start": start,
        "date": datetime.fromtimestamp(start, timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M") if start else "",
        "duration": m.get("duration", 0),
        "mode": MODE_ZH.get(m.get("game_mode"), m.get("game_mode_name", "")),
        "mode_en": m.get("game_mode_name", ""),
        "radiant_win": bool(m.get("radiant_win")),
        "winner": "radiant" if m.get("radiant_win") else "dire",
        "score": score,
        "teams": {
            "radiant": team_totals(players_out, "radiant"),
            "dire": team_totals(players_out, "dire"),
        },
        "players": players_out,
        "economy": economy,
        "kills": kills,
        "objectives": objectives,
        "purchases": purchases,
    }


def build():
    matches = []
    for path in sorted(os.listdir(JSON_DIR)):
        if not (path.startswith("match_") and path.endswith(".json")):
            continue
        if path.endswith("_raw.json"):
            continue
        try:
            with open(os.path.join(JSON_DIR, path), encoding="utf-8") as fp:
                m = json.load(fp)
        except (OSError, json.JSONDecodeError):
            continue
        if len(m.get("players", [])) != 10 or m.get("duration", 0) <= 0:
            continue
        matches.append(transform_match(m))

    matches.sort(key=lambda x: (x.get("start", 0), x.get("id", "")), reverse=True)
    data = {
        "version": 1,
        "generated_at": datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M"),
        "matches": matches,
    }
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    if "steamid" in text or re.search(r"7656119\d{10}", text):
        raise SystemExit("refusing to publish SteamID data")
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as fp:
        fp.write("window.MATCH_DATA = " + text + ";\n")
    return len(matches)


if __name__ == "__main__":
    print("matches:", build())
