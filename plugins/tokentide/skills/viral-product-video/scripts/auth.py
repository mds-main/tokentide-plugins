#!/usr/bin/env python3
"""Sign the plugin's scripts in to Tokentide, once, without the user handling a key (stdlib only).

Run by the agent, never by the user. The key is written to the key file with owner-only permissions and
never printed: output shows only its last four characters, its privacy mode and its daily cap.

  auth.py exchange --code ttlink_…   swap the one-time code from the connector's `link_local_scripts` tool
                                      for the scripts' own key (same privacy mode and caps as the connection,
                                      grouped under it: revoking the connection revokes it too)
  auth.py login [--no-browser]       without the connector: sign in with one approval on tokentide.app
                                      (OAuth device flow). Waits up to --wait seconds (default 110), then
  auth.py login --resume             keeps waiting for the same approval (the request lasts 10 minutes)
  auth.py rotate                     replace the key with a new one (same settings); the old one stops at once
  auth.py status                     which key the scripts use (masked) and whether the API accepts it
  auth.py logout [--revoke]          delete the key file (--revoke also ends the key on Tokentide)

Key file: ~/.config/tokentide/api_key ($XDG_CONFIG_HOME/tokentide when set; Windows %APPDATA%\\tokentide\\api_key;
TOKENTIDE_CONFIG_DIR overrides the folder). Endpoints: https://api.tokentide.app/api/plugin/* (the origin of
TOKENTIDE_BASE_URL; TOKENTIDE_SITE_URL overrides it; plain http only for 127.0.0.1, which the self-test uses).
The approval page for `login` is on tokentide.app.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import socket
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

import apiclient as api
import common

PY = api.PY
HERE = Path(__file__).resolve()
CLIENTS = {"claude-code": "Claude Code", "codex": "Codex", "unknown": "Tokentide plugin"}


class LinkError(Exception):
    def __init__(self, status, error, message, body=None):
        super().__init__(message)
        self.status, self.error, self.message, self.body = status, error, message, body or {}


def hostname() -> str:
    """A short name for this machine, shown in the key's name in the dashboard ("Local scripts … · <machine>")."""
    name = (socket.gethostname() or platform.node() or "this computer").split(".")[0]
    return name[:40] or "this computer"


def post(path: str, body: dict, bearer: str | None = None, timeout: int = 30) -> dict:
    url = f"{api.site_url()}{path}"
    if not api.secure_url(url):
        raise SystemExit(f"Refusing to talk to {url} over plain http: the sign-in endpoints carry keys. "
                         "Use an https TOKENTIDE_SITE_URL / TOKENTIDE_BASE_URL.")
    headers = {"Content-Type": "application/json", "Accept": "application/json",
               "User-Agent": "tokentide-video-skill/1.2 (auth.py)"}
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST", headers=headers)
    for attempt in range(3):
        try:
            with common.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as e:
            raw = e.read() or b""
            try:
                j = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                j = {}
            if not isinstance(j, dict):
                j = {}
            raise LinkError(e.code, str(j.get("error") or f"http_{e.code}"),
                            str(j.get("message") or raw[:200].decode("utf-8", "replace") or f"HTTP {e.code}"), j) from None
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            if attempt < 2 and "CERTIFICATE_VERIFY_FAILED" not in str(e):
                time.sleep(2 * (attempt + 1))
                continue
            hint = ("This Python has no CA certificates: set SSL_CERT_FILE to a CA bundle (macOS python.org builds: run "
                    "'Install Certificates.command' in the Python folder)." if "CERTIFICATE_VERIFY_FAILED" in str(e)
                    else f"Is {api.site_url()} reachable from here (sandbox network allowlist)?")
            raise SystemExit(f"Network error talking to {url}: {e}. {hint}") from None
    raise SystemExit("unreachable")


# ---------------------------------------------------------------- the key file
def _restrict_windows(path: Path) -> str | None:
    """Owner-only ACL on Windows (the 0600 equivalent): drop inherited entries, grant only this user."""
    user = os.environ.get("USERNAME")
    if not user:
        return "USERNAME is not set"
    who = f"{os.environ['USERDOMAIN']}\\{user}" if os.environ.get("USERDOMAIN") else user
    try:
        res = subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r", f"{who}:F"],
                             capture_output=True, text=True)
    except OSError as e:
        return str(e)
    return None if res.returncode == 0 else (res.stderr or res.stdout).strip()[:200]


def write_key(key: str, label: str) -> Path:
    """Writes the key to the key file atomically, readable by its owner only (0600 / owner-only ACL)."""
    path = api.key_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        os.chmod(path.parent, 0o700)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("# Tokentide key for the plugin's local scripts. Written by auth.py; never share or commit it.\n"
                    f"# {label}. Rotate: auth.py rotate · end it: auth.py logout --revoke or the dashboard.\n"
                    f"{key}\n")
        if os.name != "nt":
            os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()
    if os.name == "nt":
        problem = _restrict_windows(path)
        if problem:
            common.log(f"warning: could not restrict {path} to your user ({problem}); %APPDATA% is per-user already")
    else:
        os.chmod(path, 0o600)
    return path


def file_mode_ok(path: Path) -> bool:
    if os.name == "nt":
        return True
    try:
        return stat.S_IMODE(path.stat().st_mode) & 0o077 == 0
    except OSError:
        return False


def masked(key: str) -> str:
    return f"…{key[-4:]}" if len(key) >= 8 else "…"


def linked_line(verb: str, out: dict, path: Path) -> str:
    cap = out.get("daily_cap_usd")
    return (f"{verb}: key {masked(str(out.get('key') or ''))}, privacy mode {out.get('privacy_mode')}, "
            f"daily cap {'$' + str(cap) if cap not in (None, '') else 'none (account caps apply)'}"
            f" · stored in {path}")


def env_warning() -> None:
    if os.environ.get("TOKENTIDE_API_KEY"):
        common.log("note: TOKENTIDE_API_KEY is set in this environment and takes precedence over the key file; "
                   "unset it so the scripts use the linked key.")


# ---------------------------------------------------------------- commands
def cmd_exchange(a):
    code = a.code.strip()
    if not code.startswith("ttlink_"):
        raise SystemExit("That is not a link code. Call the connector's `link_local_scripts` tool and pass the "
                         "ttlink_… code it returns.")
    try:
        out = post("/api/plugin/exchange", {"code": code, "hostname": hostname()})
    except LinkError as e:
        if e.error == "invalid_code":
            raise SystemExit("This link code was already used or has expired (codes work once, for 5 minutes). "
                             "Agent: call `link_local_scripts` again and run the new command right away.") from None
        if e.error == "connection_revoked":
            raise SystemExit("The Tokentide connection this code came from was revoked. Agent: ask the user to "
                             f"reconnect the connector ({api.reconnect_hint()}), then call `link_local_scripts` "
                             f"again. Without the connector: {PY} {HERE} login") from None
        if e.error == "rate_limited":
            raise SystemExit("Too many link attempts from this network. Wait ten minutes, then try again.") from None
        raise SystemExit(f"Linking failed ({e.error}): {e.message}") from None
    path = write_key(str(out["key"]), str(out.get("name") or "Local scripts (plugin)"))
    print(linked_line("linked", out, path))
    env_warning()


def _state_file() -> Path:
    return api.config_dir() / "login_pending.json"


def _save_state(state: dict) -> None:
    p = _state_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(state, f)
    if os.name == "nt":
        _restrict_windows(p)


def _clear_state() -> None:
    try:
        _state_file().unlink()
    except OSError:
        pass


def cmd_login(a):
    state = None
    if a.resume:
        try:
            state = json.loads(_state_file().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            state = None
        if not state or time.time() > float(state.get("expires_at", 0)):
            _clear_state()
            raise SystemExit(f"No sign-in is waiting (or it expired). Start a new one: {PY} {HERE} login")
    else:
        client = CLIENTS.get(api.host(), CLIENTS["unknown"])
        start = post("/api/plugin/device", {"client": client, "hostname": hostname()})
        state = {"device_code": start["device_code"], "user_code": start["user_code"],
                 "url": start.get("verification_uri_complete") or start["verification_uri"],
                 "interval": int(start.get("interval") or 5), "expires_at": time.time() + int(start.get("expires_in") or 600)}
        _save_state(state)
        print(f"Approve this sign-in on Tokentide: {state['url']}\n"
              f"Check that the page shows the code {state['user_code']}. (Agent: show the user this link and code; "
              "they approve once, in the browser. Nothing to copy or paste.)", flush=True)
        if not a.no_browser:
            try:
                webbrowser.open(state["url"], new=2)
            except Exception:
                pass
    deadline = min(time.time() + max(10, a.wait), float(state["expires_at"]))
    interval = int(state.get("interval") or 5)
    while time.time() < deadline:
        time.sleep(interval)
        try:
            out = post("/api/plugin/device/token", {"device_code": state["device_code"]})
        except LinkError as e:
            if e.error == "authorization_pending":
                continue
            if e.error == "slow_down":
                interval = int(e.body.get("interval") or interval + 5)
                state["interval"] = interval
                _save_state(state)
                continue
            _clear_state()
            if e.error == "access_denied":
                raise SystemExit("The sign-in was declined on tokentide.app. Nothing was linked.") from None
            if e.error == "expired_token":
                raise SystemExit(f"The sign-in request expired. Start a new one: {PY} {HERE} login") from None
            raise SystemExit(f"Sign-in failed ({e.error}): {e.message}") from None
        _clear_state()
        path = write_key(str(out["key"]), str(out.get("name") or "Local scripts (sign-in)"))
        print(linked_line("linked", out, path))
        env_warning()
        return
    if time.time() >= float(state["expires_at"]):
        _clear_state()
        raise SystemExit(f"The sign-in request expired before it was approved. Start a new one: {PY} {HERE} login")
    print(f"Still waiting for the approval at {state['url']} (code {state['user_code']}). "
          f"Agent: once the user has approved, run: {PY} {HERE} login --resume")
    sys.exit(3)


def _file_key():
    path = api.key_file()
    key = api._read_key_file(path)
    if not key:
        raise SystemExit(api.link_instructions(f"No key file at {path}: nothing to rotate or revoke."))
    return key, path


def cmd_rotate(a):
    key, path = _file_key()
    try:
        out = post("/api/plugin/keys/rotate", {}, bearer=key)
    except LinkError as e:
        if e.status == 401:
            raise SystemExit(api.link_instructions("The key in the key file is no longer valid, so it cannot be "
                                                   "rotated; link a new one.")) from None
        raise SystemExit(f"Rotation failed ({e.error}): {e.message}") from None
    path = write_key(str(out["key"]), str(out.get("name") or "Local scripts"))
    print(linked_line("rotated", out, path) + " · the old key stopped working")
    env_warning()


def cmd_status(a):
    key, src = api.key_source()
    if not key:
        print(api.link_instructions("No Tokentide key is linked for the plugin's scripts."))
        sys.exit(1)
    where = src if src and not src.startswith("env") else "the TOKENTIDE_API_KEY environment variable"
    line = f"key {masked(key)} from {where}"
    if src and not src.startswith("env") and not file_mode_ok(Path(src)):
        line += f" · WARNING: {src} is readable by other users; run chmod 600 on it (auth.py writes it that way)"
    if a.offline:
        print(line)
        return
    try:
        acct = api.get("/account", retries=1, timeout=30).json()
    except api.APIError as e:
        print(f"{line} · rejected: {str(e).splitlines()[0]}")
        print("\n".join(str(e).splitlines()[1:]))
        sys.exit(1)
    lim = acct.get("limits") or {}
    print(f"{line} · accepted (account tier {acct.get('tier')}"
          + (f", {lim.get('requests_per_minute_per_key')} req/min" if lim.get("requests_per_minute_per_key") else "") + ")")


def cmd_logout(a):
    path = api.key_file()
    key = api._read_key_file(path)
    if a.revoke and key:
        try:
            post("/api/plugin/keys/revoke", {}, bearer=key)
            print(f"revoked: key {masked(key)} ended on Tokentide")
        except LinkError as e:
            if e.status != 401:
                raise SystemExit(f"Revoking failed ({e.error}): {e.message}. The key file was kept.") from None
            print(f"key {masked(key)} was already ended on Tokentide")
    if path.exists():
        path.unlink()
        print(f"removed {path}")
    else:
        print(f"no key file at {path}")
    _clear_state()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    ex = sub.add_parser("exchange", help="swap a link code from link_local_scripts for the scripts' key")
    ex.add_argument("--code", required=True)
    lo = sub.add_parser("login", help="sign in with one approval in the browser (device flow)")
    lo.add_argument("--no-browser", action="store_true", help="only print the approval link")
    lo.add_argument("--resume", action="store_true", help="keep waiting for the approval started earlier")
    lo.add_argument("--wait", type=int, default=110, help="seconds to wait in this run (default 110)")
    sub.add_parser("rotate", help="replace the key with a new one")
    st = sub.add_parser("status", help="show which key is used and whether it works")
    st.add_argument("--offline", action="store_true")
    out = sub.add_parser("logout", help="delete the key file")
    out.add_argument("--revoke", action="store_true", help="also end the key on Tokentide")
    a = ap.parse_args()
    {"exchange": cmd_exchange, "login": cmd_login, "rotate": cmd_rotate, "status": cmd_status,
     "logout": cmd_logout}[a.cmd](a)


if __name__ == "__main__":
    main()
