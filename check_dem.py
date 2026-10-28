# -*- coding: utf-8 -*-
"""
检查本地 dem/ 是否覆盖所有已解析比赛。

用法:
    python check_dem.py                 # 只检查
    python check_dem.py --copy-from-d   # 把 D 盘能找回的缺失录像复制到 dem/

输出:
    - 已解析但没有本地录像的比赛
    - 哪些能在 Dota 客户端重放目录找到
    - dem/ 里是否有未解析或疑似损坏的文件
"""

import argparse
import glob
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
JSON_DIR = os.path.join(ROOT, "json")
DEM_DIR = os.path.join(ROOT, "dem")
DOTA_REPLAY = "D:/Program Files (x86)/Steam/steamapps/common/dota 2 beta/game/dota/replays"
MIN_SIZE = 5 * 1024 * 1024


def parsed_ids():
    ids = set()
    for path in glob.glob(os.path.join(JSON_DIR, "match_*.json")):
        if path.endswith("_raw.json"):
            continue
        ids.add(os.path.basename(path)[6:-5])
    return ids


def dem_ids(directory):
    if not os.path.isdir(directory):
        return set()
    return {
        os.path.basename(p)[:-4]
        for p in glob.glob(os.path.join(directory, "*.dem"))
    }


def bad_demos(directory):
    bad = []
    if not os.path.isdir(directory):
        return bad
    for path in glob.glob(os.path.join(directory, "*.dem")):
        try:
            size = os.path.getsize(path)
            with open(path, "rb") as fp:
                head = fp.read(8)
        except OSError:
            bad.append((os.path.basename(path), "无法读取"))
            continue
        if size < MIN_SIZE:
            bad.append((os.path.basename(path), f"过小 {size} 字节"))
        elif head != b"PBDEMS2\x00":
            bad.append((os.path.basename(path), "文件头不是 PBDEMS2"))
    return bad


def main():
    ap = argparse.ArgumentParser(description="检查 dem/ 录像完整性")
    ap.add_argument("--copy-from-d", action="store_true",
                    help="把 D 盘能找到的缺失录像复制到 dem/（不删除源文件）")
    args = ap.parse_args()

    parsed = parsed_ids()
    local = dem_ids(DEM_DIR)
    remote = dem_ids(DOTA_REPLAY)

    missing = sorted(parsed - local)
    in_d = sorted(set(missing) & remote)
    nowhere = sorted(set(missing) - remote)
    extra = sorted(local - parsed)
    bad = bad_demos(DEM_DIR)

    print(f"已解析比赛 : {len(parsed)}")
    print(f"dem/ 中有  : {len(local)}")
    print(f"缺失       : {len(missing)}")

    if in_d:
        print(f"  D 盘可找回 ({len(in_d)}): {', '.join(in_d)}")
    if nowhere:
        print(f"  哪里都没有 ({len(nowhere)}): {', '.join(nowhere)}")
    if not missing:
        print("  无")

    if extra:
        print(f"dem/ 中未解析 ({len(extra)}): {', '.join(extra)}")
    if bad:
        print("疑似损坏/不完整:")
        for name, reason in bad:
            print(f"  {name}: {reason}")

    if args.copy_from_d and in_d:
        os.makedirs(DEM_DIR, exist_ok=True)
        for mid in in_d:
            src = os.path.join(DOTA_REPLAY, mid + ".dem")
            dst = os.path.join(DEM_DIR, mid + ".dem")
            shutil.copy2(src, dst)
            print(f"  已复制 {mid}.dem")

    return 1 if nowhere else 0


if __name__ == "__main__":
    raise SystemExit(main())
