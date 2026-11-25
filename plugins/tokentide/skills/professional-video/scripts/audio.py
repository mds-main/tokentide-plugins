#!/usr/bin/env python3
"""Voice-over, pacing, word timings, speech cuts, and generated music/SFX via Tokentide.

  tts         text -> speech file (≤4,096 chars)         POST /audio/speech; queued voice models
                                                         (e.g. ElevenLabs TTS v4 Turbo) via /audio/quote|queue
  voices      list voice models and their voices          GET  /models?type=tts and type=music
  transcribe  speech -> word timings (words.json)        POST /audio/transcriptions (default: elevenlabs/scribe-v2,
                                                         fallback: nvidia/parakeet-tdt-0.6b-v3 on private keys)
  align       offline word timings: known script + silence detection (no API, no extra deps)
  pace        slow a fast VO by lengthening silent pauses only (never time-stretches speech; voiced samples stay identical)
  split       split speech into pieces snapped to real silences (aborts if any piece edge > -50 dBFS)
  trim        trim speech with silence-snapped start/end and edge checks
  normalize   loudness-normalize a voice/audio file (linear loudnorm, else fixed gain + true-peak alimiter)
  music       original background track (rights-safe)    POST /audio/quote|queue|retrieve|complete
  sfx         original sound effect (whoosh, pop, pour…) same queued flow
  clone       NOT offered by Tokentide (it would keep voice samples upstream)

Spec mode (--spec briefs/vNN.json) reads/writes voiceover.{script,model,voice,speed,file,words}.
words.json format: {"words": [{"w": "Hello", "s": 0.12, "e": 0.41}, ...], "source": "...", "duration": 4.2}
"""
from __future__ import annotations

import argparse
import array
import difflib
import json
import math
import mimetypes
import re
import sys
import tempfile
import wave
from pathlib import Path

import common
import apiclient as api

PACE_OK = (2.2, 3.2)  # spoken words/second that read well in short-form
DEFAULT_ASR = "elevenlabs/scribe-v2"
FALLBACK_ASR = "nvidia/parakeet-tdt-0.6b-v3"
DEFAULT_PAUSES = {"sentence": 0.45, "clause": 0.36, "comma": 0.22}
_KOKORO_VOICE_RE = re.compile(r"^[a-z]{2}_[a-z]+$")


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


def _model_entry(root, model, types=("tts", "music")):
    """Catalog entry for a model: project's models.json first, else the live catalog."""
    m = common.load_models(root).get(model) if root else None
    if m:
        return m
    for t in types:
        try:
            for x in api.get(f"/models?type={t}", retries=2).json().get("data", []):
                if x.get("id") == model:
                    x.setdefault("type", t)
                    return x
        except api.APIError:
            return None
    return None


def _voice_entry(root, model):
    return _model_entry(root, model, types=("tts", "music"))


def _pick_voice(entry, wanted):
    """The requested voice if the model offers it (or takes custom voice ids), else the model's default voice."""
    spec_ = (entry or {}).get("model_spec") or {}
    mid = (entry or {}).get("id") or ""
    voices = [str(v) for v in (spec_.get("voices") or [])]
    by_lower = {v.lower(): v for v in voices}
    default = spec_.get("default_voice") or (voices[0] if voices else None)
    if not wanted:
        return default or "af_sky"
    if wanted.lower() in by_lower:
        return by_lower[wanted.lower()]
    if not voices:
        return wanted
    if spec_.get("supports_custom_voice_id"):
        # Catch leftover Kokoro voice ids (e.g. 'af_sky' from the example spec) on non-Kokoro models.
        if _KOKORO_VOICE_RE.fullmatch(wanted) and "kokoro" not in mid.lower():
            common.log(f"voice '{wanted}' is not offered by {mid} (looks like a Kokoro voice id); using its default "
                       f"voice '{default}' (`audio.py voices` lists them, or pass a custom voice id)")
            return default
        return wanted
    common.log(f"voice '{wanted}' is not offered by {mid}; using its default voice '{default}' "
               f"(`audio.py voices` lists them; set voiceover.voice in the spec)")
    return default


def _tts_queued(a, model, text, voice, speed, entry, out, root, spec, vo):
    """Voice models on Tokentide's queued audio route: quote -> queue -> poll -> the file (billed per character)."""
    import video  # shared queued-job engine

    ms = (entry or {}).get("model_spec") or {}
    body = {"model": model, "prompt": text}
    if voice:
        body["voice"] = voice
    speed_used = False
    if ms.get("supports_speed") is True and speed is not None:
        spd = float(speed)
        if ms.get("min_speed") is not None:
            spd = max(float(ms["min_speed"]), spd)
        if ms.get("max_speed") is not None:
            spd = min(float(ms["max_speed"]), spd)
        body["speed"] = spd
        speed_used = True
    body.update(vo.get("extra") or {})
    out = out.with_suffix(".mp3")
    jobs = (root / "logs" / f"{spec.vid if spec else 'adhoc'}_tts_jobs.json") if root else None
    path = video.adhoc_submit(body, out, jobs, key=out.stem, kind="audio", target="voiceover" if spec else None,
                              spec_rel=spec.rel(spec.path) if spec else None)
    rc = video.poll(path, a.poll_seconds, a.interval)
    data = common.load_json(path)
    rec = [r for r in data["jobs"] if r.get("key") == out.stem][-1]
    if rec.get("status") != "done":
        common.log("The voice-over is still being generated (or failed; see above). When `video.py poll` collects it, "
                   "the spec's voiceover.file is set; never re-run tts for it (that queues and pays again).")
        sys.exit(rc or 1)
    done = Path(rec["out"]) if Path(rec["out"]).is_absolute() else Path(data.get("root") or path.parent.parent) / rec["out"]
    api.write_sidecar(done, "/audio/queue", body, None, queue_id=rec.get("queue_id"), quote_usd=rec.get("quote_usd"))
    return done, speed_used


def cmd_tts(a):
    spec = common.Spec(a.spec) if a.spec else None
    vo = (spec.data.get("voiceover") or {}) if spec else {}
    text = _text_for(a, spec)
    root = spec.root if spec else common.find_project_root(Path(a.out).resolve().parent if a.out else Path.cwd())
    picks = common.project_meta(root).get("models", {}) if root else {}
    model = common.resolve_model(root, a.model or vo.get("model") or picks.get("tts") or "tts-kokoro")
    speed = a.speed if a.speed is not None else vo.get("speed", 1.0)
    out = Path(a.out) if a.out else (spec.root / "audio" / f"{spec.vid}_vo.{a.format}" if spec else None)
    if not out:
        common.die("--out is required without --spec")
    api.use_project(root)
    entry = _voice_entry(root, model)
    ms = (entry or {}).get("model_spec") or {}
    voice = _pick_voice(entry, a.voice or vo.get("voice"))
    queued = bool(entry) and entry.get("type") == "music"
    limit = int(ms.get("prompt_character_limit") or 4096) if queued else 4096
    if len(text) > limit:
        common.die(f"Voice-over script is {len(text)} chars; {model} accepts at most {limit:,}. Split or shorten it.")
    speed_note = ""
    if queued:
        out, speed_used = _tts_queued(a, model, text, voice, speed, entry, out, root, spec, vo)
        if not speed_used:
            speed_note = (f" [speed={speed:g} ignored: model has no native speed control]"
                          if speed is not None and abs(float(speed) - 1.0) > 1e-3
                          else " [no native speed control]")
    else:
        body = {"model": model, "input": text, "voice": voice, "response_format": a.format}
        if ms.get("supports_speed") is False:
            speed_note = (f" [speed={speed:g} ignored: model has no native speed control]"
                          if speed is not None and abs(float(speed) - 1.0) > 1e-3
                          else " [no native speed control]")
        else:
            body["speed"] = speed
        for k, v in (vo.get("extra") or {}).items():
            body[k] = v
        resp, used = api.post_adaptive("/audio/speech", body, droppable=("speed", "response_format"))
        if "speed" in body and "speed" not in used:
            speed_note = f" [speed={speed:g} dropped: not supported by {model}]"
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
    if PACE_OK[0] <= pace <= PACE_OK[1]:
        flag = "OK"
    elif pace > PACE_OK[1]:
        flag = ("TOO FAST (aim 2.2-3.2 w/s; never time-stretch speech — shorten script, use a model with native "
                "speed control, or lengthen pauses with `audio.py pace`)")
    else:
        flag = "SLOW (aim 2.2-3.2 w/s; tighten script or raise native speed if supported — never time-stretch speech)"
    print(f"{out}  {dur:.2f}s  {n} words  {pace:.2f} words/s{speed_note}  {flag}")
    if spec:
        spec.reload()
        spec.data.setdefault("voiceover", {}).update(file=spec.rel(out), model=model, voice=voice, speed=speed)
        spec.save()


def cmd_voices(a):
    import models as catalog_tools  # audio_kind: which "music" models are voices

    if a.cache:
        models = common.load_models(path=a.cache)
    else:
        models = {}
        for t in ("tts", "music"):
            for m in api.get(f"/models?type={t}").json().get("data", []):
                models[m["id"]] = {**m, "type": m.get("type") or t}
    for mid, m in sorted(models.items()):
        if m.get("type") not in ("tts", "music", None):
            continue
        if m.get("type") == "music" and catalog_tools.audio_kind(m) != "tts":
            continue
        ms = m.get("model_spec") or {}
        voices = [v for k, v in common.spec_lookup(m, "voice").items() if isinstance(v, list)]
        vs = voices[0] if voices else []
        if a.lang:
            vs = [v for v in vs if str(v).lower().startswith(a.lang.lower())]
        tags = []
        if ms.get("supports_custom_voice_id"):
            tags.append("custom voice IDs ok")
        if ms.get("supports_speed") is False:
            tags.append("no native speed")
        tag_s = f" [{', '.join(tags)}]" if tags else ""
        print(f"{mid}: {len(vs)} voices{tag_s}" + (f" -> {', '.join(map(str, vs[:60]))}" if vs else ""))


# ---------------------------------------------------------------- PCM, silence detection & safe speech cuts
def read_pcm(path) -> tuple[array.array, int, int]:
    """Read any audio file as 16-bit signed PCM `(samples, sample_rate, channels)` (stdlib-only)."""
    p = Path(path)
    if not p.exists():
        common.die(f"Audio not found: {p}")

    def _load_wav(wp: Path):
        with wave.open(str(wp), "rb") as wf:
            if wf.getsampwidth() != 2 or wf.getcomptype() != "NONE":
                return None
            sr, ch = wf.getframerate(), wf.getnchannels()
            raw = wf.readframes(wf.getnframes())
        arr = array.array("h")
        arr.frombytes(raw)
        if sys.byteorder == "big":
            arr.byteswap()
        return arr, sr, ch

    if p.suffix.lower() == ".wav":
        loaded = _load_wav(p)
        if loaded is not None:
            return loaded
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "pcm.wav"
        common.ffmpeg(["-y", "-i", p, "-vn", "-c:a", "pcm_s16le", tmp])
        loaded = _load_wav(tmp)
        if loaded is None:
            common.die(f"Could not decode PCM from {p}")
        return loaded


def write_pcm(path, samples: array.array, sample_rate: int, channels: int) -> Path:
    """Write 16-bit signed PCM WAV (lossless)."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    arr = samples
    if sys.byteorder == "big":
        arr = array.array("h", samples)
        arr.byteswap()
    with wave.open(str(out), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(arr.tobytes())
    return out


def frame_rms_dbfs(samples: array.array, f0: int, f1: int, ch: int) -> float:
    """RMS level in dBFS over PCM frame range `[f0, f1)`."""
    n_frames = len(samples) // ch
    a = max(0, min(n_frames, f0)) * ch
    b = max(a, min(n_frames, f1)) * ch
    if b <= a:
        return -120.0
    seg = samples[a:b]
    sq = sum(x * x for x in seg)
    if sq <= 0:
        return -120.0
    rms = math.sqrt(sq / len(seg))
    return 20.0 * math.log10(rms / 32768.0)


def silent_runs_pcm(samples: array.array, sr: int, ch: int, *, threshold_db: float = -60.0,
                    min_ms: float = 120.0, win_ms: float = 5.0) -> list[tuple[int, int]]:
    """Silent runs `(start_frame, end_frame)` where peak level stays <= `threshold_db` for >= `min_ms`."""
    n_frames = len(samples) // ch
    if n_frames == 0:
        return []
    win = max(1, int(round(sr * win_ms / 1000.0)))
    min_frames = max(1, int(round(sr * min_ms / 1000.0)))
    amp = 32768.0 * (10.0 ** (threshold_db / 20.0))
    runs: list[tuple[int, int]] = []
    run_start: int | None = None
    for f0 in range(0, n_frames, win):
        f1 = min(n_frames, f0 + win)
        chunk = samples[f0 * ch : f1 * ch]
        hi, lo = max(chunk), min(chunk)
        peak = hi if hi >= -lo else -lo
        if peak <= amp:
            if run_start is None:
                run_start = f0
        else:
            if run_start is not None and f0 - run_start >= min_frames:
                runs.append((run_start, f0))
            run_start = None
    if run_start is not None and n_frames - run_start >= min_frames:
        runs.append((run_start, n_frames))
    return runs


def silent_runs(audio, *, threshold_db: float = -60.0, min_ms: float = 120.0) -> tuple[list[tuple[float, float]], float]:
    """Return `([(start_s, end_s), ...], duration_s)` for silent runs <= `threshold_db` lasting >= `min_ms`."""
    samples, sr, ch = read_pcm(audio)
    dur = (len(samples) // ch) / sr
    runs = [(f0 / sr, f1 / sr) for f0, f1 in silent_runs_pcm(samples, sr, ch, threshold_db=threshold_db, min_ms=min_ms)]
    return runs, dur


def snap_cut_to_silence(target_s: float, runs: list[tuple[float, float]], *, max_drift_s: float = 0.5,
                        edge_margin_s: float = 0.10) -> float:
    """Snap a desired cut time into a real silent run (middle, or >= `edge_margin_s` from speech edges).
    Raises ValueError if no silent run lies within `max_drift_s` — never cuts mid-word."""
    if not runs:
        raise ValueError(f"No detected silent runs available to snap cut at {target_s:.3f}s")
    containing = [r for r in runs if r[0] <= target_s <= r[1]]
    if containing:
        s, e = containing[0]
        if e - s >= 2.0 * edge_margin_s:
            return min(max(target_s, s + edge_margin_s), e - edge_margin_s)
        return (s + e) / 2.0
    best = min(runs, key=lambda r: min(abs(target_s - r[0]), abs(target_s - r[1])))
    dist = min(abs(target_s - best[0]), abs(target_s - best[1]))
    if dist > max_drift_s:
        raise ValueError(f"No silence within {max_drift_s:.2f}s of {target_s:.3f}s (nearest is "
                         f"{best[0]:.3f}-{best[1]:.3f}s, {dist:.2f}s away) — refusing to cut mid-word")
    return (best[0] + best[1]) / 2.0


def check_speech_edges(samples: array.array, sr: int, ch: int, *, edge_ms: float = 15.0,
                       max_db: float = -50.0, label: str = "piece",
                       check_start: bool = True, check_end: bool = True) -> tuple[float, float]:
    """Verify the cut edges (first and/or last `edge_ms`) of a speech piece are <= `max_db` dBFS; abort otherwise."""
    n_frames = len(samples) // ch
    edge_n = max(1, min(n_frames, int(round(sr * edge_ms / 1000.0))))
    start_db = frame_rms_dbfs(samples, 0, edge_n, ch)
    end_db = frame_rms_dbfs(samples, max(0, n_frames - edge_n), n_frames, ch)
    if (check_start and start_db > max_db) or (check_end and end_db > max_db):
        raise ValueError(f"{label}: speech edge too hot (first {edge_ms:g}ms={start_db:.1f} dBFS, "
                         f"last {edge_ms:g}ms={end_db:.1f} dBFS; must be <= {max_db:g} dBFS) — cut landed inside speech")
    return start_db, end_db


def _apply_fade_in(samples: array.array, f0: int, n: int, ch: int) -> None:
    if n <= 0:
        return
    for i in range(n):
        g = i / n
        base = (f0 + i) * ch
        for c in range(ch):
            samples[base + c] = int(round(samples[base + c] * g))


def _apply_fade_out(samples: array.array, f0: int, n: int, ch: int) -> None:
    if n <= 0:
        return
    for i in range(n):
        g = (n - i) / n
        base = (f0 + i) * ch
        for c in range(ch):
            samples[base + c] = int(round(samples[base + c] * g))


def cut_speech(audio_path, cuts_s: list[float], out_dir, *, prefix: str | None = None,
               threshold_db: float = -60.0, min_ms: float = 120.0, edge_db: float = -50.0,
               edge_ms: float = 15.0, fade_ms: float = 8.0, max_drift_s: float = 0.5) -> list[dict]:
    """Split a speech file at `cuts_s`, snapping every cut to real silence and verifying 15 ms edges <= -50 dBFS."""
    src = Path(audio_path)
    samples, sr, ch = read_pcm(src)
    n_frames = len(samples) // ch
    dur = n_frames / sr
    runs_f = silent_runs_pcm(samples, sr, ch, threshold_db=threshold_db, min_ms=min_ms)
    runs_s = [(f0 / sr, f1 / sr) for f0, f1 in runs_f]
    snapped = []
    for t in sorted(set(float(x) for x in cuts_s)):
        if t <= 0.0 or t >= dur:
            continue
        st = snap_cut_to_silence(t, runs_s, max_drift_s=max_drift_s)
        if not snapped or st - snapped[-1] > 0.05:
            snapped.append(st)
    bounds = [0] + [int(round(t * sr)) for t in snapped] + [n_frames]
    fade_n = int(round(sr * fade_ms / 1000.0))
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = prefix or src.stem
    pieces = []
    for idx in range(len(bounds) - 1):
        a, b = bounds[idx], bounds[idx + 1]
        piece = array.array("h", samples[a * ch : b * ch])
        # Verify every cut edge before applying boundary fades so a bad cut is never hidden by a fade.
        start_db, end_db = check_speech_edges(piece, sr, ch, edge_ms=edge_ms, max_db=edge_db,
                                              label=f"piece {idx + 1} ({a / sr:.3f}-{b / sr:.3f}s)",
                                              check_start=(a > 0), check_end=(b < n_frames))
        pf = min(fade_n, (b - a) // 4)
        if idx > 0:
            _apply_fade_in(piece, 0, pf, ch)
        if idx < len(bounds) - 2:
            _apply_fade_out(piece, (b - a) - pf, pf, ch)
        dest = out_dir / f"{stem}_p{idx + 1:02d}.wav"
        write_pcm(dest, piece, sr, ch)
        pieces.append({"file": str(dest), "start": round(a / sr, 3), "end": round(b / sr, 3),
                       "duration": round((b - a) / sr, 3), "start_dbfs": round(start_db, 1),
                       "end_dbfs": round(end_db, 1)})
    return pieces


def trim_speech(audio_path, start_s: float | None, end_s: float | None, out_path, *,
                threshold_db: float = -60.0, min_ms: float = 120.0, edge_db: float = -50.0,
                edge_ms: float = 15.0, fade_ms: float = 8.0, max_drift_s: float = 0.5) -> dict:
    """Trim speech to `[start_s, end_s]`, snapping interior cuts to real silence and verifying 15 ms edges <= -50 dBFS."""
    src = Path(audio_path)
    samples, sr, ch = read_pcm(src)
    n_frames = len(samples) // ch
    dur = n_frames / sr
    runs_f = silent_runs_pcm(samples, sr, ch, threshold_db=threshold_db, min_ms=min_ms)
    runs_s = [(f0 / sr, f1 / sr) for f0, f1 in runs_f]
    a_s = 0.0 if start_s is None or start_s <= 0.0 else snap_cut_to_silence(float(start_s), runs_s, max_drift_s=max_drift_s)
    b_s = dur if end_s is None or end_s >= dur else snap_cut_to_silence(float(end_s), runs_s, max_drift_s=max_drift_s)
    if b_s <= a_s + 0.05:
        raise ValueError(f"Trim range invalid after snapping to silence: {a_s:.3f}s -> {b_s:.3f}s")
    a, b = int(round(a_s * sr)), int(round(b_s * sr))
    piece = array.array("h", samples[a * ch : b * ch])
    start_db, end_db = check_speech_edges(piece, sr, ch, edge_ms=edge_ms, max_db=edge_db,
                                          label=f"trim ({a_s:.3f}-{b_s:.3f}s)",
                                          check_start=(a > 0), check_end=(b < n_frames))
    pf = min(int(round(sr * fade_ms / 1000.0)), (b - a) // 4)
    if a > 0:
        _apply_fade_in(piece, 0, pf, ch)
    if b < n_frames:
        _apply_fade_out(piece, (b - a) - pf, pf, ch)
    write_pcm(out_path, piece, sr, ch)
    return {"file": str(out_path), "start": round(a / sr, 3), "end": round(b / sr, 3),
            "duration": round((b - a) / sr, 3), "start_dbfs": round(start_db, 1), "end_dbfs": round(end_db, 1)}


def _punct_pad(word: str, sentence_pad: float, clause_pad: float, comma_pad: float) -> float:
    w = (word or "").rstrip('"\'\u00bb\u201d\u2019)]}')
    if not w:
        return 0.0
    if w[-1] in ".?!\u2026":
        return sentence_pad
    if w[-1] in ":;":
        return clause_pad
    if w[-1] == ",":
        return comma_pad
    return 0.0


def pace_speech(audio_path, words: list[dict] | None, out_path, *, target_wps: float | None = None,
                sentence_pad: float = DEFAULT_PAUSES["sentence"], clause_pad: float = DEFAULT_PAUSES["clause"],
                comma_pad: float = DEFAULT_PAUSES["comma"], threshold_db: float = -60.0, min_ms: float = 120.0,
                fade_ms: float = 8.0, edge_db: float = -50.0, edge_ms: float = 15.0) -> dict:
    """Pace a voice-over by lengthening only its own silent pauses (never time-stretches speech).

    Finds interior silent runs <= `threshold_db` lasting >= `min_ms`, inserts digital silence at the
    midpoint of each selected pause with `fade_ms` fades strictly inside the silence, verifies cut
    edges <= `edge_db`, writes lossless WAV, and shifts `words` timestamps accordingly.
    Every voiced sample in the output is sample-identical to the input PCM.
    """
    samples, sr, ch = read_pcm(audio_path)
    n_frames = len(samples) // ch
    orig_dur = n_frames / sr
    runs_f = silent_runs_pcm(samples, sr, ch, threshold_db=threshold_db, min_ms=min_ms)
    interior = [(f0, f1) for f0, f1 in runs_f if f0 > 0 and f1 < n_frames]

    words = [dict(w) for w in (words or [])]
    punct_cands, plain_cands = [], []
    for f0, f1 in interior:
        mid_f = (f0 + f1) // 2
        mid_s = mid_f / sr
        if words:
            prev_w = None
            next_w = None
            for idx, w in enumerate(words):
                w_mid = (float(w["s"]) + float(w["e"])) / 2.0
                if w_mid < mid_s:
                    prev_w = w
                    next_w = words[idx + 1] if idx + 1 < len(words) else None
                else:
                    if next_w is None:
                        next_w = w
                    break
            if prev_w is None or next_w is None:
                continue
            pad = _punct_pad(prev_w["w"], sentence_pad, clause_pad, comma_pad)
            if pad > 0:
                punct_cands.append((f0, f1, mid_f, pad, prev_w["w"]))
            else:
                plain_cands.append((f0, f1, mid_f, 0.15, prev_w["w"]))
        else:
            plain_cands.append((f0, f1, mid_f, sentence_pad, ""))

    selected = list(punct_cands) if punct_cands else list(plain_cands)
    n_words = len(words)
    if target_wps is not None and n_words > 0:
        needed = max(0.0, n_words / float(target_wps) - orig_dur)
        if needed <= 0.01:
            selected = []
        elif selected:
            base = sum(c[3] for c in selected)
            scale = needed / base if base > 0 else 0.0
            # If punctuated pauses alone would need >1.5s added to a pause, also include unpunctuated interior pauses.
            if punct_cands and plain_cands and max(c[3] * scale for c in selected) > 1.5:
                selected = sorted(punct_cands + plain_cands, key=lambda c: c[2])
                base = sum(c[3] for c in selected)
                scale = needed / base if base > 0 else 0.0
            selected = [(f0, f1, mid, pad * scale, tok) for f0, f1, mid, pad, tok in selected]
            if selected and max(c[3] for c in selected) > 1.2:
                common.log(f"WARNING: reaching {target_wps:.2f} w/s requires up to +{max(c[3] for c in selected):.2f}s "
                           "per pause; consider shortening the script too")

    # Splice output PCM: keep every sample outside [mid - fade_n, mid + fade_n] verbatim (strictly inside silence).
    fade_req = int(round(sr * fade_ms / 1000.0))
    edge_n = max(1, int(round(sr * edge_ms / 1000.0)))
    out = array.array("h")
    prev = 0
    cuts = []
    for f0, f1, mid_f, add_s, tok in sorted(selected, key=lambda c: c[2]):
        extra_f = int(round(add_s * sr))
        if extra_f <= 0 or mid_f <= prev:
            continue
        # Verify 15 ms around the cut are below edge_db before fading.
        pre_db = frame_rms_dbfs(samples, max(0, mid_f - edge_n), mid_f, ch)
        post_db = frame_rms_dbfs(samples, mid_f, min(n_frames, mid_f + edge_n), ch)
        if pre_db > edge_db or post_db > edge_db:
            raise ValueError(f"pause cut at {mid_f / sr:.3f}s too hot (pre={pre_db:.1f} dBFS, post={post_db:.1f} dBFS)")
        fn = min(fade_req, mid_f - f0, f1 - mid_f, mid_f - prev)
        # Verbatim copy up to fade-out start (every voiced stretch is untouched, bit-for-bit identical).
        out.extend(samples[prev * ch : (mid_f - fn) * ch])
        if fn > 0:
            fo_seg = array.array("h", samples[(mid_f - fn) * ch : mid_f * ch])
            _apply_fade_out(fo_seg, 0, fn, ch)
            out.extend(fo_seg)
        out.extend(array.array("h", [0]) * (extra_f * ch))
        if fn > 0:
            fi_seg = array.array("h", samples[mid_f * ch : (mid_f + fn) * ch])
            _apply_fade_in(fi_seg, 0, fn, ch)
            out.extend(fi_seg)
        prev = mid_f + fn
        cuts.append({"at": round(mid_f / sr, 3), "added_s": round(extra_f / sr, 3), "after": tok,
                     "silence": [round(f0 / sr, 3), round(f1 / sr, 3)]})
    out.extend(samples[prev * ch :])
    write_pcm(out_path, out, sr, ch)
    new_dur = (len(out) // ch) / sr

    shifted = []
    for w in words:
        w_mid = (float(w["s"]) + float(w["e"])) / 2.0
        delta = sum(c["added_s"] for c in cuts if c["at"] < w_mid)
        shifted.append({"w": w["w"], "s": round(float(w["s"]) + delta, 3), "e": round(float(w["e"]) + delta, 3)})

    return {"file": str(out_path), "orig_duration": round(orig_dur, 3), "duration": round(new_dur, 3),
            "added_total_s": round(new_dur - orig_dur, 3), "cuts": cuts, "words": shifted,
            "sample_rate": sr, "channels": ch}


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


def detect_silences_ffmpeg(audio, noise="-45dB", min_sil=0.30) -> tuple[list[tuple[float, float]], float]:
    """Return `([(silence_start, silence_end), ...], duration)` via FFmpeg silencedetect."""
    dur = common.probe(audio)["duration"]
    err = common.ffmpeg(["-i", audio, "-af", f"silencedetect=noise={noise}:d={min_sil}", "-f", "null", "-"],
                        loglevel="info").stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", err)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", err)]
    runs = []
    for i, s in enumerate(starts):
        e = ends[i] if i < len(ends) else dur
        if e - s >= min_sil - 1e-3:
            runs.append((s, e))
    return runs, dur


def speech_spans(audio, noise="-35dB", min_sil=0.18):
    runs, dur = detect_silences_ffmpeg(audio, noise=noise, min_sil=min_sil)
    spans, cur = [], 0.0
    for s, e in runs:
        if s - cur > 0.05:
            spans.append((cur, s))
        cur = e
    if dur - cur > 0.05:
        spans.append((cur, dur))
    return spans or [(0.0, dur)], dur


def check_word_silences(audio, words: list[dict], *, min_sil: float = 0.30, noise: str = "-45dB") -> list[dict]:
    """Sanity-check word timings against real silences (>= `min_sil` s). Returns a list of misaligned silences
    where words overlap the silence or no word boundary falls inside it."""
    if not words:
        return []
    runs, dur = detect_silences_ffmpeg(audio, noise=noise, min_sil=min_sil)
    issues = []
    for s, e in runs:
        if s < 0.08 or e > dur - 0.08:
            continue  # ignore leading / trailing silence
        before = [w for w in words if (w["s"] + w["e"]) / 2.0 < e]
        after = [w for w in words if (w["s"] + w["e"]) / 2.0 > s]
        if not before or not after:
            continue
        overlap = sum(max(0.0, min(e, w["e"]) - max(s, w["s"])) for w in words)
        has_boundary = any(words[i]["e"] <= e + 0.05 and words[i + 1]["s"] >= s - 0.05
                           for i in range(len(words) - 1))
        limit = min(0.15, (e - s) * 0.4)
        if overlap > limit or not has_boundary:
            issues.append({"start": round(s, 3), "end": round(e, 3), "duration": round(e - s, 3),
                           "word_overlap_s": round(overlap, 3), "has_boundary": has_boundary})
    return issues


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


def _choose_default_asr(root) -> str:
    """Default to elevenlabs/scribe-v2; fall back to Parakeet if the cached ASR catalog hides it (e.g. private key)."""
    cached = common.load_models(root) if root else {}
    asrs = {mid for mid, m in cached.items() if m.get("type") == "asr"}
    if asrs and DEFAULT_ASR not in asrs and FALLBACK_ASR in asrs:
        common.log(f"[audio] {DEFAULT_ASR} not visible in models.json (private key?); falling back to {FALLBACK_ASR} "
                   "(note: Parakeet word timings can drift up to ~0.45s — never cut speech at ASR times alone)")
        return FALLBACK_ASR
    return DEFAULT_ASR


def _post_transcribe(model: str, language: str | None, files: dict):
    fields = {"model": model, "response_format": "json", "timestamps": "true"}
    if language:
        fields["language"] = language
    try:
        return api.post_multipart("/audio/transcriptions", fields, files, timeout=300)
    except api.APIError as e:
        if e.status != 400:
            raise
        common.log(f"[audio] transcription params rejected ({e.message[:100]}); retrying minimal request")
        return api.post_multipart("/audio/transcriptions", {"model": model, "response_format": "json"}, files)


def cmd_transcribe(a):
    spec, audio, out, script = _audio_and_out(a)
    root = spec.root if spec else common.find_project_root(audio.resolve().parent)
    api.use_project(root)
    dur = common.probe(audio)["duration"]
    explicit_model = bool(a.model)
    model = a.model or _choose_default_asr(root)
    send_audio = audio
    mime = api.sniff(send_audio.read_bytes()[:16])[1] or mimetypes.guess_type(send_audio.name)[0] or "audio/mpeg"
    raw = send_audio.read_bytes()
    if len(raw) > 4_300_000:  # Tokentide direct-body limit is 4.5 MB: compress speech (Opus 24 kbps ≈ 3 min/MB)
        small = send_audio.with_name(send_audio.stem + "_asr.ogg")
        common.ffmpeg(["-y", "-i", send_audio, "-ac", "1", "-c:a", "libopus", "-b:a", "24k", small])
        send_audio, raw, mime = small, small.read_bytes(), "audio/ogg"
        if len(raw) > 4_300_000:
            common.die("Audio is still over 4.5 MB after compression; transcribe a shorter file or use `audio.py align`.")
    files = {"file": (send_audio.name, raw, mime)}
    try:
        resp = _post_transcribe(model, a.language, files)
    except api.APIError as e:
        if not explicit_model and model == DEFAULT_ASR and (e.status in (403, 404) or e.code == "model_not_allowed"):
            common.log(f"[audio] {DEFAULT_ASR} unavailable ({e.code or e.status}, e.g. private key); "
                       f"falling back to {FALLBACK_ASR} (note: Parakeet timings are less precise)")
            model = FALLBACK_ASR
            resp = _post_transcribe(model, a.language, files)
        else:
            raise
    api.log_call("asr", "/audio/transcriptions", model=model, resp=resp)
    j = resp.json() if resp.is_json() else resp.body.decode("utf-8", "replace")
    words, text = words_from_transcript(j, dur)
    source = f"tokentide:{model}"
    if script:
        tokens = script.split()
        aligned = align_script(tokens, words) if words else None
        if aligned:
            words, source = aligned, source + "+script"
        else:
            words, source = align_offline(tokens, speech_spans(audio)[0]), "offline-silence+script"
    issues = check_word_silences(audio, words)
    if issues:
        spans_s = ", ".join(f"{x['start']:.2f}-{x['end']:.2f}s" for x in issues[:5])
        common.log(f"WARNING: {len(issues)} long silence(s) (>=300ms) don't fall cleanly between words "
                   f"({spans_s}). Word timings from {model} may have drifted — use {DEFAULT_ASR} when available, "
                   "and always snap any speech cut to real silence.")
    _write_words(out, words, source, dur, spec)


def cmd_align(a):
    spec, audio, out, script = _audio_and_out(a)
    if not script:
        common.die("align needs the script (--script-file or spec voiceover.script)")
    spans, dur = speech_spans(audio)
    _write_words(out, align_offline(script.split(), spans), "offline-silence+script", dur, spec)


def cmd_pace(a):
    spec = common.Spec(a.spec) if a.spec else None
    vo = (spec.data.get("voiceover") or {}) if spec else {}
    audio = Path(a.file) if a.file else (spec.p(vo.get("file")) if spec else None)
    if not audio or not audio.exists():
        common.die("No audio: pass --file or run `audio.py tts --spec` first")
    words_path = Path(a.words) if a.words else (spec.p(vo.get("words")) if spec and vo.get("words") else None)
    words_data = common.load_json(words_path) if words_path and words_path.exists() else None
    words = (words_data or {}).get("words", [])
    if not words and not a.no_words:
        common.log("note: no words.json found — lengthening all detected interior silences equally "
                   "(run `audio.py transcribe` first for punctuation-weighted pauses)")
    out = Path(a.out) if a.out else (spec.root / "audio" / f"{spec.vid}_vo_paced.wav" if spec else
                                     audio.with_name(audio.stem + "_paced.wav"))
    try:
        res = pace_speech(audio, words, out, target_wps=a.target_wps, sentence_pad=a.sentence_pad,
                          clause_pad=a.clause_pad, comma_pad=a.comma_pad, threshold_db=a.threshold_db,
                          min_ms=a.min_silence_ms, fade_ms=a.fade_ms)
    except ValueError as e:
        common.die(str(e))
    n_words = len(words) or len(re.findall(r"\w+", vo.get("script") or ""))
    old_wps = n_words / res["orig_duration"] if res["orig_duration"] and n_words else 0
    new_wps = n_words / res["duration"] if res["duration"] and n_words else 0
    wps_s = f"  {old_wps:.2f} -> {new_wps:.2f} words/s" if n_words else ""
    print(f"{out}  {res['orig_duration']:.2f}s -> {res['duration']:.2f}s (+{res['added_total_s']:.2f}s across "
          f"{len(res['cuts'])} pauses){wps_s}")
    words_out = None
    if res["words"]:
        words_out = Path(a.words_out) if a.words_out else (
            spec.root / "captions" / f"{spec.vid}_paced_words.json" if spec else
            (words_path.with_name(words_path.stem + "_paced.json") if words_path else out.with_name(out.stem + "_words.json"))
        )
        src = ((words_data or {}).get("source") or "unknown") + "+paced"
        common.save_json(words_out, {"source": src, "duration": res["duration"], "words": res["words"]})
        print(f"{words_out}  {len(res['words'])} words shifted")
    if spec:
        spec.reload()
        svo = spec.data.setdefault("voiceover", {})
        if svo.get("file") and not svo.get("raw_file"):
            svo["raw_file"] = svo["file"]
        svo["file"] = spec.rel(out)
        if words_out:
            svo["words"] = spec.rel(words_out)
        spec.save()


def cmd_split(a):
    spec = common.Spec(a.spec) if a.spec else None
    audio = Path(a.file) if a.file else (spec.p((spec.data.get("voiceover") or {}).get("file")) if spec else None)
    if not audio or not audio.exists():
        common.die("No audio: pass --file or --spec")
    cuts = [float(x.strip()) for x in a.cuts.split(",") if x.strip()]
    out_dir = Path(a.out_dir) if a.out_dir else audio.parent / f"{audio.stem}_pieces"
    try:
        pieces = cut_speech(audio, cuts, out_dir, threshold_db=a.threshold_db, min_ms=a.min_silence_ms,
                            edge_db=a.edge_db, max_drift_s=a.max_drift)
    except ValueError as e:
        common.die(str(e))
    for p in pieces:
        print(f"{p['file']}  {p['start']:.3f}-{p['end']:.3f}s ({p['duration']:.2f}s)  "
              f"edges={p['start_dbfs']:.1f}/{p['end_dbfs']:.1f} dBFS")


def cmd_trim(a):
    spec = common.Spec(a.spec) if a.spec else None
    audio = Path(a.file) if a.file else (spec.p((spec.data.get("voiceover") or {}).get("file")) if spec else None)
    if not audio or not audio.exists():
        common.die("No audio: pass --file or --spec")
    out = Path(a.out) if a.out else audio.with_name(audio.stem + "_trimmed.wav")
    try:
        res = trim_speech(audio, a.start, a.end, out, threshold_db=a.threshold_db, min_ms=a.min_silence_ms,
                          edge_db=a.edge_db, max_drift_s=a.max_drift)
    except ValueError as e:
        common.die(str(e))
    print(f"{res['file']}  {res['start']:.3f}-{res['end']:.3f}s ({res['duration']:.2f}s)  "
          f"edges={res['start_dbfs']:.1f}/{res['end_dbfs']:.1f} dBFS")


def cmd_normalize(a):
    import assemble

    spec = common.Spec(a.spec) if a.spec else None
    audio = Path(a.file) if a.file else (spec.p((spec.data.get("voiceover") or {}).get("file")) if spec else None)
    if not audio or not audio.exists():
        common.die("No audio: pass --file or --spec")
    mixcfg = (spec.data.get("audio_mix") or {}) if spec else {}
    target = {"lufs": a.lufs if a.lufs is not None else float(mixcfg.get("lufs", -14.0)),
              "true_peak": a.true_peak if a.true_peak is not None else float(mixcfg.get("true_peak", -1.5)),
              "lra": a.lra if a.lra is not None else float(mixcfg.get("lra", 11.0))}
    out = Path(a.out) if a.out else audio.with_name(audio.stem + "_norm.wav")
    res = assemble.normalize_audio(audio, out, target, video=None, label=out.name)
    ln = assemble.loudness(out, target) or {}
    print(f"{out}  path={res['path']}  {ln.get('input_i')} LUFS / {ln.get('input_tp')} dBTP")


def cmd_clone(a):
    common.die("Voice cloning isn't offered through Tokentide (it would keep voice samples upstream for days). "
               "Pick a stock voice (`audio.py voices`) or record a real voice-over and set voiceover.file.", code=2)


# ---------------------------------------------------------------- music & sound effects (queued jobs)
def _gen_body(cfg, kind_label, a, root):
    model = common.resolve_model(root, a.model or cfg.get("model") or f"@{kind_label}")
    prompt = a.prompt or cfg.get("prompt") or common.die(f"{kind_label}: prompt missing")
    entry = _model_entry(root, model, types=("music",))
    body = {"model": model, "prompt": prompt}
    wanted_dur = a.duration if a.duration is not None else cfg.get("duration_seconds")
    default_dur = 30 if kind_label == "music" else 2
    dur = common.audio_duration_for(entry, wanted_dur if wanted_dur is not None else default_dur)
    if dur is not None:
        if wanted_dur is not None and int(round(float(wanted_dur))) != dur:
            common.log(f"[audio] {model}: adjusted duration_seconds {wanted_dur:g} -> {dur}s to fit model_spec")
        body["duration_seconds"] = dur
    elif wanted_dur is not None:
        common.log(f"[audio] {model}: omitting duration_seconds (model does not accept a duration parameter)")
    instrumental = a.instrumental if a.instrumental is not None else cfg.get("force_instrumental", kind_label == "music")
    if kind_label == "music" and instrumental is not None:
        if common.audio_supports_instrumental(entry):
            body["force_instrumental"] = bool(instrumental)
        elif a.instrumental is not None or cfg.get("force_instrumental") is not None:
            common.log(f"[audio] {model}: omitting force_instrumental (supports_force_instrumental=false)")
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
        dur_s = f" {body['duration_seconds']}s" if "duration_seconds" in body else ""
        print(f"{kind_label} {body['model']}{dur_s} -> quote ${q.get('usd')}"
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
    t.add_argument("--voice", help="default spec voiceover.voice, else the model's default voice (or custom voice ID)")
    t.add_argument("--speed", type=float)
    t.add_argument("--format", default="mp3", choices=["mp3", "wav", "aac", "flac", "opus"])
    t.add_argument("--out")
    t.add_argument("--poll-seconds", type=int, default=300, help="queued voice models: how long to wait for the file")
    t.add_argument("--interval", type=float, default=5.0)
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
            x.add_argument("--model", help=f"default {DEFAULT_ASR} (falls back to {FALLBACK_ASR} on private keys)")
            x.add_argument("--language")
    p = sub.add_parser("pace", help="slow a fast VO by lengthening silent pauses only (never time-stretches speech)")
    p.add_argument("--spec")
    p.add_argument("--file", help="input VO audio (default spec voiceover.file)")
    p.add_argument("--words", help="words.json (default spec voiceover.words)")
    p.add_argument("--out", help="output paced WAV (default audio/<vid>_vo_paced.wav)")
    p.add_argument("--words-out", help="shifted words.json (default captions/<vid>_paced_words.json)")
    p.add_argument("--target-wps", type=float, help="target spoken words/s (scales punctuation pause additions)")
    p.add_argument("--pauses", action="store_true", help="apply fixed punctuation pause additions (default without --target-wps)")
    p.add_argument("--sentence-pad", type=float, default=DEFAULT_PAUSES["sentence"], help="seconds added after . ? !")
    p.add_argument("--clause-pad", type=float, default=DEFAULT_PAUSES["clause"], help="seconds added after : ;")
    p.add_argument("--comma-pad", type=float, default=DEFAULT_PAUSES["comma"], help="seconds added after ,")
    p.add_argument("--threshold-db", type=float, default=-60.0, help="silence detection threshold in dBFS")
    p.add_argument("--min-silence-ms", type=float, default=120.0, help="minimum silent run length in ms")
    p.add_argument("--fade-ms", type=float, default=8.0, help="fade length inside silence at each splice")
    p.add_argument("--no-words", action="store_true", help="lengthen all interior silences without words.json")
    sp = sub.add_parser("split", help="split speech snapped to real silences, verifying edges <= -50 dBFS")
    sp.add_argument("--spec")
    sp.add_argument("--file")
    sp.add_argument("--cuts", required=True, help="comma-separated cut times in seconds")
    sp.add_argument("--out-dir")
    sp.add_argument("--threshold-db", type=float, default=-60.0)
    sp.add_argument("--min-silence-ms", type=float, default=120.0)
    sp.add_argument("--edge-db", type=float, default=-50.0)
    sp.add_argument("--max-drift", type=float, default=0.5)
    tr = sub.add_parser("trim", help="trim speech snapped to real silences, verifying edges <= -50 dBFS")
    tr.add_argument("--spec")
    tr.add_argument("--file")
    tr.add_argument("--start", type=float)
    tr.add_argument("--end", type=float)
    tr.add_argument("--out")
    tr.add_argument("--threshold-db", type=float, default=-60.0)
    tr.add_argument("--min-silence-ms", type=float, default=120.0)
    tr.add_argument("--edge-db", type=float, default=-50.0)
    tr.add_argument("--max-drift", type=float, default=0.5)
    nm = sub.add_parser("normalize", help="loudness-normalize a voice/audio file without dynamic breathing")
    nm.add_argument("--spec")
    nm.add_argument("--file")
    nm.add_argument("--out")
    nm.add_argument("--lufs", type=float)
    nm.add_argument("--true-peak", type=float)
    nm.add_argument("--lra", type=float)
    for name in ("music", "sfx"):
        g = sub.add_parser(name)
        g.add_argument("--spec", help="uses music.generate / sfx[].generate and writes the files back into the spec")
        g.add_argument("--model", help=f"default @{name} (models.py choose {name}=<id>)")
        g.add_argument("--prompt")
        g.add_argument("--duration", type=float, help="seconds (clamped/omitted per model_spec)")
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
    {"tts": cmd_tts, "voices": cmd_voices, "transcribe": cmd_transcribe, "align": cmd_align, "pace": cmd_pace,
     "split": cmd_split, "trim": cmd_trim, "normalize": cmd_normalize, "clone": cmd_clone,
     "music": cmd_music, "sfx": cmd_sfx}[a.cmd](a)


if __name__ == "__main__":
    try:
        main()
    except api.APIError as e:
        common.die(str(e))
