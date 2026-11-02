#!/usr/bin/env python3
"""Image generation & editing through Tokentide (Venice-compatible): keyframes, product composites, cutouts, upscales.

Tokentide notes: bodies are capped at 4.5 MB (inputs are shrunk to fit; public https URLs pass through),
image requests are paced to the account limit (2/min on new accounts), and safe_mode is always on.

Subcommands (`image.py <cmd> -h` for options):
  generate    text-to-image (scenes, backgrounds, product-free shots)  POST /image/generate
  edit        one image + instruction (restyle a real product photo)   POST /image/edit
  multi-edit  2-3 images, e.g. [scene, product cutout] composite        POST /image/multi-edit
  bg-remove   product cutout with alpha                                 POST /image/background-remove
  upscale     2x/4x upscale, optional enhance                           POST /image/upscale
  styles      list style presets                                        GET  /image/styles
  frame       fit a real photo into a 9:16 keyframe (local, free)
  keyframes   run every shots[].keyframe job in a video spec, in parallel, + contact sheet
  select      mark a keyframe candidate as selected in the spec

Every output gets a <file>.json sidecar (endpoint, model, prompt, request id) = provenance log.
"""
from __future__ import annotations

import argparse
import base64
import re
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import common
import apiclient as api

FIDELITY = ("Keep the product exactly as in the reference image: identical shape, proportions, materials, colors, "
            "label text, logo and their placement. Do not add, remove or alter any text or logo. "
            "Photorealistic, product in sharp focus.")
AR_DIMS = {"9:16": (768, 1344), "16:9": (1344, 768), "1:1": (1024, 1024), "4:5": (896, 1120),
           "5:4": (1120, 896), "3:4": (960, 1280), "4:3": (1280, 960), "2:3": (832, 1248), "3:2": (1248, 832)}
DROPPABLE = ("variants", "negative_prompt", "style_preset", "cfg_scale", "steps", "quality", "resolution",
             "hide_watermark", "format", "output_format", "seed", "embed_exif_metadata", "safe_mode",
             "enhance_prompt", "style_references")


def nearest_ar(w, h) -> str:
    r = w / h
    return min(AR_DIMS, key=lambda k: abs(AR_DIMS[k][0] / AR_DIMS[k][1] - r))


def call_with_fixes(path, body):
    """POST with automatic, logged fixes for model-specific parameter differences."""
    body = dict(body)
    for attempt in range(7):
        try:
            api.throttle("image")
            return api.post_json(path, body, timeout=600), body
        except api.APIError as e:
            if e.status != 400 or attempt == 6:
                raise
            msg = e.message.lower()
            if ("width" in msg or "height" in msg) and "width" in body:
                body["aspect_ratio"] = nearest_ar(body.pop("width"), body.pop("height", body.get("width", 1)))
                common.log(f"[image] model wants aspect_ratio, not width/height -> {body['aspect_ratio']}")
                continue
            if "aspect" in msg and "aspect_ratio" in body and path.endswith("/generate"):
                body["width"], body["height"] = AR_DIMS.get(body.pop("aspect_ratio"), (1024, 1024))
                common.log(f"[image] model wants width/height -> {body['width']}x{body['height']}")
                continue
            if "modelid" in msg and "model" in body:
                body["modelId"] = body.pop("model")
                continue
            if "model" in msg and "required" in msg and "modelId" in body:
                body["model"] = body.pop("modelId")
                continue
            if "image_url" in msg and isinstance(body.get("image"), str):
                b = body.pop("image")
                if not b.startswith(("http", "data:")):
                    mime = api.sniff(base64.b64decode(b[:64]))[1] or "image/png"
                    b = f"data:{mime};base64,{b}"
                body["image_url"] = b
                continue
            dropped = [k for k in DROPPABLE if k in body and (k in msg or k.replace("_", " ") in msg)]
            if not dropped:
                raise
            for k in dropped:
                common.log(f"[image] API rejected '{k}' -> retrying without it")
                body.pop(k)
    raise RuntimeError("unreachable")


def save_blobs(blobs, out, start=1, force_index=False):
    out = Path(out)
    stem = out.with_suffix("") if out.suffix else out
    stem.parent.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, (data, ext) in enumerate(blobs):
        name = f"{stem.name}_k{start + i}" if (force_index or len(blobs) > 1) else stem.name
        p = stem.with_name(f"{name}.{ext}")
        p.write_bytes(data)
        paths.append(p)
    return paths


def parallel(fn, items, workers=3):
    if not items:
        return []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(items)))) as ex:
        futs = [ex.submit(fn, it) for it in items]
        res = []
        for f in futs:
            try:
                res.append(f.result())
            except (api.APIError, SystemExit, OSError) as e:
                res.append(e)
        return res


_MODELS = None


def estimate_usd(model, body):
    """Rough per-image price from cached model pricing (for the budget ledger only)."""
    global _MODELS
    if _MODELS is None:
        _MODELS = common.load_models(api._PROJECT_ROOT) if api._PROJECT_ROOT else {}
    entry = _MODELS.get(model)
    if not entry:
        return None
    flat = common.flatten((entry.get("model_spec") or {}).get("pricing") or {})
    nums = {k.lower(): float(v) for k, v in flat.items() if isinstance(v, (int, float)) and "usd" in k.lower()}
    if not nums:
        return None
    for hint in (str(body.get("resolution", "")).lower(), str(body.get("quality", "")).lower()):
        hits = [v for k, v in nums.items() if hint and hint in k]
        if hits:
            return max(hits)
    return max(nums.values())


def run_one(path, body, out, index=None):
    """One API call -> saved file(s) + sidecars. Returns list of paths."""
    resp, used = call_with_fixes(path, body)
    blobs = api.extract_media(resp)
    paths = save_blobs(blobs, out, start=index or 1, force_index=index is not None)
    for p in paths:
        api.write_sidecar(p, path, used, resp)
    model = used.get("model") or used.get("modelId")
    est = estimate_usd(model, used)
    api.log_call("image", path, model=model, resp=resp, n=len(paths),
                    usd_est=round(est * len(paths), 4) if est is not None else None)
    return paths


def root_for(out, a=None):
    root = common.find_project_root(Path(out).resolve().parent) or common.find_project_root(Path.cwd())
    api.use_project(root)
    if a is not None and getattr(a, "model", None):
        a.model = common.resolve_model(root, a.model)
    return root


def report(results):
    ok = 0
    for r in results:
        if isinstance(r, Exception):
            print(f"FAILED: {r}")
        else:
            for p in r:
                ok += 1
                print(p)
    if not ok:
        sys.exit(1)


# ---------------------------------------------------------------- subcommands
def cmd_generate(a):
    root_for(a.out, a)
    body = {"model": a.model, "prompt": a.prompt, "hide_watermark": True}
    opt = dict(negative_prompt=a.negative, aspect_ratio=a.aspect_ratio, resolution=a.resolution, width=a.width,
               height=a.height, quality=a.quality, seed=a.seed, style_preset=a.style_preset, cfg_scale=a.cfg_scale,
               steps=a.steps, format=a.format)
    body.update({k: v for k, v in opt.items() if v is not None})
    if a.style_ref:
        refs = []
        for item in a.style_ref:
            path, _, strength = item.partition(":")
            refs.append({"image": api.encode_image(path, max_bytes=api.per_image_budget(len(a.style_ref) + 1)),
                         "strength": float(strength or 0.6)})
        body["style_references"] = refs
    body.update(common.kv_pairs(a.set))
    if a.n > 1:
        body["variants"] = min(a.n, 4)
    resp, used = call_with_fixes("/image/generate", body)
    blobs = api.extract_media(resp)
    paths = save_blobs(blobs, a.out, force_index=a.n > 1)
    for p in paths:
        api.write_sidecar(p, "/image/generate", used, resp)
    est = estimate_usd(a.model, used)
    api.log_call("image", "/image/generate", model=a.model, resp=resp, n=len(paths),
                    usd_est=round(est * len(paths), 4) if est is not None else None)
    results = [paths]
    missing = a.n - len(blobs)
    if missing > 0:  # model ignored/rejected variants -> extra calls
        single = {k: v for k, v in used.items() if k != "variants"}
        idx = list(range(len(blobs) + 1, a.n + 1))

        def extra(i):
            b = dict(single)
            if "seed" in b:
                b["seed"] = int(b["seed"]) + i
            return run_one("/image/generate", b, a.out, index=i)
        results += parallel(extra, idx, a.parallel)
    report(results)


def edit_body(a, multi=False):
    prompt = a.prompt if a.no_lock else add_fidelity(a.prompt)
    if multi:
        body = {"modelId": a.model, "prompt": prompt,
                "images": [api.encode_image(x, mode=a.encoding, max_bytes=api.per_image_budget(len(a.images)))
                           for x in a.images]}
    else:
        body = {"model": a.model, "prompt": prompt, "image": api.encode_image(a.image, mode=a.encoding)}
    opt = dict(aspect_ratio=a.aspect_ratio, resolution=a.resolution, quality=a.quality, output_format=a.format)
    body.update({k: v for k, v in opt.items() if v is not None})
    body.update(common.kv_pairs(a.set))
    return body


def add_fidelity(prompt: str) -> str:
    if re.search(r"(do not (alter|change)|exactly as|unchanged|identical)", prompt, re.I):
        return prompt
    return prompt.rstrip(". ") + ". " + FIDELITY


def cmd_edit(a, multi=False):
    root_for(a.out, a)
    body = edit_body(a, multi)
    path = "/image/multi-edit" if multi else "/image/edit"
    if a.n == 1:
        report([run_one(path, body, a.out)])
    else:
        report(parallel(lambda i: run_one(path, body, a.out, index=i), list(range(1, a.n + 1)), a.parallel))


def cmd_bg_remove(a):
    root_for(a.out)
    body = {"image": api.encode_image(a.image, mode=a.encoding, keep_png=True)}
    body.update(common.kv_pairs(a.set))
    report([run_one("/image/background-remove", body, a.out)])


def cmd_upscale(a):
    root_for(a.out)
    body = {"image": api.encode_image(a.image, max_side=None, max_bytes=api.per_image_budget(1)), "scale": a.scale}
    if a.enhance:
        body.update(enhance=True, enhanceCreativity=a.creativity, replication=a.replication)
        if a.enhance_prompt:
            body["enhancePrompt"] = a.enhance_prompt
    body.update(common.kv_pairs(a.set))
    report([run_one("/image/upscale", body, a.out)])


def cmd_styles(a):
    j = api.get("/image/styles").json()
    items = j.get("data", j) if isinstance(j, dict) else j
    for s in items:
        print(s if isinstance(s, str) else s.get("name") or s)


def fit_frame(src, dst, fit="cover", bg="#F4F1EC", size="1080x1920"):
    w, h = size.lower().split("x")
    if fit == "cover":
        vf = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"
    else:
        vf = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color={bg}"
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    common.ffmpeg(["-y", "-i", src, "-vf", vf + ",format=rgb24", "-frames:v", "1", dst])
    return Path(dst)


def cmd_frame(a):
    print(fit_frame(a.image, a.out, a.fit, a.bg, a.size))


# ---------------------------------------------------------------- spec-driven keyframes
def next_index(folder: Path, prefix: str) -> int:
    nums = [int(m.group(1)) for p in folder.glob(prefix + "_k*.*")
            if (m := re.search(r"_k(\d+)\.[a-z0-9]+$", p.name))]
    return max(nums, default=0) + 1


def keyframe_jobs(spec, shot, n):
    kf = shot["keyframe"]
    mode = kf.get("mode", "multi-edit")
    model = common.resolve_model(spec.root, kf.get("model"))
    prompt = kf.get("prompt", "")
    ar = kf.get("aspect_ratio", spec.data.get("aspect_ratio", "9:16"))
    inputs = [spec.p(x) for x in kf.get("inputs", [])]
    for x in inputs:
        if isinstance(x, Path) and not x.exists():
            common.die(f"{shot['id']}: keyframe input not found: {x}")
    if mode in ("generate", "edit", "multi-edit") and not (model and prompt):
        common.die(f"{shot['id']}: keyframe mode '{mode}' needs model and prompt")
    lock = kf.get("lock_product", mode in ("edit", "multi-edit"))
    if lock and mode in ("edit", "multi-edit"):
        prompt = add_fidelity(prompt)
    extra = kf.get("extra") or {}
    if mode == "generate":
        if re.search(r"\b(product|bottle|package|label|logo)\b", prompt, re.I) and not kf.get("allow_invented_product"):
            common.log(f"WARNING {shot['id']}: 'generate' invents the product. Use multi-edit with a real product photo "
                       "for product shots (set allow_invented_product=true to silence).")
        body = {"model": model, "prompt": prompt, "aspect_ratio": ar, "hide_watermark": True}
        for k in ("negative_prompt", "resolution", "style_preset", "seed", "quality"):
            if kf.get(k) is not None:
                body[k] = kf[k]
        body.update(extra)
        return "/image/generate", body
    if mode == "edit":
        if len(inputs) != 1:
            common.die(f"{shot['id']}: edit mode needs exactly 1 input image")
        body = {"model": model, "prompt": prompt, "image": api.encode_image(inputs[0]), "aspect_ratio": ar}
    elif mode == "multi-edit":
        if not 2 <= len(inputs) <= 3:
            common.die(f"{shot['id']}: multi-edit needs 2-3 input images (e.g. [scene, product cutout])")
        body = {"modelId": model, "prompt": prompt,
                "images": [api.encode_image(x, max_bytes=api.per_image_budget(len(inputs))) for x in inputs],
                "aspect_ratio": ar}
    else:
        return mode, None
    for k in ("resolution", "quality"):
        if kf.get(k) is not None:
            body[k] = kf[k]
    body.update(extra)
    return ("/image/edit" if mode == "edit" else "/image/multi-edit"), body


def cmd_keyframes(a):
    import qa  # local module: contact sheets

    spec = common.Spec(a.spec)
    api.use_project(spec.root)
    kdir = spec.root / "keyframes"
    kdir.mkdir(exist_ok=True)
    work = []
    for shot in spec.shots(a.shots):
        kf = shot.get("keyframe")
        if not kf:
            continue
        if kf.get("selected") and not a.force:
            print(f"{shot['id']}: selected keyframe exists ({kf['selected']}); use --force to make more")
            continue
        n = a.n or int(kf.get("n", 3))
        mode = kf.get("mode", "multi-edit")
        prefix = f"{spec.vid}_{shot['id']}"
        if mode in ("frame", "file"):
            src = spec.p((kf.get("inputs") or [None])[0])
            if not src or not Path(src).exists():
                common.die(f"{shot['id']}: mode '{mode}' needs inputs[0] (a real photo)")
            dst = kdir / f"{prefix}_k{next_index(kdir, prefix)}.png"
            if mode == "frame":
                fit_frame(src, dst, kf.get("fit", "cover"), kf.get("bg", "#F4F1EC"))
            else:
                shutil.copy(src, dst.with_suffix(Path(src).suffix))
                dst = dst.with_suffix(Path(src).suffix)
            kf.setdefault("candidates", []).append(spec.rel(dst))
            print(f"{shot['id']}: {dst}")
            continue
        path, body = keyframe_jobs(spec, shot, n)
        start = next_index(kdir, prefix)
        for i in range(start, start + n):
            b = dict(body)
            if "seed" in b:
                b["seed"] = int(b["seed"]) + i
            work.append((shot, path, b, kdir / prefix, i))
    results = parallel(lambda w: run_one(w[1], w[2], w[3], index=w[4]), work, a.parallel)
    by_shot = {}
    for (shot, *_), res in zip(work, results):
        if isinstance(res, Exception):
            print(f"{shot['id']}: FAILED: {res}")
            continue
        by_shot.setdefault(shot["id"], []).extend(res)
    spec_fresh = common.Spec(a.spec)  # re-read to avoid clobbering concurrent edits
    for sid, paths in by_shot.items():
        kf = spec_fresh.shot(sid).setdefault("keyframe", {})
        cands = kf.setdefault("candidates", [])
        cands += [spec_fresh.rel(p) for p in paths if spec_fresh.rel(p) not in cands]
        sheet = spec_fresh.root / "qa" / f"{spec_fresh.vid}_{sid}_keyframes.jpg"
        qa.make_sheet([str(spec_fresh.p(c)) for c in cands], sheet, labels=[Path(c).stem for c in cands])
        print(f"{sid}: {len(paths)} new -> {', '.join(Path(p).name for p in paths)}  | sheet: {spec_fresh.rel(sheet)}")
    for shot in spec.shots(a.shots):  # carry over frame/file candidates added above
        if shot.get("keyframe", {}).get("mode") in ("frame", "file"):
            spec_fresh.shot(shot["id"])["keyframe"]["candidates"] = shot["keyframe"]["candidates"]
    spec_fresh.save()
    print("Next: look at each sheet next to the real product photo, then "
          "`image.py select --spec ... --shot sN --k K` (rubric: references/qa-rubric.md).")
    if any(isinstance(r, Exception) for r in results) and not by_shot:
        sys.exit(1)


def cmd_select(a):
    spec = common.Spec(a.spec)
    kf = spec.shot(a.shot).setdefault("keyframe", {})
    if a.file:
        chosen = spec.rel(spec.p(a.file))
    else:
        cands = kf.get("candidates") or []
        match = [c for c in cands if re.search(rf"_k{a.k}\.[a-z0-9]+$", c)]
        if not match:
            common.die(f"No candidate k{a.k} for {a.shot}. Candidates: {cands}")
        chosen = match[0]
    kf["selected"] = chosen
    spec.save()
    print(f"{a.shot}: keyframe.selected = {chosen}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common_out(p, default_n=1):
        p.add_argument("--out", required=True, help="output path or stem (extension comes from the response)")
        p.add_argument("--n", type=int, default=default_n, help="number of variants")
        p.add_argument("--parallel", type=int, default=3)
        p.add_argument("--set", action="append", help="extra API field key=value (JSON values ok)")

    g = sub.add_parser("generate")
    g.add_argument("--model", required=True)
    g.add_argument("--prompt", required=True)
    g.add_argument("--negative")
    g.add_argument("--aspect-ratio", default="9:16")
    g.add_argument("--resolution", help="1K|2K|4K (tiered models)")
    g.add_argument("--width", type=int)
    g.add_argument("--height", type=int)
    g.add_argument("--quality", help="low|medium|high (gpt-image models)")
    g.add_argument("--seed", type=int)
    g.add_argument("--style-preset")
    g.add_argument("--style-ref", action="append", help="path:strength (0.1-1)")
    g.add_argument("--cfg-scale", type=float)
    g.add_argument("--steps", type=int)
    g.add_argument("--format", choices=["png", "jpeg", "webp"])
    common_out(g)

    for name, multi in (("edit", False), ("multi-edit", True)):
        e = sub.add_parser(name)
        e.add_argument("--model", required=True)
        e.add_argument("--prompt", required=True)
        if multi:
            e.add_argument("--images", nargs="+", required=True, help="2-3 images, e.g. scene.png product_cutout.png")
        else:
            e.add_argument("--image", required=True)
        e.add_argument("--aspect-ratio", default="9:16", help="e.g. 9:16 or auto")
        e.add_argument("--resolution")
        e.add_argument("--quality")
        e.add_argument("--format", choices=["png", "jpeg", "webp"])
        e.add_argument("--encoding", default="base64", choices=["base64", "data-url"])
        e.add_argument("--no-lock", action="store_true", help="don't append the product-fidelity clause")
        common_out(e)

    b = sub.add_parser("bg-remove")
    b.add_argument("--image", required=True)
    b.add_argument("--encoding", default="base64", choices=["base64", "data-url"])
    common_out(b)

    u = sub.add_parser("upscale")
    u.add_argument("--image", required=True)
    u.add_argument("--scale", type=int, default=2)
    u.add_argument("--enhance", action="store_true")
    u.add_argument("--creativity", type=float, default=0.15)
    u.add_argument("--replication", type=float, default=0.35)
    u.add_argument("--enhance-prompt")
    common_out(u)

    sub.add_parser("styles")

    f = sub.add_parser("frame")
    f.add_argument("--image", required=True)
    f.add_argument("--out", required=True)
    f.add_argument("--fit", default="cover", choices=["cover", "contain"])
    f.add_argument("--bg", default="#F4F1EC", help="pad color for contain")
    f.add_argument("--size", default="1080x1920")

    k = sub.add_parser("keyframes")
    k.add_argument("--spec", required=True)
    k.add_argument("--shots", help="comma-separated shot ids (default: all)")
    k.add_argument("--n", type=int, help="variants per shot (default keyframe.n or 3)")
    k.add_argument("--parallel", type=int, default=3)
    k.add_argument("--force", action="store_true", help="generate even if a keyframe is already selected")

    s = sub.add_parser("select")
    s.add_argument("--spec", required=True)
    s.add_argument("--shot", required=True)
    s.add_argument("--k", type=int)
    s.add_argument("--file")

    a = ap.parse_args()
    {"generate": cmd_generate, "edit": lambda x: cmd_edit(x, False), "multi-edit": lambda x: cmd_edit(x, True),
     "bg-remove": cmd_bg_remove, "upscale": cmd_upscale, "styles": cmd_styles, "frame": cmd_frame,
     "keyframes": cmd_keyframes, "select": cmd_select}[a.cmd](a)


if __name__ == "__main__":
    try:
        main()
    except api.APIError as e:
        common.die(str(e))
