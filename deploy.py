# -*- coding: utf-8 -*-
"""
一键发布：生成统计与网页 → 提交 → 推送 → 启用/更新 GitHub Pages。

首次使用:
    gh auth login -h github.com
    git remote add origin git@github.com:用户名/仓库.git
"""

import datetime
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))


def git(*args):
    return subprocess.run(["git"] + list(args), cwd=ROOT,
                          text=True, capture_output=True, check=False)


def generate():
    for script in ("stats.py", "make_web.py"):
        subprocess.run([sys.executable, os.path.join(ROOT, script)],
                       cwd=ROOT, check=True)


def main():
    print("1/4 生成统计与网页…")
    generate()

    print("2/4 提交变更…")
    git("add", "-A")
    if git("diff", "--cached", "--quiet").returncode != 0:
        msg = f"更新网页 {datetime.datetime.now():%Y-%m-%d %H:%M}"
        r = git("commit", "-m", msg)
        if r.returncode != 0:
            print(r.stderr.strip())
            return 1
        print(f"  已提交: {msg}")
    else:
        print("  页面无变化，跳过提交")

    print("3/4 推送到 GitHub…")
    remote = git("remote", "get-url", "origin")
    if remote.returncode != 0:
        print("  未配置 origin，请先运行：")
        print("  git remote add origin git@github.com:用户名/仓库.git")
        return 1
    if subprocess.run(["git", "push", "-u", "origin", "HEAD:main"], cwd=ROOT).returncode != 0:
        print("  推送失败，请检查网络和 GitHub 登录。")
        return 1

    print("4/4 更新 GitHub Pages…")
    if subprocess.run(["gh", "auth", "status"], capture_output=True).returncode != 0:
        print("  gh 未登录，先运行：! gh auth login -h github.com")
        print("  登录后再双击一次本脚本即可自动启用 Pages。")
        return 0

    m = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", remote.stdout.strip())
    if not m:
        print("  无法解析 origin 地址")
        return 1
    owner, repo = m.group(1), m.group(2)
    body = ["-f", "source[branch]=main", "-f", "source[path]=/docs"]
    r = subprocess.run(["gh", "api", "-X", "POST", f"repos/{owner}/{repo}/pages"] + body,
                       capture_output=True, text=True)
    if r.returncode != 0:
        r = subprocess.run(["gh", "api", "-X", "PUT", f"repos/{owner}/{repo}/pages"] + body,
                           capture_output=True, text=True)
        if r.returncode != 0:
            print("  自动启用 Pages 失败，请到仓库 Settings → Pages 选择 main /docs")
            print("  " + r.stderr.strip()[:300])

    print(f"\n发布完成: https://{owner}.github.io/{repo}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
