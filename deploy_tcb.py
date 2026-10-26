# -*- coding: utf-8 -*-
"""
一键发布到腾讯云 CloudBase 静态托管。

前置:
    tcb login
    静态网站托管已开通（cloudbase.json 里配置 env_id）

用法: 双击 一键发布到腾讯云.bat，或 python deploy_tcb.py
"""

import json
import os
import re
import shutil
import subprocess
import sys

import scan_new

ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(ROOT, "cloudbase.json")
SECRET = os.path.join(ROOT, "cloudbase.secret.json")
JSON_DIR = os.path.join(ROOT, "json")
STATE_DIR = os.path.join(ROOT, "state")


def sync_state():
    """把比赛 JSON 脱敏后写成云端解析服务使用的 state（不含 SteamID）。"""
    if os.path.isdir(STATE_DIR):
        shutil.rmtree(STATE_DIR)
    os.makedirs(STATE_DIR)
    ids = []
    for name in sorted(os.listdir(JSON_DIR)):
        if not (name.startswith("match_") and name.endswith(".json")):
            continue
        if name.endswith("_raw.json"):
            continue
        with open(os.path.join(JSON_DIR, name), encoding="utf-8") as fp:
            data = json.load(fp)
        for p in data.get("players", []):
            p.pop("steamid", None)
        data.pop("steamid", None)
        with open(os.path.join(STATE_DIR, name), "w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False)
        ids.append(name[6:-5])
    index = {"ids": sorted(ids), "updates": {"at": "", "count": len(ids)}}
    with open(os.path.join(STATE_DIR, "index.json"), "w", encoding="utf-8") as fp:
        json.dump(index, fp, ensure_ascii=False, indent=2)
    return len(ids)


def pull_state(tcb, env_id):
    """把网页上传、只存在云端的比赛补回本地 json/（不覆盖本地原始文件）。"""
    tmp = os.path.join(ROOT, ".state_pull")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp, exist_ok=True)
    try:
        r = subprocess.run(
            [tcb, "hosting", "download", "state", tmp, "--dir", "-e", env_id],
            cwd=ROOT, capture_output=True, text=True,
        )
        if r.returncode != 0:
            return 0
        added = 0
        for name in os.listdir(tmp):
            if not (name.startswith("match_") and name.endswith(".json")):
                continue
            if name.endswith("_raw.json"):
                continue
            dst = os.path.join(JSON_DIR, name)
            if not os.path.isfile(dst):
                shutil.copy2(os.path.join(tmp, name), dst)
                added += 1
        return added
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def load_secret():
    """优先读环境变量，其次读本地 cloudbase.secret.json（不提交）。"""
    sid = os.environ.get("TENCENTCLOUD_SECRET_ID")
    skey = os.environ.get("TENCENTCLOUD_SECRET_KEY")
    token = os.environ.get("TENCENTCLOUD_TOKEN")
    if sid and skey:
        return sid, skey, token
    if os.path.isfile(SECRET):
        try:
            with open(SECRET, encoding="utf-8") as fp:
                data = json.load(fp)
            return data.get("secret_id"), data.get("secret_key"), data.get("token")
        except (OSError, json.JSONDecodeError):
            pass
    return None, None, None


def ensure_login(tcb):
    """有密钥时自动登录，避免每次手动 tcb login。"""
    sid, skey, token = load_secret()
    if not (sid and skey):
        return True  # 没有密钥，沿用已有登录状态
    cmd = [tcb, "login", "--apiKeyId", sid, "--apiKey", skey]
    if token:
        cmd += ["--token", token]
    print("使用 API 密钥自动登录腾讯云…")
    return subprocess.run(cmd, cwd=ROOT).returncode == 0


def main():
    if not os.path.isfile(CONFIG):
        print("缺少 cloudbase.json（需要 env_id）")
        return 1
    with open(CONFIG, encoding="utf-8") as fp:
        conf = json.load(fp)
    env_id = conf.get("env_id")
    if not env_id:
        print("cloudbase.json 中缺少 env_id")
        return 1

    print("1/4 扫描新录像…")
    try:
        scan_new.scan()
    except Exception as exc:
        print(f"  扫描失败，继续使用现有 JSON: {exc}")

    tcb = shutil.which("tcb")
    if not tcb:
        print("未找到 tcb 命令，请先安装：npm i -g @cloudbase/cli")
        return 1

    if not ensure_login(tcb):
        print("自动登录失败，请检查 cloudbase.secret.json 或先手动 tcb login")
        return 1

    added = pull_state(tcb, env_id)
    if added:
        print(f"2/4 从云端补回 {added} 场网页上传的比赛…")
    else:
        print("2/4 云端没有需要补回的比赛")

    print("3/4 生成统计与网页…")
    for script in ("stats.py", "make_web.py"):
        subprocess.run([sys.executable, os.path.join(ROOT, script)], cwd=ROOT, check=True)

    print("     同步云端解析状态…")
    count = sync_state()
    print(f"     state 含 {count} 场比赛（已脱敏）")

    data_file = os.path.join(ROOT, "docs", "data", "matches.js")
    if not os.path.isfile(data_file) or os.path.getsize(data_file) < 100:
        print("比赛明细数据未生成，终止发布")
        return 1
    with open(data_file, encoding="utf-8") as fp:
        data_text = fp.read()
    if "steamid" in data_text or re.search(r"7656119\d{10}", data_text):
        print("检测到 SteamID 泄露，终止发布")
        return 1

    print("4/4 上传到腾讯云…")
    r = subprocess.run(
        [tcb, "hosting", "deploy", "state", "state", "-e", env_id],
        cwd=ROOT,
    )
    if r.returncode != 0:
        print("上传解析状态失败，请检查 tcb login 是否仍有效")
        return 1

    r = subprocess.run(
        [tcb, "hosting", "deploy", "docs", "-e", env_id,
         "--entry", "index.html", "--verify"],
        cwd=ROOT,
    )
    if r.returncode != 0:
        print("上传失败，请检查 tcb login 是否仍有效")
        return 1

    domain = conf.get("domain", "")
    print("完成")
    if domain:
        print(f"\n访问地址: {domain}")
    else:
        print("\n可用 tcb hosting detail -e <env_id> 查看访问域名")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
