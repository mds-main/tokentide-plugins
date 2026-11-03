#!/usr/bin/env python3
"""Environment check for the Tokentide version: Python, ffmpeg features, fonts, key, API status,
account (balance, tier, limits), today's tide prices, and what the key's privacy mode can see.

  doctor.py [--project P]   full check (status, account, market, catalog peek); caches account in P/logs
  doctor.py --fix           also repair what the agent can: installs a pinned, checksum-verified FFmpeg
                            (libass, freetype, fontconfig, libx264) into the plugin's tools folder when
                            ffmpeg is missing or lacks a needed filter. No admin rights; the user does nothing.
  doctor.py --offline       skip network calls
Exit code 1 if something required is missing; each problem prints its fix (written for the agent).
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path

import apiclient as api
import common
import ffmpeg_setup

NEEDED_FILTERS = ["ass", "xfade", "loudnorm", "sidechaincompress", "amix", "tpad", "blackdetect", "freezedetect",
                  "silencedetect", "tile", "drawbox"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--fix", action="store_true", help="install the pinned FFmpeg when ffmpeg is missing or incomplete")
    ap.add_argument("--force", action="store_true", help="with --fix: reinstall the pinned FFmpeg")
    ap.add_argument("--ffmpeg-wheel", help="with --fix: install from a local copy of the pinned wheel (offline)")
    ap.add_argument("--project", help="project folder: caches the account snapshot (limits used for pacing)")
    a = ap.parse_args()
    ok = True

    def line(status, msg):
        print(f"[{status}] {msg}", flush=True)

    v = sys.version_info
    line("OK" if v >= (3, 8) else "FAIL", f"Python {v.major}.{v.minor}.{v.micro}" + ("" if v >= (3, 8) else " — need 3.8+"))
    ok &= v >= (3, 8)
    fb = common.ffmpeg_bin()
    missing = [f for f in NEEDED_FILTERS if not common.has_filter(f)] if fb else NEEDED_FILTERS
    if a.fix and (not fb or missing or a.force):
        why = "not found" if not fb else ("reinstall requested" if a.force and not missing else
                                          f"{fb} lacks {', '.join(missing)}")
        line("FIX", f"ffmpeg {why}: installing the pinned FFmpeg ({ffmpeg_setup.VERSION}) into {common.tools_dir()}…")
        try:
            path = ffmpeg_setup.install(force=a.force, wheel=a.ffmpeg_wheel)
            line("OK", f"installed {path} (SHA-256 verified); the scripts use it automatically")
            common._FILTERS = None
            fb = common.ffmpeg_bin()
        except (RuntimeError, OSError, KeyError) as e:
            line("FAIL", f"could not install FFmpeg: {e}")
    if not fb:
        line("FAIL", f"ffmpeg not found -> agent: run `{api.PY} {Path(__file__).resolve()} --fix` (installs a pinned, "
                     "checksum-verified FFmpeg for the plugin, no admin rights), or set FFMPEG_BIN")
        ok = False
    else:
        ver = subprocess.run([fb, "-hide_banner", "-version"], capture_output=True, text=True).stdout.splitlines()[0]
        missing = [f for f in NEEDED_FILTERS if not common.has_filter(f)]
        managed = " (plugin-managed)" if fb == common.managed_ffmpeg() else ""
        line("OK" if not missing else "FAIL", f"{ver[:60]}{managed}" + (
            f" — missing filters: {', '.join(missing)} -> agent: run `{api.PY} {Path(__file__).resolve()} --fix`"
            if missing else " — all needed filters present"))
        m = re.search(r"version (\d+)\.(\d+)", ver)
        if m and (int(m[1]), int(m[2])) < (4, 4):
            line("WARN", "ffmpeg < 4.4: amix normalize=0 may be unsupported; upgrade recommended")
        ok &= not missing
        line("OK" if api.has_encoder("libopus") else "WARN",
             "libopus " + ("available (compresses long audio under the 4.5 MB body limit)" if api.has_encoder("libopus")
                           else "missing: long transcriptions may exceed 4.5 MB"))
    if not common.ffprobe_bin() and fb:
        line("OK", "ffprobe not found: media is probed with ffmpeg -i instead")
    fonts = [f.name for f in common.font_files(a.project)]
    line("OK" if fonts else "WARN", f"fonts: {', '.join(fonts) or 'none'}"
         + (" (project brand fonts go in P/assets/fonts/)" if a.project else ""))

    base = api.base_url()
    line("OK", f"API base: {base}  (TOKENTIDE_BASE_URL overrides)")
    key, src = api.key_source()
    if not key:
        line("FAIL", api.link_instructions("No Tokentide key is linked for the plugin's scripts yet."))
        ok = False
    else:
        where = "env TOKENTIDE_API_KEY" if src == "env TOKENTIDE_API_KEY" else src
        line("OK", f"Tokentide key found ({key[:8]}…{key[-4:]}, from {where})")
        if src and not src.startswith("env") and os.name != "nt" and os.stat(src).st_mode & 0o077:
            line("WARN", f"{src} is readable by other users -> chmod 600 {src}")
        if key.startswith("tt_test_") and base == api.DEFAULT_BASE:
            line("WARN", "tt_test_ keys only work on preview/staging deployments (mock output); use tt_live_ for production")
        if not key.startswith(("tt_live_", "tt_test_")):
            line("WARN", "key doesn't look like a Tokentide key (tt_live_/tt_test_)")
    if a.offline:
        sys.exit(0 if ok else 1)
    if a.project:
        api.use_project(a.project)
    try:
        st = api.get("/status", auth=False, retries=1, timeout=20).json()
        line("OK" if st.get("status") == "operational" else "WARN",
             f"status: {st.get('status')} · components: {st.get('components')}")
    except api.APIError as e:
        line("FAIL", f"cannot reach {base}: {str(e).splitlines()[0]}\n       In hosted apps (Claude, ChatGPT) the code sandbox must allow "
                     f"{urllib.parse.urlsplit(base).hostname} (Team/Enterprise owners: Admin settings → Capabilities). Research and specs "
                     f"can still be produced; generation needs network access.")
        sys.exit(1)
    try:
        mk = api.get("/market", auth=False, retries=1, timeout=20).json()
        std, lt = mk.get("standard") or {}, mk.get("lowtide") or {}
        secs = (mk.get("epoch") or {}).get("seconds_to_reset")
        reset = f"{int(secs) // 3600}h{int(secs) % 3600 // 60:02d}m to the 00:00 UTC reset" if secs else ""
        line("OK", f"tide now: standard ×{std.get('multiplier')} ({std.get('savings_pct')}% off list) · Low Tide "
                   f"{'open ×' + str(lt.get('multiplier')) if lt.get('open') else 'closed'} · {reset}")
        line("OK", "cheapest: late in the UTC day; video queue closes ~23:14 UTC, music ~23:39 UTC")
    except api.APIError as e:
        line("WARN", f"market unavailable ({e.status})")
    if not key:
        sys.exit(1)
    try:
        acct = api.account(refresh=True)
        bal = acct.get("balance") or {}
        lim = acct.get("limits") or {}
        spendable = bal.get("spendable_usd")
        free = acct.get("free_use") is True  # free-use accounts are charged $0 and need no balance
        line("OK" if free or spendable not in (None, "0", "0.00") else "WARN",
             f"account: tier={acct.get('tier')} · spendable ${spendable} · today charged ${(acct.get('spend_today') or {}).get('charged_usd')}"
             + (" · free use: requests and quotes are charged $0" if free else ""))
        vel = lim.get("spend_velocity_usd_per_minute")
        line("OK", f"limits: {lim.get('requests_per_minute_per_key')} req/min/key · {lim.get('concurrency')} concurrent · "
                   f"{lim.get('image_requests_per_minute')} image req/min (scripts pace to this) · ≤8 unfinished video+music jobs"
                   + (f" · spend velocity ${vel}/min at list price (a larger job starts once the minute is under it; counted even on free use)"
                      if vel else ""))
    except api.APIError as e:
        line("FAIL", f"account check failed: {str(e).splitlines()[0]}")
        ok = False
    try:
        imgs = api.get("/models?type=image", retries=1, timeout=30).json().get("data", [])
        edit = api.get("/models?type=inpaint", retries=1, timeout=30).json().get("data", [])  # edit models
        vids = api.get("/models?type=video", retries=1, timeout=30).json().get("data", [])
        anon = [m for m in imgs + edit + vids if str((m.get("tokentide") or {}).get("privacy_tier") or
                                                        (m.get("model_spec") or {}).get("privacy")).lower() == "anonymized"]
        line("OK" if edit and anon else "WARN",
             f"catalog visible to this key: {len(imgs)} image · {len(edit)} edit · {len(vids)} video"
             + ("" if edit and anon else " — key looks like privacy mode 'private': background removal, most premium "
                                         "edit and video models and every music model are anonymized, so create a key "
                                         "with privacy mode 'all' (or 'private_text')"))
    except api.APIError as e:
        line("WARN", f"catalog check failed ({e.status})")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
