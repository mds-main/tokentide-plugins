"""Installs a pinned, checksum-verified static FFmpeg for the plugin (used by `doctor.py --fix`; stdlib only).

The builds come from the imageio-ffmpeg 0.6.0 wheels on PyPI: static FFmpeg 7 builds with libx264, libass,
freetype, fontconfig and fribidi, for macOS (Intel, Apple silicon), Linux (x86_64, aarch64) and Windows
(x86_64, which Windows on Arm runs too). Both the wheel and the binary inside it are checked against the
SHA-256 values below before anything is written; nothing needs admin rights. The binary goes to the
plugin's tools folder (common.tools_dir()), where common.ffmpeg_bin() finds it. These wheels ship no
ffprobe: common.probe() reads `ffmpeg -i` instead.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import common

VERSION = "imageio-ffmpeg-0.6.0"
_PYPI = "https://files.pythonhosted.org/packages"
PINS = {
    ("darwin", "x86_64"): {
        "url": f"{_PYPI}/da/58/87ef68ac83f4c7690961bce288fd8e382bc5f1513860fc7f90a9c1c1c6bf/"
               "imageio_ffmpeg-0.6.0-py3-none-macosx_10_9_intel.macosx_10_9_x86_64.whl",
        "sha256": "9d2baaf867088508d4a3458e61eeb30e945c4ad8016025545f66c4b5aaef0a61",
        "member": "imageio_ffmpeg/binaries/ffmpeg-macos-x86_64-v7.1",
        "member_sha256": "4a4a968b98859588e98500ae25973d80a5ca5eed0724222b9f76360dcb72a001",
    },
    ("darwin", "arm64"): {
        "url": f"{_PYPI}/40/5c/f3d8a657d362cc93b81aab8feda487317da5b5d31c0e1fdfd5e986e55d17/"
               "imageio_ffmpeg-0.6.0-py3-none-macosx_11_0_arm64.whl",
        "sha256": "b1ae3173414b5fc5f538a726c4e48ea97edc0d2cdc11f103afee655c463fa742",
        "member": "imageio_ffmpeg/binaries/ffmpeg-macos-aarch64-v7.1",
        "member_sha256": "6d175a4743ca50256e89a8cdd731100f9cee33bd79aeea46894d209410dc6617",
    },
    ("linux", "x86_64"): {
        "url": f"{_PYPI}/a0/2d/43c8522a2038e9d0e7dbdf3a61195ecc31ca576fb1527a528c877e87d973/"
               "imageio_ffmpeg-0.6.0-py3-none-manylinux2014_x86_64.whl",
        "sha256": "c7e46fcec401dd990405049d2e2f475e2b397779df2519b544b8aab515195282",
        "member": "imageio_ffmpeg/binaries/ffmpeg-linux-x86_64-v7.0.2",
        "member_sha256": "e7e7fb30477f717e6f55f9180a70386c62677ef8a4d4d1a5d948f4098aa3eb99",
    },
    ("linux", "aarch64"): {
        "url": f"{_PYPI}/33/e7/1925bfbc563c39c1d2e82501d8372734a5c725e53ac3b31b4c2d081e895b/"
               "imageio_ffmpeg-0.6.0-py3-none-manylinux2014_aarch64.whl",
        "sha256": "1d47bebd83d2c5fc770720d211855f208af8a596c82d17730aa51e815cdee6dc",
        "member": "imageio_ffmpeg/binaries/ffmpeg-linux-aarch64-v7.0.2",
        "member_sha256": "6bb182d0d75d23028db82e9e4f723ca69b853d055698486e6984ddb2c06fb8ce",
    },
    ("win32", "x86_64"): {
        "url": f"{_PYPI}/2c/c6/fa760e12a2483469e2bf5058c5faff664acf66cadb4df2ad6205b016a73d/"
               "imageio_ffmpeg-0.6.0-py3-none-win_amd64.whl",
        "sha256": "02fa47c83703c37df6bfe4896aab339013f62bf02c5ebf2dce6da56af04ffc0a",
        "member": "imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe",
        "member_sha256": "2ce797a0f88d7f067180338fb227f7b1928ea727bd9a4d7a1d022f7c52af71a3",
    },
}
MAX_DOWNLOAD = 120_000_000


def platform_key():
    """(os, arch) of this machine as PINS keys it, or None when no pinned build fits."""
    osname = "win32" if sys.platform == "win32" else "darwin" if sys.platform == "darwin" else \
        "linux" if sys.platform.startswith("linux") else sys.platform
    m = platform.machine().lower()
    arch = {"amd64": "x86_64", "x64": "x86_64", "x86_64": "x86_64", "arm64": "arm64", "aarch64": "aarch64"}.get(m, m)
    if osname == "darwin" and arch == "aarch64":
        arch = "arm64"
    if osname == "linux" and arch == "arm64":
        arch = "aarch64"
    if osname == "win32" and arch == "arm64":
        arch = "x86_64"  # Windows on Arm runs x64 programs
    key = (osname, arch)
    return key if key in PINS else None


def _download(url: str) -> bytes:
    """The bytes at url, over verified TLS. Falls back to curl (it uses the system's certificates, e.g. on a
    Mac whose Python has none). Integrity comes from the SHA-256 check, not from the transport."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "tokentide-video-skill/1.2 (doctor --fix)"})
        with common.urlopen(req, timeout=300) as r:
            data = r.read(MAX_DOWNLOAD + 1)
        if len(data) > MAX_DOWNLOAD:
            raise RuntimeError("download larger than expected")
        return data
    except (urllib.error.URLError, OSError, RuntimeError) as e:
        curl = shutil.which("curl")
        if not curl:
            raise RuntimeError(f"download failed: {e}") from None
        common.log(f"note: Python download failed ({e}); retrying with curl")
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "ffmpeg.whl"
            res = subprocess.run([curl, "-fsSL", "--proto", "=https", "--max-filesize", str(MAX_DOWNLOAD), "-o",
                                  str(out), url], capture_output=True, text=True)
            if res.returncode != 0:
                raise RuntimeError(f"download failed: {e}; curl: {res.stderr.strip()[:300]}") from None
            return out.read_bytes()


def install(force: bool = False, wheel: str | None = None) -> str:
    """Installs the pinned FFmpeg (or reuses a verified install) and returns its path. `wheel` installs from a
    local copy of the pinned wheel (offline machines); it is verified the same way."""
    key = platform_key()
    if not key:
        raise RuntimeError(f"no pinned FFmpeg build for {sys.platform}/{platform.machine()}; install FFmpeg with "
                           "libass yourself (e.g. apt-get install -y ffmpeg) or set FFMPEG_BIN")
    pin = PINS[key]
    root = common.tools_dir()
    dest = root / VERSION / ("ffmpeg.exe" if key[0] == "win32" else "ffmpeg")
    meta = root / "ffmpeg.json"
    if dest.is_file() and not force and hashlib.sha256(dest.read_bytes()).hexdigest() == pin["member_sha256"]:
        common.save_json(meta, {"path": str(dest), "version": VERSION, "sha256": pin["member_sha256"]})
        return str(dest)
    data = Path(wheel).read_bytes() if wheel else _download(pin["url"])
    got = hashlib.sha256(data).hexdigest()
    if got != pin["sha256"]:
        raise RuntimeError(f"checksum mismatch for the FFmpeg download (got {got[:16]}…, expected "
                           f"{pin['sha256'][:16]}…); nothing was installed")
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        binary = z.read(pin["member"])
    if hashlib.sha256(binary).hexdigest() != pin["member_sha256"]:
        raise RuntimeError("checksum mismatch for the FFmpeg binary inside the wheel; nothing was installed")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.write_bytes(binary)
    if key[0] != "win32":
        os.chmod(tmp, 0o755)
    os.replace(tmp, dest)
    res = subprocess.run([str(dest), "-hide_banner", "-version"], capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"the installed FFmpeg does not run here: {(res.stderr or res.stdout).strip()[:300]}")
    common.save_json(meta, {"path": str(dest), "version": VERSION, "sha256": pin["member_sha256"],
                            "source": pin["url"]})
    return str(dest)


def describe() -> str:
    key = platform_key()
    return json.dumps({"platform": key, "pin": PINS.get(key) if key else None}, indent=2)
