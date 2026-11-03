"""Dependency-free client for the Tokentide API — a Venice-compatible proxy with tide pricing.

Base URL: https://api.tokentide.app/v1 (production); env TOKENTIDE_BASE_URL overrides it.
Key lookup: env TOKENTIDE_API_KEY, file at TOKENTIDE_API_KEY_FILE, ./.tokentide_api_key, then the key file
  that `auth.py` writes: ~/.config/tokentide/api_key ($XDG_CONFIG_HOME/tokentide when set; Windows
  %APPDATA%\\tokentide\\api_key). Plain key or a TOKENTIDE_API_KEY=... line. Keys start with tt_live_ /
  tt_test_ (test keys only work on preview/staging deployments and return mock output). Venice keys are rejected.
  With no key, scripts print what the agent runs to link one (`auth.py`); the user never pastes a key.
Optional env: TOKENTIDE_LANE=standard|lowtide · TOKENTIDE_MAX_MULTIPLIER=0.6 · TOKENTIDE_IMAGE_RPM=2

Tokentide specifics handled here: 4.5 MB direct request bodies, OpenAI-style error envelope
({"error": {code, message, param, request_id}}), Retry-After on 429/503, no retry on 504,
Idempotency-Key on paid POSTs, per-request charge headers (X-Tokentide-Charge-USD), and a
per-account image request limit (2/min on new accounts).
"""
from __future__ import annotations

import base64
import collections
import json
import mimetypes
import os
import random
import re
import shutil
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

import common

SCRIPTS_DIR = Path(__file__).resolve().parent
PY = "python" if os.name == "nt" else "python3"   # how the instructions below name the interpreter

DEFAULT_BASE = "https://api.tokentide.app/v1"   # production; kept in sync with the plugin's .mcp.json
MAX_BODY = 4_500_000      # Tokentide's direct body limit (Venice allows 25 MB)
SAFE_BODY = 4_300_000
RETRY_STATUS = {429, 500, 502, 503}   # 504 upstream_timeout is not retried blindly
PAID_PREFIXES = ("/image/", "/images/", "/video/queue", "/audio/queue", "/audio/speech", "/audio/transcriptions",
                 "/chat/completions", "/responses", "/embeddings")
QUOTE_PREFIXES = ("/video/quote", "/audio/quote")          # lane headers change the quoted price
SAFE_POSTS = ("/video/quote", "/video/retrieve", "/video/complete", "/audio/quote", "/audio/retrieve",
              "/audio/complete", "/market/quote")          # safe to resend after a network error
_PROJECT_ROOT = None
_LANE = None

HINTS = {
    "invalid_api_key": "Key invalid or revoked. Tokentide keys start with tt_live_ (prod) or tt_test_ (preview/staging only); Venice keys don't work.",
    "insufficient_balance": "Top up the Tokentide balance (or lower the job size).",
    "spend_limit_reached": "A spend cap set in the Tokentide dashboard was reached; raise it or wait for the period to reset.",
    "model_not_allowed": "The key's privacy mode doesn't allow this model. Background removal, most premium image-edit and video models and every music model are Anonymized: create a key with privacy mode 'all' (or 'private_text').",
    "payload_too_large": "Body over 4.5 MB. Use smaller inputs or public URLs for images/video (scripts shrink images automatically).",
    "rate_limited": "A Tokentide limit (the message names it): requests/min, concurrency, image requests/min, quotes/min, "
                    ">8 unfinished video+music jobs, or spend velocity (list-$ of requests started per minute, counted even "
                    "on free use; a request of any size passes while the minute is under the limit, so a large job starts "
                    "at the next minute). "
                    "Scripts wait for Retry-After; `get_account` / doctor show the limits.",
    "price_above_limit": "Current multiplier is above your max multiplier; wait or raise TOKENTIDE_MAX_MULTIPLIER.",
    "cost_above_limit": "Worst-case charge exceeds X-Tokentide-Max-Cost-USD; raise the cap or shrink the job.",
    "epoch_rollover": "Daily reset at 00:00 UTC. Video queue closes ~23:14 UTC, music/SFX ~23:39 UTC; retry after midnight UTC.",
    "capacity_unavailable": "Discounted capacity sold out or sales paused; retry after Retry-After.",
    "upstream_timeout": "Venice didn't answer in time; don't blindly retry paid requests.",
    "duplicate_request": "Same Idempotency-Key already accepted: the first attempt went through but its response was lost (results are not replayed).",
    "lowtide_closed": "Low Tide lane closed; retry later or use the standard lane.",
}
STATUS_HINTS = {400: "Invalid parameter for this model (models.py show <id>).", 401: HINTS["invalid_api_key"],
                402: "Balance or spend cap.", 403: HINTS["model_not_allowed"], 404: "Unknown model/route or expired job.",
                413: HINTS["payload_too_large"], 422: "Content policy: rephrase; avoid real people and third-party brands.",
                429: HINTS["rate_limited"], 503: "Daily reset, sold out or paused.", 504: HINTS["upstream_timeout"]}


class APIError(Exception):
    def __init__(self, status, message, code=None, param=None, request_id=None, body=b"", headers=None, relink=False):
        self.status, self.message, self.code, self.param = status, message, code, param
        self.request_id, self.body, self.headers = request_id, body, headers or {}
        hint = HINTS.get(code or "") or STATUS_HINTS.get(status, "")
        rid = f" (request {request_id})" if request_id else ""
        text = f"HTTP {status} {code or ''}: {message}{rid}" + (f"\n  hint: {hint}" if hint else "")
        if relink:  # a linked key stops working when it, or the connection it was linked through, is revoked
            env = relink == "env TOKENTIDE_API_KEY"
            text += "\n" + link_instructions(
                "The key in TOKENTIDE_API_KEY was rejected. It takes precedence over the key file auth.py writes: "
                "unset it to use a linked key." if env else
                "The scripts' Tokentide key was revoked or is no longer valid (revoking the Tokentide connection "
                "also revokes the scripts key linked through it).")
        super().__init__(text)


VeniceError = APIError  # name kept so shared code paths read the same


def base_url() -> str:
    if os.environ.get("TOKENTIDE_BASE_URL"):
        return os.environ["TOKENTIDE_BASE_URL"].rstrip("/")
    return DEFAULT_BASE


def site_url() -> str:
    """Where the plugin's sign-in endpoints (/api/plugin/*) are called: the API's own origin, which serves them too,
    so a sandbox only has to allow api.tokentide.app. TOKENTIDE_SITE_URL overrides it."""
    if os.environ.get("TOKENTIDE_SITE_URL"):
        return os.environ["TOKENTIDE_SITE_URL"].rstrip("/")
    u = urllib.parse.urlsplit(base_url())
    return f"{u.scheme}://{u.netloc}"


def secure_url(url: str) -> bool:
    """Keys and codes travel over TLS only; plain http is allowed for this machine (the self-test's mock)."""
    u = urllib.parse.urlsplit(url)
    return u.scheme == "https" or (u.scheme == "http" and u.hostname in ("127.0.0.1", "localhost", "::1"))


def config_dir() -> Path:
    """The folder of the key file that auth.py writes (TOKENTIDE_CONFIG_DIR overrides it)."""
    if os.environ.get("TOKENTIDE_CONFIG_DIR"):
        return Path(os.environ["TOKENTIDE_CONFIG_DIR"]).expanduser()
    if os.name == "nt":
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "tokentide"
    if os.environ.get("XDG_CONFIG_HOME"):
        return Path(os.environ["XDG_CONFIG_HOME"]) / "tokentide"
    return Path.home() / ".config" / "tokentide"


def key_file() -> Path:
    return config_dir() / "api_key"


def _read_key_file(c: Path) -> str:
    try:
        if not c.is_file():
            return ""
        for line in c.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line and line.split("=", 1)[0].strip().upper().endswith("TOKENTIDE_API_KEY"):
                line = line.split("=", 1)[1].strip().strip("'\"")
            return line
    except OSError:
        pass
    return ""


def key_source():
    """(key, where it came from) — the first of env TOKENTIDE_API_KEY, TOKENTIDE_API_KEY_FILE,
    ./.tokentide_api_key and the auth.py key file. ("", None) when there is none."""
    key = os.environ.get("TOKENTIDE_API_KEY", "").strip()
    if key:
        return key, "env TOKENTIDE_API_KEY"
    cands = []
    if os.environ.get("TOKENTIDE_API_KEY_FILE"):
        cands.append(Path(os.environ["TOKENTIDE_API_KEY_FILE"]).expanduser())
    legacy = Path.home() / ".config" / "tokentide" / "api_key"
    cands += [Path.cwd() / ".tokentide_api_key", key_file()] + ([legacy] if legacy != key_file() else [])
    for c in cands:
        key = _read_key_file(c)
        if key:
            return key, str(c)
    return "", None


def host() -> str:
    """The agent app running the scripts, for host-specific advice: claude-code, codex or unknown."""
    if os.environ.get("CLAUDECODE") or os.environ.get("CLAUDE_CODE_ENTRYPOINT"):
        return "claude-code"
    if any(k.startswith("CODEX_") for k in os.environ):
        return "codex"
    return "unknown"


def reconnect_hint(h: str | None = None) -> str:
    """How the user signs in to the connector again, for the app the agent runs in (mirrors the connector)."""
    h = h or host()
    if h == "claude-code":
        return ("in the Claude desktop app, open Customize > Connectors (or the Tokentide plugin's Connectors tab) and "
                "choose Connect; in the Claude Code terminal, run /mcp and choose tokentide.")
    if h == "codex":
        return "run `codex mcp login tokentide` (or sign in to Tokentide in the app's plugin settings)."
    return "sign in to Tokentide again, once, in the app's connector or MCP server settings."


def link_instructions(reason: str) -> str:
    """What the agent does when the scripts have no usable key. Written for the agent: the user only
    approves in the browser, at most once, and never copies or pastes a key."""
    auth = SCRIPTS_DIR / "auth.py"
    return (f"{reason}\n"
            "Agent, fix this yourself; never ask the user for a key or to paste one into the chat:\n"
            "  1. If the Tokentide connector's tools are available, call `link_local_scripts` and run the command it "
            f"returns: {PY} {auth} exchange --code <code>\n"
            "     If the connector's tools fail too (the connection was revoked), ask the user to reconnect it: "
            f"{reconnect_hint()} Then call `link_local_scripts` again.\n"
            f"  2. Without the connector, run: {PY} {auth} login  (the user approves once in the browser).\n"
            "Then re-run this command.")


def get_api_key(required: bool = True) -> str:
    key, _ = key_source()
    if not key and required:
        raise SystemExit(link_instructions("No Tokentide key is linked for the plugin's scripts yet."))
    return key


def use_project(root) -> None:
    global _PROJECT_ROOT
    _PROJECT_ROOT = Path(root) if root else None


def set_lane(lane: str | None) -> None:
    """'lowtide' = cheaper best-effort lane (falls back to standard when closed); None/'standard' = default."""
    global _LANE
    _LANE = lane if lane in ("standard", "lowtide") else None


def lane_headers() -> dict:
    lane = _LANE or os.environ.get("TOKENTIDE_LANE")
    h = {}
    if lane == "lowtide":
        h.update({"X-Tokentide-Lane": "lowtide", "X-Tokentide-Lowtide-Fallback": "standard"})
    if os.environ.get("TOKENTIDE_MAX_MULTIPLIER"):
        h["X-Tokentide-Max-Multiplier"] = os.environ["TOKENTIDE_MAX_MULTIPLIER"]
    return h


class Response:
    def __init__(self, status, headers, body):
        self.status, self.headers, self.body = status, headers, body

    @property
    def content_type(self) -> str:
        return self.headers.get("content-type", "").split(";")[0].strip().lower()

    def is_json(self) -> bool:
        return self.content_type.endswith("json") or self.body[:1] in (b"{", b"[")

    def json(self):
        try:
            return json.loads(self.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise APIError(self.status, f"Expected JSON, got {self.content_type or 'unknown'} ({len(self.body)} bytes)") from None

    def _f(self, name):
        try:
            return float(self.headers[name])
        except (KeyError, ValueError):
            return None

    @property
    def charge_usd(self):
        return self._f("x-tokentide-charge-usd")

    @property
    def list_cost_usd(self):
        return self._f("x-tokentide-list-cost-usd")

    @property
    def multiplier(self):
        return self._f("x-tokentide-multiplier")

    @property
    def request_id(self):
        return self.headers.get("x-request-id")

    @property
    def balance(self) -> dict:  # Tokentide sends no balance headers; use account()
        return {}


def _retry_after(headers):
    ra = headers.get("retry-after")
    if ra:
        try:
            return float(ra)
        except ValueError:
            pass
    reset = headers.get("x-ratelimit-reset-requests")
    if reset:
        m = re.fullmatch(r"\s*([\d.]+)\s*(ms|s)?\s*", reset)
        if m:
            v = float(m.group(1))
            return v / 1000 if m.group(2) == "ms" else v
    return None


def _parse_error(body: bytes, headers: dict):
    rid = headers.get("x-request-id")
    try:
        j = json.loads(body.decode("utf-8"))
    except Exception:
        return (body[:600].decode("utf-8", "replace").strip() or "(empty body)"), None, None, rid
    if isinstance(j, dict):
        e = j.get("error")
        if isinstance(e, dict):  # Tokentide (OpenAI-style) envelope
            return (str(e.get("message") or json.dumps(e))[:2000], e.get("code"), e.get("param"),
                    e.get("request_id") or rid)
        issues = j.get("issues") if isinstance(j.get("issues"), list) else []
        param = j.get("param")
        for issue in issues:  # Venice validation errors name the field in `issues` (zod), not in `param`
            if not isinstance(issue, dict) or param:
                continue
            path = issue.get("path") or issue.get("keys") or []
            if isinstance(path, list) and path and isinstance(path[0], str):
                param = path[0]
        for k in ("error", "message", "detail", "details", "issues"):  # Venice passthrough
            if k in j:
                v = j[k]
                msg = v if isinstance(v, str) else json.dumps(v)
                if issues:
                    msg += " " + json.dumps(issues)[:1500]
                return msg[:2000], j.get("code"), param, rid
    return json.dumps(j)[:2000], None, None, rid


def request(method, path, json_body=None, *, data=None, content_type=None, timeout=300, retries=5,
            auth=True, headers=None, max_wait=120) -> Response:
    url = path if path.startswith("http") else f"{base_url()}/{path.lstrip('/')}"
    hdrs = {"User-Agent": "tokentide-video-skill/1.2", "Accept": "*/*"}
    if auth:
        if not secure_url(url):
            raise APIError(0, f"Refusing to send the Tokentide key over plain http ({url.split('?')[0][:80]}). "
                              "Use an https TOKENTIDE_BASE_URL.")
        hdrs["Authorization"] = f"Bearer {get_api_key()}"
    short = path if not path.startswith("http") else re.sub(r"\?.*", "", path)[:80]
    paid = method == "POST" and any(short.startswith(p) for p in PAID_PREFIXES)
    if paid or (method == "POST" and short.startswith(QUOTE_PREFIXES)):
        hdrs.update(lane_headers())
    if paid:
        hdrs.setdefault("Idempotency-Key", uuid.uuid4().hex)
    hdrs.update(headers or {})
    payload = None
    if json_body is not None:
        payload = json.dumps(json_body).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    elif data is not None:
        payload = data
        hdrs["Content-Type"] = content_type or "application/octet-stream"
    if payload is not None and len(payload) > MAX_BODY:
        raise APIError(413, f"request body is {len(payload) / 1e6:.2f} MB; Tokentide accepts at most 4.5 MB",
                       code="payload_too_large")
    idempotent = method in ("GET", "DELETE") or "Idempotency-Key" in hdrs or short.startswith(SAFE_POSTS)
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=payload, method=method, headers=hdrs)
        try:
            with common.urlopen(req, timeout=timeout) as r:
                return Response(r.status, {k.lower(): v for k, v in r.headers.items()}, r.read())
        except urllib.error.HTTPError as e:
            body = e.read() or b""
            h = {k.lower(): v for k, v in (e.headers.items() if e.headers else [])}
            msg, code, param, rid = _parse_error(body, h)
            if e.code in RETRY_STATUS and attempt < retries:
                ra = _retry_after(h)
                if e.code in (500, 502):
                    w = min(30.0, 0.5 * 2 ** attempt) + random.random() * 0.3
                    if "/retrieve" in short:  # Tokentide answers retrieves closer than 2 s apart with 429
                        w = max(w, 2.2)
                elif ra is not None:
                    if ra > max_wait:
                        raise APIError(e.code, f"{msg} (Retry-After {ra:.0f}s is longer than this call waits)",
                                       code, param, rid, body, h) from None
                    w = ra + random.random() * 0.5
                else:
                    w = min(60.0, 2 ** attempt + random.random())
                common.log(f"[tokentide] {method} {short} -> HTTP {e.code} {code or ''}; retry {attempt + 1}/{retries} in {w:.0f}s")
                time.sleep(w)
                continue
            if e.code == 401 and auth:
                raise APIError(401, msg, code or "invalid_api_key", param, rid, body, h,
                               relink=key_source()[1] or True) from None
            raise APIError(e.code, msg, code, param, rid, body, h) from None
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            if idempotent and attempt < retries:
                w = min(30.0, 2 ** attempt + random.random())
                common.log(f"[tokentide] network error on {short}: {e}; retry {attempt + 1}/{retries} in {w:.0f}s")
                time.sleep(w)
                continue
            tls = "CERTIFICATE_VERIFY_FAILED" in str(e)
            raise APIError(0, f"Network error: {e}. " + (
                "This Python has no CA certificates: set SSL_CERT_FILE to a CA bundle (macOS python.org builds: run "
                "'Install Certificates.command' in the Python folder)." if tls else
                f"Is {base_url()} reachable from this sandbox (network allowlist)? Run scripts/doctor.py.")) from None
    raise APIError(0, "unreachable")


def get(path, **kw) -> Response:
    return request("GET", path, **kw)


def post_json(path, body, **kw) -> Response:
    return request("POST", path, json_body=body, **kw)


def post_adaptive(path, body, droppable=(), renames=None, **kw):
    """POST JSON; on a 400 naming an optional field (error.param or message), drop/rename it and retry.
    Returns (response, final_body). Every change is logged."""
    body = dict(body)
    renames = renames or {}
    headers = dict(kw.pop("headers", None) or {})
    for _ in range(len(droppable) + len(renames) + 1):
        try:
            return post_json(path, body, headers=headers, **kw), body
        except APIError as e:
            if e.status != 400:
                raise
            msg = (e.message or "").lower()
            param = (e.param or "").lower()
            if "must be one of" in msg or "case-sensitive" in msg:
                raise  # a value the model doesn't accept: fix the value instead of dropping the field
            changed = False
            for old, new in renames.items():
                if old in body and (param in (old.lower(), new.lower()) or old.lower() in msg or new.lower() in msg):
                    common.log(f"[tokentide] {path}: renaming '{old}' -> '{new}' after 400: {e.message[:120]}")
                    body[new] = body.pop(old)
                    changed = True
            for k in droppable:
                if k in body and (param == k.lower() or k.lower() in msg):
                    common.log(f"[tokentide] {path}: API rejected '{k}' -> retrying without it")
                    body.pop(k)
                    changed = True
            if not changed:
                raise
            if "Idempotency-Key" in headers:  # the rejected attempt wasn't processed; the retry gets a new key
                headers["Idempotency-Key"] = uuid.uuid4().hex
    return post_json(path, body, headers=headers, **kw), body


def multipart(fields: dict, files: dict):
    boundary = "----vpv" + uuid.uuid4().hex
    out = bytearray()
    for name, value in fields.items():
        for v in (value if isinstance(value, (list, tuple)) else [value]):
            if v is None:
                continue
            out += f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
            out += str(v).encode("utf-8") + b"\r\n"
    for name, (filename, content, ctype) in files.items():
        out += (f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                f"Content-Type: {ctype}\r\n\r\n").encode()
        out += content + b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    return bytes(out), f"multipart/form-data; boundary={boundary}"


def post_multipart(path, fields, files, **kw) -> Response:
    data, ctype = multipart(fields, files)
    return request("POST", path, data=data, content_type=ctype, **kw)


# ---------------------------------------------------------------- account, limits, throttling
def account(refresh=False) -> dict:
    """GET /account (balance, tier, limits). Cached per project in logs/account.json for 10 minutes."""
    cache = (_PROJECT_ROOT / "logs" / "account.json") if _PROJECT_ROOT else None
    if cache and cache.is_file() and not refresh and time.time() - cache.stat().st_mtime < 600:
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    data = get("/account", retries=2, timeout=30).json()
    if cache:
        common.save_json(cache, data)
    return data


_LOCK = threading.Lock()
_CALLS = collections.defaultdict(collections.deque)
_RPM = {}


def rpm_for(kind) -> int | None:
    if kind in _RPM:
        return _RPM[kind]
    rpm = None
    if kind == "image":
        env = os.environ.get("TOKENTIDE_IMAGE_RPM")
        if env:
            rpm = int(env)
        else:
            try:
                rpm = int((account().get("limits") or {}).get("image_requests_per_minute") or 0) or None
            except (APIError, SystemExit, ValueError, TypeError):
                rpm = None
            rpm = rpm or 2  # 'new' tier default
    elif kind == "quote":
        rpm = 50  # Tokentide allows 60 quotes/min per account
    _RPM[kind] = rpm
    return rpm


def throttle(kind) -> None:
    """Client-side pacing so batches don't trip Tokentide's per-minute limits."""
    rpm = rpm_for(kind)
    if not rpm:
        return
    with _LOCK:
        q = _CALLS[kind]
        now = time.time()
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= rpm:
            wait = 60.05 - (now - q[0])
            if wait > 0:
                common.log(f"[tokentide] pacing {kind} requests ({rpm}/min limit): waiting {wait:.0f}s")
                time.sleep(wait)
            now = time.time()
            while q and now - q[0] > 60:
                q.popleft()
        q.append(time.time())


def log_call(kind, endpoint, model=None, usd=None, resp=None, **extra) -> None:
    entry = {"kind": kind, "endpoint": endpoint, "model": model}
    if resp is not None and resp.charge_usd is not None:
        entry.update(usd=resp.charge_usd, list_usd=resp.list_cost_usd, multiplier=resp.multiplier,
                     lane=resp.headers.get("x-tokentide-lane"), epoch=resp.headers.get("x-tokentide-epoch"),
                     privacy=resp.headers.get("x-tokentide-model-privacy"), request_id=resp.request_id)
    else:
        entry["usd"] = usd
        if resp is not None:
            entry["request_id"] = resp.request_id
    entry.update({k: v for k, v in extra.items() if v is not None})
    common.ledger_append(_PROJECT_ROOT, entry)


# ---------------------------------------------------------------- media helpers
def sniff(data: bytes):
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png", "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg", "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp", "image/webp"
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "wav", "audio/wav"
    if data[4:8] == b"ftyp":
        return "mp4", "video/mp4"
    if data[:3] == b"ID3" or data[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return "mp3", "audio/mpeg"
    if data[:4] == b"OggS":
        return "ogg", "audio/ogg"
    if data[:4] == b"fLaC":
        return "flac", "audio/flac"
    if data[:4] == b"\x1aE\xdf\xa3":
        return "webm", "video/webm"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif", "image/gif"
    return None, None


def per_image_budget(n_images: int, other_bytes: int = 60_000) -> int:
    """Raw bytes allowed per image so a JSON body with n base64 images stays under ~4.3 MB."""
    return max(150_000, int((SAFE_BODY - other_bytes) / 1.37 / max(1, n_images)))


def _shrink(path, max_side, keep_png, q):
    fd, tmp = tempfile.mkstemp(suffix=".png" if keep_png else ".jpg")
    os.close(fd)
    vf = f"scale='if(gt(iw,ih),min({max_side},iw),-2)':'if(gt(iw,ih),-2,min({max_side},ih))'"
    args = ["-y", "-i", str(path), "-vf", vf, "-frames:v", "1"]
    if not keep_png:
        args += ["-q:v", str(q)]
    common.ffmpeg(args + [tmp])
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data, ("image/png" if keep_png else "image/jpeg")


def encode_image(src, *, mode="base64", max_side=2048, max_bytes=None, keep_png=None) -> str:
    """Local image -> base64 or data URL sized for Tokentide's 4.5 MB body limit; URLs pass through.

    Steps down resolution (and JPEG quality) until the file fits max_bytes. PNG cutouts keep alpha.
    Public http(s) URLs are the way to send large originals (Venice fetches them, up to 25 MB).
    """
    s = str(src)
    if s.startswith(("http://", "https://", "data:")):
        return s
    p = Path(s)
    if not p.is_file():
        common.die(f"Image not found: {p}")
    max_bytes = max_bytes or per_image_budget(1)
    data = p.read_bytes()
    ext, mime = sniff(data)
    keep = keep_png if keep_png is not None else ext == "png"
    info = common.probe(p)
    side = max(info.get("width") or 0, info.get("height") or 0)
    if len(data) > max_bytes or (max_side and side > max_side):
        for ms in [m for m in (max_side or 2048, 1600, 1280, 1024, 800, 640) if m <= (max_side or 2048)]:
            for q in ((2, 4, 6) if not keep else (None,)):
                data, mime = _shrink(p, ms, keep, q or 2)
                if len(data) <= max_bytes:
                    break
            if len(data) <= max_bytes:
                break
        if len(data) > max_bytes:
            common.die(f"{p.name} can't be squeezed under {max_bytes / 1e6:.1f} MB for Tokentide's 4.5 MB body limit. "
                       "Pass a public https URL to the image instead.")
    mime = mime or mimetypes.guess_type(p.name)[0] or "image/png"
    b64 = base64.b64encode(data).decode("ascii")
    return b64 if mode == "base64" else f"data:{mime};base64,{b64}"


def encode_file_data_url(path, max_bytes=None) -> str:
    data = Path(path).read_bytes()
    limit = min(max_bytes or per_image_budget(1), per_image_budget(1))
    if len(data) > limit:
        common.die(f"{Path(path).name} is {len(data) / 1e6:.1f} MB; Tokentide bodies max out at 4.5 MB "
                   "(≈{:.1f} MB of base64 media). Host the file at a public https URL and pass the URL.".format(limit / 1e6))
    mime = sniff(data)[1] or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def extract_media(resp: Response) -> list:
    """[(bytes, ext)] from a binary response or a JSON response holding base64 strings or URLs."""
    if not resp.is_json():
        ext = sniff(resp.body)[0] or (resp.content_type.split("/")[-1] if "/" in resp.content_type else "bin")
        return [(resp.body, ext)]
    j = resp.json()
    items = []
    if isinstance(j, dict):
        for key in ("images", "data", "output", "outputs"):
            if isinstance(j.get(key), list):
                items = j[key]
                break
        else:
            for key in ("image", "b64_json", "audio", "video", "url"):
                if j.get(key):
                    items = [j[key]]
                    break
    out = []
    for it in items:
        if isinstance(it, dict):
            it = it.get("b64_json") or it.get("base64") or it.get("url") or it.get("image")
        if not isinstance(it, str) or not it:
            continue
        if it.startswith("http"):
            data = request("GET", it, auth=False, retries=3).body
        else:
            data = base64.b64decode(it.split(",", 1)[1] if it.startswith("data:") else it)
        out.append((data, sniff(data)[0] or "png"))
    if not out:
        raise APIError(resp.status, f"No media in JSON response: {json.dumps(j)[:400]}")
    return out


def redact(obj):
    if isinstance(obj, dict):
        return {k: redact(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    if isinstance(obj, str) and len(obj) > 300 and (obj.startswith("data:") or re.fullmatch(r"[A-Za-z0-9+/=]+", obj[:300])):
        return f"<{len(obj)} chars base64 omitted>"
    return obj


def write_sidecar(media_path, endpoint, body, resp=None, **extra) -> None:
    meta = {"file": Path(media_path).name, "endpoint": endpoint, "created": common.now_iso(), "api": "tokentide",
            "request": redact(body)}
    if resp is not None:
        meta["request_id"] = resp.request_id
        if resp.charge_usd is not None:
            meta.update(charge_usd=resp.charge_usd, list_cost_usd=resp.list_cost_usd, multiplier=resp.multiplier)
        for h in ("x-venice-is-blurred", "x-venice-is-content-violation", "x-tokentide-model-privacy", "x-tokentide-lane"):
            if h in resp.headers:
                meta[h] = resp.headers[h]
                if h.startswith("x-venice") and str(resp.headers[h]).lower() == "true":
                    common.log(f"WARNING: {Path(media_path).name}: {h}=true — inspect and regenerate if needed")
    meta.update({k: v for k, v in extra.items() if v is not None})
    common.save_json(str(media_path) + ".json", meta)


def has_encoder(name: str) -> bool:
    import subprocess

    b = common.ffmpeg_bin()
    if not b or not shutil.which(b) and not os.path.exists(b):
        return False
    out = subprocess.run([b, "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
    return f" {name} " in out
