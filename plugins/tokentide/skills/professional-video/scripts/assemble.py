#!/usr/bin/env python3
"""Assemble the finished video from a spec (FFmpeg).

clips / still captures -> fit (cover/contain/blur) + trim/speed/focal Ken Burns zoom & pan
      -> cuts or transitions -> optional end card / seamless loop
      -> logo/image overlays + burned captions & title/hook text (ASS) -> one high-quality encode
      -> audio mix (VO + ducked music + SFX + optional native clip audio)
      -> loudness normalization (linear loudnorm, else fixed gain + true-peak alimiter) -> mux

Outputs in <project>/renders/:
  <vid>_master.mp4    canvas (9:16 1080x1920 default; 16:9 1920x1080; 1:1 1080x1080) 30fps H.264 High + AAC 48k
  <vid>_nomusic.mp4   same minus music, for adding a licensed/commercial-library sound in-app (only if music set)
  <vid>_cover.jpg     clean frame + optional cover title; <vid>_cover_grid.jpg = centred 3:4 crop (9:16 only)
  <vid>_render.json   timeline, canvas, durations, loudness report & normalization path
--draft writes only <vid>_draft.mp4 quickly (veryfast encode) for review.
Edit grammar is documented in references/post-production.md.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

import captions
import common
from common import FPS, H, W

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
XFADES = {"fade", "fadeblack", "fadewhite", "fadegrays", "fadefast", "fadeslow", "dissolve", "wipeleft", "wiperight",
          "wipeup", "wipedown", "slideleft", "slideright", "slideup", "slidedown", "smoothleft", "smoothright",
          "smoothup", "smoothdown", "circlecrop", "rectcrop", "circleopen", "circleclose", "vertopen", "vertclose",
          "horzopen", "horzclose", "radial", "pixelize", "zoomin", "hblur", "squeezeh", "squeezev", "distance",
          "diagtl", "diagtr", "diagbl", "diagbr", "hlslice", "hrslice", "vuslice", "vdslice", "wipetl", "wipetr",
          "wipebl", "wipebr"}
OVERLAY_POS = common.CANVASES["9:16"]["overlay_pos"]


def is_image(path: Path) -> bool:
    return Path(path).suffix.lower() in IMAGE_EXTS


def parse_transition(tr) -> dict:
    if not tr:
        return {"type": "cut"}
    if isinstance(tr, str):
        return {"type": tr, "duration": 0.25}
    if isinstance(tr, dict):
        return tr
    return {"type": "cut"}


def resolve_source(spec, shot) -> tuple[Path, bool]:
    """Resolve a shot's visual source -> (path, is_still_image)."""
    v = shot.get("video") or {}
    kf = shot.get("keyframe") or {}
    src = shot.get("clip") or shot.get("image") or v.get("selected") or (v.get("candidates") or [None])[0]
    used_unselected_video = bool(not shot.get("clip") and not shot.get("image") and not v.get("selected") and src)
    if not src and not v:
        src = kf.get("selected") or (kf.get("candidates") or [None])[0] or (kf.get("inputs") or [None])[0]
    if not src:
        common.die(f"{shot['id']}: no clip or image. Generate (video.py run) and select (video.py select), "
                   f"or set shots[].clip / shots[].image / keyframe.inputs.")
    p = Path(spec.p(src))
    if not p.exists():
        common.die(f"{shot['id']}: media not found: {p}")
    if used_unselected_video:
        common.log(f"note: {shot['id']} has no selected take; using first candidate {src}")
    return p, is_image(p)


def resolve_clip(spec, shot) -> Path:
    return resolve_source(spec, shot)[0]


def parse_zoom(z):
    """Parse edit.zoom -> (kind, amount, fx, fy) or None."""
    if not z:
        return None
    if isinstance(z, str):
        kind = z.strip().lower()
        amt = 0.12 if kind == "punch" else 0.10 if kind.startswith("pan-") else 0.08
        fx, fy = 0.5, 0.5
    elif isinstance(z, dict):
        kind = str(z.get("type", "punch")).strip().lower()
        default_amt = 0.12 if kind == "punch" else 0.10 if kind.startswith("pan-") else 0.08
        amt = float(z.get("amount") if z.get("amount") is not None else default_amt)
        fx = float(z.get("x") if z.get("x") is not None else 0.5)
        fy = float(z.get("y") if z.get("y") is not None else 0.5)
    else:
        common.die(f"invalid zoom spec: {z!r}")
    valid = {"punch", "push", "pull", "pan-left", "pan-right", "pan-up", "pan-down"}
    if kind not in valid:
        common.die(f"unknown zoom type '{kind}' ({'|'.join(sorted(valid))})")
    amt = max(0.0, min(1.5, amt))
    fx = max(0.0, min(1.0, fx))
    fy = max(0.0, min(1.0, fy))
    return kind, amt, fx, fy


def _fit_color(bg: str) -> str:
    return (bg or "#0B0E14").strip()


def _fit_simple_vf(fit: str, bg: str, w: int, h: int) -> str:
    if fit == "contain":
        return f"scale={w}:{h}:force_original_aspect_ratio=decrease:flags=lanczos,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color={_fit_color(bg)}"
    return f"scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,crop={w}:{h}"


def _render_fitted_frame(src: Path, dst: Path, fit: str, bg: str, w: int, h: int) -> None:
    """Render one fitted still image to exact w x h (cover, contain, or blurred backdrop)."""
    if fit == "blur" and common.has_filter("boxblur"):
        bright = ",eq=brightness=-0.12" if common.has_filter("eq") else ""
        fc = (f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,crop={w}:{h},"
              f"boxblur=24:2{bright}[bg];"
              f"[0:v]scale={w}:{h}:force_original_aspect_ratio=decrease:flags=lanczos[fg];"
              f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1,format=rgb24[out]")
        common.ffmpeg(["-y", "-i", src, "-filter_complex", fc, "-map", "[out]", "-frames:v", "1", dst])
    else:
        vf = _fit_simple_vf("contain" if fit == "blur" else fit, bg, w, h) + ",setsar=1,format=rgb24"
        common.ffmpeg(["-y", "-i", src, "-vf", vf, "-frames:v", "1", dst])


def zoom_filters(z, dur, w=W, h=H):
    """Frame-evaluated zoom/pan filters for video clips (supports focal x/y and pans)."""
    parsed = parse_zoom(z)
    if not parsed:
        return []
    kind, amt, fx, fy = parsed
    if amt <= 1e-4:
        return []
    dur = max(0.1, float(dur))
    if kind == "punch":
        scale_f = 1.0 + amt
        cx = f"max(0,min(iw-{w},iw*{fx:.4f}-{w}/2))"
        cy = f"max(0,min(ih-{h},ih*{fy:.4f}-{h}/2))"
        return [f"scale=trunc(iw*{scale_f:.4f}/2)*2:trunc(ih*{scale_f:.4f}/2)*2:flags=lanczos,crop={w}:{h}:{cx}:{cy}"]
    if kind in ("push", "pull"):
        f = f"(1+{amt:.4f}*t/{dur:.3f})" if kind == "push" else f"(1+{amt:.4f}-{amt:.4f}*t/{dur:.3f})"
        cx = f"max(0,min(iw-{w},iw*{fx:.4f}-{w}/2))"
        cy = f"max(0,min(ih-{h},ih*{fy:.4f}-{h}/2))"
        return [f"scale=w='trunc({w}*{f}/2)*2':h='trunc({h}*{f}/2)*2':eval=frame:flags=bicubic,crop={w}:{h}:'{cx}':'{cy}'"]
    # Directional pan on video clips: scale up by (1 + amt), then slide crop window across time
    scale_f = 1.0 + amt
    sw = f"trunc({w}*{scale_f:.4f}/2)*2"
    sh = f"trunc({h}*{scale_f:.4f}/2)*2"
    cx_fix = f"max(0,min(iw-{w},iw*{fx:.4f}-{w}/2))"
    cy_fix = f"max(0,min(ih-{h},ih*{fy:.4f}-{h}/2))"
    p = f"min(1,max(0,t/{dur:.3f}))"
    if kind == "pan-right":
        cx, cy = f"(iw-{w})*{p}", cy_fix
    elif kind == "pan-left":
        cx, cy = f"(iw-{w})*(1-{p})", cy_fix
    elif kind == "pan-down":
        cx, cy = cx_fix, f"(ih-{h})*{p}"
    else:  # pan-up
        cx, cy = cx_fix, f"(ih-{h})*(1-{p})"
    return [f"scale={sw}:{sh}:flags=lanczos,crop={w}:{h}:'{cx}':'{cy}'"]


def _fade_filters(e: dict, dur: float) -> list[str]:
    vf = []
    fi = float(e.get("fade_in") or 0)
    fo = float(e.get("fade_out") or 0)
    if fi > 0:
        vf.append(f"fade=t=in:st=0:d={min(fi, dur / 2):.3f}")
    if fo > 0:
        d = min(fo, dur / 2)
        vf.append(f"fade=t=out:st={max(0.0, dur - d):.3f}:d={d:.3f}")
    return vf


def atempo_chain(speed: float):
    out, s = [], speed
    while s > 2.0:
        out.append("atempo=2.0")
        s /= 2.0
    while s < 0.5:
        out.append("atempo=0.5")
        s /= 0.5
    if abs(s - 1.0) > 1e-3:
        out.append(f"atempo={s:.4f}")
    return out


def normalize_still(src: Path, dst: Path, e: dict, w=W, h=H, fps=FPS):
    """Animate a still image (UI screenshot, real photo, slide, graphic) with smooth focal Ken Burns & fit modes."""
    dur = e.get("duration")
    if dur in (None, ""):
        t_in = float(e.get("in") or 0.0)
        t_out = e.get("out")
        dur = (float(t_out) - t_in) if t_out not in (None, "") else 4.0
    dur = max(0.2, float(dur))
    fit = str(e.get("fit") or "cover").strip().lower()
    if fit not in ("cover", "contain", "blur"):
        common.die(f"unknown fit mode '{fit}' (cover|contain|blur)")
    bg = _fit_color(e.get("bg") or "#0B0E14")
    parsed = parse_zoom(e.get("zoom"))
    extra = []
    if e.get("hflip"):
        extra.append("hflip")
    extra += _fade_filters(e, dur)

    if not parsed or parsed[1] <= 1e-4:
        base = dst.with_name(dst.stem + "_fit.png")
        _render_fitted_frame(src, base, fit, bg, w, h)
        vf = [*extra, f"setsar=1,fps={fps},format=yuv420p"]
        common.ffmpeg(["-y", "-loop", "1", "-t", f"{dur:.3f}", "-i", base, "-vf", ",".join(vf), "-an",
                       "-c:v", "libx264", "-preset", "veryfast", "-crf", "15", "-r", fps, dst])
        return common.probe(dst)["duration"], None

    kind, amt, fx, fy = parsed
    if kind == "punch":
        base = dst.with_name(dst.stem + "_fit.png")
        _render_fitted_frame(src, base, fit, bg, w, h)
        vf = zoom_filters(e.get("zoom"), dur, w=w, h=h) + extra + [f"setsar=1,fps={fps},format=yuv420p"]
        common.ffmpeg(["-y", "-loop", "1", "-t", f"{dur:.3f}", "-i", base, "-vf", ",".join(vf), "-an",
                       "-c:v", "libx264", "-preset", "veryfast", "-crf", "15", "-r", fps, dst])
        return common.probe(dst)["duration"], None

    # Supersample to 2x canvas first so zoompan produces silky sub-pixel Ken Burns motion with zero jitter.
    sw, sh = w * 2, h * 2
    base = dst.with_name(dst.stem + "_2x.png")
    _render_fitted_frame(src, base, fit, bg, sw, sh)
    n_frames = max(2, int(round(dur * fps)))
    denom = n_frames - 1
    cx_focal = f"max(0,min(iw-iw/zoom,iw*{fx:.4f}-iw/zoom/2))"
    cy_focal = f"max(0,min(ih-ih/zoom,ih*{fy:.4f}-ih/zoom/2))"
    if kind == "push":
        z_expr = f"min(1+{amt:.4f}*on/{denom},{1 + amt:.4f})"
        x_expr, y_expr = cx_focal, cy_focal
    elif kind == "pull":
        z_expr = f"max(1,{1 + amt:.4f}-{amt:.4f}*on/{denom})"
        x_expr, y_expr = cx_focal, cy_focal
    else:
        z_expr = f"{1 + amt:.4f}"
        if kind == "pan-right":
            x_expr, y_expr = f"(iw-iw/zoom)*on/{denom}", cy_focal
        elif kind == "pan-left":
            x_expr, y_expr = f"(iw-iw/zoom)*(1-on/{denom})", cy_focal
        elif kind == "pan-down":
            x_expr, y_expr = cx_focal, f"(ih-ih/zoom)*on/{denom}"
        else:  # pan-up
            x_expr, y_expr = cx_focal, f"(ih-ih/zoom)*(1-on/{denom})"

    zp = f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':d={n_frames}:s={w}x{h}:fps={fps}"
    vf = [zp, *extra, "setsar=1", "format=yuv420p"]
    common.ffmpeg(["-y", "-i", base, "-vf", ",".join(vf), "-an",
                   "-c:v", "libx264", "-preset", "veryfast", "-crf", "15", "-r", fps, dst])
    return common.probe(dst)["duration"], None


def normalize(src: Path, dst: Path, e: dict, keep_audio: bool, w=W, h=H, fps=FPS):
    if is_image(src):
        return normalize_still(src, dst, e, w=w, h=h, fps=fps)
    info = common.probe(src)
    t_in = float(e.get("in") or 0)
    t_out = e.get("out")
    if t_out in (None, "") and e.get("duration") not in (None, ""):
        t_out = t_in + float(e["duration"])
    t_out = min(float(t_out), info["duration"]) if t_out not in (None, "") else info["duration"]
    seg = max(0.2, t_out - t_in)
    speed = float(e.get("speed") or 1.0)
    out_dur = seg / speed
    fit = str(e.get("fit") or "cover").strip().lower()
    if fit not in ("cover", "contain", "blur"):
        common.die(f"unknown fit mode '{fit}' (cover|contain|blur)")
    bg = _fit_color(e.get("bg") or "#0B0E14")
    post_vf = zoom_filters(e.get("zoom"), out_dur, w=w, h=h)
    if e.get("hflip"):
        post_vf.append("hflip")
    post_vf += _fade_filters(e, out_dur)
    post_vf.append(f"setsar=1,fps={fps},format=yuv420p")

    if fit == "blur" and common.has_filter("boxblur"):
        pts = f"setpts=PTS/{speed}," if abs(speed - 1) > 1e-3 else ""
        bright = ",eq=brightness=-0.12" if common.has_filter("eq") else ""
        fc = (f"[0:v]{pts}split=2[b0][f0];"
              f"[b0]scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,crop={w}:{h},boxblur=24:2{bright}[bg];"
              f"[f0]scale={w}:{h}:force_original_aspect_ratio=decrease:flags=lanczos[fg];"
              f"[bg][fg]overlay=(W-w)/2:(H-h)/2,{','.join(post_vf)}[vout]")
        common.ffmpeg(["-y", "-ss", f"{t_in:.3f}", "-t", f"{seg:.3f}", "-i", src, "-filter_complex", fc,
                       "-map", "[vout]", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "15", "-r", fps, dst])
    else:
        vf = []
        if abs(speed - 1) > 1e-3:
            vf.append(f"setpts=PTS/{speed}")
        vf.append(_fit_simple_vf("contain" if fit == "blur" else fit, bg, w, h))
        vf += post_vf
        common.ffmpeg(["-y", "-ss", f"{t_in:.3f}", "-t", f"{seg:.3f}", "-i", src, "-vf", ",".join(vf), "-an",
                       "-c:v", "libx264", "-preset", "veryfast", "-crf", "15", "-r", fps, dst])
    audio = None
    if keep_audio and info["has_audio"]:
        if speed < 1.0 - 1e-3 and not e.get("keep_slow_audio"):
            common.log(f"note: {dst.stem} has speed={speed:g} (<1) — muting native clip audio by default "
                       "(time-stretching speech with atempo introduces stutters; set edit.keep_slow_audio=true "
                       "only for non-speech ambience)")
        else:
            if speed < 1.0 - 1e-3:
                common.log(f"WARNING: {dst.stem} keeps native audio at speed={speed:g} via atempo — "
                           "if the clip contains speech, time-stretching causes stutters; mute it instead")
            audio = dst.with_suffix(".wav")
            af = atempo_chain(speed) + ["aresample=48000"]
            common.ffmpeg(["-y", "-ss", f"{t_in:.3f}", "-t", f"{seg:.3f}", "-i", src, "-vn", "-af", ",".join(af),
                           "-ac", "2", audio])
    return common.probe(dst)["duration"], audio


def still_clip(img: Path, dst: Path, dur: float, fit="cover", bg="black", w=W, h=H, fps=FPS):
    d, _ = normalize_still(img, dst, {"duration": dur, "fit": fit, "bg": bg}, w=w, h=h, fps=fps)
    return d


def join(segs, out: Path, fps=FPS):
    n = len(segs)
    if n == 1:
        shutil.copy(segs[0]["file"], out)
        return [0.0], segs[0]["dur"]
    if all(parse_transition(s.get("trans")).get("type", "cut") == "cut" for s in segs[1:]):
        lst = out.with_suffix(".txt")
        lst.write_text("".join(f"file '{Path(s['file']).resolve()}'\n" for s in segs), encoding="utf-8")
        common.ffmpeg(["-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out])
        starts, t = [], 0.0
        for s in segs:
            starts.append(t)
            t += s["dur"]
        return starts, common.probe(out)["duration"]
    args, parts = ["-y"], []
    for k, s in enumerate(segs):
        args += ["-i", s["file"]]
        parts.append(f"[{k}:v]setpts=PTS-STARTPTS,fps={fps},format=yuv420p,settb=AVTB[i{k}]")  # same timebase everywhere
    cur, length, starts = "[i0]", segs[0]["dur"], [0.0]
    for k in range(1, n):
        tr = parse_transition(segs[k].get("trans"))
        kind, td = tr.get("type", "cut"), float(tr.get("duration", 0.25))
        if kind != "cut" and kind not in XFADES:
            common.log(f"note: transition '{kind}' unknown -> using fade")
            kind = "fade"
        lab = f"[j{k}]"
        if kind == "cut" or td <= 0:
            parts.append(f"{cur}[i{k}]concat=n=2:v=1:a=0,settb=AVTB{lab}")
            starts.append(length)
            length += segs[k]["dur"]
        else:
            td = max(0.04, min(td, segs[k]["dur"] - 0.05, length - 0.05))
            off = length - td
            parts.append(f"{cur}[i{k}]xfade=transition={kind}:duration={td:.3f}:offset={off:.3f},settb=AVTB{lab}")
            starts.append(off)
            length = length + segs[k]["dur"] - td
        cur = lab
    common.ffmpeg(args + ["-filter_complex", ";".join(parts), "-map", cur, "-c:v", "libx264", "-preset", "veryfast",
                          "-crf", "15", "-pix_fmt", "yuv420p", "-r", fps, out])
    return starts, common.probe(out)["duration"]


def prepare_fonts(tmp: Path, root=None) -> str:
    """Copies the fonts libass may use into the render folder: the project's brand fonts (P/assets/fonts/,
    then font files in P/assets/brand/) and the bundled ones."""
    fd = tmp / "fonts"
    if not fd.exists():
        fd.mkdir()
        for f in common.font_files(root):
            shutil.copy(f, fd / f.name)
    return "fonts"


def render_video(spec, joined: Path, ass: Path | None, out: Path, tmp: Path, dur: float, hold: float, draft: bool,
                 canvas=None):
    cv = canvas or common.canvas_for(spec=spec)
    fps = cv["fps"]
    ov_pos = cv["overlay_pos"]
    args, chains, cur, idx = ["-y", "-i", joined], [], "[0:v]", 1
    total = dur + hold
    if hold > 0:
        chains.append(f"{cur}tpad=stop_mode=clone:stop_duration={hold:.3f}[held]")
        cur = "[held]"
    for ov in spec.data.get("overlays") or []:
        if ov.get("type") not in ("image", "logo"):
            continue
        f = spec.p(ov.get("file"))
        if not f or not Path(f).exists():
            common.log(f"note: overlay image missing, skipped: {ov.get('file')}")
            continue
        width, op = int(ov.get("width", 180)), float(ov.get("opacity", 1.0))
        s, e = float(ov.get("start", 0)), float(ov.get("end", total))
        x, y = ((str(ov["x"]), str(ov["y"])) if "x" in ov and "y" in ov else
                ov_pos.get(ov.get("position", "top-right"), ov_pos["top-right"]))
        args += ["-loop", "1", "-t", f"{total:.3f}", "-i", Path(f).resolve()]
        chains.append(f"[{idx}:v]scale={width}:-1,format=rgba,colorchannelmixer=aa={op:.3f}[o{idx}]")
        chains.append(f"{cur}[o{idx}]overlay=x={x}:y={y}:enable='between(t,{s:.3f},{e:.3f})'[b{idx}]")
        cur, idx = f"[b{idx}]", idx + 1
    if ass and Path(ass).exists():
        shutil.copy(ass, tmp / "captions.ass")
        chains.append(f"{cur}ass=captions.ass:fontsdir={prepare_fonts(tmp, spec.root)}[sub]")
        cur = "[sub]"
    chains.append(f"{cur}format=yuv420p[vout]")
    preset, crf = ("veryfast", "23") if draft else ("slow", "18")
    common.ffmpeg(args + ["-filter_complex", ";".join(chains), "-map", "[vout]", "-an", "-c:v", "libx264",
                          "-preset", preset, "-crf", crf, "-maxrate", "12M", "-bufsize", "24M", "-profile:v", "high",
                          "-pix_fmt", "yuv420p", "-r", fps, "-g", str(fps * 2), "-movflags", "+faststart", out.resolve()],
                  cwd=tmp)


def build_mix(spec, dur, shot_starts, clip_audio, out: Path, with_music=True):
    S = spec.data
    args, chains, labels, idx = ["-y"], [], [], 0
    fmt = "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"

    def add(path, loop=False):
        nonlocal idx
        if loop:
            args.extend(["-stream_loop", "-1"])
        args.extend(["-i", str(path)])
        idx += 1
        return idx - 1

    vo = S.get("voiceover") or {}
    vo_file = spec.p(vo.get("file")) if vo.get("enabled", True) and vo.get("file") else None
    has_vo = bool(vo_file and Path(vo_file).exists())
    if has_vo:
        i = add(vo_file)
        d = int(float(vo.get("offset", 0.0)) * 1000)
        chains.append(f"[{i}:a]{fmt},volume={float(vo.get('volume', 1.0)):.3f},adelay={d}|{d}[vo]")
    music = S.get("music") or {}
    mfile = spec.p(music.get("file")) if with_music and music.get("file") else None
    if mfile and Path(mfile).exists():
        i = add(mfile, loop=True)
        fade = min(float(music.get("fade_out", 1.2)), dur / 3)
        chains.append(f"[{i}:a]{fmt},atrim=start={float(music.get('start', 0)):.3f}:duration={dur:.3f},asetpts=PTS-STARTPTS,"
                      f"volume={float(music.get('volume', 0.25)):.3f},afade=t=in:d=0.15,"
                      f"afade=t=out:st={max(0, dur - fade):.3f}:d={fade:.3f}[mus]")
        if has_vo and music.get("duck", True):
            chains.append("[vo]asplit=2[vomix][vosc]")
            chains.append("[mus][vosc]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=300[musd]")
            labels += ["[vomix]", "[musd]"]
            has_vo = False  # already added
        else:
            labels.append("[mus]")
    if has_vo:
        labels.append("[vo]")
    for k, fx in enumerate(S.get("sfx") or []):
        f = spec.p(fx.get("file"))
        if not f or not Path(f).exists():
            common.log(f"note: sfx missing, skipped: {fx.get('file')}")
            continue
        at = fx.get("at", 0)
        at = shot_starts.get(at, 0.0) + float(fx.get("offset", 0)) if isinstance(at, str) else float(at)
        i = add(f)
        d = int(at * 1000)
        chains.append(f"[{i}:a]{fmt},volume={float(fx.get('volume', 0.8)):.3f},adelay={d}|{d}[fx{k}]")
        labels.append(f"[fx{k}]")
    for k, (start, wav, vol) in enumerate(clip_audio):
        i = add(wav)
        d = int(start * 1000)
        chains.append(f"[{i}:a]{fmt},volume={vol:.3f},adelay={d}|{d}[ca{k}]")
        labels.append(f"[ca{k}]")
    if not labels:
        common.ffmpeg(["-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", f"{dur:.3f}", out])
        return False
    mix = (f"{labels[0]}anull" if len(labels) == 1 else
           f"{''.join(labels)}amix=inputs={len(labels)}:duration=longest:dropout_transition=0:normalize=0")
    chains.append(f"{mix},apad,atrim=0:{dur:.3f}[mix]")
    common.ffmpeg(args + ["-filter_complex", ";".join(chains), "-map", "[mix]", "-ar", "48000", "-ac", "2", out])
    return True


def _parse_loudnorm_json(stderr: str):
    blocks = re.findall(r"\{[^{}]*\"input_i\"[^{}]*\}", stderr, re.S)
    return json.loads(blocks[-1]) if blocks else None


def loudness(path, target=None):
    I = target["lufs"] if target else -14
    TP = target["true_peak"] if target else -1.5
    LRA = target["lra"] if target else 11
    err = common.ffmpeg(["-i", path, "-af", f"loudnorm=I={I}:TP={TP}:LRA={LRA}:print_format=json", "-f", "null", "-"],
                        loglevel="info").stderr
    return _parse_loudnorm_json(err)


def normalize_audio(wav: Path, out: Path, target: dict, *, video: Path | None = None, label: str = "mix") -> dict:
    """Two-pass loudness normalization that never silently falls back to dynamic breathing.

    Runs loudnorm pass 1, then pass 2 with `linear=true:print_format=json` and inspects
    `normalization_type`. If loudnorm fell back to 'dynamic' (common on peaky TTS tracks), re-renders
    with constant `volume=<gain>dB` plus an oversampled true-peak `alimiter` so speech never breathes.
    Works for both muxed video (`video != None`) and voice-only audio (`video=None`).
    """
    I, TP, LRA = float(target["lufs"]), float(target["true_peak"]), float(target["lra"])
    meas = loudness(wav, target)

    def _encode(af: str):
        if video is not None:
            return common.ffmpeg(["-y", "-i", video, "-i", wav, "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                                  "-af", af, "-ar", "48000", "-ac", "2", "-c:a", "aac", "-b:a", "192k",
                                  "-movflags", "+faststart", "-shortest", out], loglevel="info")
        if str(out).lower().endswith(".wav"):
            return common.ffmpeg(["-y", "-i", wav, "-vn", "-af", af, "-ar", "48000", "-ac", "2",
                                  "-c:a", "pcm_s16le", out], loglevel="info")
        return common.ffmpeg(["-y", "-i", wav, "-vn", "-af", af, "-ar", "48000", "-ac", "2",
                              "-c:a", "aac", "-b:a", "192k", out], loglevel="info")

    if not meas or common._f(meas.get("input_i"), -99) <= -70:
        _encode("anull")
        common.log(f"loudness ({label}): silent track (skipped normalization)")
        return {"path": "silent", "normalization_type": "silent", "measured": meas}

    af_ln = (f"loudnorm=I={I}:TP={TP}:LRA={LRA}:measured_I={meas['input_i']}:measured_TP={meas['input_tp']}:"
             f"measured_LRA={meas['input_lra']}:measured_thresh={meas['input_thresh']}:"
             f"offset={meas['target_offset']}:linear=true:print_format=json")
    pass2 = _parse_loudnorm_json(_encode(af_ln).stderr)
    ntype = str((pass2 or {}).get("normalization_type") or "").lower()
    if ntype == "linear":
        common.log(f"loudness ({label}): linear loudnorm -> {pass2.get('output_i')} LUFS / {pass2.get('output_tp')} dBTP")
        return {"path": "loudnorm_linear", "normalization_type": "linear", "measured": meas, "pass2": pass2}

    # loudnorm fell back to dynamic mode: use constant gain + oversampled true-peak limiter instead.
    gain_db = round(I - common._f(meas.get("input_i"), I), 2)
    limit_lin = min(1.0, max(0.0625, 10.0 ** ((TP - 0.1) / 20.0)))
    if common.has_filter("alimiter"):
        af_fix = (f"volume={gain_db:+.2f}dB,aresample=192000,"
                  f"alimiter=limit={limit_lin:.6f}:level=false:attack=5:release=50,aresample=48000")
        path_name = "gain+alimiter"
    else:
        af_fix = f"volume={gain_db:+.2f}dB"
        path_name = "gain_only"
    _encode(af_fix)
    common.log(f"loudness ({label}): loudnorm fell back to '{ntype or 'dynamic'}' -> using constant gain "
               f"({gain_db:+.2f} dB) + true-peak {path_name} (target {I:g} LUFS / <= {TP:g} dBTP)")
    return {"path": path_name, "normalization_type": "dynamic_avoided", "gain_db": gain_db,
            "limit_linear": round(limit_lin, 6), "measured": meas, "pass2_rejected": pass2}


def mux(video: Path, wav: Path, out: Path, target: dict, label: str = "mix"):
    return normalize_audio(wav, out, target, video=video, label=label)


def make_cover(spec, src_video: Path, out_dir: Path, tmp: Path, canvas=None):
    cv = canvas or common.canvas_for(spec=spec)
    S = spec.data
    cov = S.get("cover") or {}
    t = float(cov.get("time", 0.5))
    text = cov.get("text")
    frame = tmp / "cover_frame.png"
    common.ffmpeg(["-y", "-ss", f"{t:.3f}", "-i", src_video, "-frames:v", "1", frame])
    out = out_dir / f"{spec.vid}_cover.jpg"
    if text:
        cfg = {**captions.DEFAULTS, "size": cv["caption_size"], "hook_size": cv["hook_size"],
               **(S.get("captions") or {})}
        body = text.replace("\n", "\\N")
        (tmp / "cover.ass").write_text(captions.header(cfg, cv) + captions.dialogue(0, 10, "Title", body, layer=1) + "\n",
                                       encoding="utf-8")
        common.ffmpeg(["-y", "-i", "cover_frame.png", "-vf", f"ass=cover.ass:fontsdir={prepare_fonts(tmp, spec.root)}",
                       "-frames:v", "1", "-q:v", "2", out.resolve()], cwd=tmp)
    else:
        common.ffmpeg(["-y", "-i", frame, "-frames:v", "1", "-q:v", "2", out])
    grid = None
    if cv.get("cover_grid_crop"):
        grid = out_dir / f"{spec.vid}_cover_grid.jpg"
        common.ffmpeg(["-y", "-i", out, "-vf", f"crop={cv['cover_grid_crop']}", "-frames:v", "1", "-q:v", "3", grid])
    return out, grid


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--canvas", help="aspect ratio or WxH (9:16 default, 16:9, 1:1; overrides spec/project)")
    ap.add_argument("--draft", action="store_true", help="fast preview encode only (<vid>_draft.mp4)")
    ap.add_argument("--no-captions", action="store_true")
    ap.add_argument("--keep-temp", action="store_true")
    a = ap.parse_args()

    spec = common.Spec(a.spec)
    S = spec.data
    cv = common.canvas_for(spec=spec, aspect=a.canvas)
    w, h, fps = cv["w"], cv["h"], cv["fps"]
    out_dir = spec.root / "renders"
    tmp = out_dir / f".tmp_{spec.vid}"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    mixcfg = {"keep_clip_audio": False, "clip_audio_volume": 0.5, "lufs": -14, "true_peak": -1.5, "lra": 11,
              **(S.get("audio_mix") or {})}

    segs, shot_ids = [], []
    for shot in spec.shots():
        e = shot.get("edit") or {}
        src_path, _ = resolve_source(spec, shot)
        dur, wav = normalize(src_path, tmp / f"{shot['id']}.mp4", e, bool(mixcfg["keep_clip_audio"]),
                             w=w, h=h, fps=fps)
        vol = e.get("clip_audio_volume", mixcfg["clip_audio_volume"])
        segs.append({"id": shot["id"], "file": tmp / f"{shot['id']}.mp4", "dur": dur,
                     "trans": parse_transition(e.get("transition")), "audio": wav, "vol": float(vol)})
        shot_ids.append(shot["id"])
    if not segs:
        common.die("spec has no shots")
    end = S.get("end_card")
    if end and end.get("file"):
        f = Path(spec.p(end["file"]))
        dst = tmp / "end_card.mp4"
        if is_image(f):
            d = still_clip(f, dst, float(end.get("duration", 1.5)), end.get("fit", "cover"),
                           end.get("bg", "black"), w=w, h=h, fps=fps)
        else:
            d, _ = normalize(f, dst, {"out": end.get("duration"), "fit": end.get("fit", "cover")}, False, w=w, h=h, fps=fps)
        segs.append({"id": "end_card", "file": dst, "dur": d,
                     "trans": parse_transition(end.get("transition") or {"type": "fade", "duration": 0.25}),
                     "audio": None, "vol": 0})
    if S.get("loop") and not (end and end.get("file")):
        ld = float(S.get("loop_fade", 0.3))
        first = tmp / "loop_first.png"
        common.ffmpeg(["-y", "-i", segs[0]["file"], "-frames:v", "1", first])
        d = still_clip(first, tmp / "loop_tail.mp4", ld + 0.05, w=w, h=h, fps=fps)
        segs.append({"id": "loop", "file": tmp / "loop_tail.mp4", "dur": d,
                     "trans": {"type": "fade", "duration": ld}, "audio": None, "vol": 0})
    elif S.get("loop"):
        common.log("note: loop ignored because an end card is set")

    joined = tmp / "joined.mp4"
    starts, dur = join(segs, joined, fps=fps)
    shot_starts = {s["id"]: st for s, st in zip(segs, starts)}

    vo = S.get("voiceover") or {}
    hold = 0.0
    vo_file = spec.p(vo.get("file")) if vo.get("enabled", True) and vo.get("file") else None
    if vo_file and Path(vo_file).exists():
        vo_end = float(vo.get("offset", 0.0)) + common.probe(vo_file)["duration"]
        if vo_end + 0.3 > dur:
            hold = round(vo_end + 0.3 - dur, 3)
            common.log(f"WARNING: voice-over ends at {vo_end:.2f}s but the edit is {dur:.2f}s -> holding the last frame "
                       f"{hold:.2f}s. Better: lengthen shots (edit.duration/out/speed), add an end card, or tighten the script.")
    total = dur + hold

    ass = None
    if not a.no_captions:
        ass = spec.p((S.get("captions") or {}).get("file")) or (spec.root / "captions" / f"{spec.vid}.ass")
        if not Path(ass).exists():
            common.log("note: no captions .ass found (run captions.py --spec ...); rendering without captions")
            ass = None
    video_final = tmp / "video_final.mp4"
    render_video(spec, joined, ass, video_final, tmp, dur, hold, a.draft, canvas=cv)

    clip_audio = [(shot_starts[s["id"]], s["audio"], s["vol"]) for s in segs if s.get("audio")]
    target = {k: float(mixcfg[k]) for k in ("lufs", "true_peak", "lra")}
    mix_full = tmp / "mix_full.wav"
    build_mix(spec, total, shot_starts, clip_audio, mix_full, with_music=True)
    out_dir.mkdir(exist_ok=True)
    report = {"id": spec.vid, "canvas": {"aspect": cv["aspect"], "width": w, "height": h, "fps": fps},
              "duration": round(total, 3), "held_last_frame_s": hold,
              "timeline": [{"id": s["id"], "start": round(st, 3), "dur": round(s["dur"], 3)} for s, st in zip(segs, starts)],
              "outputs": {}}
    if a.draft:
        draft = out_dir / f"{spec.vid}_draft.mp4"
        res_d = mux(video_final, mix_full, draft, target, label="draft")
        report["outputs"]["draft"] = spec.rel(draft)
        report["loudness_path_draft"] = res_d["path"]
    else:
        master = out_dir / f"{spec.vid}_master.mp4"
        res_m = mux(video_final, mix_full, master, target, label="master")
        report["outputs"]["master"] = spec.rel(master)
        report["loudness_master"] = loudness(master, target)
        report["loudness_path_master"] = res_m["path"]
        if (S.get("music") or {}).get("file"):
            mix_nm = tmp / "mix_nomusic.wav"
            build_mix(spec, total, shot_starts, clip_audio, mix_nm, with_music=False)
            nomusic = out_dir / f"{spec.vid}_nomusic.mp4"
            res_nm = mux(video_final, mix_nm, nomusic, target, label="nomusic")
            report["outputs"]["nomusic"] = spec.rel(nomusic)
            report["loudness_path_nomusic"] = res_nm["path"]
        cover, grid = make_cover(spec, joined, out_dir, tmp, canvas=cv)
        report["outputs"]["cover"] = spec.rel(cover)
        if grid:
            report["outputs"]["cover_grid"] = spec.rel(grid)
    common.save_json(out_dir / f"{spec.vid}_render.json", report)
    if not a.keep_temp:
        shutil.rmtree(tmp, ignore_errors=True)
    ln = report.get("loudness_master") or {}
    path_s = f" ({report.get('loudness_path_master')})" if report.get("loudness_path_master") else ""
    print(f"Rendered {spec.vid}: {w}x{h} {total:.2f}s, {len(segs)} segments"
          + (f", {ln.get('input_i')} LUFS / {ln.get('input_tp')} dBTP{path_s}" if ln else ""))
    for k, v in report["outputs"].items():
        print(f"  {k}: {v}")
    out_file = spec.root / (report['outputs'].get('master') or report['outputs'].get('draft'))
    print(f"Next: python3 {Path(__file__).resolve().parent}/qa.py check {out_file} --spec {spec.path}")


if __name__ == "__main__":
    main()
