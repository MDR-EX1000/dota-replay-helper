import json
import unittest

import hero_stats
import make_web


def pub_match(mid, winner, heroes, date="2026-11-01 20:00"):
    """公开明细格式的最小比赛：heroes 为 10 个英雄 key，前 5 个天辉、后 5 个夜魇。"""
    players = []
    for i, hero in enumerate(heroes):
        players.append({"id": "p%d" % i, "name": "玩家%d" % i, "team": "radiant" if i < 5 else "dire",
                        "hero": hero, "hero_zh": hero + "中", "hero_image": "img/" + hero})
    return {"id": mid, "date": date, "winner": winner, "players": players}


HEROES = ["axe", "sven", "lina", "bane", "pudge", "viper", "juggernaut", "lion", "tidehunter", "zeus"]


class HeroStats(unittest.TestCase):
    def test_pick_rate_uses_games_over_total_games(self):
        ms = [pub_match("1", "radiant", HEROES), pub_match("2", "dire", HEROES), pub_match("3", "radiant", HEROES[::-1])]
        ms[2]["players"][0]["hero"] = "axe_alt"
        result = hero_stats.summarize(ms)
        self.assertEqual(result["total"], 3)
        axe = next(h for h in result["heroes"] if h["key"] == "axe")
        self.assertEqual(axe["games"], 3)
        self.assertAlmostEqual(axe["pick_rate"], 100.0)

    def test_win_rate_is_raw_and_follows_team_result(self):
        ms = [pub_match("1", "radiant", HEROES), pub_match("2", "dire", HEROES), pub_match("3", "radiant", HEROES)]
        by_key = {h["key"]: h for h in hero_stats.summarize(ms)["heroes"]}
        # axe 在天辉：赢、输、赢
        self.assertEqual((by_key["axe"]["wins"], by_key["axe"]["losses"]), (2, 1))
        self.assertAlmostEqual(by_key["axe"]["win_rate"], 200 / 3)
        self.assertEqual(by_key["axe"]["sides"]["radiant"]["games"], 3)
        self.assertAlmostEqual(by_key["axe"]["sides"]["radiant"]["win_rate"], 200 / 3)
        self.assertEqual(by_key["axe"]["sides"]["dire"], {"games": 0, "wins": 0, "losses": 0, "win_rate": None})
        # zeus 在夜魇：输、赢、输
        self.assertEqual((by_key["zeus"]["wins"], by_key["zeus"]["losses"]), (1, 2))
        self.assertAlmostEqual(by_key["zeus"]["win_rate"], 100 / 3)
        self.assertEqual(by_key["zeus"]["sides"]["dire"]["games"], 3)
        self.assertAlmostEqual(by_key["zeus"]["sides"]["dire"]["win_rate"], 100 / 3)

    def test_single_game_is_not_smoothed(self):
        by_key = {h["key"]: h for h in hero_stats.summarize([pub_match("1", "radiant", HEROES)])["heroes"]}
        self.assertEqual(by_key["axe"]["win_rate"], 100.0)
        self.assertEqual(by_key["zeus"]["win_rate"], 0.0)

    def test_same_hero_twice_in_one_match_counts_once(self):
        heroes = list(HEROES)
        heroes[9] = "axe"  # 双方都选了斧王
        axe = next(h for h in hero_stats.summarize([pub_match("1", "radiant", heroes)])["heroes"] if h["key"] == "axe")
        self.assertEqual(axe["games"], 1)
        self.assertLessEqual(axe["pick_rate"], 100.0)

    def test_player_without_hero_is_skipped_not_counted_as_hero(self):
        m = pub_match("1", "radiant", HEROES)
        m["players"][3]["hero"] = ""
        m["players"][4]["hero"] = None
        keys = {h["key"] for h in hero_stats.summarize([m])["heroes"]}
        self.assertEqual(len(keys), 8)
        self.assertNotIn("", keys)
        self.assertNotIn("None", keys)

    def test_users_are_split_by_player_and_sorted(self):
        ms = [pub_match("1", "radiant", HEROES), pub_match("2", "radiant", HEROES), pub_match("3", "radiant", HEROES)]
        ms[2]["players"][0]["id"] = "other"
        ms[2]["players"][0]["name"] = "路人"
        ms[0]["players"][0]["avatar"] = "https://avatars.steamstatic.com/example.jpg"
        axe = next(h for h in hero_stats.summarize(ms)["heroes"] if h["key"] == "axe")
        self.assertEqual(axe["user_count"], 2)
        self.assertEqual([u["name"] for u in axe["users"]], ["玩家0", "路人"])
        self.assertEqual(axe["users"][0]["games"], 2)
        self.assertEqual(axe["users"][0]["win_rate"], 100.0)
        self.assertEqual(axe["users"][0]["avatar"], "https://avatars.steamstatic.com/example.jpg")
        # 玩家0 只有 2 场、路人只有 1 场，都未达到人柱力的 3 场门槛
        self.assertIsNone(axe["mainstay"])

    def test_mainstay_requires_three_games(self):
        ms = [pub_match(str(i), "radiant", HEROES) for i in range(4)]
        ms[2]["players"][0]["id"] = "other"
        ms[2]["players"][0]["name"] = "路人"
        three = next(h for h in hero_stats.summarize(ms[:3])["heroes"] if h["key"] == "axe")
        # 玩家0 两场全胜、路人一场全胜，但都不能凭低样本当选
        self.assertIsNone(three["mainstay"])
        four = next(h for h in hero_stats.summarize(ms)["heroes"] if h["key"] == "axe")
        self.assertEqual(four["mainstay"]["name"], "玩家0")
        self.assertEqual(four["mainstay"]["games"], 3)
        self.assertEqual(four["mainstay"]["win_rate"], 100.0)

    def test_mainstay_requires_win_rate_strictly_above_fifty(self):
        ms = [pub_match(str(i), "radiant" if i % 2 == 0 else "dire", HEROES) for i in range(4)]
        axe = next(h for h in hero_stats.summarize(ms)["heroes"] if h["key"] == "axe")
        self.assertEqual(axe["mainstay"], None)  # 4 场 2 胜，正好 50% 也不入选
        ms[1]["winner"] = "radiant"
        axe = next(h for h in hero_stats.summarize(ms)["heroes"] if h["key"] == "axe")
        self.assertEqual(axe["mainstay"]["name"], "玩家0")
        self.assertEqual(axe["mainstay"]["win_rate"], 75.0)

    def test_counter_lists_need_three_games_and_are_mirrored(self):
        two = hero_stats.summarize([pub_match(str(i), "radiant", HEROES) for i in range(2)])["heroes"]
        self.assertEqual(next(h for h in two if h["key"] == "axe")["counters"], [])
        three = hero_stats.summarize([pub_match(str(i), "radiant", HEROES) for i in range(3)])["heroes"]
        axe = next(h for h in three if h["key"] == "axe")
        zeus = next(h for h in three if h["key"] == "zeus")
        axe_vs_zeus = next(r for r in axe["counters"] if r["key"] == "zeus")
        zeus_vs_axe = next(r for r in zeus["countered_by"] if r["key"] == "axe")
        self.assertEqual((axe_vs_zeus["games"], axe_vs_zeus["wins"]), (3, 3))
        self.assertEqual((zeus_vs_axe["games"], zeus_vs_axe["losses"]), (3, 3))

    def test_counter_lists_exclude_balanced_four_game_matchup(self):
        ms = [pub_match(str(i), "radiant" if i % 2 == 0 else "dire", HEROES) for i in range(4)]
        axe = next(h for h in hero_stats.summarize(ms)["heroes"] if h["key"] == "axe")
        self.assertEqual(axe["counters"], [])
        self.assertEqual(axe["countered_by"], [])

    def test_counter_lists_are_capped_at_ten(self):
        ms = []
        for i in range(36):
            heroes = list(HEROES)
            heroes[9] = "enemy%d" % (i % 12)
            ms.append(pub_match(str(i), "radiant", heroes))
        axe = next(h for h in hero_stats.summarize(ms)["heroes"] if h["key"] == "axe")
        self.assertEqual(len(axe["counters"]), 10)
        self.assertTrue(all(r["games"] >= 3 and r["win_rate"] >= 60 for r in axe["counters"]))

    def test_sorted_by_games_then_wins_then_key(self):
        ms = [pub_match("1", "radiant", HEROES), pub_match("2", "radiant", HEROES)]
        ms[1]["players"][0]["hero"] = "zzz"
        order = [h["key"] for h in hero_stats.summarize(ms)["heroes"]]
        self.assertEqual(order[0], "bane")  # 出场 2 且全胜里 key 最小
        self.assertLess(order.index("bane"), order.index("axe"))

    def test_records_are_newest_first_and_empty_input_is_safe(self):
        ms = [pub_match("1", "radiant", HEROES, "2026-11-01 20:00"), pub_match("2", "dire", HEROES, "2026-11-03 20:00")]
        axe = next(h for h in hero_stats.summarize(ms)["heroes"] if h["key"] == "axe")
        self.assertEqual([r["match"] for r in axe["records"]], ["2", "1"])
        self.assertEqual(hero_stats.summarize([]), {"total": 0, "heroes": []})

    def test_page_renders_hero_tab_and_escapes_embedded_data(self):
        m = pub_match("1", "radiant", HEROES)
        m["players"][0]["hero_zh"] = "</script><b>"
        data = hero_stats.summarize([m])
        page = make_web.render_page([], 1, "", "", "", 1, hero_data=data)
        self.assertIn('data-tab="hero"', page)
        self.assertIn('id="pane-hero"', page)
        self.assertIn("谁最爱玩", page)
        self.assertIn("人柱力", page)
        self.assertIn("虚位以待", page)
        self.assertIn("克制榜", page)
        self.assertIn("被克榜", page)
        self.assertNotIn("__HEROES__", page)
        self.assertNotIn("</script><b>", page)  # 英雄名里的脚本结束标记不能破坏页面
        self.assertIn("value=\"3\"", page)      # 最少出场场次默认 3

    def test_load_hero_stats_reads_generated_match_file_and_tolerates_missing(self):
        import tempfile, os
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "matches.js")
            with open(path, "w", encoding="utf-8") as fp:
                fp.write("window.MATCH_DATA = " + json.dumps({"matches": [pub_match("1", "radiant", HEROES)]}) + ";\n")
            self.assertEqual(make_web.load_hero_stats(path)["total"], 1)
            self.assertEqual(make_web.load_hero_stats(os.path.join(d, "none.js")), {"total": 0, "heroes": []})


if __name__ == "__main__":
    unittest.main()
