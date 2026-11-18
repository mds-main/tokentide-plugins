#!/usr/bin/env python3
"""End-to-end self-test against a local mock of the Tokentide API (no key, no network, no cost).

The mock reproduces Tokentide's documented behaviour: /v1 paths (+ /api/v1 alias), Bearer tt_ keys,
OpenAI-style error envelope, charge headers, a 4.5 MB body limit, Retry-After 429s, video jobs with no
download URL (file returned by retrieve, deleted after delivery unless delete_media_on_completion=false),
/complete taking only queue_id, queued music/SFX, /account, /market, /status, quotes that reject values a
model doesn't list (naming the parameter and the accepted values), and the plugin sign-in endpoints
(/api/plugin/*: link-code exchange, device flow, rotate, revoke) with keys grouped under a connection, so
revoking the connection ends the scripts key. The run starts with no key at all and links one the way an
agent does (`link_local_scripts` → `auth.py exchange`), in a throwaway config folder.

  selftest.py [--keep] [--workdir DIR]
"""
from __future__ import annotations

import argparse
import base64
import datetime as _dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common  # noqa: E402

MEDIA = {}
STATE = {"jobs": {}, "queue_calls": 0, "image_calls": 0, "idem": set(), "spent": 0.0,
         # Sign-in: link codes the connector minted, live keys (key -> its connection), revoked connections,
         # device-flow requests.
         "codes": {}, "keys": {}, "revoked_connections": set(), "devices": {}}


def mint_link_code(connection="conn_1") -> str:
    """What the connector's link_local_scripts tool does: a single-use code bound to the connection."""
    code = "ttlink_" + uuid.uuid4().hex
    STATE["codes"][code] = {"connection": connection, "exp": time.time() + 300}
    return code


def issue_key(connection, origin) -> dict:
    key = "tt_test_" + uuid.uuid4().hex + uuid.uuid4().hex[:8]
    STATE["keys"][key] = {"connection": connection, "origin": origin}
    return {"object": "plugin_key", "key": key, "key_id": uuid.uuid4().hex[:12], "masked": "tt_test_…" + key[-4:],
            "name": "Local scripts (plugin) · Claude Code · selftest", "privacy_mode": "all", "daily_cap_usd": "40",
            "origin": origin}


def revoke_connection(connection="conn_1") -> None:
    """Revoking the connector's key in the dashboard revokes the scripts keys linked through it."""
    STATE["revoked_connections"].add(connection)
    for k in [k for k, v in STATE["keys"].items() if v["connection"] == connection]:
        del STATE["keys"][k]


def reconnect(connection="conn_1") -> None:
    STATE["revoked_connections"].discard(connection)
MULT = {"standard": "0.709522", "lowtide": "0.496665"}


def _ts(d):
    return int(_dt.datetime.fromisoformat(d + "T00:00:00+00:00").timestamp())


def _tt(privacy):
    return {"privacy_tier": privacy, "epoch": _dt.date.today().isoformat(), "price_locked_until": None,
            "standard": {"multiplier": MULT["standard"], "input_per_1m": None, "output_per_1m": None, "per_unit": None, "unit": None},
            "lowtide": {"multiplier": MULT["lowtide"], "open": True, "eligible": True}}


def _vid(mid, created, durs, res, audio=True, end=False, privacy="anonymized", aspects=("9:16", "16:9", "1:1"), name=None):
    return {"id": mid, "type": "video", "created": _ts(created), "tokentide": _tt(privacy),
            "model_spec": {"name": name or mid, "privacy": privacy,
                           "constraints": {"durations": list(durs), "resolutions": list(res),
                                                               "aspect_ratios": list(aspects), "promptCharacterLimit": 4096},
                           "capabilities": {"supportsAudioConfig": audio, "supportsEndImage": end}}}


def _img(mid, created, pricing, inputs=None, privacy="anonymized", name=None):
    caps = {"maxInputImages": inputs} if inputs else {}
    # Like Tokentide's catalog: edit / multi-edit models are Venice type "inpaint", generators "image".
    return {"id": mid, "type": "inpaint" if "edit" in mid else "image", "created": _ts(created), "tokentide": _tt(privacy),
            "model_spec": {"name": name or mid, "privacy": privacy, "pricing": pricing, "capabilities": caps}}


QUOTE_FIELDS = {
    "video": {"model", "duration", "aspect_ratio", "resolution", "upscale_factor", "enhancement_model", "target_fps",
              "slowdown_factor", "audio", "video_url"},
    "audio": {"model", "duration_seconds", "character_count"},
}

MODELS = [
    _vid("veo3.1-full-image-to-video", "2025-10-15", ["4s", "6s", "8s"], ["720p", "1080p", "4k"], name="Veo 3.1 Full Quality"),
    _vid("kling-v3-pro-image-to-video", "2026-02-05", ["5s", "10s", "15s"], ["720p", "1080p"], end=True, name="Kling V3 Pro"),
    _vid("kling-v3-standard-image-to-video", "2026-02-05", ["5s", "10s", "15s"], ["720p", "1080p"], end=True,
         name="Kling V3 Standard"),
    _vid("seedance-2-5-image-to-video-basic", "2026-09-10", [f"{i}s" for i in range(4, 31)], ["480p", "720p", "1080p"],
         end=True, name="Seedance 2.5"),
    _vid("seedance-2-0-fast-image-to-video-basic", "2026-03-01", [f"{i}s" for i in range(4, 16)], ["480p", "720p"],
         name="Seedance 2.0 Fast"),
    _vid("minimax-h3-max-image-to-video", "2026-10-25", ["6s", "10s"], ["768p", "1080p"], privacy="private",
         name="MiniMax H3 Max"),
    _vid("grok-imagine-1-5-image-to-video-private", "2026-07-01", ["6s", "10s"], ["480p", "720p"], audio=False,
         privacy="private", name="Grok Imagine 1.5"),
    _vid("kling-o3-pro-reference-to-video", "2026-03-20", ["5s", "10s", "15s"], ["720p", "1080p"], name="Kling O3 Pro R2V"),
    _img("nano-banana-pro-edit", "2025-11-20", {"resolutions": {"1K": {"usd": 0.18}, "2K": {"usd": 0.23}},
                                                "upscale": {"2x": {"usd": 0.02}, "4x": {"usd": 0.08}}}, 3,
         name="Nano Banana Pro"),
    _img("seedream-v5-pro-edit", "2026-05-01", {"generation": {"usd": 0.06}, "upscale": {"2x": {"usd": 0.02}}}, 3,
         name="Seedream V5 Pro"),
    _img("seedream-v5-pro", "2026-05-01", {"resolutions": {"1K": {"usd": 0.06}, "2K": {"usd": 0.11}}}, name="Seedream V5 Pro"),
    _img("krea-2-turbo", "2026-09-01", {"resolutions": {"1K": {"usd": 0.04}, "2K": {"usd": 0.06}}}, privacy="private",
         name="Krea 2 Turbo"),
    {"id": "tts-kokoro", "type": "tts", "created": _ts("2025-03-19"), "tokentide": _tt("private"),
     "model_spec": {"name": "Kokoro Text to Speech", "privacy": "private", "pricing": {"input": {"usd": 3.5}},
                    "voices": ["af_sky", "am_adam", "ef_dora"]}},
    # A voice model on the queued audio route (type music, billed per thousand characters), like ElevenLabs TTS v4.
    {"id": "elevenlabs-tts-v4", "type": "music", "created": _ts("2026-09-29"), "tokentide": _tt("anonymized"),
     "model_spec": {"name": "ElevenLabs TTS v4", "privacy": "anonymized",
                    "pricing": {"per_thousand_characters": {"usd": 0.092}}, "prompt_character_limit": 5000,
                    "voices": ["Aria", "Roger", "Sarah"], "default_voice": "Aria", "supports_custom_voice_id": False}},
    {"id": "elevenlabs-tts-v4-turbo", "type": "music", "created": _ts("2026-09-29"), "tokentide": _tt("anonymized"),
     "model_spec": {"name": "ElevenLabs TTS v4 Turbo", "privacy": "anonymized",
                    "pricing": {"per_thousand_characters": {"usd": 0.046}}, "prompt_character_limit": 5000,
                    "voices": ["Aria", "Roger", "Sarah"], "default_voice": "Aria", "supports_custom_voice_id": False}},
    {"id": "elevenlabs-music", "type": "music", "created": _ts("2026-06-01"), "tokentide": _tt("anonymized"),
     "model_spec": {"name": "ElevenLabs Music", "privacy": "anonymized"}},
    {"id": "elevenlabs-sound-effects", "type": "music", "created": _ts("2026-06-01"), "tokentide": _tt("anonymized"),
     "model_spec": {"name": "ElevenLabs Sound Effects", "privacy": "anonymized"}},
    {"id": "mock-vision", "type": "text", "tokentide": _tt("private"),
     "model_spec": {"privacy": "private", "capabilities": {"supportsVision": True}}},
]


# Arena's leaderboard dataset as Hugging Face's dataset viewer serves it (lmarena-ai/leaderboard-dataset, CC BY 4.0):
# rows grouped by category, the first ones cached (/first-rows), the rest paged (/rows). Names as Arena writes them.
def _arena(category, items, date="2026-11-17"):
    return [{"model_name": n, "organization": "", "license": "Proprietary", "rating": r, "rating_lower": r - 9,
             "rating_upper": r + 9, "variance": 20.0, "vote_count": 5000, "rank": i + 1, "category": category,
             "leaderboard_publish_date": date} for i, (n, r) in enumerate(items)]


ARENA = {
    "image_to_video": _arena("overall", [("Veo 3.1 (Audio)", 1400), ("Veo 3.1 Fast (Audio)", 1390),
                                         ("Kling 3.0 Pro", 1350), ("Dreamina Seedance 2.5 (720p)", 1300),
                                         ("Seedance 2.0 Fast (720p)", 1250), ("Utopai X", 1450)], "2026-11-09"),
    "text_to_video": _arena("overall", [("Veo 3.1 (Audio)", 1360)], "2026-11-09"),
    # Product images rank on multi-image editing, which comes after two other categories and past the cached rows.
    "image_edit": _arena("overall", [("Seedream 5.0 Pro", 1392), ("Gemini 3 Pro Image (nano-banana-pro, 2K)", 1391)])
    + _arena("agentic", [("Seedream 5.0 Pro", 1300)])
    + _arena("multi_image_edit", [("Gemini 3 Pro Image (nano-banana-pro, 2K)", 1364), ("Seedream 5.0 Pro", 1412)]),
    "text_to_image": _arena("overall", [("Seedream 5.0 Pro", 1249), ("Krea 2 Turbo", 1115)]),
}
ARENA_FIRST_ROWS = 4  # the viewer caches the first 100 rows; 4 here, so the multi-image category needs paging


def list_price(b, kind):
    m = b.get("model", "")
    if kind == "audio":
        chars = b.get("character_count") or (len(b.get("prompt") or "") if "tts" in m else 0)
        if chars:
            return round(0.092 * chars / 1000, 6)
        return round(0.004 * float(b.get("duration_seconds") or 30), 4)
    secs = float(str(b.get("duration", "5s")).rstrip("s") or 5)
    rate = 0.62 if "veo" in m else 0.2 if "pro" in m or "max" in m else 0.06 if "fast" in m else 0.11
    rate *= 1.25 if b.get("audio") else 1.0
    return round(rate * secs, 4)


def ff(args):
    common.ffmpeg(["-y", *args])


def make_media(d: Path):
    ff(["-f", "lavfi", "-i", "testsrc2=size=768x1344:rate=1", "-frames:v", "1", d / "img.png"])
    ff(["-f", "lavfi", "-i", "testsrc2=size=720x1280:rate=24", "-f", "lavfi", "-i", "sine=frequency=330:sample_rate=48000",
        "-t", "5", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", d / "video.mp4"])
    ff(["-f", "lavfi", "-i", "aevalsrc=0.35*sin(2*PI*210*t)*lt(mod(t\\,1.5)\\,1.1):s=24000:d=4.4", "-c:a", "libmp3lame",
        "-b:a", "96k", d / "speech.mp3"])
    ff(["-f", "lavfi", "-i", "sine=frequency=262:duration=12", "-f", "lavfi", "-i", "sine=frequency=330:duration=12",
        "-filter_complex", "amix=inputs=2", "-c:a", "libmp3lame", d / "music.mp3"])
    for k in ("img.png", "video.mp4", "speech.mp3", "music.mp3"):
        MEDIA[k] = (d / k).read_bytes()


class Mock(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json", headers=None, charge=None):
        data = json.dumps(body).encode() if ctype == "application/json" else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Request-Id", "req_" + uuid.uuid4().hex[:10])
        self.send_header("X-RateLimit-Limit-Requests", "60")
        self.send_header("X-RateLimit-Reset-Requests", "12s")
        if charge is not None:
            STATE["spent"] += charge[0]
            self.send_header("X-Tokentide-Charge-USD", f"{charge[0]:.6f}")
            self.send_header("X-Tokentide-List-Cost-USD", f"{charge[1]:.6f}")
            self.send_header("X-Tokentide-Multiplier", MULT["standard"])
            self.send_header("X-Tokentide-Lane", self.headers.get("X-Tokentide-Lane") or "standard")
            self.send_header("X-Tokentide-Epoch", _dt.date.today().isoformat())
            self.send_header("X-Tokentide-Model-Privacy", "anonymized")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _err(self, http, code, msg, param=None, headers=None):
        self._send(http, {"error": {"message": msg, "type": "tokentide_error", "code": code, "param": param,
                                    "request_id": "req_x"}}, headers=headers)

    def _path(self):
        p = self.path
        for pre in ("/api/v1", "/v1"):
            if p.startswith(pre):
                return p[len(pre):]
        return p

    def _auth(self):
        a = self.headers.get("Authorization") or ""
        if not a.startswith("Bearer tt_") or a[len("Bearer "):] not in STATE["keys"]:
            self._err(401, "invalid_api_key", "Missing, invalid or revoked API key")
            return False
        return True

    def _plugin(self, p, raw):
        """/api/plugin/* like the web app: JSON only, no-store, keys returned once."""
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            return self._send(415, {"error": "invalid_request", "message": "Send a JSON body (application/json)."})
        b = json.loads(raw or b"{}")
        bearer = (self.headers.get("Authorization") or "")[len("Bearer "):]
        if p == "/api/plugin/exchange":
            c = STATE["codes"].pop(b.get("code"), None)
            if not c or c["exp"] < time.time():
                return self._send(400, {"error": "invalid_code", "message": "This link code was already used or has expired."})
            if c["connection"] in STATE["revoked_connections"]:
                return self._send(403, {"error": "connection_revoked", "message": "The connection was revoked."})
            return self._send(200, issue_key(c["connection"], "plugin_scripts"), headers={"Cache-Control": "no-store"})
        if p == "/api/plugin/device":
            dc, uc = "ttdev_" + uuid.uuid4().hex + uuid.uuid4().hex[:11], "BCDF-GHJK"
            STATE["devices"][dc] = {"polls": 0}
            return self._send(200, {"device_code": dc, "user_code": uc, "verification_uri": f"http://127.0.0.1/link",
                                    "verification_uri_complete": f"http://127.0.0.1/link?code={uc}",
                                    "expires_in": 600, "interval": 1})
        if p == "/api/plugin/device/token":
            d = STATE["devices"].get(b.get("device_code"))
            if not d:
                return self._send(400, {"error": "expired_token", "message": "The sign-in request expired."})
            d["polls"] += 1
            if d["polls"] < 2:  # the user approves on the website between the first and second poll
                return self._send(400, {"error": "authorization_pending", "message": "Waiting for the approval."})
            del STATE["devices"][b["device_code"]]
            return self._send(200, issue_key("device_1", "plugin_device"))
        if p in ("/api/plugin/keys/rotate", "/api/plugin/keys/revoke"):
            k = STATE["keys"].get(bearer)
            if not k:
                return self._send(401, {"error": "invalid_api_key", "message": "Send a live plugin key."})
            del STATE["keys"][bearer]
            if p.endswith("/revoke"):
                return self._send(200, {"object": "plugin_key", "revoked": True})
            return self._send(200, issue_key(k["connection"], k["origin"]))
        return self._send(404, {"error": "not_found", "message": p})

    def _charge(self, list_usd):
        m = float(MULT["lowtide"] if self.headers.get("X-Tokentide-Lane") == "lowtide" else MULT["standard"])
        return (round(list_usd * m, 6), list_usd)

    def _arena(self):
        """Hugging Face's dataset viewer for Arena's dataset (no key; it answers 503 now and then)."""
        from urllib.parse import parse_qs, urlparse
        q = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
        rows = ARENA.get(q.get("config"))
        if q.get("dataset") != "lmarena-ai/leaderboard-dataset" or rows is None or q.get("split") != "latest":
            return self._send(404, {"error": "Not found"})
        wrap = lambda rs, start: [{"row_idx": start + i, "row": r, "truncated_cells": []} for i, r in enumerate(rs)]
        if self.path.startswith("/first-rows"):
            return self._send(200, {"dataset": q["dataset"], "config": q["config"], "split": "latest", "features": [],
                                    "rows": wrap(rows[:ARENA_FIRST_ROWS], 0), "truncated": len(rows) > ARENA_FIRST_ROWS})
        STATE["arena_pages"] = STATE.get("arena_pages", 0) + 1
        if STATE["arena_pages"] == 1:
            return self._send(503, {"error": "Service Temporarily Unavailable"})
        off, n = int(q.get("offset", 0)), min(100, int(q.get("length", 100)))
        return self._send(200, {"features": [], "rows": wrap(rows[off:off + n], off), "num_rows_total": len(rows),
                                "num_rows_per_page": 100, "partial": False})

    def do_GET(self):
        if self.path.startswith(("/first-rows", "/rows")):
            return self._arena()
        p = self._path()
        if p.startswith("/status"):
            return self._send(200, {"object": "status", "status": "operational",
                                    "components": {"tokentide_api": "operational", "market": "operational",
                                                   "upstream_venice": "operational"}})
        if p.startswith("/market"):
            # GET /v1/market's shape: `standard` and `lowtide` at the top level.
            return self._send(200, {"object": "market", "epoch": {"id": "2026-11-02", "state": "open", "seconds_to_reset": 54903},
                                    "standard": {"multiplier": MULT["standard"], "savings_pct": 29},
                                    "lowtide": {"open": True, "multiplier": MULT["lowtide"], "savings_pct": 50.3}})
        if not self._auth():
            return
        if p.startswith("/models"):
            t = p.split("type=")[-1] if "type=" in p else "all"
            return self._send(200, {"object": "list", "data": [m for m in MODELS if t == "all" or m["type"] == t]})
        if p.startswith("/account"):
            return self._send(200, {"object": "account", "id": "acct_mock", "principal": "key", "tier": "new", "free_use": False,
                                    "balance": {"available_usd": "20.00", "promo_usd": "0.00", "leased_usd": "0.00",
                                                "spendable_usd": f"{20 - STATE['spent']:.2f}"},
                                    "spend_today": {"charged_usd": f"{STATE['spent']:.4f}", "list_usd": "0", "savings_usd": "0"},
                                    "limits": {"requests_per_minute_per_key": 60, "concurrency": 4,
                                               "image_requests_per_minute": 30,
                                               "spend_velocity_usd_per_minute": "0.69",
                                               "running_requests_usd": "4.32"}})
        if p.startswith("/image/styles"):
            return self._send(200, {"data": ["Cinematic"]})
        self._err(404, "not_found", f"Unknown route {p}")

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        if self.path.startswith("/api/plugin/"):
            return self._plugin(self.path, raw)
        if not self._auth():
            return
        if len(raw) > 4_500_000:
            return self._err(413, "payload_too_large", "Request body exceeds 4.5 MB")
        p = self._path()
        ctype = self.headers.get("Content-Type") or ""
        b = json.loads(raw or b"{}") if "json" in ctype else {}
        if p.startswith("/image/"):
            STATE["image_calls"] += 1
            if STATE["image_calls"] == 3:
                return self._err(429, "rate_limited", "Image requests per minute exceeded", headers={"Retry-After": "1"})
        if p == "/image/generate":
            n_img = int(b.get("variants", 1))
            return self._send(200, {"id": "gen", "images": [base64.b64encode(MEDIA["img.png"]).decode()] * n_img},
                              charge=self._charge(0.06 * n_img))
        if p == "/image/multi-edit":
            if "modelId" not in b or not 2 <= len(b.get("images", [])) <= 3:
                return self._send(400, {"error": "modelId and 2-3 images required"})
            return self._send(200, MEDIA["img.png"], "image/png", charge=self._charge(0.23))
        if p in ("/image/edit", "/image/background-remove", "/image/upscale"):
            if not b.get("image"):
                return self._err(400, "invalid_request", "image is required", param="image")
            return self._send(200, MEDIA["img.png"], "image/png", charge=self._charge(0.04))
        if p in ("/video/quote", "/audio/quote") and b.get("model") and b.get("resolution"):
            # Like Tokentide: a value the model doesn't list is refused before Venice, naming the parameter.
            m = next((x for x in MODELS if x["id"] == b["model"]), None)
            ress = ((m or {}).get("model_spec") or {}).get("constraints", {}).get("resolutions")
            if ress and b["resolution"] not in ress:
                return self._err(400, "invalid_request", f"resolution must be one of {', '.join(ress)} for "
                                 f"`{b['model']}` (values are case-sensitive).", param="resolution")
        if p in ("/video/quote", "/audio/quote"):
            kind = p.split("/")[1]
            # Venice's quote schemas reject unknown fields, and Tokentide forwards free quotes as sent.
            allowed = QUOTE_FIELDS[kind]
            extra = sorted(k for k in b if k not in allowed)
            if extra:
                return self._send(400, {"error": "Invalid request parameters",
                                        "details": {"_errors": [f"Unrecognized key(s) in object: {extra}"]},
                                        "issues": [{"code": "unrecognized_keys", "keys": extra, "path": [],
                                                    "message": "Unrecognized key(s) in object"}]})
            lp = list_price(b, kind)
            ch = self._charge(lp)[0]
            return self._send(200, {"quote": ch, "tokentide": {"list_cost_usd": lp, "charge_usd": ch,
                                                               "multiplier": MULT["standard"], "lane": "standard",
                                                               "queue_open": True,
                                                               "queue_closes_at": f"{_dt.date.today()}T23:14:00Z"}})
        if p in ("/video/queue", "/audio/queue"):
            kind = p.split("/")[1]
            key = self.headers.get("Idempotency-Key")
            if key in STATE["idem"]:
                return self._err(409, "duplicate_request", "Idempotency-Key already used")
            STATE["queue_calls"] += 1
            if STATE["queue_calls"] == 1:  # like Tokentide's spend velocity: the minute is full, the next one admits it
                return self._err(429, "rate_limited", "Spend velocity limit reached: this account's requests that finished "
                                 "this minute cost $0.72 at the Venice list price, whatever they were charged, and the limit "
                                 "is $0.69 per minute. Retry in 1 s, when the next minute starts.", headers={"Retry-After": "1"})
            if key:
                STATE["idem"].add(key)
            allowed = {"model", "prompt", "negative_prompt", "duration", "resolution", "aspect_ratio", "audio",
                       "image_url", "end_image_url", "seed", "duration_seconds", "force_instrumental", "voice"}
            bad = sorted(set(b) - allowed)
            if bad:
                return self._err(400, "invalid_request", f"Unknown field {bad[0]}", param=bad[0])
            unfinished = [j for j in STATE["jobs"].values() if not j["gone"]]
            if len(unfinished) >= 8:
                return self._err(429, "rate_limited", "Too many unfinished jobs", headers={"Retry-After": "2"})
            qid = uuid.uuid4().hex[:10]
            STATE["jobs"][qid] = {"n": 0, "kind": kind, "gone": False, "model": b["model"]}
            return self._send(200, {"model": b["model"], "queue_id": qid} if kind == "video" else
                              {"model": b["model"], "queue_id": qid, "status": "QUEUED"},
                              charge=self._charge(list_price(b, kind)))
        if p in ("/video/retrieve", "/audio/retrieve"):
            job = STATE["jobs"].get(b.get("queue_id"))
            if not job or job["gone"]:
                return self._err(404, "not_found", "Unknown queue_id")
            job["n"] += 1
            if job["n"] < 2:
                return self._send(200, {"status": "PROCESSING", "average_execution_time": 3000, "execution_duration": 900})
            if b.get("delete_media_on_completion", True) is not False:
                job["gone"] = True  # Tokentide deletes after delivery by default
            if job["kind"] == "audio":
                return self._send(200, MEDIA["speech.mp3" if "tts" in job.get("model", "") else "music.mp3"], "audio/mpeg")
            return self._send(200, MEDIA["video.mp4"], "video/mp4")
        if p in ("/video/complete", "/audio/complete"):
            if set(b) - {"queue_id"}:
                bad = sorted(set(b) - {"queue_id"})[0]
                return self._err(400, "invalid_request", f"Unknown field {bad}", param=bad)
            job = STATE["jobs"].get(b.get("queue_id"))
            if job:
                job["gone"] = True
            return self._send(200, {"success": True})
        if p == "/audio/speech":
            if len(b.get("input", "")) > 4096:
                return self._err(400, "invalid_request", "input over 4096 characters", param="input")
            return self._send(200, MEDIA["speech.mp3"], "audio/mpeg", charge=self._charge(0.002))
        if p == "/audio/transcriptions":
            fmt = re.search(rb'name="response_format"\r\n\r\n([^\r]*)\r\n', raw)
            if fmt and fmt.group(1) not in (b"json", b"text"):
                return self._err(400, "invalid_request", 'response_format must be "json" or "text"',
                                 param="response_format")
            words = "Stop scrolling this bottle keeps water ice cold for a full day".split()
            out, t = [], 0.2
            for w in words:
                out.append({"word": w, "start": round(t, 2), "end": round(t + 0.28, 2)})
                t += 0.33
            return self._send(200, {"text": " ".join(words), "words": out}, charge=self._charge(0.001))
        if p == "/chat/completions":
            content = json.dumps({"results": [{"image": "candidate", "scores": {"product_shape": 5, "label_logo": 4},
                                               "pass": True, "issues": [], "fix": ""}]})
            return self._send(200, {"choices": [{"message": {"role": "assistant", "content": content}}]},
                              charge=self._charge(0.003))
        self._err(404, "not_found", f"Unknown route {p}")


class SiteRedirect(BaseHTTPRequestHandler):
    """A front host that answers like tokentide.app's API host used to: 308 to another origin of the same site."""
    protocol_version = "HTTP/1.1"
    target = ""

    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n:
            self.rfile.read(n)
        self.send_response(308)
        self.send_header("Location", f"{self.target}{self.path}")
        self.send_header("Content-Length", "0")
        self.end_headers()


SPEC = {
    "id": "v01", "title": "Ice test", "status": "draft", "aspect_ratio": "9:16", "target_duration_s": 7,
    "budget_usd": 5, "platforms": ["tiktok", "instagram", "x"],
    "concept": {"objective": "reach", "pillar": "demo", "format": "satisfying-demo", "awareness_level": "problem-aware",
                "hook": {"text": "24 HOURS LATER…", "vo": "Stop scrolling.", "visual": "ice clinks"}, "cta": "send"},
    "product_descriptor": "matte sage-green 750 ml steel bottle with white NOVA wordmark and bamboo cap",
    "shots": [
        {"id": "s1", "purpose": "hook",
         "keyframe": {"mode": "multi-edit", "model": "@keyframe", "inputs": ["assets/scenes/counter_k1.png",
                                                                           "assets/product/front_cutout.png"],
                      "prompt": "Place the bottle from image 2 on the counter in image 1, morning light from the left",
                      "resolution": "2K", "n": 2},
         "video": {"model": "@i2v", "prompt": "slow push-in, ice cubes drop in", "duration": "5s",
                   "resolution": "720p", "audio": False, "takes": 1},
         "edit": {"in": 0.0, "out": 3.0, "zoom": "push"}},
        {"id": "s2", "purpose": "payoff",
         "keyframe": {"mode": "edit", "model": "@keyframe", "inputs": ["assets/product/front.jpg"],
                      "prompt": "Same bottle on a gym bench, condensation droplets", "n": 2},
         "video": {"model": "@i2v_audio", "prompt": "hand twists cap, ice clinks", "duration": 5,
                   "resolution": "720p", "audio": True, "takes": 2},
         "edit": {"in": 0.5, "out": 4.5, "speed": 1.1, "transition": {"type": "slideleft", "duration": 0.2}}},
    ],
    "voiceover": {"enabled": True, "model": "@tts", "voice": "af_sky", "speed": 1.0, "offset": 0.1,
                  "script": "Stop scrolling. This bottle keeps water ice cold for a full day."},
    "music": {"volume": 0.3, "duck": True,
              "generate": {"model": "@music", "prompt": "upbeat minimal electronic, bright plucks, 110 bpm",
                           "duration_seconds": 12, "force_instrumental": True}},
    "sfx": [{"at": "s2", "offset": -0.1, "volume": 0.6,
             "generate": {"model": "@sfx", "prompt": "short airy whoosh transition", "duration_seconds": 1}}],
    "audio_mix": {"keep_clip_audio": True, "clip_audio_volume": 0.2},
    "captions": {"style": "highlight", "font": "Anton", "words_per_chunk": 3},
    "overlays": [{"type": "text", "style": "hook", "text": "24 HOURS LATER…", "start": 0, "end": 2.2},
                 {"type": "text", "style": "label", "text": "AI-generated", "start": 0, "end": 99},
                 {"type": "image", "file": "assets/brand/logo.png", "position": "top-right", "width": 160, "start": 4}],
    "cover": {"time": 0.6, "text": "ICE AFTER\\N24 HOURS?"},
    "packaging": {"keywords": ["insulated bottle"],
                  "tiktok": {"caption": "insulated bottle test: 24 hours later", "hashtags": ["#insulatedbottle", "#gymtok", "#hydration"]},
                  "instagram": {"caption": "Insulated bottle vs. a full day in a hot car", "hashtags": ["#insulatedbottle"],
                                "alt_text": "Green steel bottle with ice", "trial_reel": True},
                  "x": {"text": "We left it in a hot car for 24h. Guess what was still inside?", "reply": "Would you trust it?"}},
    "claims": [{"claim": "keeps water cold 24 hours", "evidence": "lab report LR-2026-04", "status": "substantiated"}],
    "disclosure": {"ai_generated": True, "paid_partnership": False, "on_screen_label": "AI-generated"},
}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--keep", action="store_true", help="keep the temp project for inspection")
    ap.add_argument("--workdir")
    a = ap.parse_args()
    work = Path(a.workdir or tempfile.mkdtemp(prefix="vpv_tt_selftest_"))
    work.mkdir(parents=True, exist_ok=True)
    media = work / "_mock_media"
    media.mkdir(exist_ok=True)
    make_media(media)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Mock)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    config = work / "_config"  # a throwaway key-file folder: the real ~/.config/tokentide is never touched
    env = {**os.environ, "TOKENTIDE_BASE_URL": f"http://127.0.0.1:{srv.server_port}/v1",
           "TOKENTIDE_ARENA_URL": f"http://127.0.0.1:{srv.server_port}",
           "TOKENTIDE_CONFIG_DIR": str(config), "TOKENTIDE_IMAGE_RPM": "30"}
    for k in ("TOKENTIDE_API_KEY", "TOKENTIDE_API_KEY_FILE", "TOKENTIDE_SITE_URL"):
        env.pop(k, None)
    root = work / "projects" / "selftest-bottle"
    spec = root / "briefs" / "v01.json"
    results = []

    def run(name, *args, ok=(0,), expect=(), absent=(), extra_env=None):
        """Runs a script; passes when the exit code is in `ok`, every `expect` text is in its output and no
        `absent` text is (e.g. a key that must never be printed)."""
        t0 = time.time()
        r = subprocess.run([sys.executable, str(HERE / args[0]), *map(str, args[1:])], env={**env, **(extra_env or {})},
                           cwd=work, capture_output=True, text=True)
        out = r.stdout + r.stderr
        missing = [e for e in expect if e not in out] + [f"(must not print) {x[:12]}…" for x in absent if x in out]
        good = r.returncode in ok and not missing
        results.append((good, name, time.time() - t0))
        print(f"{'PASS' if good else 'FAIL'}  {name}  ({time.time() - t0:.1f}s)")
        if not good:
            print((f"missing: {missing}\n" if missing else "") + out[-2500:])
        return r

    def check(name, cond, detail=""):
        results.append((bool(cond), name, 0.0))
        print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))

    def file_key():
        lines = [x for x in (config / "api_key").read_text(encoding="utf-8").splitlines() if x and not x.startswith("#")]
        return lines[0] if lines else ""

    # Sign in once: no key at all -> the scripts tell the agent what to run -> one exchange links the scripts.
    run("no key yet: scripts tell the agent how to link", "doctor.py", "--offline", ok=(1,),
        expect=("link_local_scripts", "auth.py exchange --code", "auth.py login", "never ask the user"))
    code = mint_link_code()
    r = run("link: auth.py exchange --code (from link_local_scripts)", "auth.py", "exchange", "--code", code,
            expect=("linked: key …", "privacy mode all", "daily cap $40"))
    linked = file_key()
    check("key file holds a live key, owner-only", linked in STATE["keys"] and
          (os.name == "nt" or (config / "api_key").stat().st_mode & 0o077 == 0), oct((config / "api_key").stat().st_mode))
    check("the key never reaches the output", linked and linked not in r.stdout + r.stderr)
    run("a link code works once", "auth.py", "exchange", "--code", code, ok=(1,),
        expect=("already used or has expired", "link_local_scripts"))
    run("auth status (masked key, accepted)", "auth.py", "status", expect=(f"key …{linked[-4:]}", "accepted"),
        absent=(linked,))
    # A host that answers the sign-in routes with a 308 to another origin of the same site (as api.tokentide.app
    # once did): auth.py re-sends the POST there, over TLS or loopback only, and never to another site.
    redir = ThreadingHTTPServer(("127.0.0.1", 0), SiteRedirect)
    SiteRedirect.target = f"http://127.0.0.1:{srv.server_port}"
    threading.Thread(target=redir.serve_forever, daemon=True).start()
    run("exchange follows a same-site 308", "auth.py", "exchange", "--code", mint_link_code(),
        expect=("linked: key …",), extra_env={"TOKENTIDE_SITE_URL": f"http://127.0.0.1:{redir.server_port}"})
    SiteRedirect.target = f"http://localhost:{srv.server_port}"  # another host: not followed
    run("exchange does not follow a 308 to another host", "auth.py", "exchange", "--code", mint_link_code(), ok=(1,),
        expect=("http_308",), extra_env={"TOKENTIDE_SITE_URL": f"http://127.0.0.1:{redir.server_port}"})
    redir.shutdown()
    import auth  # noqa: E402  (the redirect rule, in process)
    check("same-site rule: api.tokentide.app ↔ tokentide.app only",
          auth.same_site("api.tokentide.app", "tokentide.app") and not auth.same_site("tokentide.app.evil.com", "tokentide.app")
          and not auth.same_site("eviltokentide.app", "tokentide.app") and not auth.same_site("api.tokentide.app", "app"))

    # The key and sign-in codes go to Tokentide hosts or this machine only.
    import apiclient as api  # noqa: E402
    check("key hosts: Tokentide, its Vercel URL and loopback only",
          api.secure_url("https://api.tokentide.app/v1") and api.secure_url("https://tokentide.app/api/plugin/x")
          and api.secure_url("https://tokentide-app.vercel.app/v1") and api.secure_url("http://127.0.0.1:9/v1")
          and not api.secure_url("http://api.tokentide.app/v1") and not api.secure_url("https://evil.example/v1")
          and not api.secure_url("https://tokentide.app.evil.com/v1") and not api.secure_url("https://eviltokentide.app/v1")
          and not api.secure_url("https://x.vercel.app/v1", "tt_live_abc")
          and api.secure_url("https://x.vercel.app/v1", "tt_test_abc"))
    run("the key is not sent to another host", "doctor.py", ok=(1,), expect=("Refusing to send the Tokentide key",),
        absent=(linked,), extra_env={"TOKENTIDE_BASE_URL": "https://evil.example/v1"})
    # A key file in the project folder never replaces the linked key.
    (work / ".tokentide_api_key").write_text("tt_live_planted0000000000000000\n", encoding="utf-8")
    current = file_key()  # the 308 exchange above linked a newer key
    run("the linked key wins over ./.tokentide_api_key", "auth.py", "status", expect=(f"key …{current[-4:]}",),
        absent=(current,))
    (work / ".tokentide_api_key").unlink()

    # common.probe without ffprobe (the plugin-managed FFmpeg ships none) reads `ffmpeg -i` correctly.
    for name, want in (("video.mp4", {"vcodec": "h264", "width": 720, "height": 1280, "pix_fmt": "yuv420p",
                                      "has_audio": True, "acodec": "aac", "sample_rate": 48000, "channels": 1}),
                       ("music.mp3", {"has_audio": True, "acodec": "mp3", "vcodec": None})):
        err = subprocess.run([common.require_ffmpeg(), "-hide_banner", "-nostdin", "-i", str(media / name)],
                             capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
        got = common.parse_ffmpeg_info(err, {"vcodec": None, "has_audio": False})
        bad = {k: got.get(k) for k, v in want.items() if got.get(k) != v}
        check(f"probe without ffprobe: {name}", not bad and got.get("duration", 0) > 1, f"wrong: {bad}")

    run("init project", "init_project.py", "Selftest Bottle", "--root", work / "projects", "--budget-usd", "20")
    ff(["-f", "lavfi", "-i", "testsrc2=size=1200x1600:rate=1", "-frames:v", "1", root / "assets/product/front.jpg"])
    ff(["-f", "lavfi", "-i", "color=c=white:s=400x120,format=rgba", "-frames:v", "1", root / "assets/brand/logo.png"])
    run("doctor (status/market/account/catalog)", "doctor.py", "--project", root, expect=("spend velocity $0.69/min", "running requests up to $4.32"))
    run("models list (cache)", "models.py", "list", "--type", "all", "--out", root / "models.json")
    r = run("models recommend (tide prices + quotes)", "models.py", "recommend", "--project", root)
    print("\n".join(l for l in r.stdout.splitlines() if l.startswith(("| Premium", "| Balanced", "| Budget", "| Newest", "| Private", "## ", "> "))))
    # The first question of every request: the user names the models, or we recommend Essential / Pro / Max.
    import models as M  # noqa: E402  (name matching and level picking, in process)
    pairs_same = [("Dreamina Seedance 2.5 (720p)", "Seedance 2.5"), ("Kling 3.0 Pro", "Kling V3 Pro"),
                  ("Gemini Omni 1.1 Flash", "Gemini Omni Flash 1.1"), ("Veo 3.1 (Audio)", "Veo 3.1 Full Quality"),
                  ("Veo 3.1 Fast (Audio, 1080p)", "Veo 3.1 Fast"), ("FLUX 3 Video (20260811)", "Flux 3"),
                  ("Grok Imagine Video 1.5 (720p)", "Grok Imagine 1.5"), ("Gemini Nano Banana 2.1", "Nano Banana 2.1"),
                  ("Gemini 3 Pro Image (nano-banana-pro, 2K)", "Nano Banana Pro"),
                  ("Gemini 3.1 Flash-Lite Image (nano-banana-2-lite)", "Nano Banana 2 Lite"),
                  ("GPT-Image-2.6 Sunburst (Medium)", "GPT Image 2.6 Sunburst Edit"), ("Seedream 5.0 Pro", "Seedream V5 Pro"),
                  ("MiniMax H3-Image", "MiniMax H3 Image"), ("Wan 2.7 Image Pro", "Wan 2.7 Pro"),
                  ("Kling 3.0 1080p (Pro)", "Kling V3 Pro"), ("Eleven v4", "ElevenLabs TTS v4")]
    pairs_diff = [("Veo 3.1 Fast (Audio)", "Veo 3.1 Full Quality"), ("Gemini Omni 1.2 Flash", "Gemini Omni Flash 1.1"),
                  ("Qwen-Image-2.1", "Qwen Image 2.1 Pro"), ("MiniMax H3", "MiniMax H3 Max"), ("Wan 3.0", "Wan 3.0 Pro"),
                  ("Dreamina Seedance 2.5 (720p)", "Seedance 2.5 Flash"), ("Kling 3.0 Pro", "Kling V3 Standard"),
                  ("Eleven Music v2.5", "MiniMax Music 2.5"), ("TTS-1", "xAI TTS v1"), ("Eleven v4", "ElevenLabs TTS v4 Turbo")]
    bad = [p for p in pairs_same if not M.same_model(M.name_key(p[0]), M.name_key(p[1]))] + \
          [p for p in pairs_diff if M.same_model(M.name_key(p[0]), M.name_key(p[1]))]
    check("leaderboard names match catalog names (and only those)", not bad, f"wrong: {bad}")
    pts = [{"id": i, "q": q, "p": p} for i, q, p in (("a", 1, 0.05), ("b", 2, 0.06), ("x", 1.5, 0.3), ("c", 3, 0.2),
                                                       ("d", 4, 1.0))]
    front = M.frontier(pts, lambda d: d["p"])
    lv = M.pick_levels(front, lambda d: d["p"])
    check("levels sit on the price/quality frontier", [d["id"] for d in front] == ["a", "b", "c", "d"]
          and [lv[k]["id"] for k in M.LEVELS] == ["b", "c", "d"], str([d["id"] for d in front]))
    (root / "arena.json").unlink(missing_ok=True)  # recommend cached it; read the dataset again
    run("models tiers (Arena ratings x Tokentide prices; estimate for voice and music)", "models.py", "tiers",
        "--project", root, expect=("| Video |", "| Voice |", "(quote)", "Arena leaderboard (arena.ai)", "CC BY 4.0",
                                   "Arena does not endorse", "· estimate", "Not rated by Arena"))
    arena = common.load_json(root / "arena.json")
    check("Arena's dataset is cached with its licence; product images rank on multi-image editing",
          arena.get("license") == "CC BY 4.0" and arena["boards"]["image_edit"]["category"] == "multi_image_edit"
          and arena["boards"]["video"]["published"] == "2026-11-09", json.dumps(arena)[:300])
    tiers = common.load_json(root / "model_tiers.json")
    got = {lv: tiers["tiers"][lv]["models"] for lv in M.LEVELS}
    check("Essential / Pro / Max video models", [got[lv].get("i2v") for lv in M.LEVELS] == [
        "seedance-2-5-image-to-video-basic", "kling-v3-pro-image-to-video", "veo3.1-full-image-to-video"], json.dumps(got))
    check("voice and music levels come from the estimate; ElevenLabs v4 is never a default (v4 Turbo instead)",
          got["max"].get("tts") == "elevenlabs-tts-v4-turbo" and got["essential"].get("tts") == "tts-kokoro"
          and "elevenlabs-tts-v4" not in json.dumps({lv: got[lv] for lv in M.LEVELS}).replace("elevenlabs-tts-v4-turbo", "")
          and got["max"].get("music") == "elevenlabs-music"
          and tiers["jobs"]["tts"]["basis"] == "estimated" and tiers["jobs"]["i2v"]["basis"] == "leaderboard"
          and got["max"].get("keyframe") == "seedream-v5-pro-edit", json.dumps(got))
    check("every level has a total", all(tiers["tiers"][lv]["total_usd"] > 0 and tiers["tiers"][lv]["label"] == "quote"
                                         for lv in M.LEVELS))
    run("models choose --tier pro", "models.py", "choose", "--project", root, "--tier", "pro",
        expect=("@i2v        -> kling-v3-pro-image-to-video",))
    run("models match: the user's own models", "models.py", "match", "Kling 3 Pro", "Sora 2", "eleven labs v4",
        "--project", root, expect=('"Kling 3 Pro" — AVAILABLE', '"Sora 2" — NOT AVAILABLE', "elevenlabs-tts-v4",
                                   "i2v=kling-v3-pro-image-to-video", "tts=elevenlabs-tts-v4-turbo",
                                   "instead of `elevenlabs-tts-v4` by default"))
    r = run("models recommend never offers ElevenLabs v4 (v4 Turbo instead)", "models.py", "recommend", "--project", root,
            "--jobs", "tts", "--cache", root / "models.json", expect=("elevenlabs-tts-v4-turbo",))
    check("ElevenLabs v4 is not among the voice options", "`elevenlabs-tts-v4`" not in r.stdout)
    run("choosing ElevenLabs v4 explicitly warns", "models.py", "choose", "--project", root, "tts=elevenlabs-tts-v4",
        expect=("is never the default", "elevenlabs-tts-v4-turbo"))
    run("models cost: the total before anything is made", "models.py", "cost", "--project", root, "--videos", "2",
        expect=("QUOTE:", "| **Total** |", "Budget:"))
    run("tiers without the dataset: everything on the estimate, said plainly", "models.py", "tiers", "--project", root,
        "--ratings", "none", expect=("No leaderboard ratings this time", "estimated, without independent ratings"))
    run("models choose", "models.py", "choose", "--project", root, "keyframe=nano-banana-pro-edit", "scene=seedream-v5-pro",
        "i2v=kling-v3-pro-image-to-video", "i2v_audio=seedance-2-5-image-to-video-basic", "tts=elevenlabs-tts-v4-turbo",
        "music=elevenlabs-music", "sfx=elevenlabs-sound-effects")
    run("bg-remove", "image.py", "bg-remove", "--image", root / "assets/product/front.jpg", "--out",
        root / "assets/product/front_cutout.png")
    run("scene generate x2 (@scene)", "image.py", "generate", "--model", "@scene", "--prompt", "empty marble counter, morning light",
        "--n", "2", "--out", root / "assets/scenes/counter")
    common.save_json(spec, SPEC)
    run("keyframes (429 retry + pacing)", "image.py", "keyframes", "--spec", spec)
    run("select keyframe s1", "image.py", "select", "--spec", spec, "--shot", "s1", "--k", "1")
    run("select keyframe s2", "image.py", "select", "--spec", spec, "--shot", "s2", "--k", "2")
    run("video dry-run quote", "video.py", "run", "--spec", spec, "--dry-run")
    run("video run (slots=2, waves, no download_url)", "video.py", "run", "--spec", spec, "--max-inflight", "2",
        "--poll-seconds", "60", "--interval", "0.3")
    run("video select s1", "video.py", "select", "--spec", spec, "--shot", "s1", "--take", "1")
    run("video select s2", "video.py", "select", "--spec", spec, "--shot", "s2", "--take", "2")
    run("music generation (queued audio job)", "audio.py", "music", "--spec", spec, "--poll-seconds", "60", "--interval", "0.3")
    run("sfx generation", "audio.py", "sfx", "--spec", spec, "--poll-seconds", "60", "--interval", "0.3")
    run("voice cloning refused (not offered)", "audio.py", "clone", "--file", root / "assets/product/front.jpg",
        "--name", "x", "--i-have-consent", ok=(2,))
    run("voices (incl. queued voice models)", "audio.py", "voices", "--cache", root / "models.json",
        expect=("elevenlabs-tts-v4-turbo: 3 voices", "tts-kokoro: 3 voices"), absent=("elevenlabs-music:",))
    run("tts via /audio/speech", "audio.py", "tts", "--text", "Stop scrolling.", "--model", "tts-kokoro", "--voice",
        "af_sky", "--out", root / "audio/kokoro_check.mp3")
    run("tts via a queued voice model (wrong voice -> its default)", "audio.py", "tts", "--spec", spec, "--interval", "0.3",
        expect=("voice 'af_sky' is not offered", "words/s"))
    check("the spec records the voice-over", common.load_json(spec)["voiceover"].get("file", "").endswith("v01_vo.mp3")
          and common.load_json(spec)["voiceover"].get("voice") == "Aria")
    run("transcribe+align", "audio.py", "transcribe", "--spec", spec)
    run("captions", "captions.py", "--spec", spec)
    run("assemble master (generated music + sfx)", "assemble.py", "--spec", spec)
    run("qa check", "qa.py", "check", root / "renders/v01_master.mp4", "--spec", spec)
    run("qa frames", "qa.py", "frames", root / "renders/v01_master.mp4", "--every", "1")
    run("qa safezone", "qa.py", "safezone", root / "renders/v01_master.mp4", "--t", "1.0")
    run("qa vision (mock)", "qa.py", "vision", "--images", root / "keyframes/v01_s1_k1.png", "--reference",
        root / "assets/product/front.jpg")
    run("package", "package.py", "--spec", spec)
    run("models show: accepted values", "models.py", "show", "minimax-h3-max-image-to-video", "--cache",
        root / "models.json", expect=("Accepted values", "resolution: 768p, 1080p", "duration: 6s, 10s"))
    run("quote: a rejected value names the parameter and the accepted values", "video.py", "quote", "--model",
        "minimax-h3-max-image-to-video", "--duration", "6s", "--resolution", "720p", "--models", root / "models.json",
        ok=(1,), expect=("resolution must be one of 768p, 1080p", "rejected: resolution=\"720p\"",
                         "accepted: 768p, 1080p"))
    run("metrics template", "metrics.py", "template", "--out", root / "logs/perf_test.csv")
    with open(root / "logs/perf_test.csv", "a", encoding="utf-8") as fh:
        fh.write("tt_002,v02,tiktok,2026-11-04 19:00,72,12,900,880,3.1,9,31,20,2,1,,3,1,10,,B-callout,myth-bust,edu,\n")
        fh.write("tt_003,v03,tiktok,2026-11-05 19:00,72,14,20000,19000,8.4,32,66,1500,120,400,,300,210,900,,C-pov,pov,story,\n")
    run("metrics analyze", "metrics.py", "analyze", "--csv", root / "logs/perf_test.csv")
    r = run("budget (exact charges + live account)", "budget.py", "--project", root, "--live")
    print("\n".join(r.stdout.splitlines()[:4]))

    # Rotation, revocation through the connection, re-linking with one approval, and the device flow.
    old_key = file_key()
    run("auth rotate (new key, old one ends)", "auth.py", "rotate", expect=("rotated: key …",), absent=(old_key,))
    check("rotation replaced the key", file_key() != old_key and old_key not in STATE["keys"] and file_key() in STATE["keys"])
    revoke_connection()
    run("connection revoked: scripts fail with what the agent does", "models.py", "list", "--type", "video", ok=(1,),
        expect=("revoked", "link_local_scripts", "reconnect"))
    run("re-linking through a revoked connection is refused", "auth.py", "exchange", "--code", mint_link_code(),
        ok=(1,), expect=("was revoked", "reconnect the connector"))
    reconnect()
    run("after reconnecting: one exchange links again", "auth.py", "exchange", "--code", mint_link_code(),
        expect=("linked: key …",))
    run("scripts work again", "models.py", "list", "--type", "video")
    run("logout --revoke", "auth.py", "logout", "--revoke", expect=("revoked: key …", "removed"))
    run("no connector: auth.py login (device flow, one approval)", "auth.py", "login", "--no-browser", "--wait", "30",
        expect=("BCDF-GHJK", "linked: key …"))
    run("signed in through the device flow", "auth.py", "status", expect=("accepted",))
    srv.shutdown()
    master = root / "renders/v01_master.mp4"
    if master.exists():
        info = common.probe(master)
        print(f"\nmaster: {info['width']}x{info['height']} {info['fps']}fps {info['duration']:.2f}s audio={info['has_audio']}")
    failed = [n for ok, n, _ in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} steps passed" + (f"; failed: {', '.join(failed)}" if failed else ""))
    if a.keep or failed:
        print(f"project kept at: {root}")
    else:
        shutil.rmtree(work, ignore_errors=True)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
