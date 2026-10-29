"""Resolve project-local deployment tools without changing the user's PATH."""
import os
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent


def find_tcb():
    local = ROOT / "tcb.cmd"
    installed = ROOT / ".local-tools" / "cli" / "node_modules" / "@cloudbase" / "cli" / "package.json"
    shim = ROOT / ".local-tools" / "cli" / "node_modules" / ".bin" / "tcb.cmd"
    if local.is_file() and installed.is_file() and shim.is_file() and (ROOT / ".local-tools" / "node.exe").is_file():
        return str(local)
    candidate = shutil.which("tcb")
    # An uninstalled local wrapper is not an available CLI.
    if candidate and Path(candidate).resolve() != local.resolve():
        return candidate
    # Windows: fall back to the global npm shim explicitly.
    appdata = os.environ.get("APPDATA")
    if appdata:
        for name in ("tcb.cmd", "tcb.CMD"):
            path = Path(appdata) / "npm" / name
            if path.is_file():
                return str(path)
    return None
