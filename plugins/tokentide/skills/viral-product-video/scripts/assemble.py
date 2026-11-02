#!/usr/bin/env python3
"""Assemble the finished vertical video from a spec (FFmpeg).

clips -> trim/speed/zoom -> cuts or transitions -> optional end card / seamless loop
      -> logo/image overlays + burned captions & hook text (ASS) -> one high-quality encode
      -> audio mix (VO + ducked music + SFX + optional native clip audio) -> two-pass loudnorm -> mux

Outputs in <project>/renders/:
  <vid>_master.mp4    1080x1920 30fps H.264 High + AAC 48k, loudness-normalised (default -14 LUFS, -1.5 dBTP)
  <vid>_nomusic.mp4   same minus music, for adding a licensed/commercial-library sound in-app (only if music set)
  <vid>_cover.jpg     clean frame + cover title; <vid>_cover_grid.jpg = centred 3:4 crop (profile grid preview)
  <vid>_render.json   timeline, durations, loudness report
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

XFADES = {"fade", "fadeblack", "fadewhite", "fadegrays", "fadefast", "fadeslow", "dissolve", "wipeleft", "wiperight",
          "wipeup", "wipedown", "slideleft", "slideright", "slideup", "slidedown", "smoothleft", "smoothright",
          "smoothup", "smoothdown", "circlecrop", "rectcrop", "circleopen", "circleclose", "vertopen", "vertclose",
          "horzopen", "horzclose", "radial", "pixelize", "zoomin", "hblur", "squeezeh", "squeezev", "distance",
          "diagtl", "diagtr", "diagbl", "diagbr", "hlslice", "hrslice", "vuslice", "vdslice", "wipetl", "wipetr",
          "wipebl", "wipebr"}
OVERLAY_POS = {"top-right": ("W-w-150", "260"), "top-left": ("60", "260"), "top-center": ("(W-w)/2", "260"),
               "center": ("(W-w)/2", "(H-h)/2"), "lower-third": ("(W-w)/2", "H-h-700"),
               "bottom-center": ("(W-w)/2", "H-h-680")}


def resolve_clip(spec, shot) -> Path:
    v = shot.get("video") or {}
    src = shot.get("clip") or v.get("selected") or (v.get("candidates") or [None])[0]
    if not src:
        common.die(f"{shot['id']}: no clip. Generate (video.py run) and select (video.py select) first, "
                   f"or set shots[].clip to an existing file.")
    p = spec.p(src)
    if not Path(p).exists():
        common.die(f"{shot['id']}: clip not found: {p}")
    if not v.get("selected") and not shot.get("clip"):
        common.log(f"note: {shot['id']} has no selected take; using first candidate {src}")
    return Path(p)


def zoom_filters(z, dur):
    if not z:
        return []
    kind = z if isinstance(z, str) else z.get("type", "punch")
    amt = float((z.get("amount") if isinstance(z, dict) else None) or (0.12 if kind == "punch" else 0.08))
    if kind == "punch":
        return [f"scale=trunc(iw*{1 + amt:.4f}/2)*2:-2:flags=lanczos,crop={W}:{H}"]
    if kind in ("push", "pull"):
        f = f"(1+{amt}*t/{dur:.3f})" if kind == "push" else f"(1+{amt}-{amt}*t/{dur:.3f})"
        return [f"scale=w='trunc({W}*{f}/2)*2':h='trunc({H}*{f}/2)*2':eval=frame:flags=bicubic,crop={W}:{H}"]
    common.die(f"unknown zoom type '{kind}' (punch|push|pull)")


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


def normalize(src: Path, dst: Path, e: dict, keep_audio: bool):
    info = common.probe(src)
    t_in = float(e.get("in") or 0)
    t_out = e.get("out")
    t_out = min(float(t_out), info["duration"]) if t_out not in (None, "") else info["duration"]
    seg = max(0.2, t_out - t_in)
    speed = float(e.get("speed") or 1.0)
    vf = []
    if abs(speed - 1) > 1e-3:
        vf.append(f"setpts=PTS/{speed}")
    vf.append(f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H},setsar=1")
    vf += zoom_filters(e.get("zoom"), seg / speed)
    if e.get("hflip"):
        vf.append("hflip")
    vf.append(f"fps={FPS},format=yuv420p")
    common.ffmpeg(["-y", "-ss", f"{t_in:.3f}", "-t", f"{seg:.3f}", "-i", src, "-vf", ",".join(vf), "-an",
                   "-c:v", "libx264", "-preset", "veryfast", "-crf", "15", "-r", FPS, dst])
    audio = None
    if keep_audio and info["has_audio"]:
        audio = dst.with_suffix(".wav")
        af = atempo_chain(speed) + ["aresample=48000"]
        common.ffmpeg(["-y", "-ss", f"{t_in:.3f}", "-t", f"{seg:.3f}", "-i", src, "-vn", "-af", ",".join(af),
                       "-ac", "2", audio])
    return common.probe(dst)["duration"], audio


def still_clip(img: Path, dst: Path, dur: float, fit="cover"):
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}" if fit == "cover" else
          f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black")
    common.ffmpeg(["-y", "-loop", "1", "-t", f"{dur:.3f}", "-i", img, "-vf", f"{vf},setsar=1,fps={FPS},format=yuv420p",
                   "-c:v", "libx264", "-preset", "veryfast", "-crf", "15", "-r", FPS, dst])
    return common.probe(dst)["duration"]


def join(segs, out: Path):
    n = len(segs)
    if n == 1:
        shutil.copy(segs[0]["file"], out)
        return [0.0], segs[0]["dur"]
    if all((s.get("trans") or {}).get("type", "cut") == "cut" for s in segs[1:]):
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
        parts.append(f"[{k}:v]setpts=PTS-STARTPTS,fps={FPS},format=yuv420p,settb=AVTB[i{k}]")  # same timebase everywhere
    cur, length, starts = "[i0]", segs[0]["dur"], [0.0]
    for k in range(1, n):
        tr = segs[k].get("trans") or {}
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
                          "-crf", "15", "-pix_fmt", "yuv420p", "-r", FPS, out])
    return starts, common.probe(out)["duration"]


def prepare_fonts(tmp: Path) -> str:
    fd = tmp / "fonts"
    if not fd.exists():
        fd.mkdir()
        for f in common.FONTS_DIR.glob("*.[ot]tf"):
            shutil.copy(f, fd / f.name)
    return "fonts"


def render_video(spec, joined: Path, ass: Path | None, out: Path, tmp: Path, dur: float, hold: float, draft: bool):
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
        x, y = (str(ov["x"]), str(ov["y"])) if "x" in ov and "y" in ov else OVERLAY_POS.get(ov.get("position", "top-right"), OVERLAY_POS["top-right"])
        args += ["-loop", "1", "-t", f"{total:.3f}", "-i", Path(f).resolve()]
        chains.append(f"[{idx}:v]scale={width}:-1,format=rgba,colorchannelmixer=aa={op:.3f}[o{idx}]")
        chains.append(f"{cur}[o{idx}]overlay=x={x}:y={y}:enable='between(t,{s:.3f},{e:.3f})'[b{idx}]")
        cur, idx = f"[b{idx}]", idx + 1
    if ass and Path(ass).exists():
        shutil.copy(ass, tmp / "captions.ass")
        chains.append(f"{cur}ass=captions.ass:fontsdir={prepare_fonts(tmp)}[sub]")
        cur = "[sub]"
    chains.append(f"{cur}format=yuv420p[vout]")
    preset, crf = ("veryfast", "23") if draft else ("slow", "18")
    common.ffmpeg(args + ["-filter_complex", ";".join(chains), "-map", "[vout]", "-an", "-c:v", "libx264",
                          "-preset", preset, "-crf", crf, "-maxrate", "12M", "-bufsize", "24M", "-profile:v", "high",
                          "-pix_fmt", "yuv420p", "-r", FPS, "-g", str(FPS * 2), "-movflags", "+faststart", out.resolve()],
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


def loudness(path):
    err = common.ffmpeg(["-i", path, "-af", "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
                        loglevel="info").stderr
    blocks = re.findall(r"\{[^{}]*\"input_i\"[^{}]*\}", err, re.S)
    return json.loads(blocks[-1]) if blocks else None


def mux(video: Path, wav: Path, out: Path, target: dict):
    I, TP, LRA = target["lufs"], target["true_peak"], target["lra"]
    m = common.ffmpeg(["-i", wav, "-af", f"loudnorm=I={I}:TP={TP}:LRA={LRA}:print_format=json", "-f", "null", "-"],
                      loglevel="info").stderr
    blocks = re.findall(r"\{[^{}]*\"input_i\"[^{}]*\}", m, re.S)
    meas = json.loads(blocks[-1]) if blocks else None
    af = "anull"
    if meas and common._f(meas.get("input_i"), -99) > -70:
        af = (f"loudnorm=I={I}:TP={TP}:LRA={LRA}:measured_I={meas['input_i']}:measured_TP={meas['input_tp']}:"
              f"measured_LRA={meas['input_lra']}:measured_thresh={meas['input_thresh']}:"
              f"offset={meas['target_offset']}:linear=true")
    common.ffmpeg(["-y", "-i", video, "-i", wav, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-af", af,
                   "-ar", "48000", "-ac", "2", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", out])
    return meas


def make_cover(spec, src_video: Path, out_dir: Path, tmp: Path):
    S = spec.data
    cov = S.get("cover") or {}
    t = float(cov.get("time", 0.5))
    text = cov.get("text")
    frame = tmp / "cover_frame.png"
    common.ffmpeg(["-y", "-ss", f"{t:.3f}", "-i", src_video, "-frames:v", "1", frame])
    out = out_dir / f"{spec.vid}_cover.jpg"
    if text:
        cfg = {**captions.DEFAULTS, **(S.get("captions") or {})}
        body = text.replace("\n", "\\N")
        (tmp / "cover.ass").write_text(captions.header(cfg) + captions.dialogue(0, 10, "Title", body, layer=1) + "\n",
                                       encoding="utf-8")
        common.ffmpeg(["-y", "-i", "cover_frame.png", "-vf", f"ass=cover.ass:fontsdir={prepare_fonts(tmp)}",
                       "-frames:v", "1", "-q:v", "2", out.resolve()], cwd=tmp)
    else:
        common.ffmpeg(["-y", "-i", frame, "-frames:v", "1", "-q:v", "2", out])
    grid = out_dir / f"{spec.vid}_cover_grid.jpg"
    common.ffmpeg(["-y", "-i", out, "-vf", "crop=1080:1440", "-frames:v", "1", "-q:v", "3", grid])
    return out, grid


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--draft", action="store_true", help="fast preview encode only (<vid>_draft.mp4)")
    ap.add_argument("--no-captions", action="store_true")
    ap.add_argument("--keep-temp", action="store_true")
    a = ap.parse_args()

    spec = common.Spec(a.spec)
    S = spec.data
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
        dur, wav = normalize(resolve_clip(spec, shot), tmp / f"{shot['id']}.mp4", e, bool(mixcfg["keep_clip_audio"]))
        vol = e.get("clip_audio_volume", mixcfg["clip_audio_volume"])
        segs.append({"id": shot["id"], "file": tmp / f"{shot['id']}.mp4", "dur": dur, "trans": e.get("transition"),
                     "audio": wav, "vol": float(vol)})
        shot_ids.append(shot["id"])
    if not segs:
        common.die("spec has no shots")
    end = S.get("end_card")
    if end and end.get("file"):
        f = spec.p(end["file"])
        dst = tmp / "end_card.mp4"
        if str(f).lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            d = still_clip(Path(f), dst, float(end.get("duration", 1.5)), end.get("fit", "cover"))
        else:
            d, _ = normalize(Path(f), dst, {"out": end.get("duration")}, False)
        segs.append({"id": "end_card", "file": dst, "dur": d,
                     "trans": end.get("transition", {"type": "fade", "duration": 0.25}), "audio": None, "vol": 0})
    if S.get("loop") and not (end and end.get("file")):
        ld = float(S.get("loop_fade", 0.3))
        first = tmp / "loop_first.png"
        common.ffmpeg(["-y", "-i", segs[0]["file"], "-frames:v", "1", first])
        d = still_clip(first, tmp / "loop_tail.mp4", ld + 0.05)
        segs.append({"id": "loop", "file": tmp / "loop_tail.mp4", "dur": d,
                     "trans": {"type": "fade", "duration": ld}, "audio": None, "vol": 0})
    elif S.get("loop"):
        common.log("note: loop ignored because an end card is set")

    joined = tmp / "joined.mp4"
    starts, dur = join(segs, joined)
    shot_starts = {s["id"]: st for s, st in zip(segs, starts)}

    vo = S.get("voiceover") or {}
    hold = 0.0
    vo_file = spec.p(vo.get("file")) if vo.get("enabled", True) and vo.get("file") else None
    if vo_file and Path(vo_file).exists():
        vo_end = float(vo.get("offset", 0.0)) + common.probe(vo_file)["duration"]
        if vo_end + 0.3 > dur:
            hold = round(vo_end + 0.3 - dur, 3)
            common.log(f"WARNING: voice-over ends at {vo_end:.2f}s but the edit is {dur:.2f}s -> holding the last frame "
                       f"{hold:.2f}s. Better: lengthen shots (edit.out/speed), add an end card, or tighten the script.")
    total = dur + hold

    ass = None
    if not a.no_captions:
        ass = spec.p((S.get("captions") or {}).get("file")) or (spec.root / "captions" / f"{spec.vid}.ass")
        if not Path(ass).exists():
            common.log("note: no captions .ass found (run captions.py --spec ...); rendering without captions")
            ass = None
    video_final = tmp / "video_final.mp4"
    render_video(spec, joined, ass, video_final, tmp, dur, hold, a.draft)

    clip_audio = [(shot_starts[s["id"]], s["audio"], s["vol"]) for s in segs if s.get("audio")]
    target = {k: float(mixcfg[k]) for k in ("lufs", "true_peak", "lra")}
    mix_full = tmp / "mix_full.wav"
    build_mix(spec, total, shot_starts, clip_audio, mix_full, with_music=True)
    out_dir.mkdir(exist_ok=True)
    report = {"id": spec.vid, "duration": round(total, 3), "held_last_frame_s": hold,
              "timeline": [{"id": s["id"], "start": round(st, 3), "dur": round(s["dur"], 3)} for s, st in zip(segs, starts)],
              "outputs": {}}
    if a.draft:
        draft = out_dir / f"{spec.vid}_draft.mp4"
        mux(video_final, mix_full, draft, target)
        report["outputs"]["draft"] = spec.rel(draft)
    else:
        master = out_dir / f"{spec.vid}_master.mp4"
        mux(video_final, mix_full, master, target)
        report["outputs"]["master"] = spec.rel(master)
        report["loudness_master"] = loudness(master)
        if (S.get("music") or {}).get("file"):
            mix_nm = tmp / "mix_nomusic.wav"
            build_mix(spec, total, shot_starts, clip_audio, mix_nm, with_music=False)
            nomusic = out_dir / f"{spec.vid}_nomusic.mp4"
            mux(video_final, mix_nm, nomusic, target)
            report["outputs"]["nomusic"] = spec.rel(nomusic)
        cover, grid = make_cover(spec, joined, out_dir, tmp)
        report["outputs"].update(cover=spec.rel(cover), cover_grid=spec.rel(grid))
    common.save_json(out_dir / f"{spec.vid}_render.json", report)
    if not a.keep_temp:
        shutil.rmtree(tmp, ignore_errors=True)
    ln = report.get("loudness_master") or {}
    print(f"Rendered {spec.vid}: {total:.2f}s, {len(segs)} segments"
          + (f", {ln.get('input_i')} LUFS / {ln.get('input_tp')} dBTP" if ln else ""))
    for k, v in report["outputs"].items():
        print(f"  {k}: {v}")
    out_file = spec.root / (report['outputs'].get('master') or report['outputs'].get('draft'))
    print(f"Next: python3 {Path(__file__).resolve().parent}/qa.py check {out_file} --spec {spec.path}")


if __name__ == "__main__":
    main()
