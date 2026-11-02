#!/usr/bin/env python3
"""Voice-over, word timings, and generated music/SFX via Tokentide (with offline fallbacks).

  tts         text -> speech file (≤4,096 chars)         POST /audio/speech
  voices      list TTS models/voices from the catalog    GET  /models?type=tts
  transcribe  speech -> word timings (words.json)        POST /audio/transcriptions (≤4.5 MB; auto-compressed)
  align       offline word timings: known script + silence detection (no API, no extra deps)
  music       original background track (rights-safe)    POST /audio/quote|queue|retrieve|complete
  sfx         original sound effect (whoosh, pop, pour…) same queued flow
  clone       NOT offered by Tokentide (it would keep voice samples upstream)

Spec mode (--spec briefs/vNN.json) reads/writes voiceover.{script,model,voice,speed,file,words}.
words.json format: {"words": [{"w": "Hello", "s": 0.12, "e": 0.41}, ...], "source": "...", "duration": 4.2}
"""
from __future__ import annotations

import argparse
import difflib
import json
import mimetypes
import re
import sys
from pathlib import Path

import common
import apiclient as api

PACE_OK = (2.2, 3.2)  # spoken words/second that read well in short-form


def _text_for(a, spec):
    if a.text:
        return a.text
    if a.text_file:
        return Path(a.text_file).read_text(encoding="utf-8").strip()
    if spec:
        t = (spec.data.get("voiceover") or {}).get("script")
        if t:
            return t.strip()
    common.die("Provide --text, --text-file or a spec with voiceover.script")


def cmd_tts(a):
    spec = common.Spec(a.spec) if a.spec else None
    vo = (spec.data.get("voiceover") or {}) if spec else {}
    text = _text_for(a, spec)
    root = spec.root if spec else common.find_project_root(Path(a.out).resolve().parent if a.out else Path.cwd())
    picks = common.project_meta(root).get("models", {}) if root else {}
    model = common.resolve_model(root, a.model or vo.get("model") or picks.get("tts") or "tts-kokoro")
    voice = a.voice or vo.get("voice") or "af_sky"
    speed = a.speed if a.speed is not None else vo.get("speed", 1.0)
    out = Path(a.out) if a.out else (spec.root / "audio" / f"{spec.vid}_vo.{a.format}" if spec else None)
    if not out:
        common.die("--out is required without --spec")
    api.use_project(root)
    if len(text) > 4096:
        common.die(f"Voice-over script is {len(text)} chars; Tokentide TTS accepts at most 4,096. Split or shorten it.")
    body = {"model": model, "input": text, "voice": voice, "response_format": a.format, "speed": speed}
    for k, v in (vo.get("extra") or {}).items():
        body[k] = v
    resp, used = api.post_adaptive("/audio/speech", body, droppable=("speed", "response_format"))
    if resp.is_json():
        common.die(f"TTS returned JSON instead of audio: {resp.body[:300]!r}")
    ext = api.sniff(resp.body)[0] or a.format
    out = out.with_suffix("." + ext)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(resp.body)
    api.write_sidecar(out, "/audio/speech", used, resp)
    api.log_call("tts", "/audio/speech", model=model, resp=resp, chars=len(text))
    dur = common.probe(out)["duration"]
    n = len(re.findall(r"\w+", text))
    pace = n / dur if dur else 0
    flag = "OK" if PACE_OK[0] <= pace <= PACE_OK[1] else "CHECK (aim 2.2-3.2 w/s; adjust speed or script)"
    print(f"{out}  {dur:.2f}s  {n} words  {pace:.2f} words/s  {flag}")
    if spec:
        spec.reload()
        spec.data.setdefault("voiceover", {}).update(file=spec.rel(out), model=model, voice=voice, speed=speed)
        spec.save()


def cmd_voices(a):
    models = common.load_models(path=a.cache) if a.cache else {
        m["id"]: m for m in (api.get("/models?type=tts").json().get("data", []))}
    for mid, m in sorted(models.items()):
        if a.cache and m.get("type") not in ("tts", None):
            continue
        voices = [v for k, v in common.spec_lookup(m, "voice").items() if isinstance(v, list)]
        vs = voices[0] if voices else []
        if a.lang:
            vs = [v for v in vs if str(v).lower().startswith(a.lang.lower())]
        print(f"{mid}: {len(vs)} voices" + (f" -> {', '.join(map(str, vs[:60]))}" if vs else ""))


# ---------------------------------------------------------------- timings
def _distribute(tokens, start, end):
    if not tokens:
        return []
    weights = [len(t) + (2 if re.search(r"[.!?,;:]$", t) else 1) for t in tokens]
    total = sum(weights)
    out, t = [], start
    for tok, w in zip(tokens, weights):
        d = (end - start) * w / total
        out.append({"w": tok, "s": round(t, 3), "e": round(t + d * 0.92, 3)})
        t += d
    return out


def words_from_transcript(j, duration):
    def grab(items):
        res = []
        for w in items or []:
            if not isinstance(w, dict):
                continue
            t = (w.get("word") or w.get("text") or "").strip()
            s, e = w.get("start"), w.get("end")
            if t and s is not None and e is not None:
                res.append({"w": t, "s": float(s), "e": float(e)})
        return res

    if isinstance(j, str):
        return _distribute(j.split(), 0.0, duration), j
    text = j.get("text", "") if isinstance(j, dict) else ""
    words = grab(j.get("words")) or grab((j.get("timestamps") or {}).get("word") if isinstance(j.get("timestamps"), dict) else None)
    if not words:
        for seg in j.get("segments") or []:
            w = grab(seg.get("words"))
            words += w or _distribute(str(seg.get("text", "")).split(), float(seg.get("start", 0)),
                                      float(seg.get("end", duration)))
    if not words and text:
        words = _distribute(text.split(), 0.0, duration)
    return words, text


def speech_spans(audio, noise="-35dB", min_sil=0.18):
    dur = common.probe(audio)["duration"]
    err = common.ffmpeg(["-i", audio, "-af", f"silencedetect=noise={noise}:d={min_sil}", "-f", "null", "-"],
                        loglevel="info").stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", err)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", err)]
    spans, cur = [], 0.0
    for i, s in enumerate(starts):
        if s - cur > 0.05:
            spans.append((cur, s))
        cur = ends[i] if i < len(ends) else dur
    if dur - cur > 0.05:
        spans.append((cur, dur))
    return spans or [(0.0, dur)], dur


def align_offline(tokens, spans):
    """Spread script tokens across detected speech spans proportionally to their length."""
    total = sum(e - s for s, e in spans)
    flat = _distribute(tokens, 0.0, total)

    def to_abs(x):
        acc = 0.0
        for s, e in spans:
            if x <= acc + (e - s) + 1e-6:
                return s + (x - acc)
            acc += e - s
        return spans[-1][1]

    return [{"w": w["w"], "s": round(to_abs(w["s"]), 3), "e": round(to_abs(w["e"]), 3)} for w in flat]


def align_script(script_tokens, tw):
    """Transfer transcript timings onto the known script (exact spelling/punctuation for captions)."""
    norm = lambda x: re.sub(r"[^\w']+", "", x.lower())
    a, b = [norm(t) for t in script_tokens], [norm(t["w"]) for t in tw]
    times = [None] * len(a)
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                times[i1 + k] = (tw[j1 + k]["s"], tw[j1 + k]["e"])
        elif tag == "replace" and j2 > j1:
            part = _distribute(script_tokens[i1:i2], tw[j1]["s"], tw[j2 - 1]["e"])
            for k, w in enumerate(part):
                times[i1 + k] = (w["s"], w["e"])
    if not any(times):
        return None
    n, i = len(times), 0
    while i < n:  # fill runs of unmatched script words between matched neighbours
        if times[i]:
            i += 1
            continue
        j = i
        while j < n and not times[j]:
            j += 1
        lo = times[i - 1][1] if i > 0 else max(0.0, times[j][0] - 0.3 * (j - i))
        hi = times[j][0] if j < n else lo + 0.3 * (j - i)
        hi = max(hi, lo + 0.08 * (j - i))
        for k, w in enumerate(_distribute(script_tokens[i:j], lo, hi)):
            times[i + k] = (w["s"], w["e"])
        i = j
    return [{"w": w, "s": round(t[0], 3), "e": round(t[1], 3)} for w, t in zip(script_tokens, times)]


def _write_words(out, words, source, duration, spec=None):
    common.save_json(out, {"source": source, "duration": round(duration, 3), "words": words})
    print(f"{out}  {len(words)} words  ({source})")
    if spec:
        spec.reload()
        spec.data.setdefault("voiceover", {})["words"] = spec.rel(out)
        spec.save()


def _audio_and_out(a):
    spec = common.Spec(a.spec) if a.spec else None
    audio = Path(a.file) if a.file else (spec.p((spec.data.get("voiceover") or {}).get("file")) if spec else None)
    if not audio or not audio.exists():
        common.die("No audio: pass --file or run `audio.py tts --spec` first")
    out = Path(a.out) if a.out else (spec.root / "captions" / f"{spec.vid}_words.json" if spec else
                                     audio.with_name(audio.stem + "_words.json"))
    script = None
    if a.script_file:
        script = Path(a.script_file).read_text(encoding="utf-8")
    elif spec and not a.no_script:
        script = (spec.data.get("voiceover") or {}).get("script")
    return spec, audio, out, script


def cmd_transcribe(a):
    spec, audio, out, script = _audio_and_out(a)
    api.use_project(spec.root if spec else None)
    dur = common.probe(audio)["duration"]
    # Tokentide accepts response_format "json" or "text"; Venice adds word and segment timings with timestamps=true.
    fields = {"model": a.model, "response_format": "json", "timestamps": "true"}
    if a.language:
        fields["language"] = a.language
    mime = api.sniff(audio.read_bytes()[:16])[1] or mimetypes.guess_type(audio.name)[0] or "audio/mpeg"
    raw = audio.read_bytes()
    if len(raw) > 4_300_000:  # Tokentide direct-body limit is 4.5 MB: compress speech (Opus 24 kbps ≈ 3 min/MB)
        small = audio.with_name(audio.stem + "_asr.ogg")
        common.ffmpeg(["-y", "-i", audio, "-ac", "1", "-c:a", "libopus", "-b:a", "24k", small])
        audio, raw, mime = small, small.read_bytes(), "audio/ogg"
        if len(raw) > 4_300_000:
            common.die("Audio is still over 4.5 MB after compression; transcribe a shorter file or use `audio.py align`.")
    files = {"file": (audio.name, raw, mime)}
    try:
        resp = api.post_multipart("/audio/transcriptions", fields, files, timeout=300)
    except api.APIError as e:
        if e.status != 400:
            raise
        common.log(f"[audio] transcription params rejected ({e.message[:100]}); retrying minimal request")
        resp = api.post_multipart("/audio/transcriptions", {"model": a.model, "response_format": "json"}, files)
    api.log_call("asr", "/audio/transcriptions", model=a.model, resp=resp)
    j = resp.json() if resp.is_json() else resp.body.decode("utf-8", "replace")
    words, text = words_from_transcript(j, dur)
    source = f"tokentide:{a.model}"
    if script:
        tokens = script.split()
        aligned = align_script(tokens, words) if words else None
        if aligned:
            words, source = aligned, source + "+script"
        else:
            words, source = align_offline(tokens, speech_spans(audio)[0]), "offline-silence+script"
    _write_words(out, words, source, dur, spec)


def cmd_align(a):
    spec, audio, out, script = _audio_and_out(a)
    if not script:
        common.die("align needs the script (--script-file or spec voiceover.script)")
    spans, dur = speech_spans(audio)
    _write_words(out, align_offline(script.split(), spans), "offline-silence+script", dur, spec)


def cmd_clone(a):
    common.die("Voice cloning isn't offered through Tokentide (it would keep voice samples upstream for days). "
               "Pick a stock voice (`audio.py voices`) or record a real voice-over and set voiceover.file.", code=2)


# ---------------------------------------------------------------- music & sound effects (queued jobs)
def _gen_body(cfg, kind_label, a, root):
    model = common.resolve_model(root, a.model or cfg.get("model") or f"@{kind_label}")
    prompt = a.prompt or cfg.get("prompt") or common.die(f"{kind_label}: prompt missing")
    body = {"model": model, "prompt": prompt,
            "duration_seconds": int(a.duration or cfg.get("duration_seconds") or (30 if kind_label == "music" else 2))}
    instrumental = a.instrumental if a.instrumental is not None else cfg.get("force_instrumental", kind_label == "music")
    if kind_label == "music" and instrumental is not None:
        body["force_instrumental"] = bool(instrumental)
    body.update(cfg.get("extra") or {})
    body.update(common.kv_pairs(a.set))
    return body


def _run_gen(a, kind_label):
    import video  # shared queued-job engine (quote -> queue -> retrieve -> complete)

    video.api.set_lane(a.lane)
    spec = common.Spec(a.spec) if a.spec else None
    root = spec.root if spec else common.find_project_root(Path(a.out).resolve().parent if a.out else Path.cwd())
    api.use_project(root)
    jobs = []
    if spec and kind_label == "music":
        cfg = (spec.data.get("music") or {}).get("generate")
        if not cfg:
            common.die('spec has no music.generate {"model": "@music", "prompt": ..., "duration_seconds": ...}')
        jobs.append((cfg, f"assets/music/{spec.vid}_music.mp3", "music"))
    elif spec:
        for i, fx in enumerate(spec.data.get("sfx") or []):
            if fx.get("generate") and not (fx.get("file") and spec.p(fx["file"]).exists()):
                jobs.append((fx["generate"], f"assets/sfx/{spec.vid}_sfx{i}.mp3", f"sfx:{i}"))
        if not jobs:
            common.die("no sfx[] entries with a generate block and no file")
    else:
        if not a.out:
            common.die("--out is required without --spec")
        jobs.append(({}, a.out, None))
    path = None
    for cfg, out, target in jobs:
        body = _gen_body(cfg, kind_label, a, root)
        q = video.quote(body, "audio")
        print(f"{kind_label} {body['model']} {body['duration_seconds']}s -> quote ${q.get('usd')}"
              + (f" (list ${q['list_usd']:.2f})" if q.get("list_usd") else ""))
        if a.dry_run:
            continue
        video.check_queue_open([q])
        dest = (root / out) if not Path(out).is_absolute() else Path(out)
        path = video.adhoc_submit(body, dest, a.jobs or (root / "logs" / (f"{spec.vid}_audio_jobs.json" if spec else
                                                                         "audio_jobs.json")),
                                  key=Path(out).stem, kind="audio", target=target,
                                  spec_rel=spec.rel(spec.path) if spec else None)
    if path:
        sys.exit(video.poll(path, a.poll_seconds, a.interval))


def cmd_music(a):
    _run_gen(a, "music")


def cmd_sfx(a):
    _run_gen(a, "sfx")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("tts")
    t.add_argument("--spec")
    t.add_argument("--text")
    t.add_argument("--text-file")
    t.add_argument("--model", help="default spec voiceover.model or tts-kokoro")
    t.add_argument("--voice", help="default spec voiceover.voice or af_sky (voices are model-specific)")
    t.add_argument("--speed", type=float)
    t.add_argument("--format", default="mp3", choices=["mp3", "wav", "aac", "flac", "opus"])
    t.add_argument("--out")
    v = sub.add_parser("voices")
    v.add_argument("--cache", help="models.json (default: live API)")
    v.add_argument("--lang", help="voice-id prefix filter, e.g. 'e' for Spanish in Kokoro (ef_/em_)")
    for name in ("transcribe", "align"):
        x = sub.add_parser(name)
        x.add_argument("--spec")
        x.add_argument("--file", help="audio file (default spec voiceover.file)")
        x.add_argument("--out", help="words.json path (default captions/<vid>_words.json)")
        x.add_argument("--script-file", help="known script text for exact caption spelling")
        x.add_argument("--no-script", action="store_true", help="ignore the spec script")
        if name == "transcribe":
            x.add_argument("--model", default="nvidia/parakeet-tdt-0.6b-v3")
            x.add_argument("--language")
    for name in ("music", "sfx"):
        g = sub.add_parser(name)
        g.add_argument("--spec", help="uses music.generate / sfx[].generate and writes the files back into the spec")
        g.add_argument("--model", help=f"default @{name} (models.py choose {name}=<id>)")
        g.add_argument("--prompt")
        g.add_argument("--duration", type=float, help="seconds")
        g.add_argument("--instrumental", type=lambda x: x.lower() == "true", help="true|false (music)")
        g.add_argument("--out", help="output path without spec, e.g. P/assets/music/track.mp3")
        g.add_argument("--jobs")
        g.add_argument("--lane", choices=["standard", "lowtide"])
        g.add_argument("--set", action="append", help="extra model field key=value")
        g.add_argument("--dry-run", action="store_true")
        g.add_argument("--poll-seconds", type=int, default=240)
        g.add_argument("--interval", type=float, default=7.0)
    c = sub.add_parser("clone")
    c.add_argument("--file", required=True)
    c.add_argument("--name", required=True)
    c.add_argument("--model", default="tts-chatterbox-hd")
    c.add_argument("--i-have-consent", action="store_true")
    a = ap.parse_args()
    {"tts": cmd_tts, "voices": cmd_voices, "transcribe": cmd_transcribe, "align": cmd_align, "clone": cmd_clone,
     "music": cmd_music, "sfx": cmd_sfx}[a.cmd](a)


if __name__ == "__main__":
    try:
        main()
    except api.APIError as e:
        common.die(str(e))
