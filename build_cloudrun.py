# -*- coding: utf-8 -*-
"""
组装并部署「上传录像」云托管服务。

用法:
    python build_cloudrun.py             # 只组装 cloudrun_build/
    python build_cloudrun.py --deploy    # 组装后提交云端构建部署

数据来源:
    --data-root 指定含 json/ 的仓库目录，默认 C:/Users/admin/Desktop/replay
    比赛 JSON 原样打包（保留 SteamID），镜像和云端 state 都不脱敏。

口令:
    环境变量 UPLOAD_CODE，或本地 upload_code.txt，默认 zgnb。
"""

import argparse
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(ROOT, "cloudrun_build")
DEFAULT_DATA_ROOT = r"C:\Users\admin\Desktop\replay"

APP_FILES = [
    "stats.py",
    "balance.py",
    "make_web.py",
    "make_match_data.py",
    "cloudbase.json",
    "aliases.json",
    "baselines.json",
    "mmr.json",
    "hero_names_zh.json",
    "ability_names_zh.json",
    "item_names_zh.json",
    "item_aliases.json",
    "item_ids.json",
    "item_costs.json",
]

SERVICE_NAME = "dota-upload"
ENV_ID = "unhappy-grouse-d3gsbs7inb2cb10d6"

# 参与页面生成的配置；与 deploy_tcb.py / upload_service/server.js 保持一致
CONFIG_FILES = [
    "aliases.json",
    "baselines.json",
    "mmr.json",
    "hero_names_zh.json",
    "ability_names_zh.json",
    "item_names_zh.json",
    "item_aliases.json",
    "item_ids.json",
    "item_costs.json",
]


def config_hash():
    import hashlib
    h = hashlib.sha256()
    for name in CONFIG_FILES:
        h.update(name.encode("utf-8"))
        path = os.path.join(ROOT, name)
        if os.path.isfile(path):
            with open(path, "rb") as fp:
                h.update(fp.read())
    return h.hexdigest()


def load_api_key():
    path = os.path.join(ROOT, "cloudbase.apikey")
    if not os.path.isfile(path):
        return ""
    with open(path, encoding="utf-8") as fp:
        return fp.read().strip()


def load_upload_code():
    code = os.environ.get("UPLOAD_CODE", "").strip()
    if code:
        return code
    path = os.path.join(ROOT, "upload_code.txt")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fp:
            return fp.read().strip()
    return "zgnb"


def copy(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)


def dir_size(path):
    total = 0
    for base, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(base, f))
            except OSError:
                pass
    return total


def build(data_root):
    if os.path.isdir(BUILD):
        shutil.rmtree(BUILD)
    app = os.path.join(BUILD, "app")
    os.makedirs(app)
    os.makedirs(os.path.join(app, "json"))
    os.makedirs(os.path.join(app, "state"))
    os.makedirs(os.path.join(BUILD, "service"))

    # 1. 代码与配置
    for name in APP_FILES:
        src = os.path.join(ROOT, name)
        if not os.path.isfile(src):
            print(f"[警告] 缺少 {name}，跳过")
            continue
        copy(src, os.path.join(app, name))

    copy(os.path.join(ROOT, "upload_service", "server.js"), os.path.join(BUILD, "service", "server.js"))
    copy(os.path.join(ROOT, "upload_service", "Dockerfile"), os.path.join(BUILD, "Dockerfile"))

    # 2. 网页与前端资源
    shutil.copytree(os.path.join(ROOT, "docs"), os.path.join(app, "docs"))

    # 3. 解析器源码
    shutil.copytree(
        os.path.join(ROOT, "mantatool"),
        os.path.join(app, "mantatool"),
        ignore=shutil.ignore_patterns("*.exe", "*.json", "classes.txt"),
    )
    manta_src = os.path.join(ROOT, "manta")
    if not os.path.isdir(manta_src):
        manta_src = os.path.join(data_root, "manta")
    if not os.path.isdir(manta_src):
        print("找不到 manta 源码（ROOT/manta 或 data_root/manta）")
        return 1
    shutil.copytree(
        manta_src,
        os.path.join(app, "manta"),
        ignore=shutil.ignore_patterns(".git", "*.dem", "testdata"),
    )

    # 4. 比赛数据（去 SteamID），同时作为 state 种子
    json_src = os.path.join(data_root, "json")
    ids = []
    if os.path.isdir(json_src):
        for name in sorted(os.listdir(json_src)):
            if not (name.startswith("match_") and name.endswith(".json")):
                continue
            if name.endswith("_raw.json"):
                continue
            src = os.path.join(json_src, name)
            shutil.copy2(src, os.path.join(app, "json", name))
            shutil.copy2(src, os.path.join(app, "state", name))
            ids.append(name[6:-5])
    else:
        print(f"[警告] {json_src} 不存在，镜像内没有历史比赛")

    index = {
        "ids": sorted(ids),
        "config_hash": config_hash(),
        "updates": {"at": "", "count": len(ids)},
    }
    with open(os.path.join(app, "state", "index.json"), "w", encoding="utf-8") as fp:
        json.dump(index, fp, ensure_ascii=False, indent=2)

    # 5. 密钥（不进 git，只进私有镜像）
    secrets = {
        "envId": ENV_ID,
        "serviceName": SERVICE_NAME,
        "domain": "https://unhappy-grouse-d3gsbs7inb2cb10d6-1514393073.tcloudbaseapp.com/",
        "uploadCode": load_upload_code(),
        "apiKey": load_api_key(),
    }
    with open(os.path.join(app, "secrets.json"), "w", encoding="utf-8") as fp:
        json.dump(secrets, fp, ensure_ascii=False, indent=2)

    if not secrets["apiKey"]:
        print("[警告] 没有 cloudbase.apikey，服务无法自动发布")

    print(f"组装完成: {BUILD}")
    print(f"  比赛 {len(ids)} 场，体积 {dir_size(BUILD) / 1024 / 1024:.1f} MB")
    print(f"  上传口令: {secrets['uploadCode']}")
    return 0


def run_cmd(cmd, **kwargs):
    """Windows 上 tcb 是 .cmd，需要经 cmd /c 执行。"""
    if os.name == "nt":
        cmd = ["cmd", "/c"] + cmd
    return subprocess.run(cmd, cwd=ROOT, **kwargs)


def deploy():
    key_path = os.path.join(ROOT, "cloudbase.apikey")
    if os.path.isfile(key_path):
        with open(key_path, encoding="utf-8") as fp:
            key = fp.read().strip()
        run_cmd(["tcb", "login", "--cloudbase-api-key", key, "-e", ENV_ID], check=False)
    cmd = [
        "tcb", "cloudrun", "deploy",
        "--source", BUILD,
        "-s", SERVICE_NAME,
        "--port", "8080",
        "--open-access-types", "PUBLIC",
        "--min-num", "0",
        "--max-num", "1",
        "--force",
        "--yes",
    ]
    print("提交云端构建…")
    r = run_cmd(cmd)
    if r.returncode != 0:
        print("部署失败，请查看云端构建日志")
        return r.returncode
    print("已提交。用 tcb cloudrun list 查看域名，或打开控制台查看构建日志。")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deploy", action="store_true")
    ap.add_argument("--data-root", default=DEFAULT_DATA_ROOT)
    args = ap.parse_args()
    if not os.path.isdir(os.path.join(ROOT, "docs")):
        print("当前目录不是 replay 仓库（缺少 docs/）")
        return 1
    if args.deploy and not load_api_key():
        print("缺少 cloudbase.apikey，部署后的服务无法自动发布，已中止")
        return 1
    code = build(args.data_root)
    if code or not args.deploy:
        return code
    return deploy()


if __name__ == "__main__":
    raise SystemExit(main())
