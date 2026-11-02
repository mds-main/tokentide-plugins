"""Shared helpers for the viral-product-video scripts (Python stdlib only).

Paths inside a video spec are relative to the project root (the folder holding
project.json), so specs stay portable.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
FONTS_DIR = SKILL_DIR / "assets" / "fonts"
TEMPLATES_DIR = SKILL_DIR / "templates"

W, H, FPS = 1080, 1920, 30  # vertical master for TikTok, Reels and X


# ---------------------------------------------------------------- basics
def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def die(msg: str, code: int = 1):
    print(f"ERROR: {msg}", file=sys.stderr, flush=True)
    sys.exit(code)


def now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def load_json(path, default=None):
    p = Path(path)
    if not p.exists():
        if default is not None:
            return default
        die(f"File not found: {p}")
    with open(p, encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError as e:
            die(f"Invalid JSON in {p}: {e}")


def save_json(path, data) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, p)


def slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return s[:60] or "project"


def kv_pairs(pairs) -> dict:
    """Parse repeated --set key=value flags; values are JSON when possible."""
    out = {}
    for p in pairs or []:
        if "=" not in p:
            die(f"--set expects key=value, got: {p}")
        k, v = p.split("=", 1)
        try:
            out[k.strip()] = json.loads(v)
        except json.JSONDecodeError:
            out[k.strip()] = v
    return out


# ---------------------------------------------------------------- projects
def find_project_root(start) -> Path | None:
    p = Path(start).resolve()
    if p.is_file() or not p.exists():
        p = p.parent
    for d in [p, *p.parents]:
        if (d / "project.json").is_file():
            return d
    return None


class Spec:
    """A video spec (briefs/vNN.json). Relative paths resolve against the project root."""

    def __init__(self, path):
        self.path = Path(path).resolve()
        self.data = load_json(self.path)
        self.root = find_project_root(self.path) or self.path.parent

    @property
    def vid(self) -> str:
        return str(self.data.get("id") or self.path.stem)

    def p(self, rel):
        if not rel:
            return None
        rel = str(rel)
        if rel.startswith(("http://", "https://", "data:")):
            return rel
        rp = Path(rel).expanduser()
        return rp if rp.is_absolute() else (self.root / rp)

    def rel(self, path) -> str:
        try:
            return str(Path(path).resolve().relative_to(self.root))
        except ValueError:
            return str(Path(path).resolve())

    def shots(self, ids=None):
        shots = [s for s in self.data.get("shots", []) if not s.get("skip")]
        if ids:
            wanted = [i.strip() for i in ids.split(",") if i.strip()]
            missing = [i for i in wanted if i not in {s.get("id") for s in shots}]
            if missing:
                die(f"Shot(s) not found in {self.path.name}: {', '.join(missing)}")
            shots = [s for s in shots if s.get("id") in wanted]
        return shots

    def shot(self, sid):
        for s in self.data.get("shots", []):
            if s.get("id") == sid:
                return s
        die(f"Shot '{sid}' not found in {self.path.name}")

    def reload(self):
        self.data = load_json(self.path)

    def save(self):
        save_json(self.path, self.data)


def project_meta(root) -> dict:
    return load_json(Path(root) / "project.json", default={}) if root else {}


def resolve_model(root, model):
    """'@i2v' -> the model the user chose for that job (project.json "models"); plain ids pass through."""
    if not model or not str(model).startswith("@"):
        return model
    alias = str(model)[1:]
    picks = project_meta(root).get("models", {}) if root else {}
    if picks.get(alias):
        return picks[alias]
    die(f"Model alias '{model}' is not set for this project. Run `models.py recommend --project <P>`, let the user "
        f"pick from the options, then `models.py choose --project <P> {alias}=<model_id>`.")


def ledger_append(root, entry: dict) -> None:
    if not root:
        return
    p = Path(root) / "logs" / "ledger.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": now_iso(), **entry}, ensure_ascii=False) + "\n")


def ledger_entries(root) -> list:
    p = Path(root) / "logs" / "ledger.jsonl"
    if not p.is_file():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out


def spent_usd(root) -> float:
    """Quoted video spend + estimated image spend (estimates come from cached model pricing)."""
    return round(sum(float(e.get("usd") or e.get("usd_est") or 0) for e in ledger_entries(root)), 4)


# ---------------------------------------------------------------- models cache
def load_models(root=None, path=None) -> dict:
    cands = [Path(path)] if path else []
    if root:
        cands.append(Path(root) / "models.json")
    for c in cands:
        if c.is_file():
            j = load_json(c)
            items = j.get("data", []) if isinstance(j, dict) else j
            return {m["id"]: m for m in items if isinstance(m, dict) and m.get("id")}
    return {}


def flatten(d, prefix="") -> dict:
    out = {}
    if isinstance(d, dict):
        for k, v in d.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(v, dict):
                out.update(flatten(v, key))
            else:
                out[key] = v
    return out


def spec_lookup(entry, *needles) -> dict:
    """{flat_key: value} for model_spec keys containing any needle (case/underscore-insensitive)."""
    flat = flatten((entry or {}).get("model_spec", entry or {}))
    norm = [n.lower().replace("_", "") for n in needles]
    return {k: v for k, v in flat.items() if any(n in k.lower().replace("_", "") for n in norm)}


# ---------------------------------------------------------------- ffmpeg
def ffmpeg_bin():
    b = os.environ.get("FFMPEG_BIN") or shutil.which("ffmpeg")
    if not b:
        try:
            import imageio_ffmpeg  # type: ignore

            b = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            b = None
    return b


def ffprobe_bin():
    return os.environ.get("FFPROBE_BIN") or shutil.which("ffprobe")


def require_ffmpeg() -> str:
    b = ffmpeg_bin()
    if not b:
        die("ffmpeg not found. Install it (apt-get install -y ffmpeg | brew install ffmpeg | "
            "pip install imageio-ffmpeg) or set FFMPEG_BIN. Then run scripts/doctor.py.")
    return b


def ffmpeg(args, *, check=True, loglevel="error", cwd=None):
    cmd = [require_ffmpeg(), "-hide_banner", "-nostdin", "-loglevel", loglevel, *[str(a) for a in args]]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                         encoding="utf-8", errors="replace", cwd=cwd)
    if check and res.returncode != 0:
        die(f"ffmpeg failed (exit {res.returncode}).\nCommand: {' '.join(cmd)[:1800]}\n{(res.stderr or '')[-2500:]}")
    return res


def _f(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _rate(r):
    if not r or r in ("0/0", "N/A"):
        return None
    if "/" in r:
        a, b = r.split("/", 1)
        return round(_f(a) / _f(b), 3) if _f(b) else None
    return _f(r) or None


def probe(path) -> dict:
    """Duration, size, fps, codecs and audio presence for a media file (ffprobe, fallback ffmpeg -i)."""
    path = str(path)
    if not os.path.exists(path):
        die(f"Media not found: {path}")
    info = {"path": path, "duration": 0.0, "width": None, "height": None, "fps": None, "vcodec": None,
            "pix_fmt": None, "has_audio": False, "acodec": None, "sample_rate": None, "channels": None,
            "bit_rate": None, "size_bytes": os.path.getsize(path)}
    fp = ffprobe_bin()
    if fp:
        res = subprocess.run([fp, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
                             capture_output=True, text=True, encoding="utf-8", errors="replace")
        if res.returncode != 0:
            die(f"ffprobe failed on {path}: {res.stderr.strip()[:500]}")
        j = json.loads(res.stdout or "{}")
        fmt = j.get("format", {})
        info["duration"] = _f(fmt.get("duration"))
        info["bit_rate"] = int(_f(fmt.get("bit_rate"))) or None
        for s in j.get("streams", []):
            if s.get("codec_type") == "video" and info["width"] is None:
                if (s.get("disposition") or {}).get("attached_pic"):
                    continue
                info.update(width=s.get("width"), height=s.get("height"), vcodec=s.get("codec_name"),
                            pix_fmt=s.get("pix_fmt"))
                info["fps"] = _rate(s.get("avg_frame_rate")) or _rate(s.get("r_frame_rate"))
                info["duration"] = info["duration"] or _f(s.get("duration"))
            elif s.get("codec_type") == "audio" and not info["has_audio"]:
                info.update(has_audio=True, acodec=s.get("codec_name"), sample_rate=int(_f(s.get("sample_rate"))) or None,
                            channels=s.get("channels"))
                info["duration"] = info["duration"] or _f(s.get("duration"))
        return info
    err = subprocess.run([require_ffmpeg(), "-hide_banner", "-i", path], capture_output=True, text=True,
                         encoding="utf-8", errors="replace").stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
    if m:
        info["duration"] = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
    m = re.search(r"Video: (\w+).*?, (\d{2,5})x(\d{2,5})", err)
    if m:
        info.update(vcodec=m[1], width=int(m[2]), height=int(m[3]))
    m = re.search(r"([\d.]+) fps", err)
    if m:
        info["fps"] = float(m[1])
    m = re.search(r"Audio: (\w+), (\d+) Hz", err)
    if m:
        info.update(has_audio=True, acodec=m[1], sample_rate=int(m[2]))
    return info


_FILTERS = None


def has_filter(name: str) -> bool:
    global _FILTERS
    if _FILTERS is None:
        res = subprocess.run([require_ffmpeg(), "-hide_banner", "-filters"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace")
        _FILTERS = {line.split()[1] for line in res.stdout.splitlines() if len(line.split()) > 2}
    return name in _FILTERS


# ---------------------------------------------------------------- subtitles
def ass_time(t: float) -> str:
    cs = int(round(max(0.0, t) * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def srt_time(t: float) -> str:
    ms = int(round(max(0.0, t) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _hex(c: str) -> str:
    h = (c or "#FFFFFF").lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    if not re.fullmatch(r"[0-9a-fA-F]{6}", h):
        die(f"Bad color '{c}' (use #RRGGBB)")
    return h.upper()


def ass_color(c: str, alpha: int = 0) -> str:
    """#RRGGBB -> &HAABBGGRR (alpha 0 = opaque, 255 = transparent)."""
    h = _hex(c)
    return f"&H{alpha:02X}{h[4:6]}{h[2:4]}{h[0:2]}"


def ass_bgr(c: str) -> str:
    """#RRGGBB -> &HBBGGRR& for inline \\c overrides."""
    h = _hex(c)
    return f"&H{h[4:6]}{h[2:4]}{h[0:2]}&"
