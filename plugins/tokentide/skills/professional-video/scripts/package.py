#!/usr/bin/env python3
"""Write ready-to-post packages per platform from a video spec, with lint checks.

  package.py --spec briefs/v01.json  ->  post/v01_tiktok.md, post/v01_instagram.md, post/v01_x.md, post/v01_posting.json

Reads spec.packaging.{tiktok,instagram,x}, spec.disclosure, spec.claims and the render outputs.
Lints: caption length, hashtag counts (Instagram hard cap 5), AI/ads disclosure, unsupported claims,
engagement bait. Exit code 1 if a blocking problem is found (e.g. unsubstantiated claim, >5 IG hashtags).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import common

LIMITS = {"tiktok": {"chars": 4000, "tags": (3, 5)}, "instagram": {"chars": 2200, "tags": (1, 5)},
          "x": {"chars": 280, "tags": (0, 2)}}
BAIT = re.compile(r"\b(like if|tag \d+ friends|comment .{1,20} to win|follow for follow|f4f|l4l|share if you)\b", re.I)
RISKY = re.compile(r"\b(cure[sd]?|guarantee[sd]?|clinically proven|doctor recommended|#1|number one|best in the world|"
                   r"risk[- ]free|100% (safe|natural|effective)|lose \d+ ?(kg|lbs?|pounds))\b", re.I)


def norm_tags(tags):
    out = []
    for t in tags or []:
        t = "#" + re.sub(r"[^\w]", "", str(t).lstrip("#"), flags=re.UNICODE)
        if len(t) > 1 and t.lower() not in [x.lower() for x in out]:
            out.append(t)
    return out


def lint(platform, text, tags, spec_data, issues):
    lim = LIMITS[platform]
    full = (text + ("\n\n" + " ".join(tags) if tags else "")).strip()
    if len(full) > lim["chars"]:
        level = "BLOCK" if platform != "x" else "WARN"
        issues.append((level, platform, f"{len(full)} chars > {lim['chars']}" +
                       (" (fine only for X Premium)" if platform == "x" else "")))
    lo, hi = lim["tags"]
    if len(tags) > hi:
        issues.append(("BLOCK" if platform == "instagram" else "WARN", platform, f"{len(tags)} hashtags (max {hi})"))
    elif len(tags) < lo:
        issues.append(("WARN", platform, f"{len(tags)} hashtags (aim {lo}-{hi})"))
    if BAIT.search(full):
        issues.append(("WARN", platform, f"engagement-bait phrasing '{BAIT.search(full).group()}' can be demoted"))
    m = RISKY.search(full)
    if m:
        claimed = " ".join(c.get("claim", "") for c in spec_data.get("claims", []) if c.get("status") == "substantiated")
        if m.group().lower() not in claimed.lower():
            issues.append(("BLOCK", platform, f"claim-like wording '{m.group()}' without a substantiated entry in claims[]"))
    first = text.strip().splitlines()[0] if text.strip() else ""
    kws = [k.lower() for k in (spec_data.get("packaging") or {}).get("keywords", [])]
    if kws and platform in ("tiktok", "instagram") and not any(k in first.lower() for k in kws):
        issues.append(("WARN", platform, "first caption line has none of packaging.keywords (search/SEO)"))


def render_md(platform, vid, p, tags, outputs, disc, spec_data):
    master = outputs.get("master", f"renders/{vid}_master.mp4")
    nomusic = outputs.get("nomusic")
    video = nomusic if (p.get("use_nomusic") and nomusic) else master
    lines = [f"# {vid} · {platform.capitalize() if platform != 'x' else 'X'}", "",
             f"**Video:** `{video}`  ", f"**Cover:** `{outputs.get('cover', '')}`  "]
    if p.get("post_time"):
        lines.append(f"**Post at:** {p['post_time']}  ")
    if p.get("hook_variant"):
        lines.append(f"**Hook variant:** {p['hook_variant']}  ")
    text = (p.get("caption") or p.get("text") or "").strip()
    lines += ["", "## Copy", "```", text + (("\n\n" + " ".join(tags)) if tags else ""), "```"]
    if platform == "x" and p.get("reply"):
        lines += ["", "**First reply (post right after):**", "```", p["reply"], "```"]
    if platform == "instagram" and p.get("alt_text"):
        lines += ["", f"**Alt text:** {p['alt_text']}"]
    check = []
    ai = disc.get("ai_generated", True)
    paid = disc.get("paid_partnership", False)
    if platform == "tiktok":
        if ai:
            check.append("Turn on TikTok's AI-generated content label (realistic AI content must be labeled)")
        check.append("Content disclosure: mark it as promoting your own brand; use Branded content if a creator is paid")
        if p.get("use_nomusic") or not (spec_data.get("music") or {}).get("file"):
            check.append("Add a sound in-app from the Commercial Music Library (business accounts) at low volume")
        check += ["Put the main keyword in the first caption line, on screen and in the voice-over (search)",
                  "Reply to the first comments within the first hour; answer the best question with a video reply"]
    elif platform == "instagram":
        if ai:
            check.append("Turn on the AI label (AI info) for realistic AI imagery")
        if paid:
            check.append("Add the Paid partnership label / tag the partner")
        check += [f"{'Share as a Trial Reel first (non-followers) to test the hook' if p.get('trial_reel') else 'Consider a Trial Reel for hook tests'}",
                  "Cover: upload the cover image; check the 3:4 grid crop (cover_grid.jpg)",
                  "Max 5 hashtags (hard cap); keyword-rich first line; add alt text",
                  "Ask for sends in the CTA ('send this to…') — sends per reach is a top ranking signal"]
        if p.get("collaborators"):
            check.append("Invite collaborators: " + ", ".join(p["collaborators"]))
    else:
        if ai:
            check.append("Disclose AI in the text or on screen (e.g. 'made with AI')")
        if paid:
            check.append("Add #ad / paid partnership disclosure")
        check += ["Upload the video natively (no external player links)",
                  "Optional: upload the .srt as captions" + (f" (`{spec_data.get('captions', {}).get('srt')}`)" if spec_data.get('captions', {}).get('srt') else ""),
                  "Stay in the replies for the first hour; replies and quotes outweigh likes",
                  "Test link placement (main post vs. first reply) rather than assuming a penalty"]
    if disc.get("on_screen_label"):
        check.append(f"On-screen disclosure present: '{disc['on_screen_label']}'")
    lines += ["", "## Before posting"] + [f"- [ ] {c}" for c in check]
    if spec_data.get("claims"):
        lines += ["", "## Claims used (evidence)"] + [f"- {c.get('claim')} — {c.get('evidence', 'NO EVIDENCE')} ({c.get('status', '?')})"
                                                      for c in spec_data["claims"]]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--platforms", help="comma list (default: spec.platforms or all three)")
    a = ap.parse_args()
    spec = common.Spec(a.spec)
    S = spec.data
    vid = spec.vid
    render = common.load_json(spec.root / "renders" / f"{vid}_render.json", default={"outputs": {}})
    outputs = render.get("outputs", {})
    if not outputs.get("master"):
        common.log("note: no master render found yet (assemble.py); packaging copy anyway")
    pk = S.get("packaging") or {}
    disc = S.get("disclosure") or {}
    plats = (a.platforms.split(",") if a.platforms else (S.get("concept") or {}).get("platforms") or S.get("platforms")
             or ["tiktok", "instagram", "x"])
    issues, posting = [], {"id": vid, "outputs": outputs, "platforms": {}}
    for c in S.get("claims", []):
        if c.get("status") != "substantiated":
            issues.append(("BLOCK", "claims", f"'{c.get('claim')}' is {c.get('status', 'unverified')} — remove or substantiate"))
    for plat in plats:
        plat = plat.strip().lower()
        if plat not in LIMITS:
            common.log(f"skip unknown platform '{plat}'")
            continue
        p = pk.get(plat) or {}
        text = (p.get("caption") or p.get("text") or "").strip()
        if not text:
            issues.append(("WARN", plat, "no caption/text in packaging"))
        tags = norm_tags(p.get("hashtags"))
        lint(plat, text, tags, S, issues)
        md = render_md(plat, vid, p, tags, outputs, disc, S)
        out = spec.root / "post" / f"{vid}_{plat}.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(md, encoding="utf-8")
        posting["platforms"][plat] = {"file": spec.rel(out), "caption": text, "hashtags": tags,
                                      "post_time": p.get("post_time"), "video": outputs.get("nomusic") if p.get("use_nomusic") else outputs.get("master")}
        print(f"{plat:<10} -> {spec.rel(out)}")
    if not disc:
        issues.append(("WARN", "disclosure", "spec.disclosure missing (ai_generated / paid_partnership)"))
    posting["issues"] = [{"level": l, "where": w, "msg": m} for l, w, m in issues]
    common.save_json(spec.root / "post" / f"{vid}_posting.json", posting)
    for l, w, m in issues:
        print(f"{l:<5} {w}: {m}")
    if any(l == "BLOCK" for l, _, _ in issues):
        print("Blocking issues: fix before publishing.")
        sys.exit(1)


if __name__ == "__main__":
    main()
