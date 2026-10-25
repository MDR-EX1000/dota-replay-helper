# -*- coding: utf-8 -*-
"""
从本地 Dota 2 中文语言文件生成装备/技能中文名映射。

用法:
    python make_name_maps.py
    python make_name_maps.py --all       # 生成所有技能名，而不只是已出现的
"""

import argparse
import glob
import json
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PAK = os.path.join(
    r"D:\Program Files (x86)\Steam\steamapps\common\dota 2 beta",
    "game", "dota", "pak01_dir.vpk",
)
CLEAN = re.compile(r"<[^>]+>|\\n|\%s\d|\%d")


def load_vpk_text(pak_path):
    import vpk
    pak = vpk.VPK(pak_path)
    data = pak.get_file("resource/localization/abilities_schinese.txt").read()
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("utf-16")


def clean(value):
    value = CLEAN.sub(" ", value)
    return re.sub(r"\s+", " ", value).strip()


def parse_items(text):
    pat = re.compile(r'"DOTA_Tooltip_Ability_item_([a-z0-9_]+)"\s+"([^"]*)"')
    out = {}
    for token, value in pat.findall(text):
        if value:
            out[token] = clean(value)
    return out


def parse_abilities(text, observed=None):
    pat = re.compile(r'"DOTA_Tooltip_[Aa]bility_([a-z0-9_]+)"\s+"([^"]*)"')
    out = {}
    for token, value in pat.findall(text):
        if (observed is None or token in observed) and value:
            out[token] = clean(value)
    return out


def observed_abilities():
    names = set()
    for path in glob.glob(os.path.join(ROOT, "json", "match_*.json")):
        if path.endswith("_raw.json"):
            continue
        try:
            with open(path, encoding="utf-8") as fp:
                data = json.load(fp)
        except (OSError, json.JSONDecodeError):
            continue
        for p in data.get("players", []):
            for a in p.get("abilities", []):
                if a.get("name"):
                    names.add(a["name"])
    return names


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pak", default=DEFAULT_PAK)
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    if not os.path.isfile(args.pak):
        print("找不到 Dota VPK:", args.pak)
        return 1

    text = load_vpk_text(args.pak)
    items = parse_items(text)
    with open(os.path.join(ROOT, "item_names_zh.json"), "w", encoding="utf-8") as fp:
        json.dump(items, fp, ensure_ascii=False, indent=2, sort_keys=True)
    print("item_names_zh.json:", len(items))

    names = None if args.all else observed_abilities()
    abilities = parse_abilities(text, names) if (names is None or names) else {}
    if abilities:
        with open(os.path.join(ROOT, "ability_names_zh.json"), "w", encoding="utf-8") as fp:
            json.dump(abilities, fp, ensure_ascii=False, indent=2, sort_keys=True)
        print("ability_names_zh.json:", len(abilities))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
