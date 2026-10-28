# -*- coding: utf-8 -*-
"""
扫描 Dota 2 重放目录，解析新增的【练习赛】录像。

由 deploy_tcb.py 在每次发布前调用；也可单独运行：
    python scan_new.py                 # 扫描 dem/ 和 Dota 客户端重放目录
    python scan_new.py --no-d          # 只扫描 dem/
    python scan_new.py --since-days 3
    python scan_new.py --all
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
JSON_DIR = os.path.join(ROOT, "json")
STATE_PATH = os.path.join(ROOT, "scan_state.json")
PARSE_EXE = os.path.join(ROOT, "mantatool", "parse.exe")

DEFAULT_REPLAY = os.path.join(ROOT, "dem")
DOTA_REPLAY = "D:/Program Files (x86)/Steam/steamapps/common/dota 2 beta/game/dota/replays"
MIN_SIZE = 5 * 1024 * 1024


def load_state():
    if not os.path.isfile(STATE_PATH):
        return {"files": {}}
    try:
        with open(STATE_PATH, encoding="utf-8") as fp:
            data = json.load(fp)
        data.setdefault("files", {})
        return data
    except (OSError, json.JSONDecodeError):
        return {"files": {}}


def save_state(state):
    with open(STATE_PATH, "w", encoding="utf-8") as fp:
        json.dump(state, fp, ensure_ascii=False, indent=2)


def is_complete_demo(path):
    try:
        if os.path.getsize(path) < MIN_SIZE:
            return False
        with open(path, "rb") as fp:
            return fp.read(8) == b"PBDEMS2\x00"
    except OSError:
        return False


def remove_outputs(match_id):
    for suffix in (".json", "_raw.json"):
        try:
            os.remove(os.path.join(JSON_DIR, f"match_{match_id}{suffix}"))
        except OSError:
            pass


def parse_one(dem_path):
    match_id = os.path.splitext(os.path.basename(dem_path))[0]
    json_path = os.path.join(JSON_DIR, f"match_{match_id}.json")

    # 已经解析过且结果还在，直接复用，避免重复解析
    if os.path.isfile(json_path):
        try:
            with open(json_path, encoding="utf-8") as fp:
                return json.load(fp), False
        except (OSError, json.JSONDecodeError):
            pass

    try:
        subprocess.run([PARSE_EXE, dem_path], cwd=ROOT, check=True,
                       capture_output=True, text=True, timeout=300)
    except (subprocess.SubprocessError, OSError) as exc:
        print(f"  [失败] 解析异常: {exc}")
        return None, False

    try:
        with open(json_path, encoding="utf-8") as fp:
            return json.load(fp), True
    except (OSError, json.JSONDecodeError):
        return None, False


def default_replay_dirs(include_d=True):
    """默认扫描源：仓库内 dem/ + Dota 客户端重放目录（可用环境变量覆盖）。"""
    env = os.environ.get("DOTA_REPLAY_DIR")
    if env:
        return [p for p in env.split(os.pathsep) if p]
    dirs = [os.path.join(ROOT, "dem")]
    if include_d and os.path.isdir(DOTA_REPLAY):
        dirs.append(DOTA_REPLAY)
    return dirs


def scan(replay_dirs=None, since_days=7, force=False, verbose=True):
    """扫描一个或多个重放目录，解析新增练习赛。

    replay_dirs 为 None 时默认扫描 dem/ 和 Dota 客户端重放目录；
    传入字符串或列表可指定目录。
    """
    if replay_dirs is None:
        replay_dirs = default_replay_dirs()
    elif isinstance(replay_dirs, str):
        replay_dirs = [replay_dirs]
    dirs = [d for d in replay_dirs if d and os.path.isdir(d)]
    if not dirs:
        if verbose:
            print("  未找到可扫描的重放目录")
        return 0

    os.makedirs(JSON_DIR, exist_ok=True)
    state = load_state()
    since_ts = 0 if force else time.time() - since_days * 86400
    processed = set()
    added = 0
    checked = 0

    for replay_dir in dirs:
        if verbose:
            print(f"  扫描目录: {replay_dir}")
        try:
            names = sorted(
                (f for f in os.listdir(replay_dir) if f.lower().endswith(".dem")),
                key=lambda f: os.path.getmtime(os.path.join(replay_dir, f)),
                reverse=True,
            )
        except OSError:
            continue

        for name in names:
            path = os.path.join(replay_dir, name)
            try:
                stat = os.stat(path)
            except OSError:
                continue

            match_id = os.path.splitext(name)[0]
            if match_id in processed:
                continue
            if not force and stat.st_mtime < since_ts:
                continue
            prev = state["files"].get(name)
            if not force and prev and prev.get("size") == stat.st_size and prev.get("mtime") == stat.st_mtime:
                continue
            if not is_complete_demo(path):
                continue

            processed.add(match_id)
            checked += 1
            data, parsed = parse_one(path)
            if not data:
                continue

            lobby = data.get("lobby_type")
            players = len(data.get("players", []))
            duration = data.get("duration", 0)
            if lobby == 1 and players == 10 and duration > 0:
                if parsed:
                    added += 1
                status = "practice"
                if verbose:
                    print(f"  ✓ {name} 练习赛 {duration // 60}:{duration % 60:02d}"
                          + ("（新解析）" if parsed else "（已解析）"))
            else:
                status = "skipped"
                remove_outputs(match_id)
                if verbose:
                    print(f"  - {name} 跳过：lobby_type={lobby}, players={players}, duration={duration}")

            state["files"][name] = {
                "size": stat.st_size,
                "mtime": stat.st_mtime,
                "match_id": match_id,
                "status": status,
                "scanned_at": datetime.now().isoformat(timespec="seconds"),
            }
            save_state(state)

    if verbose:
        print(f"  本次检查 {checked} 个新录像，新增练习赛 {added} 场")
    return added


def main():
    ap = argparse.ArgumentParser(description="扫描并解析新的练习赛录像")
    ap.add_argument("--replay-dir", action="append", default=None,
                    help="可重复；不指定时扫描 dem/ 和 Dota 客户端重放目录")
    ap.add_argument("--no-d", action="store_true", help="只扫描仓库内 dem/")
    ap.add_argument("--since-days", type=int, default=7)
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    if args.replay_dir:
        dirs = args.replay_dir
    elif args.no_d:
        dirs = [os.path.join(ROOT, "dem")]
    else:
        dirs = default_replay_dirs()
    return 0 if scan(dirs, args.since_days, args.all) >= 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
