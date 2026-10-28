"""Refresh public avatar URLs only when replay data changes. Never cache API keys or SteamIDs."""
import hashlib
import json
import os
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from player_data import IdentityResolver, steam_id

ROOT = Path(__file__).resolve().parent
CACHE_NAME = "steam_profiles.json"
CACHE_PATH = ROOT / "state" / CACHE_NAME
SECRET_PATH = ROOT / "steam.secret.json"
API_URL = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/"


def load_key():
    key = os.environ.get("STEAM_WEB_API_KEY", "").strip()
    if key:
        return key
    try:
        data = json.loads(SECRET_PATH.read_text(encoding="utf-8-sig"))
        return str(data.get("api_key") or "").strip()
    except (OSError, ValueError, AttributeError):
        return ""


def safe_avatar_url(value):
    if not isinstance(value, str) or len(value) > 2048:
        return ""
    try:
        url = urllib.parse.urlsplit(value)
        host = (url.hostname or "").lower()
        trusted = host == "steamstatic.com" or host.endswith(".steamstatic.com") or host == "steamcdn-a.akamaihd.net"
        if url.scheme == "https" and trusted and not url.username and not url.password and url.port in (None, 443):
            return value
    except ValueError:
        pass
    return ""


def read_cache(path=None):
    result = {"version": 1, "players": {}, "matches": {}}
    try:
        data = json.loads(Path(path or CACHE_PATH).read_text(encoding="utf-8"))
        for pid, profile in data.get("players", {}).items():
            avatar = safe_avatar_url(profile.get("avatar"))
            if re.fullmatch(r"p_[a-f0-9]{24}", pid) and avatar:
                result["players"][pid] = {"avatar": avatar, "updated_at": float(profile.get("updated_at", 0))}
        for mid, marker in data.get("matches", {}).items():
            if re.fullmatch(r"\d{7,12}", mid) and re.fullmatch(r"[a-f0-9]{64}", str(marker.get("fingerprint", ""))):
                result["matches"][mid] = {"fingerprint": marker["fingerprint"], "updated_at": float(marker.get("updated_at", 0))}
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return result


def write_cache(cache, path=None):
    path = Path(path or CACHE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=str(path.parent),
                                         prefix=".steam_profiles_", suffix=".tmp", delete=False) as fp:
            temporary = fp.name
            json.dump(cache, fp, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        os.replace(temporary, str(path))
    finally:
        if temporary and os.path.isfile(temporary):
            os.unlink(temporary)


def merge_cache(source, destination=None):
    """Keep the most recently refreshed public entry when synchronizing cloud state."""
    incoming, current = read_cache(source), read_cache(destination)
    for section in ("players", "matches"):
        for key, entry in incoming[section].items():
            if entry["updated_at"] >= current[section].get(key, {}).get("updated_at", -1):
                current[section][key] = entry
    write_cache(current, destination)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_summaries(ids, key):
    # Steam supports x-webapi-key; keep the key out of URLs and error messages.
    query = urllib.parse.urlencode({"steamids": ",".join(ids)})
    request = urllib.request.Request(API_URL + "?" + query,
        headers={"x-webapi-key": key, "Accept": "application/json", "User-Agent": "DotaReplayHelper/1"})
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=8) as response:
        body = response.read(1024 * 1024 + 1)
    if len(body) > 1024 * 1024:
        raise ValueError("Steam response too large")
    players = json.loads(body).get("response", {}).get("players")
    if not isinstance(players, list):
        raise ValueError("Steam response missing players")
    return players


def _config(name):
    try:
        return json.loads((ROOT / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def refresh_profiles(matches, cache_path=None, key=None, aliases=None, legacy=None):
    cache = read_cache(cache_path)
    fingerprints = {str(m["match_id"]): hashlib.sha256(json.dumps(m, sort_keys=True,
                        ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest() for m in matches}
    changed = {mid for mid, digest in fingerprints.items() if cache["matches"].get(mid, {}).get("fingerprint") != digest}
    if not changed:
        return {"status": "unchanged", "updated": 0}
    key = load_key() if key is None else key
    if not key:
        return {"status": "no_key", "updated": 0}
    resolver = IdentityResolver(matches, aliases if aliases is not None else _config("aliases.json"),
                                legacy if legacy is not None else _config("legacy_identities.json"))
    latest, affected = {}, set()
    for match in sorted(matches, key=lambda m: (m.get("start_time", 0), str(m["match_id"]))):
        for index, player in enumerate(match.get("players", [])):
            sid = steam_id(player.get("steamid"))
            if not sid:
                continue
            _, pid, _, _ = resolver.describe(player, match, index)
            latest[pid] = sid
            if str(match["match_id"]) in changed:
                affected.add(pid)
    targets = {latest[pid]: pid for pid in affected}
    profiles = {}
    now = time.time()
    try:
        ids = sorted(targets)
        for start in range(0, len(ids), 100):
            for item in fetch_summaries(ids[start:start+100], key):
                sid = str(item.get("steamid", ""))
                avatar = safe_avatar_url(item.get("avatarfull") or item.get("avatarmedium") or item.get("avatar"))
                if sid in targets and avatar:
                    profiles[targets[sid]] = {"avatar": avatar, "updated_at": now}
        cache["players"].update(profiles)
        complete = len(profiles) == len(targets)
        if complete:
            for mid in changed:
                cache["matches"][mid] = {"fingerprint": fingerprints[mid], "updated_at": now}
        # Partial results keep existing avatars; incomplete matches retry on the next generation.
        write_cache(cache, cache_path)
        return {"status": "updated" if complete else "partial", "updated": len(profiles)}
    except urllib.error.HTTPError as error:
        return {"status": "failed", "updated": 0, "http_status": error.code}
    except Exception as error:
        # Do not expose exceptions, request headers, URLs, IDs or the key in upload logs.
        return {"status": "failed", "updated": 0, "error_type": type(error).__name__}


def avatar_for(pid, cache=None):
    cache = read_cache() if cache is None else cache
    return safe_avatar_url(cache.get("players", {}).get(pid, {}).get("avatar"))
