import copy
import contextlib
import io
import re
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import build_cloudrun
import deploy_tcb
import release_preflight as preflight
from test_features import match


class ReleasePreflight(unittest.TestCase):
    def setUp(self):
        temp_root = Path(__file__).resolve().parents[1]/"cloudrun_test"/"release-tests"
        temp_root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=str(temp_root))
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/"json").mkdir()
        (self.root/"docs/data").mkdir(parents=True)
        self.game = match()
        self.game["lobby_type"] = 1
        self.game["schema"] = 3
        self.write_game(self.game)
        self.write_public([self.game["match_id"]])
        for name in ("aliases.json", "legacy_identities.json", "mmr.json", "baselines.json"):
            (self.root/name).write_text("{}",encoding="utf-8")

    def write_game(self, game):
        (self.root/"json"/('match_'+str(game["match_id"])+'.json')).write_text(json.dumps(game),encoding="utf-8")

    def write_public(self, ids):
        payload={"matches":[{"id":mid} for mid in ids]}
        (self.root/"docs/data/matches.js").write_text("window.MATCH_DATA = "+json.dumps(payload)+";",encoding="utf-8")

    def test_full_original_dataset_is_accepted(self):
        result=preflight.dataset_report(self.root)
        self.assertTrue(result["ready"])
        self.assertEqual(result["count"],1)

    def test_missing_published_matches_block_partial_release(self):
        self.write_public([self.game["match_id"],"1234567891"])
        result=preflight.dataset_report(self.root)
        self.assertFalse(result["ready"])
        self.assertEqual(result["missing_ids"],["1234567891"])

    def test_validation_subfolders_do_not_count_as_production_data(self):
        path=self.root/"json"/('match_'+self.game["match_id"]+'.json')
        nested=self.root/"json/feature_validation";nested.mkdir()
        path.rename(nested/path.name)
        self.assertEqual(preflight.dataset_report(self.root)["count"],0)

    def test_public_only_records_without_account_ids_are_rejected(self):
        for p in self.game["players"]:p.pop("steamid")
        self.write_game(self.game)
        result=preflight.dataset_report(self.root)
        self.assertFalse(result["ready"])
        self.assertTrue(result["invalid"])

    def test_duplicate_accounts_are_rejected(self):
        self.game["players"][1]["steamid"]=self.game["players"][0]["steamid"]
        self.write_game(self.game)
        self.assertFalse(preflight.dataset_report(self.root)["ready"])

    def test_non_practice_matches_are_rejected(self):
        self.game["lobby_type"]=7;self.write_game(self.game)
        self.assertFalse(preflight.dataset_report(self.root)["ready"])

    def test_malformed_players_are_reported_without_crashing(self):
        self.game["players"]=None;self.write_game(self.game)
        self.assertFalse(preflight.dataset_report(self.root)["ready"])

    def test_handoff_index_is_included_in_required_match_set(self):
        (self.root/"state").mkdir()
        (self.root/"state/index.json").write_text(json.dumps({"ids":["1234567892"]}),encoding="utf-8")
        self.assertIn("1234567892",preflight.dataset_report(self.root)["missing_ids"])

    def test_invalid_handoff_index_blocks_release(self):
        (self.root/"state").mkdir()
        (self.root/"state/index.json").write_text('{"ids":null}',encoding="utf-8")
        self.assertFalse(preflight.dataset_report(self.root)["ready"])

    def test_bad_public_baseline_cannot_be_silently_ignored(self):
        (self.root/"docs/data/matches.js").write_text("not valid JSON",encoding="utf-8")
        self.assertFalse(preflight.dataset_report(self.root)["ready"])

    def test_placeholder_credentials_are_not_accepted(self):
        for value in ("", "YOUR_KEY", "REPLACE_ME", "AKIDxxxxxxxx", "待填写"):
            self.assertFalse(preflight.configured(value))

    def test_report_does_not_include_secret_values_or_run_processes(self):
        (self.root/"cloudbase.apikey").write_text("private-cloud-key",encoding="utf-8")
        (self.root/"upload_code.txt").write_text("private-upload-code",encoding="utf-8")
        (self.root/"steam.secret.json").write_text(json.dumps({"api_key":"private-steam-key"}),encoding="utf-8")
        with patch("subprocess.run",side_effect=AssertionError("must be offline")):
            report=preflight.collect(self.root)
        text=json.dumps(report)
        for secret in ("private-cloud-key","private-upload-code","private-steam-key"):
            self.assertNotIn(secret,text)
        self.assertFalse(report["cloud_permissions_verified"])

    def test_build_stops_before_deleting_previous_package_if_data_incomplete(self):
        folder=self.root/"cloudrun_build";folder.mkdir()
        marker=folder/"keep.txt";marker.write_text("keep",encoding="utf-8")
        self.write_public([self.game["match_id"],"1234567891"])
        with patch.object(build_cloudrun,"ROOT",str(self.root)), patch.object(build_cloudrun,"BUILD",str(folder)):
            self.assertEqual(build_cloudrun.build(str(self.root)),1)
        self.assertTrue(marker.is_file())

    def test_build_requires_explicit_upload_code(self):
        folder=self.root/"cloudrun_build"
        with patch.object(build_cloudrun,"ROOT",str(self.root)), patch.object(build_cloudrun,"BUILD",str(folder)), \
             patch.object(build_cloudrun,"load_upload_code",return_value=""):
            self.assertEqual(build_cloudrun.build(str(self.root)),1)
        self.assertFalse(folder.exists())

    def test_all_publish_config_hashes_include_optional_role_overrides(self):
        self.assertEqual(build_cloudrun.CONFIG_FILES,deploy_tcb.CONFIG_FILES)
        self.assertIn("roles.json",build_cloudrun.CONFIG_FILES)
        source=(Path(__file__).resolve().parents[1]/"upload_service/server.js").read_text(encoding="utf-8")
        section=re.search(r"const CONFIG_FILES = \[(.*?)\];",source,re.S).group(1)
        self.assertEqual(build_cloudrun.CONFIG_FILES,re.findall(r"'([^']+)'",section))

    def test_build_default_uses_this_project_not_another_computer(self):
        self.assertEqual(build_cloudrun.DEFAULT_DATA_ROOT,build_cloudrun.ROOT)

    def test_project_key_login_targets_configured_environment_without_echoing_key(self):
        secret="private-project-key"
        (self.root/"cloudbase.apikey").write_text(secret,encoding="utf-8-sig")
        config=self.root/"cloudbase.json"
        config.write_text(json.dumps({"env_id":"env-local-test"}),encoding="utf-8")
        output=io.StringIO()
        with patch.object(deploy_tcb,"ROOT",str(self.root)), patch.object(deploy_tcb,"CONFIG",str(config)), \
             patch.object(deploy_tcb,"load_secret",return_value=(None,None,None)), \
             patch.object(deploy_tcb.subprocess,"run",return_value=SimpleNamespace(returncode=0)) as run, contextlib.redirect_stdout(output):
            self.assertTrue(deploy_tcb.ensure_login("local-tcb.cmd"))
        args=run.call_args.args[0]
        self.assertEqual(args[-2:],["-e","env-local-test"])
        self.assertIn(secret,args)
        self.assertNotIn(secret,output.getvalue())

    def test_cloudrun_command_always_names_the_target_environment(self):
        with patch.object(build_cloudrun,"ROOT",str(self.root)), patch.object(build_cloudrun,"ENV_ID","env-local-test"), \
             patch.object(build_cloudrun,"find_tcb",return_value="local-tcb.cmd"), \
             patch.object(build_cloudrun,"run_cmd",return_value=SimpleNamespace(returncode=0)) as run, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(build_cloudrun.deploy(),0)
        command=run.call_args.args[0]
        self.assertEqual(command[command.index("-e")+1],"env-local-test")


if __name__ == "__main__":
    unittest.main()
