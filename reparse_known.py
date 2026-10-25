# -*- coding: utf-8 -*-
"""
安全重解析：只处理已经存在于 json/ 的比赛，不会发现新录像。

用法:
    python reparse_known.py --match-id 9058079357
    python reparse_known.py --all-known
"""

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
JSON_DIR = os.path.join(ROOT, "json")
PARSE_EXE = os.path.join(ROOT, "mantatool", "parse.exe")
DEFAULT_REPLAY = os.path.join(
    r"D:\Program Files (x86)\Steam\steamapps\common\dota 2 beta",
    "game", "dota", "replays",
)


def known_ids():
    ids = []
    for path in glob.glob(os.path.join(JSON_DIR, "match_*.json")):
        if path.endswith("_raw.json"):
            continue
        ids.append(os.path.splitext(os.path.basename(path))[0][6:])
    return sorted(set(ids))


def reparse(match_id, replay_dir):
    dem = os.path.join(replay_dir, f"{match_id}.dem")
    if not os.path.isfile(dem):
        print(f"  [跳过] 找不到 {match_id}.dem")
        return False
    stage = os.path.join(JSON_DIR, ".reparse", match_id)
    shutil.rmtree(stage, ignore_errors=True)
    os.makedirs(stage, exist_ok=True)

    r = subprocess.run([PARSE_EXE, "--out", stage, "--no-raw", dem],
                       cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=300)
    if r.returncode != 0:
        print(f"  [失败] {match_id}: {(r.stderr or r.stdout)[-300:]}")
        return False

    staged = os.path.join(stage, f"match_{match_id}.json")
    try:
        with open(staged, encoding="utf-8") as fp:
            data = json.load(fp)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"  [失败] {match_id}: JSON 无效 {exc}")
        return False

    if (str(data.get("match_id")) != match_id or data.get("schema") != 2
            or data.get("lobby_type") != 1 or len(data.get("players", [])) != 10
            or data.get("duration", 0) <= 0):
        print(f"  [失败] {match_id}: 数据校验不通过")
        return False

    target = os.path.join(JSON_DIR, f"match_{match_id}.json")
    os.replace(staged, target)
    shutil.rmtree(stage, ignore_errors=True)
    print(f"  ✓ {match_id}: kills={len(data.get('kills', []))} "
          f"objectives={len(data.get('objectives', []))} "
          f"purchases={len(data.get('purchases', []))} "
          f"econ={len((data.get('economy') or {}).get('times', []))}")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--match-id", action="append", default=[])
    ap.add_argument("--all-known", action="store_true")
    ap.add_argument("--replay-dir", default=os.environ.get("DOTA_REPLAY_DIR", DEFAULT_REPLAY))
    args = ap.parse_args()

    ids = args.match_id or (known_ids() if args.all_known else [])
    if not ids:
        print("用法: --match-id ID 或 --all-known")
        return 1
    if not os.path.isfile(PARSE_EXE):
        print("parse.exe 不存在，请先重新构建")
        return 1

    ok = 0
    for mid in ids:
        if reparse(mid, args.replay_dir):
            ok += 1
    print(f"\n完成 {ok}/{len(ids)}")
    return 0 if ok == len(ids) else 1


if __name__ == "__main__":
    raise SystemExit(main())
