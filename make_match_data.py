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
from player_data import IdentityResolver, metric
from match_titles import assign_titles
from web_safety import script_json
import steam_profiles

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
HERO_PORTRAITS = load_json(os.path.join("docs", "hero_portraits.json"), {}).get("heroes", {})
ITEM_ICONS = load_json(os.path.join("docs", "item_icons.json"), {}).get("items", {})
PUBLIC_FIELDS = {'level': 'level', 'kills': 'kills', 'deaths': 'deaths', 'assists': 'assists', 'net_worth': 'net_worth', 'gpm': 'gold_per_min', 'xpm': 'xp_per_min', 'last_hits': 'last_hits', 'denies': 'denies', 'hero_damage': 'hero_damage', 'hero_damage_taken': 'hero_damage_taken', 'tower_damage': 'tower_damage', 'healing': 'hero_healing', 'stuns': 'stuns', 'wards_placed': 'observer_sentry_wards', 'wards_destroyed': 'wards_destroyed'}



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
    fields = ("kills", "deaths", "assists", "net_worth", "hero_damage", "hero_damage_taken",
              "tower_damage", "healing", "stuns", "wards_placed", "wards_destroyed")
    return {key: round(sum(p[key] for p in ps), 1) if ps and all(p[key] is not None for p in ps) else None
            for key in fields}


def transform_match(m, resolver=None, profile_cache=None):
    profile_cache = steam_profiles.read_cache() if profile_cache is None else profile_cache
    resolver = resolver or IdentityResolver([m], ALIASES, load_json("legacy_identities.json", {}))
    players_out = []
    for index, p in enumerate(m.get("players", [])):
        hero = norm_hero(p.get("hero") or p.get("hero_name", ""))
        items = []
        for raw in p.get("items") or []:
            k = item_key(raw)
            items.append({"key": k, "zh": item_zh(k), "image": ITEM_ICONS.get(k, "")})
        abilities = []
        for a in p.get("abilities") or []:
            k = a.get("name", "")
            if k:
                abilities.append({"key": k, "zh": ability_zh(k), "level": a.get("level", 0)})
        _, public_pid, display_name, identity_status = resolver.describe(p, m, index)
        players_out.append({
            "pid": p.get("player_id", 0),
            "slot": p.get("player_slot", 0),
            "team": p.get("team", ""),
            "id": public_pid,
            "avatar": steam_profiles.avatar_for(public_pid, profile_cache),
            "identity_status": identity_status,
            "name": display_name,
            "hero": hero,
            "hero_zh": hero_zh(hero),
            "hero_image": HERO_PORTRAITS.get(hero, ""),
            "level": metric(p, "level"),
            "kills": metric(p, "kills"),
            "deaths": metric(p, "deaths"),
            "assists": metric(p, "assists"),
            "net_worth": metric(p, "net_worth"),
            "gpm": metric(p, "gold_per_min"),
            "xpm": metric(p, "xp_per_min"),
            "last_hits": metric(p, "last_hits"),
            "denies": metric(p, "denies"),
            "hero_damage": metric(p, "hero_damage"),
            "hero_damage_taken": metric(p, "hero_damage_taken"),
            "tower_damage": metric(p, "tower_damage"),
            "healing": metric(p, "hero_healing"),
            "stuns": metric(p, "stuns"),
            "wards_placed": metric(p, "observer_sentry_wards"),
            "wards_destroyed": metric(p, "wards_destroyed"),
            "missing_fields": [key for key, source in PUBLIC_FIELDS.items() if metric(p, source) is None],
            "quality_verified": (p.get("data_quality") or {}).get("verified", False),
            "items": items,
            "abilities": abilities,
            "damage": p.get("damage"),
        })

    if isinstance(m.get("radiant_win"), bool):
        rating.apply(players_out, "radiant" if m["radiant_win"] else "dire")
    else:
        for p in players_out:
            p["score"] = None
            p["title"] = ""
            p["kda_title"] = ""
            p["tags"] = []

    score = {team: team_totals(players_out, team)["kills"] for team in ("radiant", "dire")}
    awards = assign_titles(players_out, m)

    # MVP/SVP 已由 rating.py 负责；只保留重分支的 5 个客观称号
    KEEP_TITLES = {"wealth", "kills", "towers", "support", "denies"}
    for p in players_out:
        p["titles"] = [t for t in (p.get("titles") or []) if t.get("key") in KEEP_TITLES]
        # title_score / support_score / tower_kills 保留为内部/测试字段，
        # MVP/SVP 不再使用它们。
    awards["unavailable"] = [
        x for x in awards.get("unavailable", []) if x.get("key") in KEEP_TITLES
    ]
    awards["rules"] = [
        r for r in awards.get("rules", []) if "MVP" not in r and "英魂" not in r
    ]
    awards["rules"].append(
        "MVP/SVP 使用 0–10 单局评分；KDA 称号（秀/天秀/天之上）与僵/硬/瘤/莽也由该评分体系给出。"
    )

    kills = []
    for k in m.get("kills") or []:
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
    for o in m.get("objectives") or []:
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
    for pu in m.get("purchases") or []:
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
            "item_image": ITEM_ICONS.get(key, ""),
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
                def total_series(series):
                    values = [series[p["pid"]][idx] if 0 <= p["pid"] < len(series) and idx < len(series[p["pid"]]) else None for p in vals_nw]
                    return sum(values) if values and all(metric({"v": v}, "v") is not None for v in values) else None
                g, x = total_series(nw), total_series(xp)
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
        "radiant_win": m.get("radiant_win"),
        "winner": ("radiant" if m["radiant_win"] else "dire") if isinstance(m.get("radiant_win"), bool) else None,
        "awards": awards,
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


def build(matches_dir=None, out_file=None):
    matches_dir = matches_dir or JSON_DIR
    out_file = out_file or OUT_FILE
    raw_matches = []
    for path in sorted(os.listdir(matches_dir)) if os.path.isdir(matches_dir) else []:
        if not (path.startswith("match_") and path.endswith(".json")):
            continue
        if path.endswith("_raw.json"):
            continue
        try:
            with open(os.path.join(matches_dir, path), encoding="utf-8") as fp:
                m = json.load(fp)
        except (OSError, json.JSONDecodeError):
            continue
        if len(m.get("players", [])) != 10 or m.get("duration", 0) <= 0:
            continue
        raw_matches.append(m)

    if not raw_matches:
        raise ValueError("没有有效比赛，已保留现有网页数据")
    resolver = IdentityResolver(raw_matches, ALIASES, load_json("legacy_identities.json", {}))
    profiles = steam_profiles.read_cache()
    matches = [transform_match(m, resolver, profiles) for m in raw_matches]

    matches.sort(key=lambda x: (x.get("start", 0), x.get("id", "")), reverse=True)
    data = {
        "version": 2,
        "generated_at": datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M"),
        "matches": matches,
    }
    text = script_json(data)
    if "steamid" in text or re.search(r"7656119\d{10}", text):
        raise SystemExit("refusing to publish SteamID data")
    os.makedirs(os.path.dirname(os.path.abspath(out_file)), exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as fp:
        fp.write("window.MATCH_DATA = " + text + ";\n")
    return len(matches)


if __name__ == "__main__":
    print("matches:", build())
