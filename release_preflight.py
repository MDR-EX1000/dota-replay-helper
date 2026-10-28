"""Offline release-readiness checks. Never logs in, uploads, builds or deploys."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import sys

from local_tools import find_tcb
from player_data import IdentityResolver, metric, steam_id

ROOT = Path(__file__).resolve().parent


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return default


def public_matches(root):
    try:
        text = (Path(root) / "docs/data/matches.js").read_text(encoding="utf-8")
        data = json.loads(text.split("=", 1)[1].strip().rstrip(";"))
        matches = data.get("matches") if isinstance(data, dict) else None
        return matches if isinstance(matches, list) and all(isinstance(m, dict) for m in matches) else None
    except (OSError, ValueError, IndexError, KeyError, TypeError):
        return None


def dataset_report(root=ROOT, data_root=None):
    root, data_root = Path(root), Path(data_root or root)
    folder = data_root / "json"
    matches, invalid, notes = [], [], []
    aliases = read_json(root / "aliases.json", {})
    legacy = read_json(root / "legacy_identities.json", {})
    aliases = aliases if isinstance(aliases, dict) else {}
    legacy = legacy if isinstance(legacy, dict) else {}
    for path in sorted(folder.glob("match_*.json")):
        filename = re.fullmatch(r"match_(\d+)\.json", path.name)
        if not filename:
            continue
        data = read_json(path)
        error = None
        if not isinstance(data, dict):
            error = "无效 JSON"
        elif str(data.get("match_id")) != filename.group(1):
            error = "文件名与比赛 ID 不一致"
        elif not isinstance(data.get("players"), list) or len(data["players"]) != 10 or any(not isinstance(p, dict) for p in data["players"]):
            error = "需 10 条有效玩家记录"
        elif metric(data, "duration") is None or data["duration"] <= 0:
            error = "时长无效"
        elif any(sum(p.get("team") == team for p in data["players"]) != 5 for team in ("radiant", "dire")):
            error = "需双方各 5 人"
        elif data.get("lobby_type") != 1:
            error = "需完整练习赛数据（lobby_type=1）"
        elif any(not (steam_id(p.get("steamid")) or steam_id(legacy.get(str(p.get("name") or "")))) for p in data["players"]):
            error = "缺少选手数字 ID，需原始 JSON 或人工确认映射"
        if error:
            invalid.append({"file": path.name, "reason": error})
            continue
        resolver = IdentityResolver([data], aliases, legacy)
        keys = [resolver.resolve(p, data, i)[0] for i, p in enumerate(data["players"])]
        if len(set(keys)) != 10:
            invalid.append({"file": path.name, "reason": "存在重复或被错误合并的账号"})
            continue
        if data.get("schema") != 3:
            notes.append({"file": path.name, "reason": "旧解析版本，字段来源需重解析核实"})
        if not isinstance(data.get("radiant_win"), bool):
            notes.append({"file": path.name, "reason": "胜负缺失，将暂停称号评选"})
        matches.append(data)
    published = public_matches(root)
    expected = {str(m.get("id")) for m in published or []}
    index_path = data_root / "state/index.json"
    remote_index = read_json(index_path, {})
    if index_path.exists() and (not isinstance(remote_index, dict) or not isinstance(remote_index.get("ids"), list)):
        invalid.append({"file": "state/index.json", "reason": "交接清单无效，无法核对线上比赛基线"})
    remote_ids = remote_index.get("ids", []) if isinstance(remote_index, dict) else []
    expected.update(str(mid) for mid in (remote_ids if isinstance(remote_ids, list) else []))
    ids = {str(m["match_id"]) for m in matches}
    return {"folder": str(folder.resolve()), "count": len(matches), "ids": sorted(ids),
            "expected_count": len(expected), "missing_ids": sorted(expected - ids),
            "invalid": invalid, "notes": notes, "baseline_readable": published is not None,
            "ready": bool(matches) and not invalid and expected.issubset(ids) and published is not None}


def configured(value):
    text = str(value or "").strip()
    return bool(text) and not any(marker in text.lower() for marker in ("replace", "your_", "xxxx", "待填写"))


def secret_file_present(path):
    try:
        return configured(Path(path).read_text(encoding="utf-8-sig"))
    except OSError:
        return False


def collect(root=ROOT, data_root=None):
    root = Path(root)
    checks = []
    def add(name, status, message, group="local"):
        checks.append({"name": name, "status": status, "message": message, "group": group})
    add("Python", "ok" if sys.version_info >= (3, 8) else "wait", "需要 Python 3.8 或更新版本")
    add("Git", "ok" if shutil.which("git") else "wait", "本机 Git 工具")
    add("Node", "ok" if (root / ".local-tools/node.exe").is_file() or shutil.which("node") else "wait", "用于前端测试和发布 CLI")
    add("CloudBase CLI", "ok" if find_tcb() else "wait", "仅检查工具存在；不会登录或查询云端")
    add("录像解析器", "ok" if (root / "mantatool/parse.exe").is_file() else "wait", "本地 Windows 解析器")
    add("manta 源码", "ok" if (root / "manta/go.mod").is_file() else "wait", "云端构建 Linux 解析器需要")
    assets = ["player_data.py", "match_titles.py", "web_safety.py", "steam_profiles.py", "make_web.py", "make_match_data.py",
              "docs/player_profiles.js", "docs/player_profiles.css", "docs/hero_portraits.json", "docs/item_icons.json"]
    missing = [name for name in assets if not (root / name).is_file()]
    add("功能源码与图片映射", "wait" if missing else "ok", "缺少：" + ", ".join(missing) if missing else "文件齐全")
    bad_configs = [name for name in ("cloudbase.json", "aliases.json", "legacy_identities.json", "mmr.json", "baselines.json")
                   if not isinstance(read_json(root / name), dict)]
    if (root / "roles.json").exists() and not isinstance(read_json(root / "roles.json"), dict):
        bad_configs.append("roles.json")
    add("配置格式", "wait" if bad_configs else "ok", "无效：" + ", ".join(bad_configs) if bad_configs else "JSON 配置可读取；MMR 保持手动")
    steam = read_json(root / "steam.secret.json", {})
    steam = steam if isinstance(steam, dict) else {}
    add("Steam 头像配置", "ok" if configured(os.environ.get("STEAM_WEB_API_KEY") or steam.get("api_key")) else "warn", "不显示 Key，不请求 Steam 接口")
    config = read_json(root / "cloudbase.json", {})
    config = config if isinstance(config, dict) else {}
    add("目标环境", "ok" if config.get("env_id") and config.get("domain") else "wait", "已配置的环境和域名仍需与朋友确认", "handoff")
    add("CloudBase API Key", "ok" if secret_file_present(root / "cloudbase.apikey") else "wait", "等待朋友提供项目实际使用的 Key", "handoff")
    add("上传口令", "ok" if configured(os.environ.get("UPLOAD_CODE")) or secret_file_present(root / "upload_code.txt") else "wait", "等待当前线上口令；构建不会退回默认口令", "handoff")
    data = dataset_report(root, data_root)
    add("正式比赛数据", "ok" if data["ready"] else "wait", "%s 场有效数据，公开/交接基线 %s 场，缺少 %s 场，无效文件 %s 个" %
        (data["count"], data["expected_count"], len(data["missing_ids"]), len(data["invalid"])), "handoff")
    published = public_matches(root)
    html = (root / "docs/index.html").read_text(encoding="utf-8") if (root / "docs/index.html").is_file() else ""
    generated_ids = {str(m.get("id")) for m in published or []}
    formal_ready = data["ready"] and generated_ids == set(data["ids"]) and "player_profiles.js" in html and "profileRoot" in html
    add("正式网页产物", "ok" if formal_ready else "wait", "需用全量数据重新生成 docs/；不使用两场本地预览替代", "handoff")
    local_ready = not any(c["status"] == "wait" and c["group"] == "local" for c in checks)
    return {"local_ready": local_ready, "ready_for_cloud_validation": not any(c["status"] == "wait" for c in checks),
            "cloud_permissions_verified": False, "checks": checks, "dataset": data,
            "notice": "仅本地检查；未联网、未登录、未上传。交接后仍需核验线上最新数据、权限及备份。"}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root", default=str(ROOT))
    ap.add_argument("--local-only", action="store_true", help="exit based on local setup; still list pending handoff items")
    ap.add_argument("--report", default=str(ROOT / "cloudrun_test/release_readiness.json"))
    args = ap.parse_args()
    report = collect(ROOT, args.data_root)
    print("本机准备：" + ("就绪" if report["local_ready"] else "尚未完成"))
    for check in report["checks"]:
        label = {"ok": "OK", "warn": "提示", "wait": "等待"}[check["status"]]
        print("[%s] %s：%s" % (label, check["name"], check["message"]))
    target = Path(args.report)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(report["notice"])
    print("报告：" + str(target))
    ready = report["local_ready"] if args.local_only else report["ready_for_cloud_validation"]
    return 0 if ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
