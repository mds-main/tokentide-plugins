#!/usr/bin/env python3
"""Live model catalog (Tokentide, proxying Venice): model levels, the user's own picks, and total quotes.

New image and video models ship constantly, so never hard-code one. Every new request starts with one
question: does the user name the models, or do we recommend them? Specs refer to the picks by alias
("@i2v", "@keyframe", ...), so switching models is one command.

  tiers      recommend: Essential / Pro / Max per job from the 30 most recent models of each job, rated by
             Artificial Analysis (--ranks ranks.json, written from its leaderboards) and priced by Tokentide
             (live quotes for video and music, catalog prices for images and voices). Each level is a point on
             the price/quality frontier: Essential = best rated among the cheapest, Pro = best rated in the
             middle price band, Max = best rated at any price. Writes model_tiers.md/.json with a cost per level.
  match      the user names models: finds them in the live catalog ("Kling 4", "nano banana 2.1"), per job,
             or says they are not available on Tokentide and lists the closest ones
  cost       total price for a planned batch with the chosen models (or --tier): a QUOTE when every line is
             priced live by Tokentide, otherwise an ESTIMATE (and says why)
  choose     store picks in project.json "models":  choose --project P --tier pro  |  choose --project P i2v=<id> ...
  recommend  detailed options per job (Premium / Alt premium / Balanced / Budget / Newest / Private)
  list       catalog table, filters --type/--find; --out caches the raw JSON (models.json)
  show ID    accepted durations, resolutions and aspect ratios, then the full JSON entry (--json: JSON only)

Jobs: keyframe (product into scene, edit models) · scene (image generation) · i2v (image-to-video) ·
      i2v_audio (image-to-video with native audio) · r2v (reference-to-video: characters/objects) ·
      t2v (text-to-video, product-free B-roll) · upscale (video upscale) · tts (voice-over) · music · sfx
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import common
import apiclient as api

TYPES = ["text", "image", "video", "tts", "asr", "upscale", "inpaint", "embedding", "music"]
JOBS = {
    "keyframe": ("image", "Keyframe: real product composited into a scene (edit / multi-edit)"),
    "scene": ("image", "Scene / background image generation (no product)"),
    "i2v": ("video", "Product image-to-video (audio off; VO/music added in post)"),
    "i2v_audio": ("video", "Image-to-video with native sound (pours, clicks, ambience)"),
    "r2v": ("video", "Reference-to-video: consistent characters / objects across shots"),
    "t2v": ("video", "Text-to-video: product-free B-roll"),
    "upscale": ("video", "Video upscale (finishing)"),
    "tts": ("tts", "Voice-over (TTS)"),
    "music": ("music", "Original background music (rights-safe)"),
    "sfx": ("music", "Sound effects (whooshes, pops, pours)"),
}
# Rough quality prior per family (Nov 2026). Only a tie-breaker: leaderboard --ranks override it, and
# unknown/new families start mid-pack so new releases are never buried.
FAMILY_PRIOR = {
    "veo": 3.0, "sora": 3.0, "kling": 2.8, "kling-o": 2.8, "seedance": 2.8, "runway": 2.4, "hailuo": 2.4,
    "minimax": 2.4, "wan": 2.3, "gemini-omni": 2.3, "luma": 2.2, "ray": 2.2, "vidu": 2.1, "grok-imagine": 2.0,
    "hunyuan": 2.0, "ltx": 1.9, "pika": 1.8,
    "nano-banana": 2.9, "gpt-image": 2.9, "seedream": 2.7, "flux": 2.5, "qwen-image": 2.4, "ideogram": 2.3,
    "recraft": 2.3, "luma-uni": 2.2, "hidream": 2.0, "firered": 1.8, "chroma": 1.6, "z-image": 1.6,
    "venice-sd": 1.5,
}
DEFAULT_PRIOR = 2.3
LANE = "standard"  # price lane used for image prices and quotes (--lane)
NATIVE_AUDIO_FAMILIES = {"veo", "seedance", "kling", "kling-o", "ltx", "sora", "wan", "gemini-omni"}
TIER_WORDS = {"premium": r"ultra|max|full|pro|premium|prime|master|hd",
              "fast": r"fast|turbo|flash|mini|lite|draft|schnell|distilled|lightning"}
STOP_TOKENS = {"video", "edit", "private", "basic", "i2v", "t2v", "r2v", "v2v", "upscale", "standard", "std", "public"}

# The three levels offered to the user (references/models.md has the wording in each language).
LEVELS = ("essential", "pro", "max")
LEVEL_NAMES = {"essential": "Essential", "pro": "Pro", "max": "Max"}
LEVEL_WHY = {"essential": "best rated among the low-cost models", "pro": "best rated in the middle price range",
             "max": "best rated at any price"}
# Jobs that get a level pick (the user's four choices: video, images, voice, music) and the leaderboard each uses.
TIER_JOBS = ("i2v", "keyframe", "scene", "tts", "music")
BOARDS = {"i2v": "video", "i2v_audio": "video", "r2v": "video", "t2v": "video_t2v", "keyframe": "image_edit",
          "scene": "image", "tts": "tts", "music": "music"}
BOARD_FALLBACK = {"video_t2v": "video"}
AA_BOARDS = {  # board -> (what it rates, Artificial Analysis leaderboard page as of Nov 2026)
    "video": ("turning an image into video", "https://artificialanalysis.ai/video/leaderboard/image-to-video"),
    "image_edit": ("editing images", "https://artificialanalysis.ai/image/leaderboard/editing"),
    "image": ("creating images from text", "https://artificialanalysis.ai/image/leaderboard/text-to-image"),
    "tts": ("text to speech", "https://artificialanalysis.ai/text-to-speech/leaderboard/provider-voice"),
    "music": ("instrumental music", "https://artificialanalysis.ai/music/leaderboard/instrumental"),
    "video_t2v": ("text to video", "https://artificialanalysis.ai/video/leaderboard/text-to-video"),
}
BG_REMOVE_LIST_USD = 0.03  # /image/background-remove (bria-bg-remover, not in the catalog): flat list price
# A planned batch, priced by `cost` and `tiers` (override with the flags of the same name).
PLAN = {"videos": 3, "shots": 3, "takes": 2, "clip_seconds": 5, "resolution": "1080p", "audio_shots": 1,
        "keyframes": 3, "scenes": 3, "vo_chars": 260, "music_seconds": 20, "sfx": 2, "sfx_seconds": 2, "cutouts": 2}


# ---------------------------------------------------------------- catalog
def fetch(kind: str) -> list:
    try:
        j = api.get(f"/models?type={kind}", retries=3).json()
    except api.APIError as e:
        if e.status in (400, 404, 422):
            return []
        raise
    data = j.get("data", []) if isinstance(j, dict) else j
    for m in data:
        if kind != "all":
            m.setdefault("type", kind)
    return data


def fetch_all(kind: str) -> list:
    if kind != "all":
        return fetch(kind)
    data = fetch("all")
    have = {m.get("type") for m in data}
    for t in TYPES:
        if t not in have:
            data += fetch(t)
    seen, out = set(), []
    for m in data:
        if m.get("id") not in seen:
            seen.add(m.get("id"))
            out.append(m)
    return out


def catalog(a) -> list:
    if getattr(a, "cache", None):
        return list(common.load_models(path=a.cache).values())
    models = fetch_all("all")
    out = getattr(a, "out", None)
    if not out and getattr(a, "project", None):
        out = Path(a.project) / "models.json"
    if out:
        common.save_json(out, {"fetched": common.now_iso(), "data": models})
        common.log(f"cached {len(models)} models -> {out}")
    return models


# ---------------------------------------------------------------- traits
def spec(m) -> dict:
    return m.get("model_spec") or {}


def tt(m) -> dict:
    return m.get("tokentide") or {}


def tt_multiplier(m, lane="standard"):
    v = (tt(m).get(lane) or {}).get("multiplier") if isinstance(tt(m).get(lane), dict) else None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def display_name(m) -> str:
    return str(spec(m).get("name") or m.get("id"))


def privacy(m) -> str:
    p = tt(m).get("privacy_tier") or spec(m).get("privacy") or spec(m).get("privacyLevel")
    if p:
        return str(p).lower()
    traits = [str(t).lower() for t in spec(m).get("traits") or []]
    return "private" if any("private" in t for t in traits) or m.get("id", "").endswith("-private") else "?"


def video_mode(m) -> str:
    mid = m["id"].lower()
    if "upscale" in mid:
        return "upscale"
    if "motion-control" in mid:
        return "motion"
    if "reference-to-video" in mid or mid.endswith("-r2v"):
        return "r2v"
    if "image-to-video" in mid or mid.endswith("-i2v"):
        return "i2v"
    if "text-to-video" in mid or mid.endswith("-text") or mid.endswith("-t2v"):
        return "t2v"
    if "edit-video" in mid or "video-to-video" in mid or mid.endswith("-v2v"):
        return "v2v"
    mt = str(spec(m).get("model_type") or spec(m).get("modelType") or
             (spec(m).get("constraints") or {}).get("model_type") or "").lower()
    for key, mode in (("reference", "r2v"), ("image", "i2v"), ("text", "t2v"), ("video", "v2v")):
        if key in mt:
            return mode
    return "?"


def image_kind(m) -> str:
    if m.get("type") == "inpaint":  # Venice's type for edit / multi-edit models
        return "edit"
    mid = m["id"].lower()
    if "upscal" in mid:
        return "upscale"
    if "background" in mid or "bg-remove" in mid or "remove-bg" in mid:
        return "bg"
    caps = {k.lower(): v for k, v in (spec(m).get("capabilities") or {}).items()}
    if "edit" in mid or "inpaint" in mid or caps.get("supportsedit") or caps.get("supportsimageedit"):
        return "edit"
    return "gen"


def audio_kind(m) -> str:
    """What a model of type "music" (Tokentide's queued audio route) makes: music, sfx, tts (a voice read from
    text, e.g. ElevenLabs TTS v4) or other (voice changer)."""
    mid = m["id"].lower()
    if re.search(r"voice[-_ ]?changer|speech[-_ ]?to[-_ ]?speech", mid):
        return "other"
    if re.search(r"(^|[-_])tts([-_]|$)|text[-_]to[-_]speech", mid):
        return "tts"
    if re.search(r"sfx|sound[-_ ]?effect|text[-_]to[-_]audio", mid):
        return "sfx"
    return "music"


def queued_tts(m) -> bool:
    """TTS models served through the queued audio route (/audio/quote|queue|retrieve) rather than /audio/speech."""
    return m.get("type") == "music" and audio_kind(m) == "tts"


def tier(mid: str) -> str:
    t = mid.lower()
    for name, pat in TIER_WORDS.items():  # premium is checked first
        if re.search(rf"(^|[-_.])({pat})($|[-_.])", t):
            return name
    return "standard"


def family_version(mid: str):
    """'veo3.1-full-image-to-video' -> ('veo', (3, 1)); 'kling-o3-pro-…' -> ('kling-o', (3,));
    'gpt-image-2-edit' -> ('gpt-image', (2,)); 'nano-banana-pro-edit' -> ('nano-banana', ())."""
    base = re.sub(r"(image|text|reference)-to-video|edit-video|video-to-video|motion-control", "", mid.lower())
    toks = [t for t in re.split(r"[-_]", base) if t]
    tierpat = f"{TIER_WORDS['premium']}|{TIER_WORDS['fast']}"
    fam, rest = [], []
    for i, tok in enumerate(toks):
        if re.search(r"\d", tok):
            alpha = re.match(r"[a-z]+", tok)
            if alpha and alpha.group() not in ("v", "gen", "ver") and not re.fullmatch(r"\d+(k|p|b|fps)", tok):
                fam.append(alpha.group())  # veo3.1 -> veo, o3 -> o, sd35 -> sd
            rest = toks[i:]
            break
        if tok in STOP_TOKENS or re.fullmatch(tierpat, tok):
            continue
        fam.append(tok)
    family = "-".join(fam) or (toks[0] if toks else mid)
    nums = []
    for tok in rest:
        if re.fullmatch(r"\d+(k|p|b|fps)|\d+\.\d+b", tok):
            continue  # resolution / parameter-size tokens are not versions
        nums += [int(x) for x in re.findall(r"\d+", tok)]
        if len(nums) >= 2:
            break
    return family, tuple(nums[:2])


def res_px(s) -> float:
    s = str(s).lower()
    return {"8k": 4320, "4k": 2160, "2k": 1440, "1k": 1080}.get(s, num(s))


def bool_caps(m, *needles) -> bool | None:
    vals = [v for v in common.spec_lookup(m, *needles).values() if isinstance(v, bool)]
    return any(vals) if vals else None


def lists(m, needle):
    for v in common.spec_lookup(m, needle).values():
        if isinstance(v, list) and v:
            return [str(x) for x in v]
    return []


def num(s) -> float:
    x = re.search(r"\d+(?:\.\d+)?", str(s))
    return float(x.group()) if x else 0.0


def created(m):
    c = m.get("created") or spec(m).get("created") or spec(m).get("releaseDate")
    try:
        if isinstance(c, (int, float)):
            return dt.datetime.fromtimestamp(c / 1000 if c > 1e12 else c, dt.timezone.utc)
        if isinstance(c, str) and c:
            return dt.datetime.fromisoformat(c.replace("Z", "+00:00"))
    except (ValueError, OSError):
        pass
    return None


def image_price(m):
    flat = common.flatten(spec(m).get("pricing") or {})
    flat = {k: v for k, v in flat.items() if "upscale" not in k.lower() and "inputimages" not in k.lower()}
    nums = {k.lower(): float(v) for k, v in flat.items() if isinstance(v, (int, float)) and "usd" in k.lower()}
    if not nums:
        nums = {k.lower(): float(v) for k, v in flat.items() if isinstance(v, (int, float)) and "diem" not in k.lower()}
    for hint in ("2k", "1k", "high", "generation"):
        hits = [v for k, v in nums.items() if hint in k]
        if hits:
            return max(hits)
    return max(nums.values()) if nums else None


def extra_input_price(m):
    """List price per input image beyond the included ones (some edit models charge for a second image)."""
    pr = (spec(m).get("pricing") or {}).get("inputImages") or {}
    try:
        return float((pr.get("additional") or {}).get("usd")), int(pr.get("included") or 1)
    except (TypeError, ValueError):
        return 0.0, 1


def tts_price_1k(m, lane="standard"):
    """(Tokentide price, list price) per 1,000 characters of voice-over, from the catalog."""
    mult = tt_multiplier(m, lane)
    pricing = spec(m).get("pricing") or {}
    lst = None
    try:
        if isinstance(pricing.get("per_thousand_characters"), dict):
            lst = float(pricing["per_thousand_characters"]["usd"])
        elif isinstance(pricing.get("input"), dict):  # /audio/speech models: USD per 1M characters
            lst = float(pricing["input"]["usd"]) / 1000
    except (KeyError, TypeError, ValueError):
        lst = None
    lane_prices = tt(m).get(lane) if isinstance(tt(m).get(lane), dict) else {}
    try:
        if lane_prices.get("per_unit") and "1m" in str(lane_prices.get("unit") or "").lower():
            return float(lane_prices["per_unit"]) / 1000, lst
    except (TypeError, ValueError):
        pass
    if lst is None:
        return None, None
    return (round(lst * mult, 6) if mult else lst), lst


# ---------------------------------------------------------------- Artificial Analysis scores
GENERIC_WORDS = {"video", "image", "images", "edit", "editing", "tts", "text", "to", "speech", "audio", "model",
                 "i2v", "t2v", "r2v", "reference", "basic", "private", "and", "the", "v"}
VENDOR_WORDS = {"eleven", "minimax", "dreamina", "bytedance", "google", "openai", "xai", "alibaba", "tencent",
                "kuaishou", "microsoft", "bfl"}
SYNONYMS = {"elevenlabs": "eleven"}


def _name_tokens(text: str) -> list:
    x = re.sub(r"\b\d+(?:\.\d+)?[mb]\b", " ", text)  # parameter sizes: 82M, 1.7B
    x = re.sub(r"\b\d{3,4}p\b|\b[248]k\b|\b\d{4}-\d{2}-\d{2}\b", " ", x)  # resolutions, dates
    out = []
    for t in re.findall(r"[a-z]+|\d+(?:\.\d+)*", x):
        if t[0].isdigit():
            parts = [str(int(p)) for p in t.split(".")]
            while len(parts) > 1 and parts[-1] == "0":
                parts.pop()
            t = ".".join(parts)  # "3.0" -> "3", "02" -> "2"
        t = SYNONYMS.get(t, t)
        if t not in GENERIC_WORDS:
            out.append(t)
    return out


def name_key(name: str):
    """'Dreamina Seedance 2.5' / 'Seedance 2.5' -> (('seedance', '2.5'), {'dreamina'}, ()). Text in brackets
    (a resolution, '(Pro)', '(max)') is kept apart: it may or may not be part of the model's name."""
    s = str(name or "").lower()
    s = re.sub(r"(?<=\d)-(?=\d)", ".", s) if re.fullmatch(r"[a-z0-9.\-_]+", s) else s  # ids: 'seedance-2-5' -> 2.5
    paren = " ".join(re.findall(r"[\(\[]([^\)\]]*)[\)\]]", s))
    core = _name_tokens(re.sub(r"[\(\[][^\)\]]*[\)\]]", " ", s))
    return (tuple(t for t in core if t not in VENDOR_WORDS), frozenset(t for t in core if t in VENDOR_WORDS),
            tuple(_name_tokens(paren)))


def same_model(lb, cat) -> bool:
    """A leaderboard name and a catalog name denote the same model: same words apart from vendor names
    (which one side may omit) and, on the leaderboard side, an optional bracketed qualifier."""
    if not lb[0] or not cat[0]:
        return False
    if lb[1] and cat[1] and not (lb[1] & cat[1]):
        return False  # 'Eleven Music v2.5' is not 'MiniMax Music 2.5'
    if not any(t[0].isalpha() for t in lb[0]) and not (lb[1] & cat[1]):
        return False  # a bare version ('Eleven v4' -> '4') needs the vendor on both sides: 'TTS-1' is not 'xAI TTS v1'
    return cat[0] == lb[0] or bool(lb[2]) and cat[0] == lb[0] + lb[2]


def model_keys(m) -> list:
    keys = [name_key(display_name(m))]
    k = name_key(m.get("id", ""))
    if k not in keys:
        keys.append(k)
    return keys


def _entries(items) -> list:
    out = []
    for e in items or []:
        if not isinstance(e, dict):
            continue
        try:
            s = float(e.get("elo", e.get("score")))
        except (TypeError, ValueError):
            continue
        out.append({"id": e.get("id"), "match": str(e["match"]).lower() if e.get("match") else None,
                    "name": e.get("name"), "score": s, "rank": e.get("rank"),
                    "key": name_key(e["name"]) if e.get("name") else None})
    for i, e in enumerate(sorted(out, key=lambda x: -x["score"])):
        e.setdefault("pos", i + 1)
        if not e["rank"]:
            e["rank"] = i + 1
    return out


def load_ranks(path) -> dict:
    """Leaderboard scores per board: {"boards": {board: [entries]}, "source", "date"}.
    New format: {"source", "date", "boards": {"video": {"url", "entries": [{"name", "elo", "id"?, "rank"?}]}, ...}}.
    Old format ({"entries": [{"match", "score"}]} or {match: score}) becomes one board "*" every job uses."""
    if not path:
        return {"boards": {}}
    data = common.load_json(path)
    boards = {}
    if isinstance(data, dict) and isinstance(data.get("boards"), dict):
        for b, v in data["boards"].items():
            boards[b] = _entries(v.get("entries", []) if isinstance(v, dict) else v)
    else:
        items = data.get("entries", data) if isinstance(data, dict) else data
        if isinstance(items, dict):
            items = [{"match": k, "score": v} for k, v in items.items() if k not in ("source", "date", "notes")]
        boards["*"] = _entries(items)
    meta = data if isinstance(data, dict) else {}
    urls = {b: (v.get("url") if isinstance(v, dict) else None) for b, v in (meta.get("boards") or {}).items()}
    return {"boards": {k: v for k, v in boards.items() if v}, "source": meta.get("source"), "date": meta.get("date"),
            "urls": urls}


def board_for(job, ranks):
    boards = ranks.get("boards") or {}
    b = BOARDS.get(job)
    if b in boards:
        return b
    if BOARD_FALLBACK.get(b) in boards:
        return BOARD_FALLBACK[b]
    return "*" if "*" in boards else None


def lb_entry(m, entries):
    """The leaderboard entry for a catalog model: an exact `id`, else the longest `match` substring of the id,
    else the same name (the highest score when several names fit)."""
    mid = m["id"].lower()
    exact = [e for e in entries if e.get("id") and str(e["id"]).lower() == mid]
    if exact:
        return max(exact, key=lambda e: e["score"])
    subs = [e for e in entries if e.get("match") and e["match"] in mid]
    if subs:
        return max(subs, key=lambda e: len(e["match"]))
    keys = model_keys(m)
    named = [e for e in entries if e.get("key") and not e.get("id") and not e.get("match")
             and any(same_model(e["key"], k) for k in keys)]
    return max(named, key=lambda e: e["score"]) if named else None


# ---------------------------------------------------------------- recommend
def describe(m, job):
    mid = m["id"]
    fam, ver = family_version(mid)
    d = {"id": mid, "name": display_name(m), "job": job, "family": fam, "version": ".".join(map(str, ver)) if ver else "",
         "_ver": ver, "_m": m, "tier": tier(mid), "privacy": privacy(m), "created": created(m),
         "offline": bool(spec(m).get("offline")), "deprecated": bool(spec(m).get("deprecation") or spec(m).get("deprecated")),
         "traits": [str(t).lower() for t in spec(m).get("traits") or []]}
    if JOBS[job][0] == "video":
        durs = lists(m, "duration")
        ress = lists(m, "resolution")
        d.update(durations=durs, resolutions=ress, aspects=lists(m, "aspect"),
                 max_dur=max([num(x) for x in durs], default=None), max_res=max(ress, key=res_px) if ress else None,
                 audio=bool_caps(m, "audio"), end_frame=bool_caps(m, "endimage", "end_image", "lastframe"))
        if d["audio"] is None and fam in NATIVE_AUDIO_FAMILIES:
            d["audio_guess"] = True
    elif JOBS[job][0] == "image":
        caps = common.spec_lookup(m, "maxinputimages", "max_input_images")
        mx = [v for v in caps.values() if isinstance(v, (int, float))]
        lp = image_price(m)
        mult = tt_multiplier(m, LANE)
        d.update(list_price=lp, price=round(lp * mult, 4) if (lp is not None and mult) else lp, multiplier=mult,
                 max_inputs=int(mx[0]) if mx else None, resolutions=lists(m, "resolution"))
    if JOBS[job][0] in ("video", "music") or job == "tts":
        lt = tt(m).get("lowtide") if isinstance(tt(m).get("lowtide"), dict) else {}
        d["lowtide_ok"] = bool(lt.get("eligible")) if lt else None
    if job == "tts":
        voices = lists(m, "voice")
        p1k, l1k = tts_price_1k(m, LANE)
        d.update(voices=len(voices), sample_voices=voices[:6], queued=queued_tts(m), price=p1k, list_price=l1k)
    return d


def candidates(models, job, prune=True):
    kind = JOBS[job][0]
    out = []
    for m in models:
        mt = m.get("type")
        if kind == "image" and mt not in ("image", "inpaint"):  # edit models are type "inpaint"
            continue
        if kind == "video" and mt != "video":
            continue
        if kind == "tts" and not (mt == "tts" or queued_tts(m)):
            continue
        if kind == "music":
            if mt != "music" or audio_kind(m) != job:
                continue
        if kind == "image":
            ik = image_kind(m)
            if (job == "keyframe" and ik != "edit") or (job == "scene" and ik != "gen"):
                continue
        if kind == "video":
            vm = video_mode(m)
            want = {"i2v": "i2v", "i2v_audio": "i2v", "r2v": "r2v", "t2v": "t2v", "upscale": "upscale"}[job]
            if vm != want:
                continue
        d = describe(m, job)
        if d["offline"] or d["deprecated"]:
            continue
        if job == "i2v_audio" and not (d.get("audio") or d.get("audio_guess")):
            continue
        out.append(d)
    if not prune:
        return out
    # keep the newest two versions per (family, mode): older generations are superseded
    by_fam = {}
    for d in out:
        by_fam.setdefault(d["family"], set()).add(d["_ver"])
    keep = []
    for d in out:
        vers = sorted(v for v in by_fam[d["family"]] if v)
        if not d["_ver"] or not vers or d["_ver"] in vers[-2:]:
            d["version_rank"] = (len(vers) - 1 - vers.index(d["_ver"])) if d["_ver"] in vers else 0
            keep.append(d)
    return keep


def normalized(entries) -> dict:
    """Leaderboard scores scaled to 0–4 within one board (so they mix with the prior's scale)."""
    if not entries:
        return {}
    lo, hi = min(e["score"] for e in entries), max(e["score"] for e in entries)
    return {id(e): (4.0 * (e["score"] - lo) / (hi - lo) if hi > lo else 3.0) for e in entries}


def quality(d, entries, now, scale=None):
    e = lb_entry(d["_m"], entries) if entries else None
    if e:
        d["quality_source"] = f"leaderboard:{e.get('name') or e.get('match') or e.get('id')}"
        d["aa"], d["aa_rank"] = e["score"], e.get("rank")
        base = (scale or normalized(entries)).get(id(e), 3.0)
    else:
        d["quality_source"] = "prior"
        base = FAMILY_PRIOR.get(d["family"], DEFAULT_PRIOR)
        base += {"premium": 0.5, "standard": 0.0, "fast": -0.6}[d["tier"]]
        base += {0: 0.4, 1: 0.0}.get(d.get("version_rank", 0), -0.3)
        if "highest_quality" in d["traits"] or "best" in d["traits"]:
            base += 0.3
    age = (now - d["created"]).days if d["created"] else None
    d["age_days"] = age
    d["new"] = age is not None and age <= 60
    if d["new"] and not e:
        base += 0.3
    return round(base, 2)


def standard_body(d, job, dur, res):
    body = {"model": d["id"]}
    durs = d.get("durations") or []
    body["duration"] = min(durs, key=lambda x: (abs(num(x) - dur), num(x))) if durs else f"{dur}s"
    if not str(body["duration"]).endswith("s"):
        body["duration"] = f"{int(num(body['duration']))}s"
    ress = d.get("resolutions") or []
    if ress:
        le = [r for r in ress if res_px(r) <= res_px(res)]
        body["resolution"] = max(le, key=res_px) if le else min(ress, key=res_px)
    else:
        body["resolution"] = res
    if d.get("aspects") and "9:16" in d["aspects"]:
        body["aspect_ratio"] = "9:16"
    if job == "i2v_audio":
        body["audio"] = True
    elif d.get("audio"):
        body["audio"] = False
    return body


def quote_all(items, job, dur, res, music_s=30, sfx_s=3):
    import video  # Tokentide-aware quote helper (throttled to the 60/min quote limit)

    def q(d):
        if JOBS[job][0] == "music":
            body = {"model": d["id"], "duration_seconds": music_s if job == "music" else sfx_s}
            kind = "audio"
        else:
            body, kind = standard_body(d, job, dur, res), "video"
        try:
            r = video.quote(body, kind)
            d["price"], d["list_price"], d["multiplier"] = r.get("usd"), r.get("list_usd"), r.get("multiplier")
            d["queue_open"] = r.get("queue_open")
            d["quoted"] = {"duration": body.get("duration") or f"{body.get('duration_seconds')}s",
                           "resolution": body.get("resolution", ""), "audio": body.get("audio")}
        except (api.APIError, ValueError, TypeError) as e:
            d["price"], d["quote_error"] = None, str(e)[:120]
        p = d.get("price") or d.get("list_price")  # free-use accounts are quoted $0: rank them on the list price
        if p and d.get("quoted"):
            d["usd_per_s"] = round(p / max(1.0, num(d["quoted"]["duration"])), 4)
    with ThreadPoolExecutor(max_workers=3) as ex:
        list(ex.map(q, items))


def pick_options(items, job):
    """A spread of choices across quality/price:
    Premium (best expected quality) · Alt premium (best of another family) · Balanced (quality per dollar)
    · Budget (clearly cheaper, still acceptable: drafts, hook tests, volume) · Newest (released ≤60 days) · Private."""
    if not items:
        return []
    items = sorted(items, key=lambda d: (-d["q"], d.get("usd_per_s") or d.get("price") or 1e9))
    main = items
    if job == "keyframe":  # compositing a real product into a scene needs ≥2 input images
        multi = [d for d in items if (d.get("max_inputs") or 2) >= 2]
        main = multi or items
    opts = []

    def add(label, d, why):
        for o in opts:
            if o["id"] == d["id"]:
                o["labels"].append(label)
                return
        opts.append({**d, "labels": [label], "why": why})

    top = main[0]
    add("Premium", top, "highest expected quality")
    alt = next((d for d in main[1:] if d["family"] != top["family"]), None)
    if alt and alt["q"] >= top["q"] - 0.8:
        add("Alt premium", alt, "top quality from another model family")
    priced = [d for d in main if d.get("price")]
    if priced:
        unit = lambda d: d.get("usd_per_s") or d["price"]  # per second for video, so 4 s and 5 s quotes compare
        ok = [d for d in priced if d["q"] >= top["q"] - 1.3] or priced
        pmin = min(unit(d) for d in ok)
        bal = max(ok, key=lambda d: d["q"] - 0.6 * math.log2(unit(d) / pmin) if pmin else d["q"])
        add("Balanced", bal, "best quality per dollar")
        wide = [d for d in priced if d["q"] >= top["q"] - 2.0] or priced
        cheaper = [d for d in wide if unit(d) <= 0.75 * unit(bal)]
        budget = min(cheaper or wide, key=lambda d: (unit(d), -d["q"]))
        add("Budget", budget, "cheapest acceptable — drafts, hook tests, volume")
    newest = [d for d in main if d.get("new")]
    if newest:
        n = max(newest, key=lambda d: (d["created"], d["q"]))
        add("Newest", n, f"released ~{n['age_days']} days ago — worth a test take")
    priv = [d for d in items if d["privacy"] == "private"]
    if priv:
        note = "" if job != "keyframe" or (priv[0].get("max_inputs") or 2) >= 2 else " (single-image edit only)"
        add("Private", priv[0], "zero data retention — confidential / unreleased products" + note)
    return opts


def fmt_price(d, job):
    p = d.get("price")
    if p is None:
        return "?"
    lp = d.get("list_price")
    lt = " · LT" if d.get("lowtide_ok") else ""
    if job == "tts":
        return f"${p:.3f}/1k chars" + (f" (list ${lp:.3f})" if lp and abs(lp - p) > 0.0005 else "") + lt
    tail = f" (list ${lp:.2f})" if lp and abs(lp - p) > 0.004 else ""
    if JOBS[job][0] in ("video", "music"):
        q = d.get("quoted") or {}
        return f"${p:.2f}/{q.get('duration', '')} {q.get('resolution', '')}".strip() + tail + lt
    return f"${p:.3f}/img" + (f" (list ${lp:.3f})" if lp and abs(lp - p) > 0.0005 else "")


def per_video(d, job, shots=3, takes=2, kf_per_shot=3):
    p = d.get("price")
    if p is None:
        return None
    return round(p * shots * takes, 2) if JOBS[job][0] == "video" else round(p * shots * kf_per_shot, 2)


def privacy_warning(models) -> list:
    privs = {privacy(m) for m in models}
    edit_models = [m for m in models if m.get("type") in ("image", "inpaint") and image_kind(m) == "edit"]
    if "anonymized" not in privs or not edit_models:
        return ["> **Your key only sees Private models.** Its privacy mode is `private` (the default for keys made before "
                "2026-11-17), which hides the anonymized models: background removal, most premium image-edit and video models, and every music "
                "model. Set the key to privacy mode `all` (or `private_text`, which keeps only text models private) "
                "in the Tokentide dashboard to get the full catalog.", ""]
    return []


def cmd_recommend(a):
    global LANE
    LANE = a.lane or "standard"
    api.set_lane(a.lane)
    if a.project:
        api.use_project(a.project)
    models = catalog(a)
    ranks = load_ranks(a.ranks)
    now = dt.datetime.now(dt.timezone.utc)
    jobs = ([j.strip() for j in a.jobs.split(",")] if a.jobs else
            ["keyframe", "scene", "i2v", "i2v_audio", "r2v", "tts", "music", "sfx"])
    report = {"generated": common.now_iso(), "standard_clip": {"duration_s": a.duration, "resolution": a.resolution},
              "ranks_file": a.ranks, "jobs": {}}
    lines = [f"# Model options — live from Tokentide {now:%Y-%m-%d} ({LANE} lane)",
             f"Quality = {'leaderboard ranks + ' if ranks['boards'] else ''}family prior, tier, recency (newest versions first). "
             f"Prices are what Tokentide charges now (Venice list × today's tide multiplier); video/music are live quotes "
             f"for one {a.duration}s clip / 30 s track. Per-video ≈ 3 shots × 2 takes (images: 3 shots × 3 variants). "
             f"LT = eligible for the cheaper Low Tide lane. Prices fall through the UTC day (cheapest just before 00:00 UTC).", ""]
    lines += privacy_warning(models)
    for job in jobs:
        if job not in JOBS:
            common.log(f"unknown job '{job}' (valid: {', '.join(JOBS)})")
            continue
        items = candidates(models, job)
        entries = ranks["boards"].get(board_for(job, ranks) or "", [])
        scale = normalized(entries)
        for d in items:
            d["q"] = quality(d, entries, now, scale)
        if JOBS[job][0] in ("video", "music") and job != "upscale" and items and not a.no_quote:
            items = sorted(items, key=lambda d: -d["q"])[: a.max_quotes]
            quote_all(items, job, a.duration, a.resolution)
        opts = pick_options(items, job) if job != "tts" else sorted(items, key=lambda d: (-d["q"], d["id"]))[:4]
        report["jobs"][job] = {"label": JOBS[job][1], "options": [], "candidates": len(items)}
        lines += [f"## {job} — {JOBS[job][1]}", ""]
        if not opts:
            lines += ["_No matching models in the live catalog._", ""]
            continue
        if job == "tts":
            lines += ["| model | voices | privacy | added | price |", "|---|---|---|---|---|"]
        elif JOBS[job][0] == "music":
            lines += ["| option | model | added | privacy | price | why |", "|---|---|---|---|---|---|"]
        elif JOBS[job][0] == "video":
            lines += ["| option | model | ver | added | max dur | max res | audio | end frame | privacy | price | ≈ per video | why |",
                      "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        else:
            lines += ["| option | model | ver | added | inputs | privacy | price | ≈ per video | why |",
                      "|---|---|---|---|---|---|---|---|---|"]
        for o in opts:
            added = o["created"].strftime("%Y-%m") if o.get("created") else "?"
            yn = lambda v, g=False: "yes" if v else ("likely" if g else ("no" if v is False else "?"))
            pv = per_video(o, job)
            if job == "tts":
                lines.append(f"| `{o['id']}` | {o.get('voices', '?')} | {o['privacy']} | {added} | {fmt_price(o, job)} |")
            elif JOBS[job][0] == "music":
                lines.append(f"| {'/'.join(o['labels'])}{' 🆕' if o.get('new') else ''} | `{o['id']}` | {added} | "
                             f"{o['privacy']} | {fmt_price(o, job)} | {o['why']} |")
            elif JOBS[job][0] == "video":
                lines.append(f"| {'/'.join(o['labels'])}{' 🆕' if o.get('new') else ''} | `{o['id']}` | {o['version'] or '-'} | {added} | "
                             f"{(str(int(o['max_dur'])) + 's') if o.get('max_dur') else '?'} | {o.get('max_res') or '?'} | "
                             f"{yn(o.get('audio'), o.get('audio_guess'))} | {yn(o.get('end_frame'))} | {o['privacy']} | "
                             f"{fmt_price(o, job)} | {('$' + format(pv, '.2f')) if pv is not None else '?'} | {o['why']} |")
            else:
                lines.append(f"| {'/'.join(o['labels'])}{' 🆕' if o.get('new') else ''} | `{o['id']}` | {o['version'] or '-'} | {added} | "
                             f"{o.get('max_inputs') or '?'} | {o['privacy']} | {fmt_price(o, job)} | "
                             f"{('$' + format(pv, '.2f')) if pv is not None else '?'} | {o['why']} |")
            report["jobs"][job]["options"].append(jsonable(o))
        lines.append("")
    lines += ["Pick per job, then: `models.py choose --project <P> i2v=<id> keyframe=<id> scene=<id> tts=<id> music=<id> sfx=<id>`",
              "Prices: video/music = live Tokentide quotes; images = Venice list × current multiplier (2K when tiered). "
              "Quality is an estimate — a test take on the shortlisted models is the real judge."]
    text = "\n".join(lines) + "\n"
    out_dir = Path(a.project) if a.project else Path(".")
    md = out_dir / "model_options.md"
    md.write_text(text, encoding="utf-8")
    common.save_json(out_dir / "model_options.json", report)
    print(text)
    print(f"saved {md} and model_options.json")


def jsonable(d) -> dict:
    return {k: (v.isoformat() if isinstance(v, dt.datetime) else v) for k, v in d.items() if not k.startswith("_")}


# ---------------------------------------------------------------- prices for a plan
class Pricer:
    """Tokentide prices for single jobs, each priced once: live quotes for video and queued audio (free),
    catalog price × the live multiplier for images and voices. Every price says how it was obtained:
    "quote" (a live Tokentide quote), "price" (Tokentide's catalog price right now) or "estimate"."""

    def __init__(self, models: dict, lane: str, fallback: dict | None = None):
        self.models, self.lane, self.cache, self.fallback = models, lane, {}, fallback or {}

    def _quote(self, body, kind):
        import video
        k = json.dumps([kind, body], sort_keys=True)
        if k not in self.cache:
            try:
                r = video.quote(body, kind)
                self.cache[k] = (r.get("usd"), r.get("list_usd"), "quote", "")
            except (api.APIError, ValueError, TypeError) as e:
                self.cache[k] = (None, None, "error", str(e).splitlines()[0][:160])
        return self.cache[k]

    def _fb(self, mid, unit, err):
        """An earlier price for this model (model_tiers.json / model_options.json), marked as an estimate."""
        fb = self.fallback.get(mid)
        if fb is not None:
            return fb * unit, None, "estimate", f"no live price ({err}); used an earlier price"
        return None, None, "missing", err or "no price"

    def video(self, mid, seconds, res, audio):
        m = self.models.get(mid)
        if not m:
            return None, None, "missing", f"{mid} is not in the catalog"
        d = describe(m, "i2v_audio" if audio else "i2v")
        body = standard_body(d, "i2v_audio" if audio else "i2v", seconds, res)
        usd, lst, basis, note = self._quote(body, "video")
        if usd is None:
            return self._fb(mid, num(body["duration"]), note)
        return usd, lst, basis, f"{body['duration']} {body.get('resolution', '')}{' with sound' if audio else ''}".strip()

    def audio(self, mid, seconds=None, chars=None):
        body = {"model": mid}
        if seconds:
            body["duration_seconds"] = int(seconds)
        if chars:
            body["character_count"] = int(chars)
        usd, lst, basis, note = self._quote(body, "audio")
        if usd is None:
            return self._fb(mid, seconds or (chars or 0) / 1000, note)
        return usd, lst, basis, note

    def image(self, mid, inputs=1):
        m = self.models.get(mid)
        if not m:
            return None, None, "missing", f"{mid} is not in the catalog"
        lp, mult = image_price(m), tt_multiplier(m, self.lane)
        if lp is None:
            return self._fb(mid, 1, "the catalog lists no image price")
        extra, included = extra_input_price(m)
        lp += extra * max(0, inputs - included)
        if not mult:
            return lp, lp, "estimate", "no live multiplier; Venice list price"
        return round(lp * mult, 6), lp, "price", ""

    def flat(self, list_usd, ref_model):
        """A fixed-price route the catalog doesn't list (background removal): its list price × the live image
        multiplier (the same for every image model)."""
        mult = tt_multiplier(self.models.get(ref_model) or {}, self.lane) if ref_model else None
        if not mult:
            return list_usd, list_usd, "estimate", "list price; no live multiplier"
        return round(list_usd * mult, 6), list_usd, "price", "flat list price"

    def tts(self, mid, chars):
        m = self.models.get(mid)
        if not m:
            return None, None, "missing", f"{mid} is not in the catalog"
        if queued_tts(m):
            usd, lst, basis, note = self.audio(mid, chars=chars)
            if usd is not None:
                return usd, lst, basis, note
        p1k, l1k = tts_price_1k(m, self.lane)
        if p1k is None:
            return self._fb(mid, chars / 1000, "the catalog lists no voice price")
        return round(p1k * chars / 1000, 6), (l1k * chars / 1000 if l1k else None), "price", ""


def plan_from(a) -> dict:
    return {k: (getattr(a, k) if getattr(a, k, None) is not None else v) for k, v in PLAN.items()}


def plan_lines(picks: dict, plan: dict, pricer: Pricer) -> list:
    """One line per kind of job in the planned batch: what, model, how many, unit price, subtotal, basis."""
    n = plan["videos"]
    rows = []

    def row(label, job, count, priced, unit_label, model=None):
        usd, lst, basis, note = priced
        rows.append({"what": label, "job": job, "model": model or picks.get(job), "count": count, "unit": unit_label,
                     "unit_usd": usd, "list_usd": lst, "basis": basis, "note": note,
                     "usd": round(usd * count, 4) if usd is not None else None,
                     "list_total": round(lst * count, 4) if lst is not None else None})

    silent = max(0, plan["shots"] - plan["audio_shots"]) if picks.get("i2v_audio") else plan["shots"]
    if picks.get("i2v") and silent:
        row("Video clips", "i2v", n * silent * plan["takes"],
            pricer.video(picks["i2v"], plan["clip_seconds"], plan["resolution"], False), "clip")
    if picks.get("i2v_audio") and plan["audio_shots"]:
        row("Video clips with sound", "i2v_audio", n * min(plan["audio_shots"], plan["shots"]) * plan["takes"],
            pricer.video(picks["i2v_audio"], plan["clip_seconds"], plan["resolution"], True), "clip")
    if picks.get("keyframe"):
        row("Product images", "keyframe", n * plan["shots"] * plan["keyframes"], pricer.image(picks["keyframe"], 2), "image")
    if picks.get("scene") and plan["scenes"]:
        row("Background images", "scene", n * plan["scenes"], pricer.image(picks["scene"]), "image")
    if picks.get("tts") and plan["vo_chars"]:
        row("Voice-over", "tts", n, pricer.tts(picks["tts"], plan["vo_chars"]), f"{plan['vo_chars']} characters")
    if picks.get("music") and plan["music_seconds"]:
        row("Music", "music", n, pricer.audio(picks["music"], seconds=plan["music_seconds"]),
            f"{plan['music_seconds']} s track")
    if picks.get("sfx") and plan["sfx"]:
        row("Sound effects", "sfx", n * plan["sfx"], pricer.audio(picks["sfx"], seconds=plan["sfx_seconds"]),
            f"{plan['sfx_seconds']} s effect")
    if plan["cutouts"]:
        bg = picks.get("bg_remove")
        priced = pricer.image(bg) if bg else pricer.flat(BG_REMOVE_LIST_USD, picks.get("keyframe") or picks.get("scene"))
        row("Product cut-outs (once)", "bg_remove", plan["cutouts"], priced, "image", bg or "bria-bg-remover")
    return rows


def summarize(rows, plan, models, lane) -> dict:
    priced = [r for r in rows if r["usd"] is not None]
    total = round(sum(r["usd"] for r in priced), 2)
    missing = [r for r in rows if r["usd"] is None]
    estimated = [r for r in rows if r["basis"] == "estimate"]
    label = "quote" if rows and not missing and not estimated else "estimate"
    lt = None  # Low Tide: list price × each model's Low Tide multiplier, when every line has a list price
    if lane != "lowtide" and rows and all(r["list_total"] is not None for r in rows):
        s, any_lt = 0.0, False
        for r in rows:
            m = models.get(r["model"]) or {}
            low = tt(m).get("lowtide") if isinstance(tt(m).get("lowtide"), dict) else {}
            mult = tt_multiplier(m, "lowtide") if low.get("eligible") and low.get("open") is not False else None
            any_lt |= bool(mult)
            s += r["list_total"] * (mult or (r["usd"] / r["list_total"] if r["list_total"] else 1.0))
        lt = round(s, 2) if any_lt and s < total - 0.005 else None
    return {"label": label, "total_usd": total, "per_video_usd": round(total / max(1, plan["videos"]), 2),
            "lowtide_usd": lt, "missing": [r["what"] for r in missing],
            "estimated": [r["what"] for r in estimated]}


def money(x) -> str:
    return "?" if x is None else (f"${x:.2f}" if x >= 0.995 else f"${x:.3f}" if x >= 0.01 else f"${x:.4f}")


def fallback_prices(root) -> dict:
    """Unit prices seen earlier in this project (per clip second, per image, per 1k chars...), for estimates."""
    out = {}
    if not root:
        return out
    for name in ("model_tiers.json", "model_options.json"):
        data = common.load_json(Path(root) / name, default={}) or {}
        for job, j in (data.get("jobs") or {}).items():
            for o in (j.get("options") or j.get("rated") or []):
                if o.get("usd_per_s"):
                    out.setdefault(o["id"], o["usd_per_s"])
                elif o.get("price") is not None and JOBS.get(job, ("",))[0] in ("image",):
                    out.setdefault(o["id"], o["price"])
    return out


def bg_remove_model(models: dict):
    bg = [m for m in models.values() if m.get("type") in ("image", "inpaint") and image_kind(m) == "bg"
          and not spec(m).get("offline")]
    return max(bg, key=lambda m: (created(m) or dt.datetime.min.replace(tzinfo=dt.timezone.utc)))["id"] if bg else None


# ---------------------------------------------------------------- tiers (recommendation)
def frontier(items, unit):
    """The price/quality frontier: models no other model beats on both price and quality, cheapest first."""
    out, best = [], -math.inf
    for d in sorted(items, key=lambda d: (unit(d), -d["q"])):
        if d["q"] > best:
            out.append(d)
            best = d["q"]
    return out


def pick_levels(front, unit) -> dict:
    """Essential / Pro / Max on the frontier. Its price range is split in three equal steps on a log scale:
    Essential = best rated in the cheapest third, Pro = best rated up to the second third, Max = best rated.
    With three or more frontier models the three levels are always three different models."""
    n = len(front)
    if not n:
        return {}
    top = front[-1]
    if n == 1:
        return {"essential": top, "pro": top, "max": top}
    if n == 2:
        return {"essential": front[0], "pro": top, "max": top}
    lo, hi = unit(front[0]), unit(top)
    r = (hi / lo) if lo else 1.0
    e1, e2 = lo * r ** (1 / 3) * 1.0001, lo * r ** (2 / 3) * 1.0001
    ie = max([i for i in range(n - 2) if unit(front[i]) <= e1] or [0])
    ip = max([i for i in range(ie + 1, n - 1) if unit(front[i]) <= e2] or [ie + 1])
    return {"essential": front[ie], "pro": front[ip], "max": top}


def recent(items, n):
    old = dt.datetime.min.replace(tzinfo=dt.timezone.utc)
    return sorted(items, key=lambda d: (d["created"] or old, d["id"]), reverse=True)[:n]


def unit_of(d, job):
    if JOBS[job][0] == "video":
        return d.get("usd_per_s")
    return d.get("price") or d.get("list_price")  # $0 on free-use accounts: rank on the list price


def tier_job(models, job, ranks, now, a, pricer) -> dict:
    """Levels for one job: the a.recent most recent models, their leaderboard scores and Tokentide prices."""
    items = recent(candidates(models, job, prune=False), a.recent)
    if job == "keyframe":  # compositing a real product into a scene needs ≥2 input images
        items = [d for d in items if (d.get("max_inputs") or 2) >= 2] or items
    entries = ranks["boards"].get(board_for(job, ranks) or "", [])
    scale = normalized(entries)
    for d in items:
        d["q"] = quality(d, entries, now, scale)
    rated = [d for d in items if d["quality_source"] != "prior"]
    basis = "leaderboard" if rated else "estimated"
    pool = rated or items
    if JOBS[job][0] in ("video", "music") and pool and not a.no_quote:
        pool = sorted(pool, key=lambda d: -d["q"])[: a.max_quotes]
        quote_all(pool, job, a.clip_seconds or PLAN["clip_seconds"], a.resolution or PLAN["resolution"],
                  music_s=a.music_seconds or PLAN["music_seconds"])
    priced = [d for d in pool if unit_of(d, job)]
    front = frontier(priced, lambda d: unit_of(d, job))
    levels = pick_levels(front, lambda d: unit_of(d, job))
    unrated = [d for d in items if d["quality_source"] == "prior" and basis == "leaderboard"]
    return {"job": job, "board": board_for(job, ranks), "basis": basis, "recent": len(items), "rated": rated,
            "unrated": unrated, "priced": priced, "frontier": front, "levels": levels,
            "unpriced": [d for d in pool if not unit_of(d, job)]}


def audio_pick(i2v_res, level, models):
    """The model for shots that need real sound: the level's video model when it makes sound, else the best
    rated video model with sound that costs no more."""
    pick = i2v_res["levels"].get(level)
    if not pick:
        return None
    if pick.get("audio") or pick.get("audio_guess"):
        return pick["id"]
    unit = lambda d: d.get("usd_per_s") or math.inf
    sound = [d for d in i2v_res["priced"] if d.get("audio") or d.get("audio_guess")]
    cheaper = [d for d in sound if unit(d) <= unit(pick)]
    if cheaper:
        return max(cheaper, key=lambda d: d["q"])["id"]
    return min(sound, key=unit)["id"] if sound else None


def sfx_pick(models, music_id, n_recent):
    items = recent(candidates(models, "sfx", prune=False), n_recent)
    if not items:
        return None
    vendor = (music_id or "").split("-")[0]
    same = [d for d in items if d["id"].split("-")[0] == vendor]
    return (same or items)[0]["id"]


def level_cell(d, job) -> str:
    if not d:
        return "—"
    u = unit_of(d, job)
    if JOBS[job][0] == "video":
        price = f"{money(u)}/s"
    elif job == "tts":
        price = f"{money(u)}/1k chars"
    elif JOBS[job][0] == "music":
        price = f"{money(d.get('price'))}/{(d.get('quoted') or {}).get('duration', 'track')}"
    else:
        price = f"{money(u)}/image"
    rank = f" · AA #{d['aa_rank']}" if d.get("aa_rank") else ""
    return f"{d['name']} (`{d['id']}`){rank} · {price}"


def cmd_tiers(a):
    global LANE
    LANE = a.lane or "standard"
    api.set_lane(a.lane)
    root = Path(a.project) if a.project else None
    if root:
        api.use_project(root)
    models_list = catalog(a)
    models = {m["id"]: m for m in models_list}
    ranks = load_ranks(a.ranks)
    now = dt.datetime.now(dt.timezone.utc)
    plan = plan_from(a)
    pricer = Pricer(models, LANE, fallback_prices(root))
    res = {job: tier_job(models_list, job, ranks, now, a, pricer) for job in TIER_JOBS}
    bg = bg_remove_model(models)
    report = {"generated": common.now_iso(), "lane": LANE, "plan": plan, "recent": a.recent,
              "source": {"name": ranks.get("source") or "Artificial Analysis", "date": ranks.get("date"),
                         "urls": {b: (ranks.get("urls") or {}).get(b) or AA_BOARDS.get(b, ("", ""))[1]
                                  for b in ranks["boards"]}},
              "jobs": {}, "tiers": {}}
    for job, r in res.items():
        report["jobs"][job] = {"board": r["board"], "basis": r["basis"], "recent": r["recent"],
                               "rated": [jsonable(d) for d in r["rated"]],
                               "frontier": [d["id"] for d in r["frontier"]],
                               "levels": {lv: (d["id"] if d else None) for lv, d in r["levels"].items()},
                               "not_rated": [d["id"] for d in r["unrated"]],
                               "unpriced": {d["id"]: d.get("quote_error", "no price") for d in r["unpriced"]}}
    for lv in LEVELS:
        picks = {job: (r["levels"].get(lv) or {}).get("id") for job, r in res.items()}
        picks["i2v_audio"] = audio_pick(res["i2v"], lv, models)
        picks["sfx"] = sfx_pick(models_list, picks.get("music"), a.recent)
        if bg:
            picks["bg_remove"] = bg
        rows = plan_lines(picks, plan, pricer)
        report["tiers"][lv] = {"name": LEVEL_NAMES[lv], "models": {k: v for k, v in picks.items() if v and k != "bg_remove"},
                               "names": {k: display_name(models[v]) for k, v in picks.items() if v and v in models},
                               "lines": rows, **summarize(rows, plan, models, LANE)}
    # ---- the report the agent reads (and adapts for the user, in the user's language)
    src = report["source"]
    L = [f"# Model levels — live from Tokentide {now:%Y-%m-%d} ({LANE} lane)", ""]
    if ranks["boards"]:
        L.append(f"Quality ratings: {src['name']} leaderboards ({src['date'] or 'date not recorded'}), "
                 "artificialanalysis.ai — credit them whenever you show these ratings.")
    else:
        L.append("> **No leaderboard scores** (`--ranks` missing or empty): quality is the skill's own estimate. Read the "
                 "Artificial Analysis leaderboards first (references/models.md §3) and run `tiers` again.")
    L += [f"Candidates: the {a.recent} most recent models per job in the live catalog. Prices: what Tokentide charges "
          "right now (live quotes for video and music, catalog price × today's multiplier for images and voices).",
          f"Plan priced: {plan['videos']} videos × {plan['shots']} shots × {plan['takes']} takes of {plan['clip_seconds']} s "
          f"at {plan['resolution']} ({plan['audio_shots']} shot per video with real sound), {plan['keyframes']} product "
          f"images per shot, {plan['scenes']} backgrounds, ~{plan['vo_chars']} characters of voice-over, a "
          f"{plan['music_seconds']} s track and {plan['sfx']} sound effects per video.", ""]
    L += privacy_warning(models_list)
    L += ["| | Essential | Pro | Max |", "|---|---|---|---|"]
    labels = {"i2v": "Video", "keyframe": "Images: product shots", "scene": "Images: backgrounds", "tts": "Voice",
              "music": "Music"}
    for job in TIER_JOBS:
        L.append(f"| {labels[job]} | " + " | ".join(level_cell(res[job]["levels"].get(lv), job) for lv in LEVELS) + " |")
    L.append("| Clips with sound | " + " | ".join(
        f"`{report['tiers'][lv]['models'].get('i2v_audio') or '—'}`" for lv in LEVELS) + " |")
    L.append("| ≈ per video | " + " | ".join(money(report["tiers"][lv]["per_video_usd"]) for lv in LEVELS) + " |")
    L.append(f"| **{plan['videos']} videos** | " + " | ".join(
        f"**{money(report['tiers'][lv]['total_usd'])}** ({report['tiers'][lv]['label']})" for lv in LEVELS) + " |")
    lts = [report["tiers"][lv].get("lowtide_usd") for lv in LEVELS]
    if any(lts):
        L.append("| with Low Tide (slower, cheaper) | " + " | ".join(f"≈ {money(x)}" if x else "—" for x in lts) + " |")
    L += ["", "Essential = " + LEVEL_WHY["essential"] + "; Pro = " + LEVEL_WHY["pro"] + "; Max = " + LEVEL_WHY["max"] +
          " (each is on the price/quality frontier of its job).", ""]
    for lv in LEVELS:
        t = report["tiers"][lv]
        if t["missing"] or t["estimated"]:
            L.append(f"- {t['name']}: ESTIMATE — " + "; ".join(
                f"{r['what']}: {r['note']}" for r in t["lines"] if r["basis"] in ("estimate", "missing", "error")))
    L += ["", "## Per job", ""]
    for job in TIER_JOBS:
        r = res[job]
        L.append(f"### {labels[job]} — {JOBS[job][1]}")
        if r["board"]:
            what, url = AA_BOARDS.get(r["board"], ("", ""))
            L.append(f"Leaderboard: {what or r['board']} ({(ranks.get('urls') or {}).get(r['board']) or url}). "
                     f"{len(r['rated'])} of the {r['recent']} most recent models are rated; frontier: "
                     + (", ".join(f"`{d['id']}`" for d in r["frontier"]) or "none"))
        else:
            L.append(f"No leaderboard for this job: levels use the skill's estimate ({r['recent']} recent models).")
        if r["unrated"]:
            L.append("Not rated yet (new or not on the leaderboard): " + ", ".join(f"`{d['id']}`" for d in r["unrated"][:12])
                     + " — add their leaderboard name or `id` to ranks.json if they are listed.")
        if r["unpriced"]:
            L.append("No price: " + ", ".join(f"`{d['id']}` ({d.get('quote_error', 'no price')[:60]})" for d in r["unpriced"][:6]))
        L.append("")
    L += ["Then: `models.py choose --project <P> --tier essential|pro|max` and tell the user the models in plain words.",
          "Exact cost of a level for another plan: `models.py cost --project <P> --tier <level> --videos <n>`."]
    text = "\n".join(L) + "\n"
    out_dir = root or Path(".")
    (out_dir / "model_tiers.md").write_text(text, encoding="utf-8")
    common.save_json(out_dir / "model_tiers.json", report)
    print(text)
    print(f"saved {out_dir / 'model_tiers.md'} and model_tiers.json")


# ---------------------------------------------------------------- the user's own models
SUGGEST_JOBS = ("i2v", "i2v_audio", "keyframe", "scene", "tts", "music", "sfx")  # r2v / t2v only when a video needs them
def jobs_of(m) -> list:
    t = m.get("type")
    if t == "video":
        vm = video_mode(m)
        jobs = {"i2v": ["i2v"], "r2v": ["r2v"], "t2v": ["t2v"], "upscale": ["upscale"]}.get(vm, [])
        d = describe(m, "i2v") if vm == "i2v" else {}
        if vm == "i2v" and (d.get("audio") or d.get("audio_guess")):
            jobs.append("i2v_audio")
        return jobs
    if t in ("image", "inpaint"):
        return {"edit": ["keyframe"], "gen": ["scene"], "bg": ["bg_remove"]}.get(image_kind(m), [])
    if t == "tts":
        return ["tts"]
    if t == "music":
        return {"music": ["music"], "sfx": ["sfx"], "tts": ["tts"]}.get(audio_kind(m), [])
    return []


def similarity(q, m) -> float:
    """1.0 for the same model name, else the share of the asked words found in the model's name
    (a version like "3" counts partly for "3.1")."""
    best = 0.0
    for k in model_keys(m):
        if same_model(q, k):
            return 1.0
        qa, ka = list(q[0]) + list(q[1]), set(k[0]) | set(k[1])
        if not qa or not any(t[0].isalpha() and t in ka for t in qa):
            continue  # a shared version number alone ("Sora 2" vs "GPT Image 2") is not similar
        hit = 0.0
        for t in qa:
            if t in ka:
                hit += 1
            elif t[0].isdigit() and any(x.startswith(t + ".") for x in ka):
                hit += 0.6
        best = max(best, hit / max(len(qa), len(ka)) * 0.9)
    return best


def cmd_match(a):
    root = Path(a.project) if a.project else None
    if root and not a.cache:
        api.use_project(root)
    models = [m for m in catalog(a) if jobs_of(m) and not spec(m).get("offline")]
    report = {"generated": common.now_iso(), "asked": []}
    picks = {}
    for phrase in a.names:
        exact = [m for m in models if m["id"].lower() == phrase.strip().lower()]
        q = name_key(phrase)
        scored = sorted(((1.0 if m in exact else similarity(q, m), m) for m in models),
                        key=lambda x: (-x[0], -(created(x[1]) or dt.datetime.min.replace(tzinfo=dt.timezone.utc)).timestamp()))
        found = [m for s, m in scored if s >= 0.999]
        close = [(s, m) for s, m in scored if 0.35 <= s < 0.999][:5]
        entry = {"asked": phrase, "available": bool(found), "models": [], "closest": []}
        print(f"\n## \"{phrase}\" — " + ("AVAILABLE on Tokentide" if found else "NOT AVAILABLE on Tokentide"))
        for m in found:
            js = jobs_of(m)
            entry["models"].append({"id": m["id"], "name": display_name(m), "jobs": js, "privacy": privacy(m),
                                    "added": created(m).strftime("%Y-%m-%d") if created(m) else None})
            print(f"- `{m['id']}` ({display_name(m)}) · jobs: {', '.join(js)} · {privacy(m)}")
            for j in js:
                if j in SUGGEST_JOBS:
                    picks.setdefault(j, m["id"])
        if not found:
            for s, m in close:
                entry["closest"].append({"id": m["id"], "name": display_name(m), "jobs": jobs_of(m), "similarity": round(s, 2)})
                print(f"- closest: `{m['id']}` ({display_name(m)}) · jobs: {', '.join(jobs_of(m))}")
            if not close:
                print("- nothing similar in the catalog")
        report["asked"].append(entry)
    if picks:
        print("\nSuggested (confirm each job with the user; a name can cover several jobs):\n"
              "  models.py choose --project <P> " + " ".join(f"{j}={i}" for j, i in picks.items()))
    if a.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    if root:
        common.save_json(root / "model_match.json", report)


# ---------------------------------------------------------------- cost (the up-front total)
def cmd_cost(a):
    global LANE
    LANE = a.lane or "standard"
    api.set_lane(a.lane)
    root = Path(a.project)
    meta = common.project_meta(root)
    if not meta:
        common.die(f"No project.json in {root}")
    api.use_project(root)
    models = common.load_models(root) if (root / "models.json").is_file() and not a.refresh else \
        {m["id"]: m for m in catalog(argparse.Namespace(project=str(root), cache=None, out=None))}
    if a.tier:
        tiers = common.load_json(root / "model_tiers.json", default={}) or {}
        picks = dict(((tiers.get("tiers") or {}).get(a.tier) or {}).get("models") or {})
        if not picks:
            common.die(f"No level '{a.tier}' in {root}/model_tiers.json — run `models.py tiers --project {root}` first.")
    else:
        picks = dict(meta.get("models") or {})
    for item in a.picks or []:
        if "=" in item:
            job, mid = (x.strip() for x in item.split("=", 1))
            picks[job] = mid
    if not picks:
        common.die("No models chosen yet: `models.py choose --project <P> ...` (or pass --tier / job=id).")
    unknown = [f"{j}={m}" for j, m in picks.items() if m not in models]
    if "bg_remove" not in picks:
        bg = bg_remove_model(models)
        if bg:
            picks["bg_remove"] = bg
    plan = plan_from(a)
    rows = plan_lines(picks, plan, Pricer(models, LANE, fallback_prices(root)))
    s = summarize(rows, plan, models, LANE)
    cap = meta.get("budget_usd")
    spent = common.spent_usd(root)
    out = {"generated": common.now_iso(), "lane": LANE, "tier": a.tier, "plan": plan, "models": picks, "lines": rows,
           **s, "budget_usd": cap, "spent_usd": spent}
    common.save_json(root / "cost_quote.json", out)
    print(f"# {'QUOTE' if s['label'] == 'quote' else 'ESTIMATE'} — {plan['videos']} videos"
          + (f" ({LEVEL_NAMES.get(a.tier, a.tier)} level)" if a.tier else "") + f", {LANE} lane, {common.now_iso()[:16]} UTC\n")
    print("| what | model | how many | each | subtotal | priced by |\n|---|---|---|---|---|---|")
    for r in rows:
        name = display_name(models[r["model"]]) if r["model"] in models else r["model"]
        print(f"| {r['what']} | {name} | {r['count']} × {r['unit']} | {money(r['unit_usd'])} | {money(r['usd'])} | "
              f"{r['basis']}{(': ' + r['note']) if r['note'] and r['basis'] != 'quote' else ''} |")
    print(f"| **Total** | | | | **{money(s['total_usd'])}** | ≈ {money(s['per_video_usd'])} per video |\n")
    if unknown:
        print("Not in the live catalog (not available on Tokentide to this key): " + ", ".join(unknown))
    if s["label"] == "quote":
        print(f"QUOTE: {money(s['total_usd'])} for this plan at Tokentide's prices right now. Prices change through the "
              "UTC day (they fall towards 00:00 UTC); retakes beyond the plan cost extra; failed jobs are refunded.")
    else:
        why = ", ".join(s["missing"] + s["estimated"]) or "some prices"
        print(f"ESTIMATE: about {money(s['total_usd'])} — an estimate, not a quote: the final price may vary "
              f"(no live price for {why}).")
    if s.get("lowtide_usd"):
        print(f"With the Low Tide lane (best-effort, may wait or fall back): about {money(s['lowtide_usd'])}.")
    if cap:
        left = float(cap) - spent
        flag = "fits" if s["total_usd"] <= left + 1e-9 else "is OVER"
        print(f"Budget: this {flag} the project cap (${float(cap):.2f}, ${spent:.2f} spent so far). "
              "Ask the user before raising it.")
    print(f"saved {root / 'cost_quote.json'}")


# ---------------------------------------------------------------- choose / list / show
def cmd_choose(a):
    root = Path(a.project)
    meta = common.project_meta(root)
    if not meta:
        common.die(f"No project.json in {root}")
    known = common.load_models(root)
    picks = meta.setdefault("models", {})
    if not a.tier and not a.picks:
        common.die("Pass --tier essential|pro|max and/or job=model_id pairs.")
    if a.tier:
        tiers = common.load_json(root / "model_tiers.json", default={}) or {}
        level = ((tiers.get("tiers") or {}).get(a.tier) or {}).get("models") or {}
        if not level:
            common.die(f"No level '{a.tier}' in {root}/model_tiers.json — run `models.py tiers --project {root}` first.")
        picks.update({k: v for k, v in level.items() if v})
        meta["models_tier"] = a.tier
    for item in a.picks or []:
        if "=" not in item:
            common.die(f"expected job=model_id, got {item}")
        job, mid = (x.strip() for x in item.split("=", 1))
        if known and mid not in known:
            common.log(f"WARNING: {mid} is not in {root}/models.json — check the id (models.py match \"<name>\")")
        picks[job] = mid
    explicit = {x.split("=", 1)[0].strip() for x in (a.picks or []) if "=" in x}
    if "i2v" in explicit and "i2v_audio" not in explicit:  # shots with real sound: the same model when it makes sound
        m = known.get(picks["i2v"])
        if m and (bool_caps(m, "audio") or (bool_caps(m, "audio") is None and family_version(m["id"])[0] in NATIVE_AUDIO_FAMILIES)):
            picks["i2v_audio"] = picks["i2v"]
        elif known:
            common.log(f"{picks['i2v']} makes silent clips: for shots that need real sound, pick a video model with sound "
                       "(models.py tiers / recommend) and `choose i2v_audio=<id>`; until then they use @i2v_audio's "
                       f"current pick ({picks.get('i2v_audio') or 'none'}).")
    if a.picks and not a.tier:
        meta["models_tier"] = "custom"
    meta["models_chosen_at"] = common.now_iso()
    common.save_json(root / "project.json", meta)
    for job, mid in picks.items():
        name = display_name(known[mid]) if mid in known else ""
        print(f"@{job:<10} -> {mid}" + (f"  ({name})" if name and name != mid else ""))
    print('Specs can now use "model": "@<job>" (e.g. "@i2v", "@keyframe").')


def cmd_list(a):
    models = catalog(a)
    if a.type != "all":
        models = [m for m in models if m.get("type") == a.type]
    if a.find:
        f = a.find.lower()
        models = [m for m in models if f in json.dumps(m, ensure_ascii=False).lower()]
    if a.json:
        print(json.dumps(models, indent=2, ensure_ascii=False))
        return
    by_type = {}
    for m in models:
        by_type.setdefault(m.get("type") or "?", []).append(m)
    for t, items in sorted(by_type.items()):
        print(f"\n## {t} ({len(items)})")
        for m in sorted(items, key=lambda x: x.get("id", "")):
            c = created(m)
            mode = video_mode(m) if t == "video" else (image_kind(m) if t in ("image", "inpaint") else
                                                         audio_kind(m) if t == "music" else "")
            flags = [x for x, on in (("OFFLINE", spec(m).get("offline")), ("DEPRECATED", spec(m).get("deprecation"))) if on]
            hits = common.spec_lookup(m, "duration", "resolution", "aspect", "audio", "endimage", "maxinput", "vision")
            extra = "; ".join(f"{k.split('.')[-1]}={json.dumps(v)[:40]}" for k, v in list(hits.items())[:5])
            print(f"- {m.get('id')}  [{privacy(m)}{(' · ' + mode) if mode else ''}{(' · ' + c.strftime('%Y-%m')) if c else ''}]"
                  f"{(' ' + ' '.join(flags)) if flags else ''}  {extra}")
    if not models:
        print("No models matched.", file=sys.stderr)


def accepted_values(m) -> dict:
    """The request values a model accepts, from its catalog entry: {"duration": [...], "resolution": [...],
    "aspect_ratio": [...]}. Tokentide rejects anything else before Venice sees it, and values are case-sensitive."""
    out = {}
    for field, needle in (("duration", "duration"), ("resolution", "resolution"), ("aspect_ratio", "aspect")):
        vals = lists(m, needle)
        if vals:
            out[field] = vals
    return out


def cmd_show(a):
    m = next((x for x in catalog(a) if x.get("id") == a.id), None)
    if not m:
        common.die(f"Model '{a.id}' not found (check the id with `models.py match \"<name>\"` or `models.py list --find ...`)")
    if not a.json:
        acc = accepted_values(m)
        if acc:
            print(f"Accepted values for {a.id} (use them exactly; they are case-sensitive):")
            for field, vals in acc.items():
                print(f"  {field}: {', '.join(vals)}")
            print()
    print(json.dumps(m, indent=2, ensure_ascii=False))


def plan_args(p):
    g = p.add_argument_group("plan (what gets priced)")
    g.add_argument("--videos", type=int, help=f"videos in the batch (default {PLAN['videos']})")
    g.add_argument("--shots", type=int, help=f"shots per video (default {PLAN['shots']})")
    g.add_argument("--takes", type=int, help=f"video takes per shot (default {PLAN['takes']})")
    g.add_argument("--clip-seconds", type=int, help=f"seconds per clip (default {PLAN['clip_seconds']})")
    g.add_argument("--resolution", help=f"clip resolution (default {PLAN['resolution']})")
    g.add_argument("--audio-shots", type=int, help=f"shots per video that need real sound (default {PLAN['audio_shots']})")
    g.add_argument("--keyframes", type=int, help=f"product images per shot (default {PLAN['keyframes']})")
    g.add_argument("--scenes", type=int, help=f"background images per video (default {PLAN['scenes']})")
    g.add_argument("--vo-chars", type=int, help=f"voice-over characters per video (default {PLAN['vo_chars']}; ~15 s)")
    g.add_argument("--music-seconds", type=int, help=f"music track per video (default {PLAN['music_seconds']} s; 0 = none)")
    g.add_argument("--sfx", type=int, help=f"sound effects per video (default {PLAN['sfx']})")
    g.add_argument("--sfx-seconds", type=int, help=f"seconds per sound effect (default {PLAN['sfx_seconds']})")
    g.add_argument("--cutouts", type=int, help=f"product cut-outs for the project (default {PLAN['cutouts']})")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    ti = sub.add_parser("tiers", help="Essential / Pro / Max levels (recommendation)")
    ti.add_argument("--project", help="project folder: caches models.json and writes model_tiers.md/.json there")
    ti.add_argument("--ranks", help="Artificial Analysis scores (ranks.json; format in references/models.md §3)")
    ti.add_argument("--recent", type=int, default=30, help="most recent models considered per job (default 30)")
    ti.add_argument("--max-quotes", type=int, default=15, help="max models quoted per job (Tokentide: 60 quotes/min)")
    ti.add_argument("--no-quote", action="store_true")
    ti.add_argument("--lane", choices=["standard", "lowtide"], help="price everything for this lane")
    ti.add_argument("--cache", help="use a cached models.json instead of refetching")
    plan_args(ti)
    ma = sub.add_parser("match", help="find the models the user names in the live catalog")
    ma.add_argument("names", nargs="+", help='model names as the user wrote them, e.g. "Kling 4" "nano banana 2.1"')
    ma.add_argument("--project")
    ma.add_argument("--cache")
    ma.add_argument("--json", action="store_true")
    co = sub.add_parser("cost", help="total price of a planned batch (quote or estimate)")
    co.add_argument("--project", required=True)
    co.add_argument("--tier", choices=LEVELS, help="price a level from model_tiers.json instead of the chosen models")
    co.add_argument("picks", nargs="*", help="job=model_id overrides, e.g. i2v=kling-v4-image-to-video")
    co.add_argument("--lane", choices=["standard", "lowtide"])
    co.add_argument("--refresh", action="store_true", help="refetch the catalog instead of using models.json")
    plan_args(co)
    li = sub.add_parser("list")
    li.add_argument("--type", default="all", help="all|" + "|".join(TYPES))
    li.add_argument("--find")
    li.add_argument("--out", help="cache raw catalog JSON here (e.g. <project>/models.json)")
    li.add_argument("--cache", help="read a cached models.json instead of the API")
    li.add_argument("--json", action="store_true")
    sh = sub.add_parser("show")
    sh.add_argument("id")
    sh.add_argument("--cache")
    sh.add_argument("--json", action="store_true", help="only the raw catalog entry")
    r = sub.add_parser("recommend", help="detailed options per job")
    r.add_argument("--project", help="project folder: caches models.json and writes model_options.md/.json there")
    r.add_argument("--jobs", help="comma list (default keyframe,scene,i2v,i2v_audio,r2v,tts,music,sfx); also t2v, upscale")
    r.add_argument("--ranks", help="leaderboard scores (ranks.json; see references/models.md)")
    r.add_argument("--duration", type=int, default=5, help="standard clip length for quotes (s)")
    r.add_argument("--resolution", default="1080p")
    r.add_argument("--max-quotes", type=int, default=10, help="max models quoted per job (Tokentide: 60 quotes/min)")
    r.add_argument("--no-quote", action="store_true")
    r.add_argument("--lane", choices=["standard", "lowtide"], help="price everything for this lane")
    r.add_argument("--cache", help="use a cached models.json instead of refetching")
    c = sub.add_parser("choose")
    c.add_argument("--project", required=True)
    c.add_argument("--tier", choices=LEVELS, help="take every job's model from this level of model_tiers.json")
    c.add_argument("picks", nargs="*", help="job=model_id, e.g. i2v=kling-v3-pro-image-to-video (overrides --tier)")
    a = ap.parse_args()
    {"tiers": cmd_tiers, "match": cmd_match, "cost": cmd_cost, "list": cmd_list, "show": cmd_show,
     "recommend": cmd_recommend, "choose": cmd_choose}[a.cmd](a)


if __name__ == "__main__":
    try:
        main()
    except api.APIError as e:
        common.die(str(e))
