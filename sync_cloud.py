# -*- coding: utf-8 -*-
"""
把网页上传的比赛同步到本地（不发布）。

用法:
    python sync_cloud.py            # 补回缺失比赛，并重建本地 state/
    python sync_cloud.py --quiet    # 供一键脚本调用，失败时静默

说明:
    网页上传的比赛只存在云端 state/；本脚本按比赛 ID 补回 json/，
    不覆盖本地已有的原始 JSON（原始 JSON 含 SteamID，便于本地别名/MMR 匹配）。
    需要先 tcb login，或配置 cloudbase.secret.json。
"""

import argparse
import json
import os
import shutil
import sys

import deploy_tcb
from local_tools import find_tcb

ROOT = os.path.dirname(os.path.abspath(__file__))
JSON_DIR = os.path.join(ROOT, "json")


def local_ids():
    try:
        return {
            name[6:-5] for name in os.listdir(JSON_DIR)
            if name.startswith("match_") and name.endswith(".json")
            and not name.endswith("_raw.json")
        }
    except OSError:
        return set()


def main():
    ap = argparse.ArgumentParser(description="同步网页上传的比赛到本地")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    quiet = args.quiet

    def say(msg):
        if not quiet:
            print(msg)

    config = os.path.join(ROOT, "cloudbase.json")
    if not os.path.isfile(config):
        say("缺少 cloudbase.json")
        return 1
    with open(config, encoding="utf-8") as fp:
        env_id = json.load(fp).get("env_id")
    if not env_id:
        say("cloudbase.json 中缺少 env_id")
        return 1

    tcb = find_tcb()
    if not tcb:
        say("未找到 tcb，请先安装：npm i -g @cloudbase/cli")
        return 1
    if not deploy_tcb.ensure_login(tcb):
        say("CloudBase 未登录：请运行 tcb login，或配置 cloudbase.secret.json")
        return 1

    os.makedirs(JSON_DIR, exist_ok=True)
    before = local_ids()
    deploy_tcb.pull_state(tcb, env_id)
    after = local_ids()
    new_ids = sorted(after - before)

    # 重建本地 state/ 并写入配置哈希，保持与发布链路一致
    count = deploy_tcb.sync_state()

    if new_ids:
        say(f"已补回 {len(new_ids)} 场网页上传的比赛：{', '.join(new_ids)}")
    else:
        say("本地已是最新，没有需要补回的比赛")
    say(f"本地共 {count} 场")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
