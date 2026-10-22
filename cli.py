# -*- coding: utf-8 -*-
"""
对黑助手 CLI

用法:
    python cli.py stats                  # 重新生成汇总表
    python cli.py ratings                # 查看评分
    python cli.py web                    # 生成网页并打开
    python cli.py web --serve            # 生成网页并起本地服务器
    python cli.py publish                # 生成网页并起局域网服务器（默认 0.0.0.0:8000）
    python cli.py roll "A" ... "J"       # 规则化 roll
    python cli.py parse path\\to\\x.dem    # 解析重放
"""

import argparse
import datetime
import functools
import http.server
import os
import re
import socket
import socketserver
import subprocess
import sys
import webbrowser

ROOT = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.join(ROOT, "docs")
DEFAULT_PORT = 8000


def run_py(script, extra=None):
    cmd = [sys.executable, os.path.join(ROOT, script)] + (extra or [])
    subprocess.run(cmd, cwd=ROOT, check=True)


def generate():
    """重新生成汇总表和网页。"""
    run_py("stats.py")
    run_py("make_web.py")


def serve(host, port, open_browser=True):
    # 只服务 docs/（网页本体），不暴露 dem、json、脚本等目录
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=DOCS)
    with socketserver.ThreadingTCPServer((host, port), handler) as httpd:
        httpd.daemon_threads = True
        display = "127.0.0.1" if host in ("0.0.0.0", "") else host
        url = f"http://{display}:{port}/index.html"
        print(f"\n网页已发布: {url}")
        if host in ("0.0.0.0", ""):
            try:
                lan = socket.gethostbyname(socket.gethostname())
                print(f"局域网访问: http://{lan}:{port}/index.html")
            except OSError:
                pass
        print("按 Ctrl+C 停止\n")
        if open_browser:
            webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n已停止")


def _git(*args):
    return subprocess.run(["git"] + list(args), cwd=ROOT,
                          text=True, capture_output=True, check=False)


def cmd_deploy(args):
    """生成网页 → 提交 → 推送 → 启用/更新 GitHub Pages。"""
    generate()
    _git("add", "-A")
    if _git("diff", "--cached", "--quiet").returncode != 0:
        msg = args.message or f"更新网页 {datetime.datetime.now():%Y-%m-%d %H:%M}"
        r = _git("commit", "-m", msg)
        if r.returncode != 0:
            print(r.stderr.strip())
            return 1
        print(f"已提交: {msg}")
    else:
        print("页面无变化，跳过提交")

    remote = _git("remote", "get-url", "origin")
    if remote.returncode != 0:
        print("未配置 origin。先运行：")
        print("  git remote add origin git@github.com:用户名/仓库.git")
        return 1

    push = subprocess.run(["git", "push", "-u", "origin", "HEAD:main"], cwd=ROOT)
    if push.returncode != 0:
        return 1

    if subprocess.run(["gh", "auth", "status"], capture_output=True).returncode != 0:
        print("\nGitHub CLI 未登录，先运行：! gh auth login -h github.com")
        print("登录后再执行一次 deploy 即可自动启用 Pages。")
        return 0

    m = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", remote.stdout.strip())
    if not m:
        print("无法解析 origin 地址")
        return 1
    owner, repo = m.group(1), m.group(2)
    body = ["-f", "source[branch]=main", "-f", "source[path]=/docs"]
    r = subprocess.run(["gh", "api", "-X", "POST", f"repos/{owner}/{repo}/pages"] + body,
                       capture_output=True, text=True)
    if r.returncode != 0:
        r = subprocess.run(["gh", "api", "-X", "PUT", f"repos/{owner}/{repo}/pages"] + body,
                           capture_output=True, text=True)
        if r.returncode != 0:
            print("自动启用 Pages 失败，请在仓库 Settings → Pages 选择 main /docs")
            print(r.stderr.strip()[:300])
    print(f"\nPages 地址: https://{owner}.github.io/{repo}/")
    return 0


def cmd_web(args, publish=False):
    generate()
    if publish or args.serve:
        host = "0.0.0.0" if (publish or args.lan) else "127.0.0.1"
        serve(host, args.port, open_browser=not args.no_open)
    elif not args.no_open:
        webbrowser.open(os.path.join(DOCS, "index.html"))


def main():
    p = argparse.ArgumentParser(prog="cli.py", description="Dota 2 对黑助手 CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    w = sub.add_parser("web", help="生成网页（可选启动服务器）")
    w.add_argument("--serve", action="store_true", help="启动本地 HTTP 服务器")
    w.add_argument("--lan", action="store_true", help="服务器监听 0.0.0.0，局域网可访问")
    w.add_argument("--port", type=int, default=DEFAULT_PORT)
    w.add_argument("--no-open", action="store_true", help="不自动打开浏览器")

    pub = sub.add_parser("publish", help="生成网页并启动局域网服务器")
    pub.add_argument("--port", type=int, default=DEFAULT_PORT)
    pub.add_argument("--no-open", action="store_true")

    dep = sub.add_parser("deploy", help="生成并发布到 GitHub Pages")
    dep.add_argument("-m", "--message", default=None, help="提交信息")

    sub.add_parser("stats", help="重新生成汇总表")
    sub.add_parser("ratings", help="查看评分")

    r = sub.add_parser("roll", help="规则化 roll")
    r.add_argument("players", nargs=argparse.REMAINDER)

    pa = sub.add_parser("parse", help="解析重放")
    pa.add_argument("demos", nargs=argparse.REMAINDER)

    args = p.parse_args()

    if args.cmd == "stats":
        run_py("stats.py")
    elif args.cmd == "ratings":
        run_py("balance.py")
    elif args.cmd == "web":
        cmd_web(args)
    elif args.cmd == "publish":
        cmd_web(args, publish=True)
    elif args.cmd == "deploy":
        return cmd_deploy(args)
    elif args.cmd == "roll":
        players = [x for x in args.players if x != "--"]
        run_py("roll.py", players)
    elif args.cmd == "parse":
        demos = [x for x in args.demos if x != "--"]
        if not demos:
            print("用法: python cli.py parse <file.dem> ...")
            return 1
        exe = os.path.join(ROOT, "mantatool", "parse.exe")
        subprocess.run([exe] + demos, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
