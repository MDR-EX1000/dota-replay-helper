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
