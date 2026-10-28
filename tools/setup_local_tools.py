"""Install a project-local npm and pinned CloudBase CLI. Never logs in or deploys."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / ".local-tools"
NPM_VERSION = "11.6.2"
TCB_VERSION = "3.8.8"
REGISTRY = "https://registry.npmjs.org"


def metadata(package, version):
    url = REGISTRY + "/" + package.replace("/", "%2f") + "/" + version
    with urllib.request.urlopen(url, timeout=35) as response:
        return json.load(response)


def prepare_npm():
    target = TOOLS / "npm"
    package = target / "package.json"
    if package.is_file() and json.loads(package.read_text(encoding="utf-8"))["version"] == NPM_VERSION:
        return
    data = metadata("npm", NPM_VERSION)
    with urllib.request.urlopen(data["dist"]["tarball"], timeout=60) as response:
        payload = response.read()
    algorithm, expected = data["dist"]["integrity"].split("-", 1)
    actual = base64.b64encode(hashlib.new(algorithm, payload).digest()).decode("ascii")
    if actual != expected:
        raise ValueError("npm archive integrity verification failed")
    target.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        for entry in archive:
            if not entry.name.startswith("package/") or not entry.isfile():
                continue
            path = (target / entry.name[len("package/"):]).resolve()
            if target.resolve() not in path.parents:
                raise ValueError("unsafe npm archive path")
            path.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(entry) as source:
                path.write_bytes(source.read())


def main():
    TOOLS.mkdir(parents=True, exist_ok=True)
    node = TOOLS / "node.exe"
    if not node.is_file():
        source = shutil.which("node")
        if not source:
            print("Node.js not found. Install Node.js with npm, then run this script again.")
            return 1
        shutil.copy2(source, node)
    print("Preparing project-local npm " + NPM_VERSION, flush=True)
    prepare_npm()
    manifest = TOOLS / "cli" / "node_modules" / "@cloudbase" / "cli" / "package.json"
    if not manifest.is_file() or json.loads(manifest.read_text(encoding="utf-8"))["version"] != TCB_VERSION:
        env = dict(os.environ)
        env.update(CI="true", NPM_CONFIG_CACHE=str(TOOLS / "npm-cache"),
                   NPM_CONFIG_UPDATE_NOTIFIER="false", NPM_CONFIG_AUDIT="false", NPM_CONFIG_FUND="false")
        env["PATH"] = str(TOOLS) + os.pathsep + env.get("PATH", "")
        print("Installing project-local CloudBase CLI " + TCB_VERSION, flush=True)
        command = [str(node), str(TOOLS / "npm" / "bin" / "npm-cli.js"), "install", "--prefix", str(TOOLS / "cli"),
                   "@cloudbase/cli@" + TCB_VERSION, "--registry=" + REGISTRY, "--no-audit", "--no-fund", "--progress=false"]
        result = subprocess.run(command, cwd=str(TOOLS), env=env, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=600)
        (TOOLS / "install.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        if result.returncode:
            print("CLI installation failed. See .local-tools/install.log; no cloud operations were performed.")
            print((result.stdout + result.stderr)[-1800:])
            return result.returncode
    data = json.loads(manifest.read_text(encoding="utf-8"))
    entry = data["bin"]["tcb"] if isinstance(data["bin"], dict) else data["bin"]
    version = subprocess.run([str(node), str(manifest.parent / entry), "--version"], cwd=str(TOOLS),
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    print("CloudBase CLI: " + version.stdout.strip())
    if version.returncode:
        print("CLI version check failed; no login or deployment was attempted.")
        return version.returncode
    (TOOLS / "versions.json").write_text(json.dumps({"npm": NPM_VERSION, "cloudbase_cli": TCB_VERSION}, indent=2), encoding="utf-8")
    print("Ready. Use .\\tcb.cmd or .\\npm.cmd from this project. No system PATH changes were made.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
