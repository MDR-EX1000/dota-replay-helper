# -*- coding: utf-8 -*-
"""
一键发布到腾讯云 CloudBase 静态托管。

前置:
    tcb login
    静态网站托管已开通（cloudbase.json 里配置 env_id）

用法: 双击 一键发布到腾讯云.bat，或 python deploy_tcb.py
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

import scan_new
from local_tools import find_tcb
from release_preflight import dataset_report

ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(ROOT, "cloudbase.json")
SECRET = os.path.join(ROOT, "cloudbase.secret.json")
JSON_DIR = os.path.join(ROOT, "json")
STATE_DIR = os.path.join(ROOT, "state")

# 参与页面生成的配置；只同步哈希，不同步内容（其中含 SteamID）
CONFIG_FILES = [
    "aliases.json",
    "legacy_identities.json",
    "roles.json",
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
    h = hashlib.sha256()
    for name in CONFIG_FILES:
        h.update(name.encode("utf-8"))
        path = os.path.join(ROOT, name)
        if os.path.isfile(path):
            with open(path, "rb") as fp:
                h.update(fp.read())
    return h.hexdigest()


def sync_state():
    """把比赛 JSON 原样同步到云端解析服务使用的 state（保留 SteamID）。"""
    profile_path = os.path.join(STATE_DIR, "steam_profiles.json")
    profiles = None
    if os.path.isfile(profile_path):
        with open(profile_path, "rb") as fp:
            profiles = fp.read()
    if os.path.isdir(STATE_DIR):
        shutil.rmtree(STATE_DIR)
    os.makedirs(STATE_DIR)
    if profiles is not None:
        with open(profile_path, "wb") as fp:
            fp.write(profiles)
    ids = []
    for name in sorted(os.listdir(JSON_DIR)):
        if not (name.startswith("match_") and name.endswith(".json")):
            continue
        if name.endswith("_raw.json"):
            continue
        shutil.copy2(os.path.join(JSON_DIR, name), os.path.join(STATE_DIR, name))
        ids.append(name[6:-5])
    index = {
        "ids": sorted(ids),
        "config_hash": config_hash(),
        "updates": {"at": "", "count": len(ids)},
    }
    with open(os.path.join(STATE_DIR, "index.json"), "w", encoding="utf-8") as fp:
        json.dump(index, fp, ensure_ascii=False, indent=2)
    return len(ids)


def remote_index(tcb, env_id):
    """读取云端 state/index.json（用于发布前检查竞态）。"""
    tmp = os.path.join(ROOT, ".state_index.json")
    try:
        r = subprocess.run(
            [tcb, "hosting", "download", "state/index.json", tmp, "-e", env_id],
            cwd=ROOT, capture_output=True, text=True,
        )
        if r.returncode != 0 or not os.path.isfile(tmp):
            return None
        with open(tmp, encoding="utf-8") as fp:
            return json.load(fp)
    except (OSError, json.JSONDecodeError):
        return None
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


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
        profile_path = os.path.join(tmp, "steam_profiles.json")
        if os.path.isfile(profile_path):
            from steam_profiles import merge_cache
            merge_cache(profile_path, os.path.join(STATE_DIR, "steam_profiles.json"))
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
        key_path = os.path.join(ROOT, "cloudbase.apikey")
        try:
            with open(key_path, encoding="utf-8-sig") as fp:
                api_key = fp.read().strip()
            with open(CONFIG, encoding="utf-8-sig") as fp:
                env_id = json.load(fp).get("env_id")
        except (OSError, ValueError, AttributeError):
            api_key, env_id = "", ""
        if api_key and env_id:
            # Do not echo credentials or CLI output into application logs.
            print("使用项目 CloudBase API Key 登录…")
            result = subprocess.run([tcb, "login", "--cloudbase-api-key", api_key, "-e", env_id],
                                    cwd=ROOT, capture_output=True)
            return result.returncode == 0
        return True  # 沿用已有登录状态；预检不会据此声称已验证权限
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

    tcb = find_tcb()
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

    dataset = dataset_report(ROOT)
    if not dataset["ready"]:
        print("正式比赛数据不完整，已停止生成与发布；请先补齐全部原始 JSON 并运行 release_preflight.py")
        return 1

    print("3/4 生成统计与网页…")
    for script in ("stats.py", "make_web.py"):
        subprocess.run([sys.executable, os.path.join(ROOT, script)], cwd=ROOT, check=True)

    print("     同步云端解析状态…")
    count = sync_state()
    print(f"     state 含 {count} 场比赛（完整数据，含 SteamID）")

    data_file = os.path.join(ROOT, "docs", "data", "matches.js")
    if not os.path.isfile(data_file) or os.path.getsize(data_file) < 100:
        print("比赛明细数据未生成，终止发布")
        return 1
    with open(data_file, encoding="utf-8") as fp:
        data_text = fp.read()
    if "steamid" in data_text or re.search(r"7656119\d{10}", data_text):
        print("检测到 SteamID 泄露，终止发布")
        return 1

    remote = remote_index(tcb, env_id)
    if remote:
        local_ids = {
            name[6:-5] for name in os.listdir(JSON_DIR)
            if name.startswith("match_") and name.endswith(".json")
            and not name.endswith("_raw.json")
        }
        missing = [str(i) for i in remote.get("ids", []) if str(i) not in local_ids]
        if missing:
            print(
                "云端有本地还没有的比赛（%s）；可能有网页上传刚完成，"
                "请重新运行发布以补回后再上传" % ", ".join(missing[:5])
            )
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
