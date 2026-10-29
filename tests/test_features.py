import copy
import json
import math
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import balance
import make_match_data
import make_web
import stats
from player_data import IdentityResolver, STEAM_BASE, metric, steam_id
from web_safety import script_json


def match(mid="1234567890"):
    players = []
    for i in range(10):
        players.append(dict(player_id=i, steamid=str(STEAM_BASE+100+i), name="player-%s" % i,
            team="radiant" if i < 5 else "dire", hero="hero%s" % i,
            level=20, kills=i+1, deaths=2, assists=i+2, net_worth=1000+i*100,
            gold_per_min=300, xp_per_min=400, last_hits=100, denies=i+1,
            hero_damage=10000+i*100, hero_damage_taken=5000, tower_damage=100+i,
            hero_healing=0, stuns=0, observer_sentry_wards=2, wards_destroyed=1,
            items=[], abilities=[]))
    return dict(match_id=mid, start_time=1, duration=600, radiant_win=True, players=players,
        kills=[], purchases=[], objectives=[dict(t=100, kind="tower", target="npc_dota_badguys_tower1_top",
            killer="hero4", team="radiant")])


class Features(unittest.TestCase):
    def setUp(self):
        self.patches = [patch.object(stats, "load_aliases", return_value={}),
                        patch.object(balance, "load_aliases", return_value={}),
                        patch.object(stats, "load_legacy_identities", return_value={}),
                        patch.object(stats, "load_role_overrides", return_value={}),
                        patch.object(stats, "MMR", {}), patch.object(make_match_data, "ALIASES", {})]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def test_account_rename_does_not_split(self):
        a, b = match(), match("1234567891")
        b["start_time"] = 2
        b["players"][0]["name"] = "renamed"
        rows = stats.aggregate([a, b])
        self.assertEqual(len(rows), 10)
        self.assertEqual(len(balance.build_ratings([a, b])), 10)
        self.assertEqual(next(r for r in rows if r["玩家"] == "renamed")["场次"], 2)
        self.assertEqual(IdentityResolver([a]).describe(a["players"][0], a)[1],
                         IdentityResolver([b]).describe(b["players"][0], b)[1])

    def test_homonyms_stay_separate_and_display_labels_are_unique(self):
        m = match()
        m["players"][1]["name"] = m["players"][0]["name"]
        rows = stats.aggregate([m])
        self.assertEqual(len(rows), 10)
        self.assertEqual(len({r["玩家"] for r in rows}), 10)
        public, count = make_web.collect_players([m])
        self.assertEqual((len(public), count), (10, 1))
        self.assertEqual(len({p["id"] for p in public}), 10)

    def test_explicit_account_groups_merge_but_nickname_aliases_do_not(self):
        a, b = match(), match("1234567891")
        old = a["players"][0]["steamid"]
        new = str(STEAM_BASE+500)
        b["players"][0]["steamid"] = new
        resolver = IdentityResolver([a, b], {old:"group", new:"group"})
        self.assertEqual(resolver.resolve(a["players"][0], a)[0], resolver.resolve(b["players"][0], b)[0])
        resolver = IdentityResolver([a, b], {"player-0":"nickname-only"})
        self.assertNotEqual(resolver.resolve(a["players"][0], a)[0], resolver.resolve(b["players"][0], b)[0])

    def test_legacy_names_require_explicit_mapping(self):
        a, b = match(), match("1234567891")
        del b["players"][0]["steamid"]
        rows = stats.aggregate([a, b])
        self.assertEqual(len(rows), 11)
        self.assertEqual(sum(r["_identity_status"] == "unresolved" for r in rows), 1)
        resolver = IdentityResolver([a, b], legacy={"player-0":a["players"][0]["steamid"]})
        self.assertEqual(resolver.resolve(a["players"][0], a)[0], resolver.resolve(b["players"][0], b)[0])

    def test_invalid_ids_do_not_merge_anonymous_players(self):
        m = match()
        for p in m["players"]:
            p["steamid"] = "0"
            p["name"] = "same"
        self.assertEqual(len(stats.aggregate([m])), 10)
        self.assertEqual(steam_id("0"), "")

    def test_missing_invalid_and_real_zero_are_distinct(self):
        self.assertEqual(metric({"v":0}, "v"), 0)
        for value in (None, True, -1, math.nan, math.inf, "0"):
            self.assertIsNone(metric({"v":value}, "v"))
        self.assertIsNone(metric({"v":0, "data_quality":{"missing_fields":["v"]}}, "v"))

    def test_incomplete_statistics_use_valid_samples_and_provisional_rating(self):
        a, b = match(), match("1234567891")
        b["players"][0]["gold_per_min"] = None
        row = next(r for r in stats.aggregate([a, b]) if r["玩家"] == "player-0")
        self.assertEqual(row["平均GPM"], 300)
        self.assertEqual(row["_samples"]["gold_per_min"], 1)
        rating = next(p for p in balance.build_ratings([a, b]).values() if p["name"] == "player-0")
        self.assertTrue(rating["provisional"])
        self.assertEqual(rating["rating"], 1000)

    def test_missing_net_worth_does_not_create_false_role_rank(self):
        m = match()
        del m["players"][0]["net_worth"]
        self.assertTrue(all(r["定位"] == "未定" for r in stats.aggregate([m])))

    def test_five_objective_titles_and_single_mvp_per_side(self):
        public = make_match_data.transform_match(match())
        keys = [t["key"] for p in public["players"] for t in p["titles"]]
        self.assertEqual(set(keys), {"wealth", "kills", "towers", "support", "denies"})
        titles = [p["title"] for p in public["players"] if p.get("title")]
        self.assertEqual(sorted(titles), ["MVP", "SVP"])
        self.assertEqual(next(p for p in public["players"] if p["title"] == "MVP")["team"], "radiant")
        self.assertEqual(next(p for p in public["players"] if p["title"] == "SVP")["team"], "dire")

    def test_unknown_result_has_no_score_or_honor(self):
        m = match()
        m["radiant_win"] = None
        public = make_match_data.transform_match(m)
        self.assertIsNone(public["winner"])
        self.assertTrue(all(p["score"] is None for p in public["players"]))
        self.assertFalse(any(p.get("honor") for p in public["players"]))

    def test_tower_and_combined_ward_titles(self):
        m = match()
        for p in m["players"]:
            p["observer_wards_placed"] = 0
            p["sentry_wards_placed"] = 0
        m["players"][0].update(tower_damage=9000, observer_wards_placed=16,
                               sentry_wards_placed=2, wards_destroyed=12)
        m["objectives"] = [dict(kind="tower", killer="hero0", team="radiant")
                           for _ in range(3)]
        public = make_match_data.transform_match(m)
        self.assertIn("敌塔师", public["players"][0]["tags"])
        self.assertIn("光明使者", public["players"][0]["tags"])

    def test_missing_metric_excludes_player_from_rating_but_keeps_others(self):
        m = match()
        del m["players"][0]["hero_damage"]
        public = make_match_data.transform_match(m)
        self.assertIsNone(public["players"][0]["hero_damage"])
        self.assertIsNone(public["players"][0]["score"])
        self.assertEqual(public["players"][0]["title"], "")
        self.assertTrue(any(t["key"] == "wealth" for p in public["players"] for t in p["titles"]))

    def test_missing_winner_kill_prevents_false_kill_title_and_score(self):
        m = match()
        m["players"][0]["kills"] = None
        public = make_match_data.transform_match(m)
        self.assertIsNone(public["score"]["radiant"])
        self.assertIn("kills", {t["key"] for t in public["awards"]["unavailable"]})

    def test_basic_ties_award_both_and_zero_does_not_award(self):
        m = match()
        m["players"][8]["net_worth"] = m["players"][9]["net_worth"]
        for p in m["players"]:
            p["denies"] = 0
        public = make_match_data.transform_match(m)
        self.assertEqual(sum(t["key"] == "wealth" for p in public["players"] for t in p["titles"]), 2)
        self.assertFalse(any(t["key"] == "denies" for p in public["players"] for t in p["titles"]))

    def test_mvp_ties_are_deterministic_without_rounding(self):
        m = match()
        for p in m["players"]:
            p["net_worth"] = 1000
            for key in ("kills", "deaths", "assists", "hero_damage", "tower_damage", "stuns", "hero_healing", "observer_sentry_wards", "wards_destroyed"):
                p[key] = 1
        public = make_match_data.transform_match(m)
        self.assertEqual([p["pid"] for p in public["players"] if p["title"] == "MVP"], [0])
        self.assertEqual([p["pid"] for p in public["players"] if p["title"] == "SVP"], [5])

    def test_summon_tower_attribution_and_creep_exclusion(self):
        m = match()
        m["players"][4]["hero"] = "shadowshaman"
        m["objectives"][0]["killer"] = "npcdotashadowshamanward1"
        m["objectives"].append(dict(kind="tower", killer="npcdotacreepgoodguysmelee", team="radiant"))
        public = make_match_data.transform_match(m)
        self.assertEqual(public["players"][4]["tower_kills"], 1)
        self.assertEqual(sum(p["tower_kills"] for p in public["players"]), 1)

    def test_unknown_tower_owner_suspends_tower_award(self):
        m = match()
        m["objectives"][0]["killer"] = "unknown-summon"
        public = make_match_data.transform_match(m)
        self.assertTrue(all(p["tower_kills"] is None for p in public["players"]))
        self.assertIn("towers", {t["key"] for t in public["awards"]["unavailable"]})

    def test_denied_tower_not_counted(self):
        m = match()
        m["objectives"][0]["denied"] = True
        public = make_match_data.transform_match(m)
        self.assertEqual(sum(p["tower_kills"] for p in public["players"]), 0)

    def test_short_or_unknown_result_match_has_no_titles(self):
        for update in ({"duration":180}, {"radiant_win":None}):
            m = match()
            m.update(update)
            public = make_match_data.transform_match(m)
            self.assertFalse(public["awards"]["eligible"])
            self.assertFalse(any(p["titles"] for p in public["players"]))

    def test_unknown_result_is_not_displayed_as_zero_win_rate(self):
        m = match()
        m["radiant_win"] = None
        players, _ = make_web.collect_players([m])
        self.assertTrue(all(p["winRate"] is None and p["provisional"] for p in players))

    def test_mvp_weights_keep_zero_components_zero(self):
        m = match()
        for p in m["players"]:
            for field in ("kills", "deaths", "assists", "hero_damage", "tower_damage", "hero_healing", "stuns", "observer_sentry_wards", "wards_destroyed"):
                p[field] = 0
        m["players"][0]["kills"] = 100
        m["players"][5]["kills"] = 10
        public = make_match_data.transform_match(m)
        self.assertEqual(public["players"][0]["title_score"], 30)
        self.assertEqual(public["players"][5]["title_score"], 3)

    def test_equal_positive_tower_counts_do_not_award(self):
        m = match()
        m["objectives"] = [dict(kind="tower", killer=p["hero"], team=p["team"]) for p in m["players"]]
        public = make_match_data.transform_match(m)
        self.assertTrue(all(p["tower_kills"] == 1 for p in public["players"]))
        self.assertFalse(any(t["key"] == "towers" for p in public["players"] for t in p["titles"]))

    def test_cli_name_resolution_uses_display_labels(self):
        import roll
        players = balance.build_ratings([match()])
        key = roll.resolve("player-0", players)
        self.assertIsNotNone(key)
        self.assertEqual(players[key]["name"], "player-0")

    def test_safe_serialization_and_nickname_rendering(self):
        name = '\"></script><script>alert(1)</script>&\u2028\u2029'
        encoded = script_json({"name":name})
        self.assertNotIn("<", encoded)
        self.assertNotIn("\u2028", encoded)
        self.assertEqual(json.loads(encoded)["name"], name)
        self.assertNotIn("escJs", make_web.TEMPLATE)
        self.assertNotIn('onchange="toggle', make_web.TEMPLATE)
        self.assertIn("data-player-id", make_web.TEMPLATE)

    def test_template_tokens_in_names_stay_literal(self):
        players = [{"name": '__AI_ENDPOINT__ __TIME__ </script> " &'}]
        html = make_web.render_page(players, 1, "", "", "local", "123")
        self.assertIn("const PLAYERS = " + script_json(players) + ";", html)
        self.assertEqual(len(re.findall(r"<script>(.*?)</script>", html, re.S)), 1)

    def test_public_output_has_no_raw_account_ids(self):
        m = match()
        public = make_match_data.transform_match(m)
        data = script_json(public)
        for player in m["players"]:
            self.assertNotIn(player["steamid"], data)
        self.assertNotIn('"steamid"', data)

    def test_missing_economy_samples_are_not_zero(self):
        m = match()
        m["economy"] = {"times":[0,60], "net_worth":[[None,1000] for _ in range(10)], "xp":[[None,100] for _ in range(10)]}
        public = make_match_data.transform_match(m)
        self.assertEqual(public["economy"]["team"]["radiant"]["gold"], [None,5000])

    def test_empty_input_does_not_overwrite_existing_output(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)/"matches.js"
            target.write_text("keep me", encoding="utf-8")
            with self.assertRaises(ValueError):
                make_match_data.build(temp, str(target))
            self.assertEqual(target.read_text(encoding="utf-8"), "keep me")

    def test_missing_statistics_can_render_local_html(self):
        m = match()
        for field in ("hero_damage", "hero_damage_taken", "net_worth", "gold_per_min", "xp_per_min", "kills"):
            m["players"][0].pop(field)
        with tempfile.TemporaryDirectory() as temp:
            path = str(Path(temp)/"stats.html")
            stats.write_html(stats.aggregate([m]), [m], path)
            self.assertIn("暂无数据", Path(path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
