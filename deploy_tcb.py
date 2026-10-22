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
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(ROOT, "cloudbase.json")
SECRET = os.path.join(ROOT, "cloudbase.secret.json")


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

    print("1/3 生成统计与网页…")
    for script in ("stats.py", "make_web.py"):
        subprocess.run([sys.executable, os.path.join(ROOT, script)], cwd=ROOT, check=True)

    tcb = shutil.which("tcb")
    if not tcb:
        print("未找到 tcb 命令，请先安装：npm i -g @cloudbase/cli")
        return 1

    if not ensure_login(tcb):
        print("自动登录失败，请检查 cloudbase.secret.json 或先手动 tcb login")
        return 1

    print("2/3 上传到腾讯云…")
    r = subprocess.run(
        [tcb, "hosting", "deploy", "docs", "-e", env_id,
         "--entry", "index.html", "--verify"],
        cwd=ROOT,
    )
    if r.returncode != 0:
        print("上传失败，请检查 tcb login 是否仍有效")
        return 1

    domain = conf.get("domain", "")
    print("3/3 完成")
    if domain:
        print(f"\n访问地址: {domain}")
    else:
        print("\n可用 tcb hosting detail -e <env_id> 查看访问域名")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
