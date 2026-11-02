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
FONTS_DIR = SKILL_DIR / "assets" / "fonts"   # bundled fonts (SIL OFL)
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


# ---------------------------------------------------------------- fonts
FONT_GLOBS = ("*.ttf", "*.otf", "*.TTF", "*.OTF")


def font_dirs(root=None) -> list:
    """Folders whose fonts captions and overlays can use, first match wins: the project's brand fonts
    (P/assets/fonts/, then font files in P/assets/brand/), then the bundled fonts."""
    dirs = []
    if root:
        dirs += [Path(root) / "assets" / "fonts", Path(root) / "assets" / "brand"]
    dirs.append(FONTS_DIR)
    return [d for d in dirs if d.is_dir()]


def font_files(root=None) -> list:
    seen, out = set(), []
    for d in font_dirs(root):
        for g in FONT_GLOBS:
            for f in sorted(d.glob(g)):
                if f.name.lower() not in seen:
                    seen.add(f.name.lower())
                    out.append(f)
    return out


def font_available(name: str, root=None) -> bool:
    """True when a font file plausibly holds the family `name` (file names like Anton-Regular.ttf or
    MontserratExtraBold.otf). libass matches the family name inside the file, so this is a hint."""
    want = re.sub(r"[^a-z0-9]", "", (name or "").lower())
    first = re.sub(r"[^a-z0-9]", "", (name or "").split()[0].lower()) if (name or "").split() else ""
    for f in font_files(root):
        stem = re.sub(r"[^a-z0-9]", "", f.stem.lower())
        if want and (stem.startswith(want) or (first and stem.startswith(first))):
            return True
    return False


# ---------------------------------------------------------------- TLS
_SSL_CTX = None


def ssl_context():
    """A verifying TLS context that also works on fresh machines: python.org's macOS builds ship without
    CA certificates until "Install Certificates" runs, so fall back to the system bundle (macOS keeps one
    at /etc/ssl/cert.pem) or certifi. Verification is never turned off."""
    global _SSL_CTX
    if _SSL_CTX is not None:
        return _SSL_CTX
    import ssl

    ctx = ssl.create_default_context()
    paths = ssl.get_default_verify_paths()
    has_default = any(x and os.path.exists(x) for x in (os.environ.get("SSL_CERT_FILE"), os.environ.get("SSL_CERT_DIR"),
                                                       paths.cafile, paths.capath))
    if not has_default and sys.platform != "win32":
        bundles = ["/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt", "/etc/pki/tls/certs/ca-bundle.crt"]
        try:
            import certifi  # type: ignore

            bundles.append(certifi.where())
        except Exception:
            pass
        for b in bundles:
            if os.path.isfile(b):
                ctx.load_verify_locations(cafile=b)
                break
    _SSL_CTX = ctx
    return ctx


def urlopen(req, timeout=60):
    import urllib.request

    return urllib.request.urlopen(req, timeout=timeout, context=ssl_context())


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
def tools_dir() -> Path:
    """Where `doctor.py --fix` installs the pinned FFmpeg: TOKENTIDE_TOOLS_DIR, else the user's cache folder."""
    if os.environ.get("TOKENTIDE_TOOLS_DIR"):
        return Path(os.environ["TOKENTIDE_TOOLS_DIR"]).expanduser()
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "tokentide" / "tools"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "tokentide" / "tools"
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "tokentide" / "tools"


def managed_ffmpeg() -> str | None:
    """The FFmpeg that `doctor.py --fix` installed (checksum-verified at install time), if any."""
    meta = tools_dir() / "ffmpeg.json"
    try:
        path = json.loads(meta.read_text(encoding="utf-8")).get("path")
    except (OSError, ValueError, AttributeError):
        return None
    return path if path and os.path.isfile(path) and os.access(path, os.X_OK) else None


def ffmpeg_bin():
    """FFMPEG_BIN, then the plugin-managed FFmpeg, then ffmpeg on PATH, then imageio-ffmpeg's."""
    b = os.environ.get("FFMPEG_BIN") or managed_ffmpeg() or shutil.which("ffmpeg")
    if not b:
        try:
            import imageio_ffmpeg  # type: ignore

            b = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            b = None
    return b


def ffprobe_bin():
    """FFPROBE_BIN, then the ffprobe next to the chosen ffmpeg, then ffprobe on PATH. The plugin-managed
    FFmpeg ships without one: without any ffprobe, probe() reads `ffmpeg -i` instead."""
    if os.environ.get("FFPROBE_BIN"):
        return os.environ["FFPROBE_BIN"]
    fb = ffmpeg_bin()
    if fb:
        sib = Path(fb).with_name("ffprobe" + (".exe" if fb.lower().endswith(".exe") else ""))
        if sib.is_file():
            return str(sib)
    return shutil.which("ffprobe")


def require_ffmpeg() -> str:
    b = ffmpeg_bin()
    if not b:
        die("ffmpeg not found. Agent: run `python3 " + str(Path(__file__).resolve().parent / "doctor.py") + " --fix` "
            "(installs a pinned, checksum-verified FFmpeg for the plugin; no admin rights, nothing for the user to do), "
            "or set FFMPEG_BIN to an ffmpeg built with libass.")
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


_LAYOUT_CHANNELS = {"mono": 1, "stereo": 2, "2.1": 3, "quad": 4, "4.0": 4, "5.0": 5, "5.1": 6, "5.1(side)": 6,
                    "6.1": 7, "7.1": 8}


def _split_top(s: str) -> list:
    """Split an ffmpeg stream description on commas outside parentheses/brackets."""
    out, depth, cur = [], 0, ""
    for ch in s:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def parse_ffmpeg_info(text: str, info: dict | None = None) -> dict:
    """The fields of probe() from `ffmpeg -i` output, for machines without ffprobe. Skips cover art
    (attached pictures) and reads codecs like "aac (LC) (mp4a / 0x6134706D)" by their first word."""
    info = dict(info or {})
    info.setdefault("duration", 0.0)
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", text)
    if m:
        info["duration"] = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
    m = re.search(r"Duration: .*?bitrate: (\d+) kb/s", text)
    if m:
        info["bit_rate"] = int(m[1]) * 1000
    for line in text.splitlines():
        sm = re.search(r"Stream #\S+.*?: (Video|Audio): (.*)$", line)
        if not sm:
            continue
        kind, parts = sm[1], _split_top(sm[2])
        cm = re.match(r"([\w-]+)", parts[0]) if parts else None
        codec = cm[1] if cm else None
        if kind == "Video":
            if "attached pic" in line or info.get("width"):
                continue
            info["vcodec"] = codec
            for i, part in enumerate(parts[1:], 1):
                size = re.match(r"(\d{2,5})x(\d{2,5})\b", part)
                fps = re.match(r"([\d.]+) fps\b", part)
                if size:
                    info["width"], info["height"] = int(size[1]), int(size[2])
                elif fps:
                    info["fps"] = float(fps[1])
                elif i == 1:
                    pf = re.match(r"([a-z][a-z0-9_]*)(?:\(|$)", part)
                    info["pix_fmt"] = pf[1] if pf else None
            if not info.get("fps"):
                tbr = re.search(r"([\d.]+) tbr", sm[2])
                info["fps"] = float(tbr[1]) if tbr else None
        elif kind == "Audio" and not info.get("has_audio"):
            info.update(has_audio=True, acodec=codec)
            for part in parts[1:]:
                hz = re.match(r"(\d+) Hz\b", part)
                n = re.match(r"(\d+) channels\b", part)
                if hz:
                    info["sample_rate"] = int(hz[1])
                elif n:
                    info["channels"] = int(n[1])
                elif part in _LAYOUT_CHANNELS and not info.get("channels"):
                    info["channels"] = _LAYOUT_CHANNELS[part]
    return info


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
    err = subprocess.run([require_ffmpeg(), "-hide_banner", "-nostdin", "-i", path], capture_output=True, text=True,
                         encoding="utf-8", errors="replace").stderr
    return parse_ffmpeg_info(err, info)


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
