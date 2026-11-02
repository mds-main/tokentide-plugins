#!/usr/bin/env python3
"""Live model catalog (Tokentide, proxying Venice) and recommendations with quality/price options.

New image and video models ship constantly, so never hard-code one. At the start of every
project (and before each new batch) run `recommend`, show the user the options, then `choose`.
Specs refer to the picks by alias ("@i2v", "@keyframe", ...), so switching models is one command.

  list       catalog table, filters --type/--find; --out caches the raw JSON (models.json)
  show ID    full JSON entry for one model
  recommend  per job: Premium / Balanced / Budget / Newest / Private options from live /models data,
             with real prices from free /video/quote calls for a standard clip (default 5 s, 1080p, 9:16).
             --ranks ranks.json adds current leaderboard scores (see references/models.md).
  choose     store picks in project.json "models":  choose --project P i2v=<id> keyframe=<id> ...

Jobs: keyframe (product into scene, edit models) · scene (image generation) · i2v (image-to-video) ·
      i2v_audio (image-to-video with native audio) · r2v (reference-to-video: characters/objects) ·
      t2v (text-to-video, product-free B-roll) · upscale (video upscale) · tts (voice-over)
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
    mt = str(spec(m).get("model_type") or spec(m).get("modelType") or "").lower()
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
    flat = {k: v for k, v in flat.items() if "upscale" not in k.lower()}
    nums = {k.lower(): float(v) for k, v in flat.items() if isinstance(v, (int, float)) and "usd" in k.lower()}
    if not nums:
        nums = {k.lower(): float(v) for k, v in flat.items() if isinstance(v, (int, float)) and "diem" not in k.lower()}
    for hint in ("2k", "1k", "high", "generation"):
        hits = [v for k, v in nums.items() if hint in k]
        if hits:
            return max(hits)
    return max(nums.values()) if nums else None


def load_ranks(path):
    if not path:
        return {}
    data = common.load_json(path)
    items = data.get("entries", data) if isinstance(data, dict) else data
    if isinstance(items, dict):
        items = [{"match": k, "score": v} for k, v in items.items() if k not in ("source", "date", "notes")]
    ranks = {str(e["match"]).lower(): float(e["score"]) for e in items if isinstance(e, dict) and "match" in e}
    if not ranks:
        return {}
    lo, hi = min(ranks.values()), max(ranks.values())
    return {k: (4.0 * (v - lo) / (hi - lo) if hi > lo else 3.0) for k, v in ranks.items()}


# ---------------------------------------------------------------- recommend
def describe(m, job):
    mid = m["id"]
    fam, ver = family_version(mid)
    d = {"id": mid, "job": job, "family": fam, "version": ".".join(map(str, ver)) if ver else "", "_ver": ver,
         "tier": tier(mid), "privacy": privacy(m), "created": created(m), "offline": bool(spec(m).get("offline")),
         "deprecated": bool(spec(m).get("deprecation") or spec(m).get("deprecated")),
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
    if JOBS[job][0] in ("video", "music"):
        lt = tt(m).get("lowtide") if isinstance(tt(m).get("lowtide"), dict) else {}
        d["lowtide_ok"] = bool(lt.get("eligible")) if lt else None
    if job == "tts":
        voices = lists(m, "voice")
        d.update(voices=len(voices), sample_voices=voices[:6])
    return d


def candidates(models, job):
    kind = JOBS[job][0]
    out = []
    for m in models:
        mt = m.get("type")
        if kind == "image" and mt not in ("image", "inpaint"):  # edit models are type "inpaint"
            continue
        if kind == "video" and mt != "video":
            continue
        if kind == "tts" and mt != "tts":
            continue
        if kind == "music":
            if mt != "music":
                continue
            is_sfx = bool(re.search(r"sfx|sound[-_ ]?effect", m["id"].lower()))
            if (job == "sfx") != is_sfx:
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


def quality(d, ranks, now):
    best = None
    for key, score in ranks.items():
        if key in d["id"].lower() and (best is None or len(key) > len(best[0])):
            best = (key, score)
    if best:
        d["quality_source"] = f"leaderboard:{best[0]}"
        base = best[1]
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
    if d["new"] and not best:
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


def quote_all(items, job, dur, res):
    import video  # Tokentide-aware quote helper (throttled to the 60/min quote limit)

    def q(d):
        if JOBS[job][0] == "music":
            body = {"model": d["id"], "duration_seconds": 30 if job == "music" else 3}
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
        if d.get("price") and d.get("quoted"):
            d["usd_per_s"] = round(d["price"] / max(1.0, num(d["quoted"]["duration"])), 4)
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
    tail = f" (list ${lp:.2f})" if lp and abs(lp - p) > 0.004 else ""
    lt = " · LT" if d.get("lowtide_ok") else ""
    if JOBS[job][0] in ("video", "music"):
        q = d.get("quoted") or {}
        return f"${p:.2f}/{q.get('duration', '')} {q.get('resolution', '')}".strip() + tail + lt
    return f"${p:.3f}/img" + (f" (list ${lp:.3f})" if lp and abs(lp - p) > 0.0005 else "")


def per_video(d, job, shots=3, takes=2, kf_per_shot=3):
    p = d.get("price")
    if p is None:
        return None
    return round(p * shots * takes, 2) if JOBS[job][0] == "video" else round(p * shots * kf_per_shot, 2)


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
             f"Quality = {'leaderboard ranks + ' if ranks else ''}family prior, tier, recency (newest versions first). "
             f"Prices are what Tokentide charges now (Venice list × today's tide multiplier); video/music are live quotes "
             f"for one {a.duration}s clip / 30 s track. Per-video ≈ 3 shots × 2 takes (images: 3 shots × 3 variants). "
             f"LT = eligible for the cheaper Low Tide lane. Prices fall through the UTC day (cheapest just before 00:00 UTC).", ""]
    privs = {privacy(m) for m in models}
    edit_models = [m for m in models if m.get("type") in ("image", "inpaint") and image_kind(m) == "edit"]
    if "anonymized" not in privs or not edit_models:
        lines += ["> **Your key only sees Private models.** Tokentide keys default to privacy mode `private`, which hides "
                  "the anonymized models: background removal, most premium image-edit and video models, and every music "
                  "model. Create a key with privacy mode `all` (or `private_text`, which keeps only text models private) "
                  "in the Tokentide dashboard to get the full catalog.", ""]
    for job in jobs:
        if job not in JOBS:
            common.log(f"unknown job '{job}' (valid: {', '.join(JOBS)})")
            continue
        items = candidates(models, job)
        for d in items:
            d["q"] = quality(d, ranks, now)
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
            lines += ["| model | voices | privacy | added |", "|---|---|---|---|"]
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
                lines.append(f"| `{o['id']}` | {o.get('voices', '?')} | {o['privacy']} | {added} |")
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
            report["jobs"][job]["options"].append({k: (v.isoformat() if isinstance(v, dt.datetime) else v)
                                                   for k, v in o.items() if not k.startswith("_")})
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


def cmd_choose(a):
    root = Path(a.project)
    meta = common.project_meta(root)
    if not meta:
        common.die(f"No project.json in {root}")
    known = common.load_models(root)
    picks = meta.setdefault("models", {})
    for item in a.picks:
        if "=" not in item:
            common.die(f"expected job=model_id, got {item}")
        job, mid = (x.strip() for x in item.split("=", 1))
        if known and mid not in known:
            common.log(f"WARNING: {mid} is not in {root}/models.json — check the id (models.py list --find ...)")
        picks[job] = mid
    meta["models_chosen_at"] = common.now_iso()
    common.save_json(root / "project.json", meta)
    for job, mid in picks.items():
        print(f"@{job:<10} -> {mid}")
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
            mode = video_mode(m) if t == "video" else (image_kind(m) if t == "image" else "")
            flags = [x for x, on in (("OFFLINE", spec(m).get("offline")), ("DEPRECATED", spec(m).get("deprecation"))) if on]
            hits = common.spec_lookup(m, "duration", "resolution", "aspect", "audio", "endimage", "maxinput", "vision")
            extra = "; ".join(f"{k.split('.')[-1]}={json.dumps(v)[:40]}" for k, v in list(hits.items())[:5])
            print(f"- {m.get('id')}  [{privacy(m)}{(' · ' + mode) if mode else ''}{(' · ' + c.strftime('%Y-%m')) if c else ''}]"
                  f"{(' ' + ' '.join(flags)) if flags else ''}  {extra}")
    if not models:
        print("No models matched.", file=sys.stderr)


def cmd_show(a):
    m = next((x for x in catalog(a) if x.get("id") == a.id), None)
    if not m:
        common.die(f"Model '{a.id}' not found (check the id with `models.py list --find ...`)")
    print(json.dumps(m, indent=2, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    li = sub.add_parser("list")
    li.add_argument("--type", default="all", help="all|" + "|".join(TYPES))
    li.add_argument("--find")
    li.add_argument("--out", help="cache raw catalog JSON here (e.g. <project>/models.json)")
    li.add_argument("--cache", help="read a cached models.json instead of the API")
    li.add_argument("--json", action="store_true")
    sh = sub.add_parser("show")
    sh.add_argument("id")
    sh.add_argument("--cache")
    r = sub.add_parser("recommend")
    r.add_argument("--project", help="project folder: caches models.json and writes model_options.md/.json there")
    r.add_argument("--jobs", help="comma list (default keyframe,scene,i2v,i2v_audio,r2v,tts,music,sfx); also t2v, upscale")
    r.add_argument("--ranks", help="JSON of current leaderboard scores keyed by model-id substring")
    r.add_argument("--duration", type=int, default=5, help="standard clip length for quotes (s)")
    r.add_argument("--resolution", default="1080p")
    r.add_argument("--max-quotes", type=int, default=10, help="max models quoted per job (Tokentide: 60 quotes/min)")
    r.add_argument("--no-quote", action="store_true")
    r.add_argument("--lane", choices=["standard", "lowtide"], help="price everything for this lane")
    r.add_argument("--cache", help="use a cached models.json instead of refetching")
    c = sub.add_parser("choose")
    c.add_argument("--project", required=True)
    c.add_argument("picks", nargs="+", help="job=model_id, e.g. i2v=kling-v3-pro-image-to-video")
    a = ap.parse_args()
    {"list": cmd_list, "show": cmd_show, "recommend": cmd_recommend, "choose": cmd_choose}[a.cmd](a)


if __name__ == "__main__":
    try:
        main()
    except api.APIError as e:
        common.die(str(e))
