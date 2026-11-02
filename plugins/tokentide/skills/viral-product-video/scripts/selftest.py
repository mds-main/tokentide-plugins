#!/usr/bin/env python3
"""End-to-end self-test against a local mock of the Tokentide API (no key, no network, no cost).

The mock reproduces Tokentide's documented behaviour: /v1 paths (+ /api/v1 alias), Bearer tt_ keys,
OpenAI-style error envelope, charge headers, a 4.5 MB body limit, Retry-After 429s, video jobs with no
download URL (file returned by retrieve, deleted after delivery unless delete_media_on_completion=false),
/complete taking only queue_id, queued music/SFX, /account, /market and /status.

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
STATE = {"jobs": {}, "queue_calls": 0, "image_calls": 0, "idem": set(), "spent": 0.0}
MULT = {"standard": "0.709522", "lowtide": "0.496665"}


def _ts(d):
    return int(_dt.datetime.fromisoformat(d + "T00:00:00+00:00").timestamp())


def _tt(privacy):
    return {"privacy_tier": privacy, "epoch": _dt.date.today().isoformat(), "price_locked_until": None,
            "standard": {"multiplier": MULT["standard"], "input_per_1m": None, "output_per_1m": None, "per_unit": None, "unit": None},
            "lowtide": {"multiplier": MULT["lowtide"], "open": True, "eligible": True}}


def _vid(mid, created, durs, res, audio=True, end=False, privacy="anonymized", aspects=("9:16", "16:9", "1:1")):
    return {"id": mid, "type": "video", "created": _ts(created), "tokentide": _tt(privacy),
            "model_spec": {"privacy": privacy, "constraints": {"durations": list(durs), "resolutions": list(res),
                                                               "aspect_ratios": list(aspects), "promptCharacterLimit": 4096},
                           "capabilities": {"supportsAudioConfig": audio, "supportsEndImage": end}}}


def _img(mid, created, pricing, inputs=None, privacy="anonymized"):
    caps = {"maxInputImages": inputs} if inputs else {}
    # Like Tokentide's catalog: edit / multi-edit models are Venice type "inpaint", generators "image".
    return {"id": mid, "type": "inpaint" if "edit" in mid else "image", "created": _ts(created), "tokentide": _tt(privacy),
            "model_spec": {"privacy": privacy, "pricing": pricing, "capabilities": caps}}


QUOTE_FIELDS = {
    "video": {"model", "duration", "aspect_ratio", "resolution", "upscale_factor", "enhancement_model", "target_fps",
              "slowdown_factor", "audio", "video_url"},
    "audio": {"model", "duration_seconds", "character_count"},
}

MODELS = [
    _vid("veo3.1-full-image-to-video", "2025-10-15", ["4s", "6s", "8s"], ["720p", "1080p", "4k"]),
    _vid("kling-v3-pro-image-to-video", "2026-02-05", ["5s", "10s", "15s"], ["720p", "1080p"], end=True),
    _vid("kling-v3-standard-image-to-video", "2026-02-05", ["5s", "10s", "15s"], ["720p", "1080p"], end=True),
    _vid("seedance-2-5-image-to-video-basic", "2026-09-10", [f"{i}s" for i in range(4, 31)], ["480p", "720p", "1080p"], end=True),
    _vid("seedance-2-0-fast-image-to-video-basic", "2026-03-01", [f"{i}s" for i in range(4, 16)], ["480p", "720p"]),
    _vid("minimax-h3-max-image-to-video", "2026-10-25", ["6s", "10s"], ["768p", "1080p"], privacy="private"),
    _vid("grok-imagine-1-5-image-to-video-private", "2026-07-01", ["6s", "10s"], ["480p", "720p"], audio=False, privacy="private"),
    _vid("kling-o3-pro-reference-to-video", "2026-03-20", ["5s", "10s", "15s"], ["720p", "1080p"]),
    _img("nano-banana-pro-edit", "2025-11-20", {"resolutions": {"1K": {"usd": 0.18}, "2K": {"usd": 0.23}},
                                                "upscale": {"2x": {"usd": 0.02}, "4x": {"usd": 0.08}}}, 3),
    _img("seedream-v5-pro-edit", "2026-05-01", {"generation": {"usd": 0.06}, "upscale": {"2x": {"usd": 0.02}}}, 3),
    _img("seedream-v5-pro", "2026-05-01", {"resolutions": {"1K": {"usd": 0.06}, "2K": {"usd": 0.11}}}),
    _img("krea-2-turbo", "2026-09-01", {"resolutions": {"1K": {"usd": 0.04}, "2K": {"usd": 0.06}}}, privacy="private"),
    {"id": "tts-kokoro", "type": "tts", "tokentide": _tt("private"),
     "model_spec": {"privacy": "private", "voices": ["af_sky", "am_adam", "ef_dora"]}},
    {"id": "elevenlabs-music", "type": "music", "created": _ts("2026-06-01"), "tokentide": _tt("anonymized"),
     "model_spec": {"privacy": "anonymized"}},
    {"id": "elevenlabs-sound-effects", "type": "music", "created": _ts("2026-06-01"), "tokentide": _tt("anonymized"),
     "model_spec": {"privacy": "anonymized"}},
    {"id": "mock-vision", "type": "text", "tokentide": _tt("private"),
     "model_spec": {"privacy": "private", "capabilities": {"supportsVision": True}}},
]


def list_price(b, kind):
    m = b.get("model", "")
    if kind == "audio":
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
        if not a.startswith("Bearer tt_"):
            self._err(401, "invalid_api_key", "Missing or invalid API key")
            return False
        return True

    def _charge(self, list_usd):
        m = float(MULT["lowtide"] if self.headers.get("X-Tokentide-Lane") == "lowtide" else MULT["standard"])
        return (round(list_usd * m, 6), list_usd)

    def do_GET(self):
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
                                               "image_requests_per_minute": 30}})
        if p.startswith("/image/styles"):
            return self._send(200, {"data": ["Cinematic"]})
        self._err(404, "not_found", f"Unknown route {p}")

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
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
            if STATE["queue_calls"] == 1:
                return self._err(429, "rate_limited", "Too many requests", headers={"Retry-After": "1"})
            if key:
                STATE["idem"].add(key)
            allowed = {"model", "prompt", "negative_prompt", "duration", "resolution", "aspect_ratio", "audio",
                       "image_url", "end_image_url", "seed", "duration_seconds", "force_instrumental"}
            bad = sorted(set(b) - allowed)
            if bad:
                return self._err(400, "invalid_request", f"Unknown field {bad[0]}", param=bad[0])
            unfinished = [j for j in STATE["jobs"].values() if not j["gone"]]
            if len(unfinished) >= 8:
                return self._err(429, "rate_limited", "Too many unfinished jobs", headers={"Retry-After": "2"})
            qid = uuid.uuid4().hex[:10]
            STATE["jobs"][qid] = {"n": 0, "kind": kind, "gone": False}
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
                return self._send(200, MEDIA["music.mp3"], "audio/mpeg")
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
    env = {**os.environ, "TOKENTIDE_BASE_URL": f"http://127.0.0.1:{srv.server_port}/v1",
           "TOKENTIDE_API_KEY": "tt_test_mock", "TOKENTIDE_IMAGE_RPM": "30"}
    env.pop("TOKENTIDE_API_KEY_FILE", None)
    root = work / "projects" / "selftest-bottle"
    spec = root / "briefs" / "v01.json"
    results = []

    def run(name, *args, ok=(0,)):
        t0 = time.time()
        r = subprocess.run([sys.executable, str(HERE / args[0]), *map(str, args[1:])], env=env, cwd=work,
                           capture_output=True, text=True)
        good = r.returncode in ok
        results.append((good, name, time.time() - t0))
        print(f"{'PASS' if good else 'FAIL'}  {name}  ({time.time() - t0:.1f}s)")
        if not good:
            print((r.stdout + r.stderr)[-2500:])
        return r

    run("init project", "init_project.py", "Selftest Bottle", "--root", work / "projects", "--budget-usd", "20")
    ff(["-f", "lavfi", "-i", "testsrc2=size=1200x1600:rate=1", "-frames:v", "1", root / "assets/product/front.jpg"])
    ff(["-f", "lavfi", "-i", "color=c=white:s=400x120,format=rgba", "-frames:v", "1", root / "assets/brand/logo.png"])
    run("doctor (status/market/account/catalog)", "doctor.py", "--project", root)
    run("models list (cache)", "models.py", "list", "--type", "all", "--out", root / "models.json")
    r = run("models recommend (tide prices + quotes)", "models.py", "recommend", "--project", root)
    print("\n".join(l for l in r.stdout.splitlines() if l.startswith(("| Premium", "| Balanced", "| Budget", "| Newest", "| Private", "## ", "> "))))
    run("models choose", "models.py", "choose", "--project", root, "keyframe=nano-banana-pro-edit", "scene=seedream-v5-pro",
        "i2v=kling-v3-pro-image-to-video", "i2v_audio=seedance-2-5-image-to-video-basic", "tts=tts-kokoro",
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
    run("tts", "audio.py", "tts", "--spec", spec)
    run("transcribe+align", "audio.py", "transcribe", "--spec", spec)
    run("captions", "captions.py", "--spec", spec)
    run("assemble master (generated music + sfx)", "assemble.py", "--spec", spec)
    run("qa check", "qa.py", "check", root / "renders/v01_master.mp4", "--spec", spec)
    run("qa frames", "qa.py", "frames", root / "renders/v01_master.mp4", "--every", "1")
    run("qa safezone", "qa.py", "safezone", root / "renders/v01_master.mp4", "--t", "1.0")
    run("qa vision (mock)", "qa.py", "vision", "--images", root / "keyframes/v01_s1_k1.png", "--reference",
        root / "assets/product/front.jpg")
    run("package", "package.py", "--spec", spec)
    run("metrics template", "metrics.py", "template", "--out", root / "logs/perf_test.csv")
    with open(root / "logs/perf_test.csv", "a", encoding="utf-8") as fh:
        fh.write("tt_002,v02,tiktok,2026-11-04 19:00,72,12,900,880,3.1,9,31,20,2,1,,3,1,10,,B-callout,myth-bust,edu,\n")
        fh.write("tt_003,v03,tiktok,2026-11-05 19:00,72,14,20000,19000,8.4,32,66,1500,120,400,,300,210,900,,C-pov,pov,story,\n")
    run("metrics analyze", "metrics.py", "analyze", "--csv", root / "logs/perf_test.csv")
    r = run("budget (exact charges + live account)", "budget.py", "--project", root, "--live")
    print("\n".join(r.stdout.splitlines()[:4]))
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
