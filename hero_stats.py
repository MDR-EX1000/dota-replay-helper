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
    heroes = []
    for g in groups.values():
        decided = g["wins"] + g["losses"]
        users = sorted(g["users"].values(), key=lambda u: (-u["games"], -u["wins"], u["name"]))
        for u in users:
            d = u["wins"] + u["losses"]
            u["win_rate"] = u["wins"] / d * 100 if d else None
        # 人柱力：至少使用该英雄 3 场才参与评选，避免 1 场 100% 压过 5 场 80%。
        # 候选中原始胜率最高；同胜率比胜场，再比出场，最后按名字保证可复现。
        candidates = [u for u in users if u["games"] >= 3]
        mainstay = max(candidates, key=lambda u: (u["win_rate"] if u["win_rate"] is not None else -1,
                                                 u["wins"], u["games"], u["name"])) if candidates else None
        heroes.append({
            "key": g["key"], "name": g["name"], "image": g["image"], "games": g["games"],
            "wins": g["wins"], "losses": g["losses"],
            "pick_rate": g["games"] / total * 100 if total else None,
            "win_rate": g["wins"] / decided * 100 if decided else None,
            "user_count": len(users), "users": users, "mainstay": mainstay,
            "records": sorted(g["records"], key=lambda r: (r["date"], str(r["match"])), reverse=True),
        })
    heroes.sort(key=lambda h: (-h["games"], -h["wins"], h["key"]))
    return {"total": total, "heroes": heroes}
