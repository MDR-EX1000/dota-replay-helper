import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import deploy_tcb
import make_match_data
import make_web
import steam_profiles as steam
from player_data import IdentityResolver
from test_features import match


class SteamProfiles(unittest.TestCase):
    def setUp(self):
        test_root = Path(__file__).resolve().parents[1]/"cloudrun_test"/"profile-tests"
        test_root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=str(test_root))
        self.addCleanup(self.temp.cleanup)
        self.cache = Path(self.temp.name)/"steam_profiles.json"
        self.game = match()

    def response(self, ids, key):
        return [{"steamid": sid, "avatarfull":"https://avatars.steamstatic.com/avatar_full.jpg",
                 "personaname":"not-used-as-the-display-name"} for sid in ids]

    def refresh(self, matches=None, **kwargs):
        return steam.refresh_profiles(matches or [self.game], self.cache, key="test-secret",
                                      aliases={}, legacy={}, **kwargs)

    def test_no_key_never_calls_steam_or_marks_matches_synced(self):
        with patch.object(steam, "fetch_summaries") as fetch:
            result = steam.refresh_profiles([self.game], self.cache, key="")
        self.assertEqual(result["status"], "no_key")
        fetch.assert_not_called()
        self.assertFalse(self.cache.exists())

    def test_rebuilding_same_replays_does_not_refresh_again(self):
        with patch.object(steam, "fetch_summaries", side_effect=self.response) as fetch:
            self.assertEqual(self.refresh()["updated"], 10)
            self.assertEqual(self.refresh()["status"], "unchanged")
        self.assertEqual(fetch.call_count, 1)

    def test_new_replay_refreshes_only_its_participants(self):
        with patch.object(steam, "fetch_summaries", side_effect=self.response):
            self.refresh()
        updated = match("1234567891")
        updated["players"] = copy.deepcopy(updated["players"][:2])
        with patch.object(steam, "fetch_summaries", side_effect=self.response) as fetch:
            result = self.refresh([self.game, updated])
        self.assertEqual(result["updated"], 2)
        self.assertEqual(len(fetch.call_args.args[0]), 2)

    def test_modified_replay_refreshes_even_if_match_id_is_the_same(self):
        with patch.object(steam, "fetch_summaries", side_effect=self.response):
            self.refresh()
        changed = copy.deepcopy(self.game)
        changed["players"][0]["kills"] += 1
        with patch.object(steam, "fetch_summaries", side_effect=self.response) as fetch:
            self.assertEqual(self.refresh([changed])["status"], "updated")
        fetch.assert_called_once()

    def test_failure_keeps_cache_and_does_not_expose_key(self):
        with patch.object(steam, "fetch_summaries", side_effect=self.response):
            self.refresh()
        original = self.cache.read_bytes()
        changed = match("1234567891")
        with patch.object(steam, "fetch_summaries", side_effect=RuntimeError("test-secret")):
            result = self.refresh([self.game, changed])
        self.assertEqual(result["status"], "failed")
        self.assertNotIn("test-secret", str(result))
        self.assertEqual(self.cache.read_bytes(), original)

    def test_partial_response_keeps_existing_avatars_and_retries_later(self):
        with patch.object(steam, "fetch_summaries", side_effect=self.response):
            self.refresh()
        changed = match("1234567891")
        with patch.object(steam, "fetch_summaries", return_value=[]):
            self.assertEqual(self.refresh([changed])["status"], "partial")
        self.assertEqual(len(steam.read_cache(self.cache)["players"]), 10)
        self.assertNotIn("1234567891", steam.read_cache(self.cache)["matches"])
        with patch.object(steam, "fetch_summaries", side_effect=self.response) as fetch:
            self.assertEqual(self.refresh([changed])["status"], "updated")
        fetch.assert_called_once()

    def test_cache_is_public_only_without_ids_keys_or_steam_names(self):
        with patch.object(steam, "fetch_summaries", side_effect=self.response):
            self.refresh()
        text = self.cache.read_text(encoding="utf-8")
        self.assertNotIn("test-secret", text)
        self.assertNotIn("personaname", text)
        for p in self.game["players"]:
            self.assertNotIn(p["steamid"], text)
        self.assertFalse(list(self.cache.parent.glob(".steam_profiles_*.tmp")))

    def test_avatar_urls_are_restricted_to_https_steam_image_hosts(self):
        for url in ("javascript:alert(1)", "https://steamstatic.com.evil.test/a.jpg",
                    "https://steamstatic.com@evil.test/a.jpg", "https://user@avatars.steamstatic.com/a.jpg",
                    "http://avatars.steamstatic.com/a.jpg", "https://avatars.steamstatic.com:8000/a.jpg"):
            self.assertEqual(steam.safe_avatar_url(url), "")
        self.assertTrue(steam.safe_avatar_url("https://avatars.steamstatic.com/a.jpg"))

    def test_api_key_is_a_header_and_not_in_the_request_url(self):
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value.read.return_value = b'{"response":{"players":[]}}'
        with patch.object(steam.urllib.request, "build_opener", return_value=opener):
            steam.fetch_summaries([self.game["players"][0]["steamid"]], "private-key")
        req = opener.open.call_args.args[0]
        self.assertNotIn("private-key", req.full_url)
        self.assertEqual({k.lower():v for k,v in req.header_items()}["x-webapi-key"], "private-key")

    def test_public_avatar_is_attached_using_the_same_identity_as_statistics(self):
        resolver = IdentityResolver([self.game], {})
        pid = resolver.describe(self.game["players"][0], self.game)[1]
        cache = {"players":{pid:{"avatar":"https://avatars.steamstatic.com/a.jpg"}},"matches":{}}
        public = make_match_data.transform_match(self.game, resolver, cache)
        self.assertEqual(public["players"][0]["avatar"], "https://avatars.steamstatic.com/a.jpg")
        self.assertEqual(public["players"][1]["avatar"], "")

    def test_local_state_rebuild_preserves_avatar_cache(self):
        with patch.object(steam, "fetch_summaries", side_effect=self.response):
            self.refresh()
        state = self.cache.parent
        source = state/"json"
        source.mkdir()
        (source/"match_1234567890.json").write_text(json.dumps(self.game), encoding="utf-8")
        before = self.cache.read_bytes()
        # Use a child directory for the rebuilt state so source data cannot be deleted.
        destination = state/"state"
        destination.mkdir()
        target = destination/steam.CACHE_NAME
        target.write_bytes(before)
        with patch.object(deploy_tcb, "STATE_DIR", str(destination)), patch.object(deploy_tcb, "JSON_DIR", str(source)):
            deploy_tcb.sync_state()
        self.assertEqual(target.read_bytes(), before)

    def test_cache_merge_preserves_newer_entry(self):
        pid = "p_"+"a"*24
        incoming = self.cache.parent/"incoming.json"
        steam.write_cache({"players":{pid:{"avatar":"https://avatars.steamstatic.com/new.jpg","updated_at":20}},"matches":{}}, self.cache)
        steam.write_cache({"players":{pid:{"avatar":"https://avatars.steamstatic.com/old.jpg","updated_at":10}},"matches":{}}, incoming)
        steam.merge_cache(incoming, self.cache)
        self.assertTrue(steam.read_cache(self.cache)["players"][pid]["avatar"].endswith("new.jpg"))


if __name__ == "__main__":
    unittest.main()
