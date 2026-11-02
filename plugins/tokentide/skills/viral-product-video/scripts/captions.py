#!/usr/bin/env python3
"""Build burned-in captions (ASS) + an SRT from word timings, plus hook/label text overlays.

Most short-form views start muted, so captions carry the message. Styles:
  highlight  2-4 word chunks, the spoken word pops in the highlight color (default)
  karaoke    chunk fills with the highlight color as words are spoken
  single     one big word at a time, centered
  plain      chunk text, no highlight

Spec mode:  captions.py --spec briefs/v01.json
  reads voiceover.words (words.json), captions{...}, overlays[type=text]; writes captions/<vid>.ass + .srt
Text overlays: {"type":"text","style":"hook|label|title","text":"...","start":0,"end":2.5,
                "position":"top|upper|middle|lower|top-left"}
Positions keep text inside the 1080x1920 safe area (top 250px, bottom 650px and right 150px stay clear).
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import common

DEFAULTS = {"style": "highlight", "font": "Anton", "size": 104, "primary": "#FFFFFF", "highlight": "#FFE14D",
            "outline_color": "#000000", "outline": 6, "shadow": 2, "words_per_chunk": 3, "max_chars": 16,
            "position": "lower", "uppercase": True, "keep_punct": False, "hook_font": None, "hook_size": 84}
POS = {  # alignment, margin_v
    "top": (8, 340), "upper": (8, 560), "middle": (5, 0), "lower": (2, 680), "bottom": (2, 660),
    "top-left": (7, 262), "top-right": (9, 262),
}
EMOJI = re.compile("[\U0001F000-\U0001FFFF☀-➿️‍]+")


def clean(text: str, upper: bool, keep_punct: bool) -> str:
    t = EMOJI.sub("", text).replace("\\", "/").replace("{", "(").replace("}", ")").strip()
    if not keep_punct:
        t = re.sub(r"[.,;:]+$", "", t)
    return t.upper() if upper else t


def chunk_words(words, wpc, max_chars, gap_break=0.45):
    chunks, cur = [], []
    for w in words:
        if cur:
            joined = len(" ".join(x["w"] for x in cur + [w]))
            if len(cur) >= wpc or joined > max_chars or w["s"] - cur[-1]["e"] > gap_break:
                chunks.append(cur)
                cur = []
        cur.append(w)
        if re.search(r"[.!?;:]$", w["w"]) or (w["w"].endswith(",") and len(cur) >= 2):
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    return chunks


def header(c) -> str:
    font = c["font"]
    hook_font = c.get("hook_font") or font
    prim, hl = common.ass_color(c["primary"]), common.ass_color(c["highlight"])
    oc = common.ass_color(c["outline_color"])
    shadow = common.ass_color("#000000", 0x80)
    box = common.ass_color("#000000", 0x55)
    al, mv = POS.get(c["position"], POS["lower"])
    big = int(c["size"] * 1.35)
    fmt = ("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
           "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
           "MarginL, MarginR, MarginV, Encoding")
    styles = [
        f"Style: Caption,{font},{c['size']},{prim},{prim},{oc},{shadow},-1,0,0,0,100,100,0,0,1,{c['outline']},{c['shadow']},{al},90,150,{mv},1",
        f"Style: Karaoke,{font},{c['size']},{hl},{prim},{oc},{shadow},-1,0,0,0,100,100,0,0,1,{c['outline']},{c['shadow']},{al},90,150,{mv},1",
        f"Style: Single,{font},{big},{prim},{prim},{oc},{shadow},-1,0,0,0,100,100,0,0,1,{c['outline'] + 2},{c['shadow']},5,90,150,0,1",
        f"Style: Hook,{hook_font},{c['hook_size']},{prim},{prim},{box},{shadow},-1,0,0,0,100,100,0,0,3,16,0,8,90,150,340,1",
        f"Style: Label,{hook_font},42,{prim},{prim},{box},{shadow},-1,0,0,0,100,100,0,0,3,8,0,7,60,150,262,1",
        f"Style: Title,{hook_font},112,{prim},{prim},{box},{shadow},-1,0,0,0,100,100,0,0,3,22,0,5,90,150,0,1",
    ]
    return ("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 0\n"
            "ScaledBorderAndShadow: yes\nYCbCr Matrix: TV.709\n\n[V4+ Styles]\n" + fmt + "\n" + "\n".join(styles) +
            "\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")


def dialogue(s, e, style, text, layer=0, ml=0, mr=0, mv=0) -> str:
    return f"Dialogue: {layer},{common.ass_time(s)},{common.ass_time(e)},{style},,{ml},{mr},{mv},,{text}"


def caption_events(words, c):
    ev, srt = [], []
    if not words:
        return ev, srt
    up, kp = c["uppercase"], c["keep_punct"]
    hl = common.ass_bgr(c["highlight"])
    style = c["style"]
    if style == "single":
        for i, w in enumerate(words):
            e = words[i + 1]["s"] if i + 1 < len(words) and words[i + 1]["s"] - w["e"] < 0.35 else w["e"] + 0.15
            ev.append(dialogue(w["s"], max(e, w["s"] + 0.08), "Single",
                               "{\\fscx115\\fscy115\\t(0,90,\\fscx100\\fscy100)}" + clean(w["w"], up, kp)))
            srt.append((w["s"], e, clean(w["w"], False, True)))
        return ev, srt
    chunks = chunk_words(words, int(c["words_per_chunk"]), int(c["max_chars"]))
    for ci, ch in enumerate(chunks):
        start = ch[0]["s"]
        nxt = chunks[ci + 1][0]["s"] if ci + 1 < len(chunks) else None
        end = ch[-1]["e"] + 0.25
        if nxt is not None:
            end = nxt if nxt - ch[-1]["e"] < 0.35 else min(end, nxt)
        toks = [clean(w["w"], up, kp) for w in ch]
        srt.append((start, end, " ".join(clean(w["w"], False, True) for w in ch)))
        if style == "plain":
            ev.append(dialogue(start, end, "Caption", " ".join(toks)))
        elif style == "karaoke":
            parts, t = [], start
            for i, w in enumerate(ch):
                nxt_s = ch[i + 1]["s"] if i + 1 < len(ch) else ch[-1]["e"]
                k = max(1, int(round((nxt_s - t) * 100)))
                parts.append(f"{{\\k{k}}}{toks[i]}")
                t = nxt_s
            ev.append(dialogue(start, end, "Karaoke", " ".join(parts)))
        else:  # highlight: one event per word, active word recolored + pop
            for i, w in enumerate(ch):
                s = start if i == 0 else w["s"]
                e = ch[i + 1]["s"] if i + 1 < len(ch) else end
                line = " ".join(
                    (f"{{\\c{hl}\\fscx112\\fscy112\\t(0,90,\\fscx100\\fscy100)}}{tok}{{\\r}}" if k == i else tok)
                    for k, tok in enumerate(toks))
                ev.append(dialogue(s, max(e, s + 0.05), "Caption", line))
    return ev, srt


def overlay_events(overlays, c):
    ev = []
    for ov in overlays or []:
        if ov.get("type") != "text" or not ov.get("text"):
            continue
        style = {"hook": "Hook", "label": "Label", "title": "Title"}.get(ov.get("style", "hook"), "Hook")
        default_pos = {"Hook": "top", "Label": "top-left", "Title": "middle"}[style]
        al, mv = POS.get(ov.get("position", default_pos), POS[default_pos])
        fi, fo = int(ov.get("fade_in", 80)), int(ov.get("fade_out", 120))
        text = clean(ov["text"], ov.get("uppercase", False), True).replace("\n", "\\N")
        layer = 2 if style == "Label" else 1  # separate layers: libass never shifts one to avoid the other
        ev.append(dialogue(float(ov.get("start", 0)), float(ov.get("end", 2.5)), style,
                           f"{{\\an{al}\\fad({fi},{fo})}}{text}", layer=layer, mv=mv))
    return ev


def build(words, cfg, overlays, out_ass: Path, out_srt: Path | None):
    c = {**DEFAULTS, **{k: v for k, v in (cfg or {}).items() if v is not None}}
    if not (common.FONTS_DIR / f"{c['font']}-Regular.ttf").exists() and not list(common.FONTS_DIR.glob(f"{c['font'].split()[0]}*")):
        common.log(f"note: font '{c['font']}' not bundled; libass will fall back unless it's installed system-wide")
    ev, srt = caption_events(words, c) if c.get("enabled", True) else ([], [])
    ev += overlay_events(overlays, c)
    out_ass.parent.mkdir(parents=True, exist_ok=True)
    out_ass.write_text(header(c) + "\n".join(ev) + "\n", encoding="utf-8")
    if out_srt and srt:
        out_srt.write_text("\n".join(f"{i}\n{common.srt_time(s)} --> {common.srt_time(e)}\n{t}\n"
                                     for i, (s, e, t) in enumerate(srt, 1)), encoding="utf-8")
    return len(ev), len(srt)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec")
    ap.add_argument("--words", help="words.json (default spec voiceover.words)")
    ap.add_argument("--out", help="output .ass (default captions/<vid>.ass)")
    ap.add_argument("--srt", help="output .srt (default next to .ass)")
    for k, v in DEFAULTS.items():
        if isinstance(v, bool):
            ap.add_argument("--" + k.replace("_", "-"), type=lambda s: s.lower() in ("1", "true", "yes"), default=None)
        else:
            ap.add_argument("--" + k.replace("_", "-"), type=type(v) if v is not None else str, default=None)
    ap.add_argument("--hook", help="hook text overlay (non-spec mode)")
    ap.add_argument("--hook-end", type=float, default=2.5)
    a = ap.parse_args()

    spec = common.Spec(a.spec) if a.spec else None
    cfg = dict((spec.data.get("captions") or {}) if spec else {})
    cfg.update({k: getattr(a, k) for k in DEFAULTS if getattr(a, k) is not None})
    overlays = list((spec.data.get("overlays") or []) if spec else [])
    if a.hook:
        overlays.append({"type": "text", "style": "hook", "text": a.hook, "start": 0, "end": a.hook_end})
    words_path = Path(a.words) if a.words else (spec.p((spec.data.get("voiceover") or {}).get("words")) if spec else None)
    words = []
    if words_path and Path(words_path).exists():
        words = common.load_json(words_path).get("words", [])
    elif cfg.get("enabled", True) and (spec is None or (spec.data.get("voiceover") or {}).get("enabled", True)):
        common.log("note: no words.json found -> only text overlays will be rendered "
                   "(run audio.py transcribe/align first for spoken captions)")
    out = Path(a.out) if a.out else (spec.root / "captions" / f"{spec.vid}.ass" if spec else Path("captions.ass"))
    srt = Path(a.srt) if a.srt else out.with_suffix(".srt")
    n_ev, n_srt = build(words, cfg, overlays, out, srt)
    print(f"{out}  ({n_ev} events)" + (f"  + {srt} ({n_srt} cues)" if n_srt else ""))
    if spec:
        spec.reload()
        spec.data.setdefault("captions", {})["file"] = spec.rel(out)
        if n_srt:
            spec.data["captions"]["srt"] = spec.rel(srt)
        spec.save()


if __name__ == "__main__":
    main()
