# -*- coding: utf-8 -*-
"""英雄出场与胜率统计：只读公开比赛明细（docs/data/matches.js 里的 matches 列表）。

口径：
  - 出场场次：该英雄在多少场比赛里出现过，一场里同一英雄最多算一次。
  - 出场率 = 出场场次 / 总场次。
  - 胜率 = 该英雄所在队伍获胜的场次 / 出场场次，使用原始值，不做平滑或收缩。
  - 比赛胜负以 match["winner"] 为准；缺少英雄标识的玩家记录直接跳过，不拿空值当英雄。
"""

TEAMS = ("radiant", "dire")


def hero_key(player):
    return str(player.get("hero") or "").strip()


def summarize(matches):
    """返回 {"total": 总场次, "heroes": [...]}。

    英雄按出场降序、胜场降序、key 升序；每个英雄带使用者明细和逐场记录，供详情页使用。
    """
    total = 0
    groups = {}
    matchups = {}
    for match in matches:
        players = match.get("players") or []
        if not players:
            continue
        total += 1
        winner = match.get("winner")
        seen = set()
        for player in players:
            key = hero_key(player)
            if not key or key in seen:
                continue
            seen.add(key)
            won = (player.get("team") == winner) if winner in TEAMS and player.get("team") in TEAMS else None
            g = groups.setdefault(key, {"key": key, "name": "", "image": "", "games": 0,
                                        "wins": 0, "losses": 0, "users": {}, "records": []})
            g["name"] = g["name"] or player.get("hero_zh") or key
            g["image"] = g["image"] or player.get("hero_image") or ""
            g["games"] += 1
            user_id = player.get("id") or player.get("name") or "?"
            user = g["users"].setdefault(user_id, {"id": player.get("id") or "", "name": player.get("name") or "",
                                                   "avatar": player.get("avatar") or "", "games": 0, "wins": 0, "losses": 0})
            user["avatar"] = user["avatar"] or player.get("avatar") or ""
            user["games"] += 1
            if won is True:
                g["wins"] += 1
                user["wins"] += 1
            elif won is False:
                g["losses"] += 1
                user["losses"] += 1
            g["records"].append({"match": match.get("id"), "date": match.get("date") or "",
                                 "player": player.get("name") or "", "player_id": player.get("id") or "",
                                 "avatar": player.get("avatar") or "", "team": player.get("team"), "win": won})
        # 有向对阵：A 对 B 的胜率只看双方不同阵营的交手，和英雄总胜率无关。
        for player in players:
            key, team = hero_key(player), player.get("team")
            if not key or team not in TEAMS:
                continue
            won = (team == winner) if winner in TEAMS else None
            if won is None:
                continue
            for opponent in players:
                opp = hero_key(opponent)
                if not opp or opponent.get("team") not in TEAMS or opponent.get("team") == team:
                    continue
                row = matchups.setdefault((key, opp), {"games": 0, "wins": 0, "losses": 0})
                row["games"] += 1
                row["wins" if won else "losses"] += 1

    # 至少交手 3 场，胜率 >=60% 为克制、<=40% 为被克；最多各 10 个，不凑数。
    relations = {}
    for (key, opp), row in matchups.items():
        if row["games"] < 3:
            continue
        win_rate = row["wins"] / row["games"] * 100
        kind = "counters" if win_rate >= 60 else "countered_by" if win_rate <= 40 else None
        if not kind:
            continue
        entry = {"key": opp, "name": groups[opp]["name"], "image": groups[opp]["image"],
                 "win_rate": win_rate, **row}
        relations.setdefault((key, kind), []).append(entry)

    def relation_rows(key, kind):
        rows = relations.get((key, kind), [])
        rows.sort(key=lambda r: ((-r["win_rate"] if kind == "counters" else r["win_rate"]),
                                 -r["games"], -r["wins"] if kind == "counters" else -r["losses"], r["key"]))
        return rows[:10]

    heroes = []
    for g in groups.values():
        decided = g["wins"] + g["losses"]
        users = sorted(g["users"].values(), key=lambda u: (-u["games"], -u["wins"], u["name"]))
        for u in users:
            d = u["wins"] + u["losses"]
            u["win_rate"] = u["wins"] / d * 100 if d else None
        # 人柱力：至少使用该英雄 3 场且原始胜率 > 50%，避免低样本或不胜者当选。
        # 候选中原始胜率最高；同胜率比胜场，再比出场，最后按名字保证可复现。
        candidates = [u for u in users if u["games"] >= 3 and u["win_rate"] is not None and u["win_rate"] > 50]
        mainstay = max(candidates, key=lambda u: (u["win_rate"] if u["win_rate"] is not None else -1,
                                                 u["wins"], u["games"], u["name"])) if candidates else None
        heroes.append({
            "key": g["key"], "name": g["name"], "image": g["image"], "games": g["games"],
            "wins": g["wins"], "losses": g["losses"],
            "pick_rate": g["games"] / total * 100 if total else None,
            "win_rate": g["wins"] / decided * 100 if decided else None,
            "user_count": len(users), "users": users, "mainstay": mainstay,
            "counters": relation_rows(g["key"], "counters"),
            "countered_by": relation_rows(g["key"], "countered_by"),
            "records": sorted(g["records"], key=lambda r: (r["date"], str(r["match"])), reverse=True),
        })
    heroes.sort(key=lambda h: (-h["games"], -h["wins"], h["key"]))
    return {"total": total, "heroes": heroes}
