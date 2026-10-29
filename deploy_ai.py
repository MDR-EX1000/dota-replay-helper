# -*- coding: utf-8 -*-
"""
一键部署 AI 匹配助手：
1. 从 Claude Code 的 settings.json 读取当前 DeepSeek Key
2. 生成不入库的 cloudbaserc.json
3. 部署 CloudBase HTTP 云函数 roll-ai
4. 写入 ai_endpoint 并重新发布静态网页

用法: python deploy_ai.py
"""

import json
import os
import re
import shutil
import subprocess
import sys

from local_tools import find_tcb

ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(ROOT, "cloudbase.json")
BASERC = os.path.join(ROOT, "cloudbaserc.json")
FUNCTION_NAME = "roll-ai"
ROUTE_PATH = "/api/roll-ai"


def load_key():
    key = os.environ.get("DEEPSEEK_API_KEY")
    if key:
        return key.strip()
    settings = os.path.expanduser("~/.claude/settings.json")
    try:
        with open(settings, encoding="utf-8") as fp:
            env = json.load(fp).get("env", {})
        return (env.get("ANTHROPIC_AUTH_TOKEN") or "").strip()
    except (OSError, json.JSONDecodeError):
        return ""


def tcb_cmd():
    return find_tcb()


def run(cmd, input_text=None):
    print("$", " ".join(cmd[1:]))
    return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True,
                          encoding="utf-8", errors="replace", input=input_text)


def main():
    if not os.path.isfile(CONFIG):
        print("缺少 cloudbase.json")
        return 1
    with open(CONFIG, encoding="utf-8") as fp:
        conf = json.load(fp)
    env_id = conf.get("env_id")
    if not env_id:
        print("cloudbase.json 缺少 env_id")
        return 1

    tcb = tcb_cmd()
    if not tcb:
        print("未找到 tcb，请先安装 @cloudbase/cli")
        return 1

    key = load_key()
    if not key:
        print("未找到 DeepSeek Key：~/.claude/settings.json 的 env.ANTHROPIC_AUTH_TOKEN")
        print("也可以设置环境变量 DEEPSEEK_API_KEY 后重试")
        return 1

    # 后端配置只写本地，已被 .gitignore 忽略
    with open(BASERC, "w", encoding="utf-8") as fp:
        json.dump({
            "envId": env_id,
            "functionRoot": "./cloudfunctions",
            "functions": [{
                "name": FUNCTION_NAME,
                "runtime": "Nodejs20.19",
                "handler": "index.main",
                "timeout": 30,
                "memorySize": 256,
                "envVariables": {"DEEPSEEK_API_KEY": key},
            }],
        }, fp, ensure_ascii=False, indent=2)

    print("1/4 部署云函数…")
    r = run([tcb, "fn", "deploy", FUNCTION_NAME, "--httpFn",
             "--path", ROUTE_PATH, "-e", env_id, "--force", "--json"])
    if r.returncode != 0 and "is used" in (r.stdout or "") + (r.stderr or ""):
        # 路由已存在时，只更新函数代码，不再创建访问路径
        r = run([tcb, "fn", "deploy", FUNCTION_NAME, "--httpFn",
                 "-e", env_id, "--force", "--json"])
    if r.returncode != 0:
        print((r.stdout or "")[-2000:])
        print((r.stderr or "")[-2000:])
        return 1

    print("2/4 解析访问地址…")
    # HTTP 访问服务的固定域名格式
    endpoint = f"https://{env_id}.service.tcloudbase.com{ROUTE_PATH}"
    print("   端点:", endpoint)

    # 尽力设置路由限频，失败不阻塞
    try:
        payload = json.dumps({
            "domain": "*",
            "routes": [{
                "path": ROUTE_PATH,
                "upstreamResourceType": "WEB_SCF",
                "upstreamResourceName": FUNCTION_NAME,
                "qpsPolicy": {
                    "qpsTotal": 60,
                    "qpsPerClient": {"limitBy": "ClientIP", "limitValue": 6}
                }
            }]
        }, ensure_ascii=False)
        run([tcb, "routes", "edit", "-r", "ap-shanghai", "-e", env_id,
             "--data", payload], input_text="y\n")
    except Exception:
        pass

    print("3/4 更新页面配置…")
    conf["ai_endpoint"] = endpoint
    with open(CONFIG, "w", encoding="utf-8") as fp:
        json.dump(conf, fp, ensure_ascii=False, indent=2)

    print("4/4 重新生成并发布网页…")
    for script in ("make_web.py", "deploy_tcb.py"):
        r = subprocess.run([sys.executable, os.path.join(ROOT, script)], cwd=ROOT)
        if r.returncode != 0:
            print(f"{script} 失败")
            return 1

    print("\nAI 助手部署完成")
    print("访问页面后，Roll 结果底部会出现「交互式匹配改进」")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
