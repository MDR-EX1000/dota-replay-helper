"""Shared account identity and missing-aware statistics. Internal keys stay private."""
import hashlib
import math

STEAM_BASE = 76561197960265728
METRICS = ("kills", "deaths", "assists", "net_worth", "gold_per_min",
           "xp_per_min", "last_hits", "denies", "hero_damage",
           "hero_damage_taken", "tower_damage", "hero_healing", "stuns",
           "observer_sentry_wards", "wards_destroyed", "level")


def steam_id(value):
    text = str(value or "")
    if text.isdigit() and STEAM_BASE < int(text) < STEAM_BASE + 2 ** 32:
        return text
    return ""


def metric(player, field):
    value = player.get(field)
    if field in (player.get("data_quality") or {}).get("missing_fields", []):
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(value) and value >= 0 else None


def average(values, digits=1):
    valid = [v for v in values if v is not None]
    return round(sum(valid) / len(valid), digits) if valid else None


def public_id(key):
    # A deterministic public pseudonym, not an anonymity guarantee.
    return "p_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]


class IdentityResolver:
    def __init__(self, matches, aliases=None, legacy=None):
        self.aliases = aliases or {}
        self.legacy = legacy or {}
        groups = {}
        for sid, label in self.aliases.items():
            if steam_id(sid):
                groups.setdefault(label, []).append(sid)
        self.groups = {sid: min(ids, key=int) for ids in groups.values() for sid in ids}
        self.names = {}
        self.status = {}
        for match in sorted(matches, key=lambda m: (m.get("start_time", 0), str(m.get("match_id", "")))):
            for index, player in enumerate(match.get("players", [])):
                key, status = self.resolve(player, match, index)
                raw = str(player.get("name") or "")
                sid = steam_id(player.get("steamid"))
                label = self.aliases.get(sid) or self.aliases.get(raw) or raw
                if not label or steam_id(label):
                    label = "未命名选手"
                self.names[key] = str(label)
                self.status[key] = status
        labels = {}
        for key, label in self.names.items():
            labels.setdefault(label, []).append(key)
        for label, keys in labels.items():
            if len(keys) > 1:
                for key in keys:
                    self.names[key] = label + " · " + public_id(key)[-6:]

    def resolve(self, player, match, index=0):
        sid = steam_id(player.get("steamid"))
        if not sid:
            # Only an explicit mapping can attach a nickname-only historical row.
            sid = steam_id(self.legacy.get(str(player.get("name") or "")))
        if sid:
            return "account:" + self.groups.get(sid, sid), "verified"
        mid = str(match.get("match_id") or "unknown")
        slot = player.get("player_id", index)
        return "unresolved:%s:%s:%s" % (mid, slot, index), "unresolved"

    def describe(self, player, match, index=0):
        key, status = self.resolve(player, match, index)
        return key, public_id(key), self.names.get(key, "未命名选手"), status


def ranks(match):
    """Do not rank a partial population as though missing net worth were zero."""
    players = match.get("players", [])
    if any(metric(p, "net_worth") is None for p in players):
        return {}
    result = {i: [None, None] for i in range(len(players))}
    for rank, i in enumerate(sorted(result, key=lambda i: (-metric(players[i], "net_worth"), i)), 1):
        result[i][0] = rank
    for team in ("radiant", "dire"):
        indices = [i for i, p in enumerate(players) if p.get("team") == team]
        for rank, i in enumerate(sorted(indices, key=lambda i: (-metric(players[i], "net_worth"), i)), 1):
            result[i][1] = rank
    return result


def aggregate_players(matches, aliases, overrides, mmr, hero_names, legacy=None):
    resolver = IdentityResolver(matches, aliases, legacy)
    rows = {}
    for match in sorted(matches, key=lambda m: (m.get("start_time", 0), str(m.get("match_id", "")))):
        positions = ranks(match)
        for index, p in enumerate(match.get("players", [])):
            key, pid, name, status = resolver.describe(p, match, index)
            row = rows.setdefault(key, {"name": name, "id": pid, "status": status,
                "steamids": set(), "games": 0, "wins": 0, "results": 0,
                "rank_all": [], "rank_team": [], "heroes": {},
                "metrics": {f: [] for f in METRICS}, "kda": [], "dmg_ratio": [], "taken_ratio": []})
            sid = steam_id(p.get("steamid")) or steam_id((legacy or {}).get(str(p.get("name") or "")))
            if sid:
                row["steamids"].add(sid)
            row["games"] += 1
            if isinstance(match.get("radiant_win"), bool) and p.get("team") in ("radiant", "dire"):
                row["results"] += 1
                row["wins"] += (p["team"] == "radiant") == match["radiant_win"]
            for field in METRICS:
                row["metrics"][field].append(metric(p, field))
            kda = tuple(metric(p, f) for f in ("kills", "deaths", "assists"))
            if all(v is not None for v in kda):
                row["kda"].append(kda)
            nw = metric(p, "net_worth")
            for field, dest in (("hero_damage", "dmg_ratio"), ("hero_damage_taken", "taken_ratio")):
                damage = metric(p, field)
                if damage is not None and nw is not None and nw > 0:
                    row[dest].append(damage / nw)
            if index in positions:
                row["rank_all"].append(positions[index][0])
                row["rank_team"].append(positions[index][1])
            hero = str(p.get("hero") or p.get("hero_name") or "").lower()
            hero = hero.replace("cdota_unit_hero_", "").replace("npc_dota_hero_", "").replace("_", "")
            if hero:
                zh = hero_names.get(hero, hero)
                row["heroes"][zh] = row["heroes"].get(zh, 0) + 1

    out = []
    for key, row in rows.items():
        n, values = row["games"], row["metrics"]
        samples = {f: sum(v is not None for v in vs) for f, vs in values.items()}
        samples.update(kda=len(row["kda"]), dmg_gold=len(row["dmg_ratio"]), role=len(row["rank_team"]))
        core_rate = sum(r <= 3 for r in row["rank_team"]) / len(row["rank_team"]) if row["rank_team"] else None
        role = ("核心" if core_rate >= .5 else "酱油") if core_rate is not None else "未定"
        override = next((overrides[k] for k in [key, row["name"]] + sorted(row["steamids"]) if k in overrides), {})
        if override.get("role") in ("核心", "酱油"):
            role = override["role"]
        mmr_value = next((mmr[k] for k in [key, row["name"]] + sorted(row["steamids"]) if k in mmr), None)
        try:
            mmr_value = max(0, int(mmr_value)) if mmr_value is not None else None
        except (TypeError, ValueError):
            mmr_value = None
        sums = [sum(v[i] for v in row["kda"]) for i in range(3)]
        kda = round((sums[0] + sums[2]) / max(sums[1], 1), 2) if row["kda"] else None
        def avg(field, scale=1):
            return average([v / scale if v is not None else None for v in values[field]])
        kd = "/".join("%.1f" % (v / len(row["kda"])) for v in sums) if row["kda"] else "暂无数据"
        samples["results"] = row["results"]
        ready = row["status"] == "verified" and row["results"] == n and role != "未定" and all(samples[f] == n for f in ("kda", "gold_per_min", "xp_per_min", "dmg_gold", "role"))
        results = row["results"]
        exact = {"kda": (sums[0]+sums[2])/max(sums[1],1) if row["kda"] else None,
                 "gpm": average(values["gold_per_min"], 12), "xpm": average(values["xp_per_min"], 12),
                 "dmg_gold": average(row["dmg_ratio"], 12)}
        out.append({"_identity": key, "_id": row["id"], "_identity_status": row["status"],
            "_samples": samples, "_rating_ready": ready, "_rating_inputs": exact, "_mmr": mmr_value,
            "玩家": row["name"], "SteamID": " / ".join(sorted(row["steamids"])),
            "场次": n, "胜": row["wins"], "负": results-row["wins"],
            "胜率": "%.1f%%" % (100*row["wins"]/results) if results else "暂无数据",
            "_winrate": row["wins"]/results if results else 0,
            "定位": role, "核心率": "%.0f%%" % (100*core_rate) if core_rate is not None else "暂无数据",
            "_core_rate": core_rate, "全场经济平均排名": average(row["rank_all"], 2),
            "队内经济平均排名": average(row["rank_team"], 2), "平均GPM": avg("gold_per_min"),
            "平均XPM": avg("xp_per_min"), "KDA": kda, "平均K/D/A": kd,
            "场均击杀": avg("kills"), "场均死亡": avg("deaths"), "场均助攻": avg("assists"),
            "平均补刀": avg("last_hits"), "平均净资产(K)": avg("net_worth", 1000),
            "造成英雄伤害(K)": avg("hero_damage", 1000), "承受英雄伤害(K)": avg("hero_damage_taken", 1000),
            "伤害/经济": average(row["dmg_ratio"], 2), "承伤/经济": average(row["taken_ratio"], 2),
            "MMR": mmr_value if mmr_value is not None else "-", "英雄池": len(row["heroes"]),
            "常用英雄": ", ".join("%s(%s)" % x for x in sorted(row["heroes"].items(), key=lambda x: (-x[1], x[0]))[:3])})
    return sorted(out, key=lambda r: (-r["_winrate"], -r["场次"], -(r["平均GPM"] or 0)))
