#!/usr/bin/env python3
"""Quality control for keyframes, clips and final renders.

  check     specs, black/frozen frames, loudness, platform limits on a render (exit 1 on FAIL)
  frames    extract frames + a labelled contact sheet so you can LOOK at a clip or render
  sheet     contact sheet from still images (e.g. keyframe candidates)
  safezone  a frame with the platform UI zones shaded: check text/logo/hook placement
  vision    optional batch scoring with a vision model (via Tokentide) vs product reference photos (JSON)

The decisive QA step is visual: open the sheet / safe-zone images and judge them against
references/qa-rubric.md. `vision` is for headless runs or a second opinion.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import sys
import tempfile
from pathlib import Path

import common

UI = {"top": 250, "bottom": 650, "right": 150, "left": 60}  # conservative union of TikTok/Reels overlays


def _label_filter(text, tmpdir: Path):
    if not common.has_filter("drawtext"):
        return ""
    font = next(iter(sorted(common.FONTS_DIR.glob("Montserrat*.ttf"))), None) or next(iter(common.FONTS_DIR.glob("*.ttf")), None)
    if not font:
        return ""
    if not (tmpdir / "label.ttf").exists():
        shutil.copy(font, tmpdir / "label.ttf")
    safe = re.sub(r"[^A-Za-z0-9 _.\-]", "", text)[:40]
    return (f",drawtext=fontfile=label.ttf:text='{safe}':x=12:y=12:fontsize=34:fontcolor=white:"
            f"box=1:boxcolor=black@0.65:boxborderw=8")


def make_sheet(images, out, cols=None, tile_w=360, labels=None):
    images = [str(i) for i in images if Path(i).exists()]
    if not images:
        return None
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    n = len(images)
    cols = cols or min(4, n)
    rows = math.ceil(n / cols)
    first = common.probe(images[0])
    if first.get("width") and first.get("height"):
        tile_h = max(120, int(round(tile_w * first["height"] / first["width"] / 2)) * 2)
    else:
        tile_h = int(tile_w * 16 / 9)
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        for i in range(cols * rows):
            dst = tdp / f"tile_{i:03d}.png"
            if i < n:
                lab = _label_filter(labels[i] if labels and i < len(labels) else Path(images[i]).stem, tdp)
                vf = (f"scale={tile_w}:{tile_h}:force_original_aspect_ratio=decrease,"
                      f"pad={tile_w}:{tile_h}:(ow-iw)/2:(oh-ih)/2:color=0x111111{lab}")
                common.ffmpeg(["-y", "-i", Path(images[i]).resolve(), "-vf", vf, "-frames:v", "1", dst.name], cwd=tdp)
            else:
                common.ffmpeg(["-y", "-f", "lavfi", "-i", f"color=c=0x111111:s={tile_w}x{tile_h}", "-frames:v", "1", dst.name], cwd=tdp)
        common.ffmpeg(["-y", "-framerate", "1", "-i", "tile_%03d.png", "-vf",
                       f"tile={cols}x{rows}:padding=8:margin=8:color=0x222222", "-frames:v", "1", "-q:v", "3",
                       out.resolve()], cwd=tdp)
    return out


def frame_times(dur, every, at):
    if at:
        out = []
        for x in at.split(","):
            x = x.strip()
            out.append(dur / 2 if x == "mid" else max(0.0, dur - 0.15) if x == "end" else float(x))
        return sorted(set(round(t, 2) for t in out if 0 <= t <= dur))
    ts = [0.3]
    t = every
    while t < dur - 0.2:
        ts.append(t)
        t += every
    ts.append(max(0.0, dur - 0.15))
    ts = sorted(set(round(x, 2) for x in ts))
    while len(ts) > 24:
        ts = ts[::2] + ([ts[-1]] if ts[-1] not in ts[::2] else [])
    return ts


def cmd_frames(a):
    src = Path(a.file)
    dur = common.probe(src)["duration"]
    root = common.find_project_root(src.resolve().parent)
    out_dir = Path(a.out) if a.out else ((root / "qa" if root else src.parent) / f"{src.stem}_frames")
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, t in enumerate(frame_times(dur, a.every, a.at)):
        p = out_dir / f"f{i:02d}_{t:05.2f}s.jpg"
        common.ffmpeg(["-y", "-ss", f"{t:.3f}", "-i", src, "-frames:v", "1", "-q:v", "3", p])
        paths.append(p)
    sheet = make_sheet(paths, out_dir.parent / f"{src.stem}_sheet.jpg", cols=a.cols,
                       labels=[f"{float(p.stem.split('_')[1][:-1]):.1f}s" for p in paths])
    print(f"{len(paths)} frames -> {out_dir}\nsheet: {sheet}")


def cmd_sheet(a):
    print(make_sheet(a.images, a.out, cols=a.cols, labels=[Path(i).stem for i in a.images]))


def cmd_safezone(a):
    src = Path(a.file)
    out = Path(a.out) if a.out else src.with_name(src.stem + "_safezone.jpg")
    spec = common.Spec(a.spec) if getattr(a, "spec", None) else None
    if a.canvas or spec:
        cv = common.canvas_for(spec=spec, aspect=a.canvas)
    else:
        info = common.probe(src)
        cv = common.canvas_for(aspect=common.nearest_canvas_aspect(info.get("width") or 0, info.get("height") or 0))
    w, h, u = cv["w"], cv["h"], cv["safe"]
    with tempfile.TemporaryDirectory() as td:
        frame = Path(td) / "f.png"
        if src.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
            common.ffmpeg(["-y", "-i", src, "-vf", f"scale={w}:{h}", "-frames:v", "1", frame])
        else:
            common.ffmpeg(["-y", "-ss", f"{a.t:.3f}", "-i", src, "-vf", f"scale={w}:{h}", "-frames:v", "1", frame])
        boxes = [
            f"drawbox=x=0:y=0:w=iw:h={u['top']}:color=red@0.30:t=fill",
            f"drawbox=x=0:y=ih-{u['bottom']}:w=iw:h={u['bottom']}:color=red@0.30:t=fill",
            f"drawbox=x=0:y={u['top']}:w={u['left']}:h=ih-{u['top']}-{u['bottom']}:color=yellow@0.25:t=fill",
        ]
        if u.get("action_y") is not None:
            ay = u["action_y"]
            boxes.append(f"drawbox=x=iw-{u['right']}:y={ay}:w={u['right']}:h=ih-{ay}-{u['bottom']}:color=orange@0.40:t=fill")
        else:
            boxes.append(f"drawbox=x=iw-{u['right']}:y={u['top']}:w={u['right']}:h=ih-{u['top']}-{u['bottom']}:color=yellow@0.25:t=fill")
        boxes.append(f"drawbox=x={u['left']}:y={u['top']}:w=iw-{u['left']}-{u['right']}:h=ih-{u['top']}-{u['bottom']}:color=lime@0.9:t=4")
        if cv.get("grid_box"):
            gx, gy, gw, gh = cv["grid_box"]
            boxes.append(f"drawbox=x={gx}:y={gy}:w={gw}:h={gh}:color=cyan@0.8:t=3")
        out.parent.mkdir(parents=True, exist_ok=True)
        common.ffmpeg(["-y", "-i", frame, "-vf", ",".join(boxes), "-frames:v", "1", "-q:v", "3", out])
    extra = ", orange = action buttons, cyan box = 4:5 / grid-safe region for covers" if cv.get("grid_box") else ""
    print(f"{out}  ({cv['aspect']} {w}x{h})\n"
          f"  red = UI/player margins (keep text/logos out), yellow = edge margin, green box = safe text area{extra}")


def detect(path):
    err = common.ffmpeg(["-i", path, "-vf", "blackdetect=d=0.15:pic_th=0.97:pix_th=0.10,freezedetect=n=0.003:d=1.5",
                         "-an", "-f", "null", "-"], loglevel="info").stderr
    black = [(float(s), float(e)) for s, e in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", err)]
    fs = [float(x) for x in re.findall(r"freeze_start: ([\d.]+)", err)]
    fe = [float(x) for x in re.findall(r"freeze_end: ([\d.]+)", err)]
    freeze = [(s, fe[i] if i < len(fe) else None) for i, s in enumerate(fs)]
    return black, freeze


def measure_loudness(path):
    err = common.ffmpeg(["-i", path, "-af", "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
                        loglevel="info").stderr
    blocks = re.findall(r"\{[^{}]*\"input_i\"[^{}]*\}", err, re.S)
    return json.loads(blocks[-1]) if blocks else {}


def cmd_check(a):
    path = Path(a.file)
    info = common.probe(path)
    root = common.find_project_root(path.resolve().parent)
    spec = common.Spec(a.spec) if a.spec else None
    cv = common.canvas_for(spec=spec, root=root, aspect=getattr(a, "canvas", None))
    res = []

    def add(level, what, detail):
        res.append({"level": level, "check": what, "detail": detail})

    w, h, d = info["width"], info["height"], info["duration"]
    exp_w, exp_h, exp_ar = cv["w"], cv["h"], cv["aspect"]
    if (w, h) == (exp_w, exp_h):
        add("PASS", "resolution", f"{exp_w}x{exp_h} ({exp_ar})")
    elif w and h and abs(w / h - exp_w / exp_h) < 0.015:
        add("WARN", "resolution", f"{w}x{h} is {exp_ar} but not {exp_w}x{exp_h} — export the master at {exp_w}x{exp_h}")
    else:
        add("FAIL", "resolution", f"{w}x{h} is not {exp_ar} ({exp_w}x{exp_h})")
    fps = info["fps"] or 0
    add("PASS" if 23.9 <= fps <= 60.1 else "WARN", "fps", f"{fps}")
    add("PASS" if info["vcodec"] == "h264" and info["pix_fmt"] == "yuv420p" else "WARN", "codec",
        f"{info['vcodec']}/{info['pix_fmt']} (want h264/yuv420p)")
    add("PASS" if info["has_audio"] else "WARN", "audio", "present" if info["has_audio"] else "no audio track")
    target = a.target
    if spec:
        target = target or spec.data.get("target_duration_s")
    if target:
        tol = max(1.0, 0.15 * float(target))
        add("PASS" if abs(d - float(target)) <= tol else "WARN", "duration", f"{d:.2f}s vs target {target}s")
    else:
        add("PASS", "duration", f"{d:.2f}s")
    plats = {str(p).strip().lower() for p in (spec.data.get("platforms") or [])} if spec else None
    for plat_key, cap, label in (("x", 140, "X non-Premium max 2:20"), ("instagram", 180, "Reels recommended max 3:00"),
                                 ("youtube-shorts", 180, "YouTube Shorts max 3:00"), ("tiktok", 600, "TikTok 10:00")):
        if (plats is None or plat_key in plats) and d > cap:
            add("WARN", "length cap", f"{d:.0f}s > {cap}s ({label})")
    mb = info["size_bytes"] / 1e6
    add("PASS" if mb < 250 else "WARN", "file size", f"{mb:.1f} MB")
    black, freeze = detect(path)
    for s, e in black:
        if s < 0.5:
            add("FAIL", "black frames", f"{s:.2f}-{e:.2f}s at the start kills the hook")
        elif e < d - 0.5:
            add("WARN", "black frames", f"{s:.2f}-{e:.2f}s mid-video")
    if not black:
        add("PASS", "black frames", "none")
    for s, e in freeze:
        add("WARN", "frozen frames", f"{s:.2f}-{(e if e else d):.2f}s static (frozen AI clip or held frame?)")
    if not freeze:
        add("PASS", "frozen frames", "none ≥1.5s")
    if info["has_audio"]:
        mixcfg = (spec.data.get("audio_mix") or {}) if spec else {}
        tgt_lufs = float(mixcfg.get("lufs", -14.0))
        tgt_tp = float(mixcfg.get("true_peak", -1.5))
        tp_max = max(tgt_tp + 0.5, -1.0) if tgt_tp <= -1.5 else tgt_tp + 0.5
        ln = measure_loudness(path)
        li, tp = common._f(ln.get("input_i"), -99), common._f(ln.get("input_tp"), 0)
        if li <= -70:
            add("WARN", "loudness", "silent audio track — fine only if you add a sound in-app before posting")
        else:
            add("PASS" if (tgt_lufs - 2.0) <= li <= (tgt_lufs + 2.0) else "WARN", "loudness",
                f"{li} LUFS (target {tgt_lufs:g} ±2)")
            add("PASS" if tp <= tp_max else "WARN", "true peak", f"{tp} dBTP (≤ {tp_max:g})")
    width = max(len(r["check"]) for r in res)
    for r in res:
        print(f"{r['level']:<5} {r['check']:<{width}}  {r['detail']}")
    if root:
        common.save_json(root / "qa" / f"{path.stem}_auto.json", {"file": str(path), "checks": res, "probe": info})
    fails = [r for r in res if r["level"] == "FAIL"]
    print(f"\n{'FAIL' if fails else 'OK'}: {len(fails)} fail, {sum(r['level'] == 'WARN' for r in res)} warn. "
          "Automated checks don't replace looking at the frames (qa.py frames / safezone).")
    sys.exit(1 if fails else 0)


RUBRIC = """You are a strict QA reviewer for professional product marketing videos.
Compare every CANDIDATE image with the REFERENCE photos of the real product.
Score each candidate 0-5 on: product_shape, label_logo (text and logo correct and legible vs reference),
color_match, anatomy (hands/people; 5 if none visible), artifacts (5 = no morphing, melting, duplicates, warped
geometry, flicker traces), stray_text (5 = no unintended or garbled text), composition (clear subject, strong
framing matching the canvas), safe_zone (5 = key content inside the safe area, nothing important trapped in UI margins).
pass = product_shape>=4 and label_logo>=4 and color_match>=4 and anatomy>=3 and artifacts>=4 and stray_text>=4.
Return ONLY JSON: {"results":[{"image":"<name>","scores":{...},"pass":true,"issues":["..."],"fix":"<one concrete change to the prompt or approach>"}]}"""

RUBRICS = {
    "product": RUBRIC,
    "people": """You are a strict visual QA director for cinematic videos featuring real people.
Compare every CANDIDATE image side-by-side with the REFERENCE photos of the real person(s).
Score each candidate 0-5 on: facial_likeness (exact match to each person's face, eyes, nose, jaw, hair, age, skin tone),
identity_consistency (faithful relative height, build and natural rapport), anatomy (natural hands, fingers, posture, eye-line),
lighting_realism (natural skin texture, coherent scene light, zero plastic AI sheen), artifacts (5 = no extra limbs, melting,
duplicates, warped details), stray_text (5 = no unintended or garbled text), composition, safe_zone.
pass = facial_likeness>=4 and identity_consistency>=4 and anatomy>=4 and lighting_realism>=4 and artifacts>=4 and stray_text>=4.
Return ONLY JSON: {"results":[{"image":"<name>","scores":{...},"pass":true,"issues":["..."],"fix":"<one concrete change to the prompt or approach>"}]}""",
    "app": """You are a strict visual QA reviewer for software, web app and data walkthrough videos.
Inspect every CANDIDATE image (comparing against REFERENCE captures if supplied).
Score each candidate 0-5 on: ui_fidelity (5 = razor-sharp real UI text, buttons, icons and numbers with zero AI distortion),
legibility (focal labels and numbers readable even at 50% mobile scale), privacy_hygiene (5 = zero loading spinners, cookie
banners, dev overlays, real personal emails, API keys, tokens or private PII), artifacts (5 = no clipping or visual glitches),
composition, safe_zone (5 = key UI clear of player/platform UI overlays).
pass = ui_fidelity>=5 and legibility>=4 and privacy_hygiene>=5 and artifacts>=4 and safe_zone>=4.
Return ONLY JSON: {"results":[{"image":"<name>","scores":{...},"pass":true,"issues":["..."],"fix":"<one concrete change to the capture or framing>"}]}""",
    "general": """You are a strict visual QA director for studio-grade videos.
Compare every CANDIDATE image with any REFERENCE images (real photos, places, objects, Style Master or Character Sheet).
Score each candidate 0-5 on: subject_fidelity (faithful to references/style bible; 5 if consistent), visual_craft (cinematic
framing, coherent lighting, color palette, zero cheap AI sheen), anatomy (natural hands, faces, perspective and geometry),
artifacts (5 = no melting, duplicates, warped edges or flicker), stray_text (5 = no unintended or garbled text),
composition, safe_zone (5 = focal subject and titles clear of platform UI margins).
pass = subject_fidelity>=4 and visual_craft>=4 and anatomy>=3 and artifacts>=4 and stray_text>=4.
Return ONLY JSON: {"results":[{"image":"<name>","scores":{...},"pass":true,"issues":["..."],"fix":"<one concrete change to the prompt or approach>"}]}""",
}


def resolve_vision_mode(mode: str, references: list | None) -> str:
    m = (mode or "auto").strip().lower()
    if m != "auto":
        return m if m in RUBRICS else "general"
    parts = [p.lower() for r in (references or []) for p in Path(r).parts]
    if "people" in parts:
        return "people"
    if "captures" in parts:
        return "app"
    if "product" in parts:
        return "product"
    return "general"


def pick_vision_model(root):
    models = common.load_models(root)
    if not models:
        import apiclient as api

        models = {m["id"]: m for m in api.get("/models?type=text").json().get("data", [])}
    cands = []
    for mid, m in models.items():
        caps = (m.get("model_spec") or {}).get("capabilities") or {}
        if caps.get("supportsVision"):
            priv = str((m.get("model_spec") or {}).get("privacy", "")).lower() == "private"
            cands.append((0 if priv else 1, mid))
    if not cands:
        common.die("No vision-capable model found; pass --model (see models.py --type text --find vision)")
    return sorted(cands)[0][1]


def cmd_vision(a):
    import apiclient as api

    root = common.find_project_root(Path(a.images[0]).resolve().parent)
    api.use_project(root)
    model = a.model or pick_vision_model(root)
    mode = resolve_vision_mode(getattr(a, "mode", "auto"), a.reference)
    rubric = RUBRICS[mode]
    content = [{"type": "text", "text": rubric + (f"\nContext: {a.context}" if a.context else "")}]
    for r in a.reference or []:
        content += [{"type": "text", "text": f"REFERENCE {Path(r).name}:"},
                    {"type": "image_url", "image_url": {"url": api.encode_image(r, mode="data-url", max_side=1024, keep_png=False)}}]
    for i in a.images:
        content += [{"type": "text", "text": f"CANDIDATE {Path(i).name}:"},
                    {"type": "image_url", "image_url": {"url": api.encode_image(i, mode="data-url", max_side=1024, keep_png=False)}}]
    body = {"model": model, "messages": [{"role": "user", "content": content}], "temperature": 0.1,
            "venice_parameters": {"include_venice_system_prompt": False}}
    resp, _ = api.post_adaptive("/chat/completions", body, droppable=("venice_parameters", "temperature"))
    api.log_call("vision", "/chat/completions", model=model, resp=resp)
    text = resp.json()["choices"][0]["message"]["content"]
    text = text if isinstance(text, str) else json.dumps(text)
    m = re.search(r"\{.*\}", text, re.S)
    try:
        data = json.loads(m.group()) if m else {"raw": text}
    except json.JSONDecodeError:
        data = {"raw": text}
    data["model"] = model
    data["mode"] = mode
    out = Path(a.out) if a.out else ((root / "qa") if root else Path(".")) / "vision_qa.json"
    common.save_json(out, data)
    for r in data.get("results", []):
        print(f"{'PASS' if r.get('pass') else 'FAIL'} {r.get('image')} [{mode}]: {r.get('scores')} {('- ' + '; '.join(r.get('issues', []))) if r.get('issues') else ''}")
    print(f"saved {out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("file")
    c.add_argument("--spec")
    c.add_argument("--canvas", help="expected aspect ratio or WxH (9:16, 16:9, 1:1; default from spec/project)")
    c.add_argument("--target", type=float, help="target duration (s)")
    f = sub.add_parser("frames")
    f.add_argument("file")
    f.add_argument("--every", type=float, default=1.0)
    f.add_argument("--at", help="comma list of seconds, 'mid', 'end'")
    f.add_argument("--cols", type=int)
    f.add_argument("--out")
    s = sub.add_parser("sheet")
    s.add_argument("images", nargs="+")
    s.add_argument("--out", required=True)
    s.add_argument("--cols", type=int)
    z = sub.add_parser("safezone")
    z.add_argument("file")
    z.add_argument("--spec")
    z.add_argument("--canvas", help="aspect ratio (9:16, 16:9, 1:1; default from spec or input dimensions)")
    z.add_argument("--t", type=float, default=1.0, help="time of the frame to inspect")
    z.add_argument("--out")
    v = sub.add_parser("vision")
    v.add_argument("--images", nargs="+", required=True)
    v.add_argument("--reference", nargs="*", help="real reference photos, captures or style anchors")
    v.add_argument("--mode", default="auto", choices=["auto", "general", "product", "people", "app"],
                   help="QA rubric mode (auto detects from reference folder: people/captures/product/general)")
    v.add_argument("--model")
    v.add_argument("--context", help="what the shot should show")
    v.add_argument("--out")
    a = ap.parse_args()
    {"check": cmd_check, "frames": cmd_frames, "sheet": cmd_sheet, "safezone": cmd_safezone, "vision": cmd_vision}[a.cmd](a)


if __name__ == "__main__":
    main()
