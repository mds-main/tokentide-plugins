#!/usr/bin/env python3
"""Tokentide queued media jobs (video, and music/SFX via audio.py): quote -> queue -> retrieve -> complete.

  run      plan every shot x take from a video spec, quote the total, enforce budget, queue (max 6 in
           flight; the rest wait as 'planned'), then poll (time-boxed). --dry-run = quote only.
  poll     resume a jobs file: collects finished files and queues planned takes as slots free up
  status   show job states
  select   mark a take as the shot's selected clip in the spec
  quote    price a single job (free; 60 quotes/min per account)
  submit   queue a single ad-hoc job
  upscale  Topaz upscale of a finished file (needs a public https URL: bodies are capped at 4.5 MB)
  cleanup  call /video/complete for downloaded jobs not yet cleaned up

Tokentide differences vs. Venice handled here: no download_url (the finished file comes back from
retrieve), files are kept until verified (delete_media_on_completion=false, then complete), every queue
carries an Idempotency-Key and an X-Tokentide-Max-Cost-USD guard, ≤8 unfinished jobs per account,
polling ≥2 s apart, and a daily queue cutoff (~23:14 UTC video, ~23:39 UTC music) before the 00:00 UTC reset.
Jobs live in <project>/logs/<vid>_video_jobs.json (there is no endpoint to list past jobs).
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import apiclient as api
import common

PENDING = ("queued", "processing")
# Venice's quote schemas reject unknown fields, and Tokentide forwards free quotes as sent: send only the
# pricing fields of each job kind (the same ones Tokentide's own queue-time quote uses).
VIDEO_QUOTE_KEYS = ("model", "duration", "aspect_ratio", "resolution", "upscale_factor", "enhancement_model",
                    "target_fps", "slowdown_factor", "audio", "video_url")
AUDIO_QUOTE_KEYS = ("model", "duration_seconds")
QUOTE_KEYS = VIDEO_QUOTE_KEYS  # cache key for video plans
MAX_INFLIGHT = 6  # Tokentide allows 8 unfinished video and music jobs per account, together; keep headroom


def norm_duration(d) -> str:
    if isinstance(d, (int, float)):
        return f"{int(round(d))}s"
    d = str(d).strip()
    return d if d.endswith("s") else f"{d}s"


def _num(s) -> float:
    m = re.search(r"[\d.]+", str(s))
    return float(m.group()) if m else 0.0


def validate(body, entry):
    """Best-effort checks against the cached model spec. Returns (body, warnings)."""
    warns = []
    if not entry:
        return body, warns
    for key, field in (("duration", "duration"), ("resolution", "resolution"), ("aspect", "aspect_ratio")):
        allowed = [v for v in common.spec_lookup(entry, key).values() if isinstance(v, list) and v]
        if not allowed or field not in body:
            continue
        opts = [str(x) for x in allowed[0]]
        if field == "duration":
            opts_n = {norm_duration(o): o for o in opts}
            if body[field] not in opts_n:
                best = min(opts_n, key=lambda o: abs(_num(o) - _num(body[field])))
                warns.append(f"duration {body[field]} not offered {list(opts_n)}; using {best}")
                body[field] = best
        elif str(body[field]) not in opts:
            if field == "resolution":
                best = min(opts, key=lambda o: abs(_num(o) - _num(body[field])))
                warns.append(f"resolution {body[field]} not offered {opts}; using {best}")
                body[field] = best
            else:
                warns.append(f"aspect_ratio {body[field]} not offered {opts}; omitting it")
                body.pop(field)
    limits = [v for k, v in common.spec_lookup(entry, "promptcharacter", "prompt_character", "promptlimit").items()
              if isinstance(v, (int, float))]
    limit = min(limits[0], 32000) if limits else 32000  # Tokentide caps video prompts at 32,000 chars
    if len(body.get("prompt", "")) > limit:
        common.die(f"{body['model']}: prompt is {len(body['prompt'])} chars; limit is {int(limit)}. Shorten it.")
    audio_caps = {k: v for k, v in common.spec_lookup(entry, "audio").items() if isinstance(v, bool)}
    if "audio" in body and audio_caps and not any(audio_caps.values()):
        warns.append("model exposes no audio config; dropping 'audio'")
        body.pop("audio")
    return body, warns


def build_job(spec, shot, models):
    v = shot.get("video") or {}
    model = common.resolve_model(spec.root, v.get("model")) or common.die(f"{shot['id']}: video.model missing")
    prompt = v.get("prompt") or common.die(f"{shot['id']}: video.prompt missing")
    body = {"model": model, "prompt": prompt, "duration": norm_duration(v.get("duration", "5s"))}
    for k in ("negative_prompt", "resolution"):
        if v.get(k):
            body[k] = v[k]
    ar = v.get("aspect_ratio", spec.data.get("aspect_ratio", "9:16"))
    if ar:
        body["aspect_ratio"] = ar
    if v.get("audio") is not None:
        body["audio"] = bool(v["audio"])
    needs_image = any(t in model for t in ("image-to-video", "reference-to-video", "motion-control"))
    kf = shot.get("keyframe") or {}
    img = v.get("image") or kf.get("selected") or (kf.get("candidates") or [None])[0]
    n_imgs = 1 + (1 if v.get("end_image") else 0)
    budget = api.per_image_budget(n_imgs, other_bytes=len(prompt) * 2 + 20_000)
    if "text-to-video" not in model and img:
        body["image_url"] = api.encode_image(spec.p(img), mode="data-url", max_side=int(v.get("max_input_side", 1920)),
                                             max_bytes=budget, keep_png=False)
    elif needs_image:
        common.die(f"{shot['id']}: {model} needs an input image (keyframe.selected or video.image)")
    if v.get("end_image"):
        body["end_image_url"] = api.encode_image(spec.p(v["end_image"]), mode="data-url", max_side=1920,
                                                 max_bytes=budget, keep_png=False)
    body.update(v.get("extra") or {})
    if "seedance" in model and ("image-to-video" in model or "reference-to-video" in model):
        body.pop("aspect_ratio", None)  # Seedance I2V/R2V takes the ratio from the input image
    body, warns = validate(body, models.get(model))
    if models and model not in models:
        warns.append(f"model '{model}' not in models.json — refresh with models.py or fix the id "
                     "(or your key's privacy mode hides it)")
    return body, warns


def quote_body(body, kind="video") -> dict:
    """The /quote body for a queue body: its pricing fields only. Music models priced per thousand
    characters also need `character_count` (the prompt length)."""
    q = {k: body[k] for k in (AUDIO_QUOTE_KEYS if kind == "audio" else VIDEO_QUOTE_KEYS) if k in body}
    if kind == "audio" and isinstance(body.get("prompt"), str) and body["prompt"]:
        q["character_count"] = len(body["prompt"])
    return q


def quote(body, kind="video", lane=None) -> dict:
    """Free price check. Returns {"usd", "list_usd", "multiplier", "queue_open", "queue_closes_at",
    "retry_after_s", "lane"}. lane="standard" prices the Standard lane even when --lane lowtide is set."""
    api.throttle("quote")
    q = quote_body(body, kind)
    headers = {"X-Tokentide-Lane": "standard", "X-Tokentide-Lowtide-Fallback": "none"} if lane == "standard" else None
    resp, _ = api.post_adaptive(f"/{kind}/quote", q, droppable=("aspect_ratio", "audio", "resolution", "character_count"),
                                retries=3, headers=headers)
    j = resp.json()
    out = {"usd": None}
    if isinstance(j, (int, float)):
        out["usd"] = float(j)
        return out
    for k in ("quote", "price", "usd", "cost"):
        if isinstance(j, dict) and j.get(k) is not None and _num(j[k]):
            out["usd"] = float(_num(j[k]))
            break
    tt = j.get("tokentide") if isinstance(j, dict) else None
    if isinstance(tt, dict):
        out.update(list_usd=_maybe(tt.get("list_cost_usd")), multiplier=_maybe(tt.get("multiplier")),
                   lane=tt.get("lane"), queue_open=tt.get("queue_open"), queue_closes_at=tt.get("queue_closes_at"),
                   retry_after_s=_maybe(tt.get("retry_after_seconds")), kind=kind)
        if out["usd"] is None and tt.get("charge_usd") is not None:
            out["usd"] = _maybe(tt["charge_usd"])
    return out


def _maybe(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def jobs_file(spec) -> Path:
    return spec.root / "logs" / f"{spec.vid}_video_jobs.json"


_STANDARD_QUOTES: dict = {}


def cost_cap(rec, body):
    """X-Tokentide-Max-Cost-USD for a queue: the quote + 10%. Tokentide also holds the cap against the
    Standard re-price when Low Tide is closed and the job falls back, so on the Low Tide lane the cap
    comes from a Standard quote (otherwise every fallback would fail with 409 cost_above_limit)."""
    usd = rec.get("quote_usd")
    kind = rec.get("kind", "video")
    if api.lane_headers().get("X-Tokentide-Lane") == "lowtide":
        k = json.dumps([kind, quote_body(body, kind)], sort_keys=True)
        if k not in _STANDARD_QUOTES:
            try:
                _STANDARD_QUOTES[k] = quote(body, kind, lane="standard").get("usd")
            except api.APIError:
                _STANDARD_QUOTES[k] = None
        usd = max(x for x in (usd, _STANDARD_QUOTES[k], 0.0) if x is not None)
    return f"{math.ceil(usd * 1.10 * 100) / 100:.2f}" if usd else None


def submit(rec, body):
    """Queue one job with an idempotency key and a server-side cost cap (quote + 10%)."""
    kind = rec.get("kind", "video")
    rec.setdefault("idempotency_key", uuid.uuid4().hex)
    headers = {"Idempotency-Key": rec["idempotency_key"]}
    cap = cost_cap(rec, body)
    if cap:
        headers["X-Tokentide-Max-Cost-USD"] = cap
    resp, used = api.post_adaptive(f"/{kind}/queue", body, droppable=("negative_prompt", "audio", "aspect_ratio"),
                                   timeout=300, retries=4, headers=headers)
    j = resp.json()
    rec.update(queue_id=j.get("queue_id") or j.get("id"), model=j.get("model") or rec["model"], status="queued",
               submitted_at=common.now_iso(), request=api.redact(used))
    if not rec["queue_id"]:
        raise api.APIError(resp.status, f"queue returned no queue_id: {json.dumps(j)[:300]}")
    rec["charge_usd"] = resp.charge_usd
    api.log_call(kind, f"/{kind}/queue", model=rec["model"], usd=rec.get("quote_usd"), resp=resp,
                 queue_id=rec["queue_id"], key=rec["key"])
    return rec


def retrieve_once(rec, dest: Path):
    kind = rec.get("kind", "video")
    resp = api.post_json(f"/{kind}/retrieve", {"model": rec["model"], "queue_id": rec["queue_id"],
                                                "delete_media_on_completion": False}, timeout=600, retries=3)
    if not resp.is_json():
        ext = api.sniff(resp.body)[0]
        if ext and dest.suffix.lstrip(".") != ext and kind == "audio":
            dest = dest.with_suffix("." + ext)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(resp.body)
        return "done", {"path": dest}
    j = resp.json()
    st = str(j.get("status", "")).upper()
    if st in ("FAILED", "ERROR", "CANCELLED", "CANCELED", "REJECTED"):
        return "failed", j
    return "processing", j


def complete(rec):
    kind = rec.get("kind", "video")
    try:
        api.post_adaptive(f"/{kind}/complete", {"queue_id": rec["queue_id"], "model": rec["model"]},
                          droppable=("model",), retries=2, timeout=60)
        rec["completed"] = True
    except api.APIError as e:
        rec["complete_error"] = str(e)[:200]


def _rebuild(rec, root, models_cache):
    """Rebuild a planned job's body from its spec (bodies carry images, so they aren't stored)."""
    if rec.get("body_file"):
        return common.load_json(Path(root) / rec["body_file"])
    spec = common.Spec(Path(root) / rec["spec"])
    body, _ = build_job(spec, spec.shot(rec["shot"]), models_cache)
    return body


def _fill_slots(data, root, max_inflight):
    inflight = [r for r in data["jobs"] if r.get("status") in PENDING]
    planned = [r for r in data["jobs"] if r.get("status") == "planned"]
    if not planned or len(inflight) >= max_inflight:
        return
    models = common.load_models(root)
    for rec in planned[: max_inflight - len(inflight)]:
        try:
            submit(rec, _rebuild(rec, root, models))
            print(f"queued {rec['key']} ({rec['model']}) id={rec['queue_id']}")
        except api.APIError as e:
            if e.code == "rate_limited":
                print(f"  {rec['key']}: account job limit reached; will retry next poll")
                break
            if e.code == "epoch_rollover":
                print(f"  {rec['key']}: queue closed for the daily reset (00:00 UTC); re-run poll after midnight UTC")
                break
            rec.update(status="failed", last_error=str(e)[:300])
            print(f"queue FAILED {rec['key']}: {e}")
        except SystemExit as e:
            rec.update(status="failed", last_error=f"rebuild failed: {e}")


def poll(path: Path, max_seconds=240, interval=7.0, max_inflight=MAX_INFLIGHT) -> int:
    path = Path(path)
    data = common.load_json(path)
    root = path.resolve().parent.parent
    if not (root / "project.json").is_file():
        root = Path(data.get("root") or root)
    api.use_project(root)
    interval = max(interval, 2.5)  # Tokentide: ≥2 s between polls per job
    t0 = time.time()
    while True:
        _fill_slots(data, root, max_inflight)
        common.save_json(path, data)
        pending = [r for r in data["jobs"] if r.get("status") in PENDING]
        if not pending and not any(r.get("status") == "planned" for r in data["jobs"]):
            break
        for rec in pending:
            dest = root / rec["out"]
            try:
                state, info = retrieve_once(rec, dest)
            except api.APIError as e:
                rec["errors"] = rec.get("errors", 0) + 1
                rec["last_error"] = str(e)[:300]
                if e.status == 404:
                    rec["status"] = "failed"
                    rec["last_error"] = ("job not found — Tokentide refunds failed jobs automatically (then 404), or the "
                                         "media expired; check usage. " + rec["last_error"])
                elif e.status in (400, 410, 422) or rec["errors"] >= 6:
                    rec["status"] = "failed"
                if rec["status"] == "failed":
                    common.log(f"[{rec['key']}] FAILED: {rec['last_error'][:200]}")
                common.save_json(path, data)
                continue
            if state == "done":
                dest = info["path"]
                pr = common.probe(dest)
                if not pr["duration"]:
                    rec["errors"] = rec.get("errors", 0) + 1
                    rec["last_error"] = "downloaded file unreadable; will retrieve again"
                    common.save_json(path, data)
                    continue
                rec["out"] = str(Path(dest).resolve().relative_to(root.resolve())) if str(dest).startswith(str(root)) else str(dest)
                rec.update(status="done", finished_at=common.now_iso(),
                           probe={k: pr[k] for k in ("duration", "width", "height", "fps", "has_audio")})
                complete(rec)
                print(f"[{rec['key']}] done -> {rec['out']} ({pr['duration']:.1f}s"
                      + (f" {pr['width']}x{pr['height']}" if pr["width"] else "") + ")")
            elif state == "failed":
                rec.update(status="failed", last_error=json.dumps(info)[:300])
                print(f"[{rec['key']}] FAILED: {rec['last_error']}")
            else:
                rec["status"] = "processing"
                avg, el = info.get("average_execution_time"), info.get("execution_duration")
                if avg and el is not None:
                    rec["eta_s"] = max(0, round((avg - el) / 1000))
            common.save_json(path, data)
        if not any(r.get("status") in PENDING + ("planned",) for r in data["jobs"]):
            break
        if time.time() - t0 >= max_seconds:
            break
        time.sleep(interval)
    _sync_spec(data, root)
    return _summary(data, path)


def _sync_spec(data, root):
    if not data.get("spec"):
        return
    spec = common.Spec(root / data["spec"])
    changed = False
    for rec in data["jobs"]:
        if rec.get("status") != "done":
            continue
        target = rec.get("target")
        if target == "music":
            spec.data.setdefault("music", {})["file"] = rec["out"]
            changed = True
        elif target and target.startswith("sfx:"):
            i = int(target.split(":", 1)[1])
            if i < len(spec.data.get("sfx", [])):
                spec.data["sfx"][i]["file"] = rec["out"]
                changed = True
        elif rec.get("shot"):
            v = spec.shot(rec["shot"]).setdefault("video", {})
            cands = v.setdefault("candidates", [])
            if rec["out"] not in cands:
                cands.append(rec["out"])
                changed = True
    if changed:
        spec.save()


def _summary(data, path) -> int:
    jobs = data["jobs"]
    done = [r for r in jobs if r.get("status") == "done"]
    pend = [r for r in jobs if r.get("status") in PENDING]
    plan = [r for r in jobs if r.get("status") == "planned"]
    fail = [r for r in jobs if r.get("status") == "failed"]
    spent = sum(r.get("charge_usd") or 0 for r in jobs if r.get("queue_id"))
    print(f"\nJobs: {len(done)} done, {len(pend)} running, {len(plan)} waiting for a slot, {len(fail)} failed"
          f" · charged ${spent:.2f}  ({path})")
    for r in pend:
        print(f"  running {r['key']} ({r['model']}) eta~{r.get('eta_s', '?')}s")
    for r in fail:
        print(f"  failed  {r['key']}: {r.get('last_error', '')[:160]}")
    if pend or plan:
        print(f"Re-run to keep polling (safe, never re-submits): python3 {Path(__file__).resolve()} poll --jobs {Path(path).resolve()}")
        return 2
    return 1 if fail and not done else 0


def check_queue_open(quotes):
    """Stop before queueing when Tokentide says the queue is closed: after the daily cutoff (video ~23:14 UTC,
    music ~23:39 UTC, until the 00:00 UTC reset), or while capacity is sold out, paused or shed."""
    closed = [q for q in quotes if q and q.get("queue_open") is False]
    if closed:
        q = closed[0]
        cutoff = "~23:39 UTC" if q.get("kind") == "audio" else "~23:14 UTC"
        wait = q.get("retry_after_s")
        when = f"; retry in about {int(wait) // 60} min {int(wait) % 60} s" if wait else ""
        common.die(f"Tokentide's queue is closed right now{when}. After the daily cutoff ({cutoff}) it reopens just "
                   "after the 00:00 UTC reset; otherwise capacity is briefly sold out or paused. Quotes still work.",
                   code=4)


def cmd_run(a):
    spec = common.Spec(a.spec)
    api.use_project(spec.root)
    api.set_lane(a.lane)
    models = common.load_models(spec.root, a.models)
    path = jobs_file(spec)
    data = common.load_json(path, default={"spec": spec.rel(spec.path), "root": str(spec.root), "jobs": []})
    plan = []
    for shot in spec.shots(a.shots):
        v = shot.get("video")
        if not v:
            continue
        existing = [r for r in data["jobs"] if r.get("shot") == shot["id"] and r.get("status") != "failed"]
        takes = a.takes or int(v.get("takes", 2))
        if v.get("selected") and not a.force:
            print(f"{shot['id']}: clip already selected ({v['selected']}); --force to generate more")
            continue
        if existing and not a.force:
            print(f"{shot['id']}: {len(existing)} take(s) already planned/queued/done; --force to add {takes} more")
            continue
        body, warns = build_job(spec, shot, models)
        for w in warns:
            print(f"  ! {shot['id']}: {w}")
        start = max([r.get("take", 0) for r in data["jobs"] if r.get("shot") == shot["id"]], default=0) + 1
        for t in range(start, start + takes):
            key = f"{shot['id']}_t{t}"
            plan.append(({"key": key, "kind": "video", "shot": shot["id"], "take": t, "model": body["model"],
                          "spec": spec.rel(spec.path), "out": f"clips/{spec.vid}_{key}.mp4"}, dict(body)))
    if not plan:
        print("Nothing to generate.")
        return
    cache, total, list_total, unknown, quotes = {}, 0.0, 0.0, 0, []
    for rec, body in plan:
        k = json.dumps(quote_body(body), sort_keys=True)
        if k not in cache:
            try:
                cache[k] = quote(body)
            except api.APIError as e:
                common.die(f"Quote failed for {rec['key']} ({body['model']}): {e}")
        q = cache[k]
        quotes.append(q)
        rec["quote_usd"] = q.get("usd")
        if q.get("usd") is None:
            unknown += 1
        else:
            total += q["usd"]
            list_total += q.get("list_usd") or q["usd"]
    print(f"{'take':<12}{'model':<44}{'dur':>5}{'res':>7}{'audio':>7}{'usd':>8}")
    for rec, body in plan:
        qv = rec["quote_usd"]
        print(f"{rec['key']:<12}{body['model'][:43]:<44}{body['duration']:>5}{str(body.get('resolution', '-')):>7}"
              f"{str(body.get('audio', '-')):>7}{(f'{qv:.2f}' if qv is not None else '?'):>8}")
    mult = next((q.get("multiplier") for q in quotes if q.get("multiplier")), None)
    print(f"Quoted total: ${total:.2f}" + (f" (+{unknown} unquoted)" if unknown else "")
          + (f" · Venice list ${list_total:.2f}, multiplier {mult:.3f}" if mult else "")
          + (f" · lane {a.lane}" if a.lane else ""))
    limit = a.max_usd if a.max_usd is not None else spec.data.get("budget_usd")
    if limit is not None and total > float(limit):
        common.die(f"Quote ${total:.2f} exceeds the video budget ${float(limit):.2f}. Fewer takes/shorter clips/"
                   f"lower resolution/cheaper model/Low Tide lane, or raise budget_usd / pass --max-usd.", code=3)
    cap = common.project_meta(spec.root).get("budget_usd")
    if cap is not None:
        remaining = float(cap) - common.spent_usd(spec.root)
        if total > remaining:
            common.die(f"Quote ${total:.2f} exceeds the remaining project budget ${remaining:.2f} "
                       f"(cap ${float(cap):.2f}). Ask the user before raising it in project.json.", code=3)
    if a.dry_run:
        print("Dry run: nothing queued. (Prices follow Tokentide's tide table: cheapest late in the UTC day; "
              "--lane lowtide is cheaper when open.)")
        return
    check_queue_open(quotes)
    inflight = len([r for r in data["jobs"] if r.get("status") in PENDING])
    free = max(0, a.max_inflight - inflight)
    now_items, later = plan[:free], plan[free:]
    with ThreadPoolExecutor(max_workers=max(1, min(3, len(now_items)))) as ex:
        futs = [ex.submit(submit, rec, body) for rec, body in now_items]
        for (rec, _), f in zip(now_items, futs):
            try:
                data["jobs"].append(f.result())
                print(f"queued {rec['key']} ({rec['model']}) id={rec['queue_id']}")
            except (api.APIError, SystemExit) as e:
                code = getattr(e, "code", None)
                if code in ("rate_limited", "epoch_rollover"):
                    rec["status"] = "planned"
                    print(f"  {rec['key']}: {code}; kept as planned")
                else:
                    rec.update(status="failed", last_error=str(e)[:300])
                    print(f"queue FAILED {rec['key']}: {e}")
                data["jobs"].append(rec)
    for rec, _ in later:
        rec["status"] = "planned"
        data["jobs"].append(rec)
    if later:
        print(f"{len(later)} take(s) wait for a free slot (max {a.max_inflight} unfinished jobs); poll queues them.")
    common.save_json(path, data)
    sys.exit(poll(path, a.poll_seconds, a.interval, a.max_inflight))


def cmd_poll(a):
    api.set_lane(a.lane)
    sys.exit(poll(Path(a.jobs), a.max_seconds, a.interval, a.max_inflight))


def cmd_status(a):
    data = common.load_json(a.jobs)
    for r in data["jobs"]:
        print(f"{r['key']:<12}{r.get('status', '?'):<11}{r['model']:<44}{r.get('charge_usd') or r.get('quote_usd') or '':<8}{r['out']}")


def cmd_select(a):
    spec = common.Spec(a.spec)
    v = spec.shot(a.shot).setdefault("video", {})
    if a.file:
        chosen = spec.rel(spec.p(a.file))
    else:
        match = [c for c in v.get("candidates", []) if c.endswith(f"_t{a.take}.mp4")]
        if not match:
            common.die(f"No take {a.take} for {a.shot}. Candidates: {v.get('candidates')}")
        chosen = match[0]
    v["selected"] = chosen
    spec.save()
    print(f"{a.shot}: video.selected = {chosen}")


def adhoc_body(a):
    anchor = Path(a.out).resolve().parent if getattr(a, "out", None) else Path.cwd()
    model = common.resolve_model(common.find_project_root(anchor), a.model)
    body = {"model": model, "duration": norm_duration(a.duration)}
    if a.prompt:
        body["prompt"] = a.prompt
    for k, val in (("resolution", a.resolution), ("aspect_ratio", a.aspect_ratio), ("negative_prompt", a.negative)):
        if val:
            body[k] = val
    if a.audio is not None:
        body["audio"] = a.audio
    n = 1 + (1 if a.end_image else 0)
    if a.image:
        body["image_url"] = api.encode_image(a.image, mode="data-url", max_side=1920,
                                             max_bytes=api.per_image_budget(n), keep_png=False)
    if a.end_image:
        body["end_image_url"] = api.encode_image(a.end_image, mode="data-url", max_side=1920,
                                                 max_bytes=api.per_image_budget(n), keep_png=False)
    body.update(common.kv_pairs(a.set))
    return body


def cmd_quote(a):
    api.set_lane(a.lane)
    q = quote(adhoc_body(a))
    print(json.dumps(q, indent=2))


def adhoc_submit(body, out, jobs, key, kind="video", target=None, spec_rel=None):
    out = Path(out).resolve()
    root = common.find_project_root(out.parent) or out.parent
    path = Path(jobs) if jobs else root / "logs" / f"adhoc_{kind}_jobs.json"
    data = common.load_json(path, default={"root": str(root), "jobs": []})
    if spec_rel:
        data["spec"] = spec_rel
    try:
        rel = str(out.relative_to(root))
    except ValueError:
        rel = str(out)
    rec = {"key": key or out.stem, "kind": kind, "model": body["model"], "out": rel}
    if target:
        rec["target"] = target
    try:
        q = quote(body, kind)
        rec["quote_usd"] = q.get("usd")
        check_queue_open([q])
    except api.APIError:
        rec["quote_usd"] = None
    data["jobs"].append(submit(rec, body))
    common.save_json(path, data)
    print(f"queued {rec['key']} id={rec['queue_id']} quote=${rec['quote_usd']}")
    return path


def cmd_submit(a):
    api.set_lane(a.lane)
    api.use_project(common.find_project_root(Path(a.out).resolve().parent))
    path = adhoc_submit(adhoc_body(a), a.out, a.jobs, a.key)
    sys.exit(poll(path, a.poll_seconds, a.interval))


def cmd_upscale(a):
    api.use_project(common.find_project_root(Path(a.out).resolve().parent))
    if a.video.startswith("http"):
        url, dur = a.video, a.duration
    else:
        src = Path(a.video)
        dur = a.duration or common.probe(src)["duration"]
        url = api.encode_file_data_url(src)  # dies with guidance when over the 4.5 MB body limit
    body = {"model": a.model, "video_url": url, "upscale_factor": a.factor, "duration": norm_duration(max(1, round(dur or 5)))}
    body.update(common.kv_pairs(a.set))
    path = adhoc_submit(body, a.out, a.jobs, a.key or "upscale")
    sys.exit(poll(path, a.poll_seconds, a.interval))


def cmd_cleanup(a):
    data = common.load_json(a.jobs)
    for r in data["jobs"]:
        if r.get("status") == "done" and not r.get("completed"):
            complete(r)
            print(f"completed {r['key']}: {r.get('completed', False)}")
    common.save_json(a.jobs, data)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--spec", required=True)
    r.add_argument("--shots", help="comma-separated shot ids (default all)")
    r.add_argument("--takes", type=int, help="takes per shot (default video.takes or 2)")
    r.add_argument("--max-usd", type=float, help="abort if the quoted total exceeds this")
    r.add_argument("--models", help="models.json path (default <project>/models.json)")
    r.add_argument("--lane", choices=["standard", "lowtide"], help="lowtide = cheaper best-effort lane (falls back to standard)")
    r.add_argument("--max-inflight", type=int, default=MAX_INFLIGHT, help="unfinished jobs at once (Tokentide max 8)")
    r.add_argument("--dry-run", action="store_true", help="quote only")
    r.add_argument("--force", action="store_true", help="add takes even if some exist/selected")
    r.add_argument("--poll-seconds", type=int, default=240, help="time box for polling in this call")
    r.add_argument("--interval", type=float, default=7.0)
    p = sub.add_parser("poll")
    p.add_argument("--jobs", required=True)
    p.add_argument("--max-seconds", type=int, default=240)
    p.add_argument("--interval", type=float, default=7.0)
    p.add_argument("--max-inflight", type=int, default=MAX_INFLIGHT)
    p.add_argument("--lane", choices=["standard", "lowtide"])
    s = sub.add_parser("status")
    s.add_argument("--jobs", required=True)
    se = sub.add_parser("select")
    se.add_argument("--spec", required=True)
    se.add_argument("--shot", required=True)
    se.add_argument("--take", type=int)
    se.add_argument("--file")
    for name in ("quote", "submit"):
        q = sub.add_parser(name)
        q.add_argument("--model", required=True)
        q.add_argument("--prompt")
        q.add_argument("--duration", default="5s")
        q.add_argument("--resolution")
        q.add_argument("--aspect-ratio")
        q.add_argument("--negative")
        q.add_argument("--audio", type=lambda x: x.lower() == "true", help="true|false")
        q.add_argument("--image", help="local file (shrunk to fit 4.5 MB) or public https URL")
        q.add_argument("--end-image")
        q.add_argument("--lane", choices=["standard", "lowtide"])
        q.add_argument("--set", action="append", help="extra field key=value (JSON ok), e.g. elements=[...]")
        if name == "submit":
            q.add_argument("--out", required=True)
            q.add_argument("--jobs")
            q.add_argument("--key")
            q.add_argument("--poll-seconds", type=int, default=240)
            q.add_argument("--interval", type=float, default=7.0)
    u = sub.add_parser("upscale")
    u.add_argument("--video", required=True, help="public https URL (local files only if under ~3 MB)")
    u.add_argument("--duration", type=float, help="clip length in seconds (needed for URLs)")
    u.add_argument("--out", required=True)
    u.add_argument("--model", default="topaz-video-upscale")
    u.add_argument("--factor", type=int, default=2)
    u.add_argument("--set", action="append")
    u.add_argument("--jobs")
    u.add_argument("--key")
    u.add_argument("--poll-seconds", type=int, default=240)
    u.add_argument("--interval", type=float, default=7.0)
    c = sub.add_parser("cleanup")
    c.add_argument("--jobs", required=True)
    a = ap.parse_args()
    {"run": cmd_run, "poll": cmd_poll, "status": cmd_status, "select": cmd_select, "quote": cmd_quote,
     "submit": cmd_submit, "upscale": cmd_upscale, "cleanup": cmd_cleanup}[a.cmd](a)


if __name__ == "__main__":
    try:
        main()
    except api.APIError as e:
        common.die(str(e))
