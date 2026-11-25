#!/usr/bin/env python3
"""Write ready-to-publish or direct-delivery packages from a video spec, with lint checks.

  package.py --spec briefs/v01.json  ->  post/v01_<platform>.md, post/v01_posting.json

Supports: youtube, youtube-shorts, tiktok, instagram, x, linkedin, and general / personal / web delivery.
Lints: title/caption lengths, hashtag limits (Instagram hard cap 5), AI/ads disclosure, unsupported claims,
engagement bait. Exit code 1 if a blocking problem is found (e.g. unsubstantiated claim, >5 IG hashtags).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import common

LIMITS = {
    "youtube": {"title": 100, "chars": 5000, "tags": (0, 15)},
    "youtube-shorts": {"title": 100, "chars": 5000, "tags": (2, 5)},
    "tiktok": {"chars": 4000, "tags": (3, 5)},
    "instagram": {"chars": 2200, "tags": (1, 5)},
    "x": {"chars": 280, "tags": (0, 2)},
    "linkedin": {"chars": 3000, "tags": (3, 5)},
    "general": {"chars": 10000, "tags": (0, 20), "direct": True},
    "personal": {"chars": 10000, "tags": (0, 20), "direct": True},
    "web": {"chars": 10000, "tags": (0, 20), "direct": True},
}
LABELS = {
    "youtube": "YouTube", "youtube-shorts": "YouTube Shorts", "tiktok": "TikTok",
    "instagram": "Instagram", "x": "X", "linkedin": "LinkedIn",
    "general": "Direct Delivery", "personal": "Personal Delivery", "web": "Web Delivery",
}
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


def lint(platform, title, text, tags, spec_data, issues):
    lim = LIMITS[platform]
    if lim.get("direct"):
        return
    if lim.get("title") and title and len(title) > lim["title"]:
        issues.append(("BLOCK", platform, f"title is {len(title)} chars > {lim['title']}"))
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
    combined = f"{title}\n{full}".strip()
    m = RISKY.search(combined)
    if m:
        claimed = " ".join(c.get("claim", "") for c in spec_data.get("claims", []) if c.get("status") == "substantiated")
        if m.group().lower() not in claimed.lower():
            issues.append(("BLOCK", platform, f"claim-like wording '{m.group()}' without a substantiated entry in claims[]"))
    first = (title or (text.strip().splitlines()[0] if text.strip() else "")).lower()
    kws = [k.lower() for k in (spec_data.get("packaging") or {}).get("keywords", [])]
    if kws and platform in ("tiktok", "instagram", "youtube", "youtube-shorts") and not any(k in first for k in kws):
        issues.append(("WARN", platform, "title/first line has none of packaging.keywords (search/SEO)"))


def render_md(platform, vid, p, tags, outputs, disc, spec_data):
    master = outputs.get("master", f"renders/{vid}_master.mp4")
    nomusic = outputs.get("nomusic")
    video = nomusic if (p.get("use_nomusic") and nomusic) else master
    srt = (spec_data.get("captions") or {}).get("srt")
    label = LABELS.get(platform, platform.capitalize())
    lines = [f"# {vid} · {label}", "", f"**Video:** `{video}`  "]
    if nomusic and video != nomusic:
        lines.append(f"**No-music master:** `{nomusic}`  ")
    if outputs.get("cover"):
        lines.append(f"**Cover / thumbnail:** `{outputs.get('cover', '')}`  ")
    if srt:
        lines.append(f"**Subtitles (.srt):** `{srt}`  ")
    if p.get("post_time"):
        lines.append(f"**Post at:** {p['post_time']}  ")
    if p.get("hook_variant"):
        lines.append(f"**Hook variant:** {p['hook_variant']}  ")

    title = (p.get("title") or (spec_data.get("title") if platform in ("youtube", "youtube-shorts") else "") or "").strip()
    text = (p.get("description") or p.get("caption") or p.get("text") or p.get("notes") or "").strip()
    if title and platform in ("youtube", "youtube-shorts"):
        lines += ["", "## Title", "```", title, "```"]
    if text or tags:
        heading = "## Notes" if LIMITS[platform].get("direct") else "## Description" if platform.startswith("youtube") else "## Copy"
        body = text + (("\n\n" + " ".join(tags)) if tags and platform != "youtube" else "")
        lines += ["", heading, "```", body.strip(), "```"]
    if platform == "youtube" and p.get("chapters"):
        lines += ["", "## Chapters", "```"] + [str(c) for c in p["chapters"]] + ["```"]
    if platform == "youtube" and p.get("tags"):
        lines += ["", "**YouTube Studio tags:** " + ", ".join(str(t) for t in p["tags"])]
    if platform.startswith("youtube") and p.get("pinned_comment"):
        lines += ["", "**Pinned comment:**", "```", p["pinned_comment"], "```"]
    if platform == "x" and p.get("reply"):
        lines += ["", "**First reply (post right after):**", "```", p["reply"], "```"]
    if platform == "instagram" and p.get("alt_text"):
        lines += ["", f"**Alt text:** {p['alt_text']}"]

    check = []
    ai = disc.get("ai_generated", False if LIMITS[platform].get("direct") else True)
    paid = disc.get("paid_partnership", False)
    if platform == "youtube":
        if ai:
            check.append("Turn on YouTube Studio's 'Altered or synthetic content' disclosure when realistic AI visuals/voices are used")
        if paid:
            check.append("Check 'My video contains paid promotion' in YouTube Studio")
        check += ["Upload the custom thumbnail (`cover`) and verify mobile legibility (2–4 words max)",
                  "Upload the `.srt` captions file for accessibility, search indexing and translations" + (f" (`{srt}`)" if srt else ""),
                  "Confirm exact-second chapters start at `0:00` and the primary link is in the top 2 lines",
                  "Post and pin the first comment right after publishing"]
    elif platform == "youtube-shorts":
        if ai:
            check.append("Turn on YouTube Studio's 'Altered or synthetic content' disclosure for realistic AI")
        check += ["Link a full 16:9 guide via YouTube's 'Related video' selector if applicable",
                  "Verify key visuals and captions stay clear of Shorts bottom/right overlays"]
    elif platform == "tiktok":
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
    elif platform == "linkedin":
        if ai:
            check.append("Note AI-assisted production transparently if visuals/voices could appear authentic")
        check += ["Upload the video natively (avoid external video links)",
                  "Attach the `.srt` captions file so silent workplace viewers can follow" + (f" (`{srt}`)" if srt else ""),
                  "Hook clearly in the first 2 lines before '...see more'"]
    elif platform == "x":
        if ai:
            check.append("Disclose AI in the text or on screen (e.g. 'made with AI')")
        if paid:
            check.append("Add #ad / paid partnership disclosure")
        check += ["Upload the video natively (no external player links)",
                  "Optional: upload the .srt as captions" + (f" (`{srt}`)" if srt else ""),
                  "Stay in the replies for the first hour; replies and quotes outweigh likes"]
    else:  # general / personal / web
        check += ["Verify playback, audio sync and aspect ratio on target screen/device",
                  "Share the master MP4 (and optional `.srt` / cover poster) directly"]
        if ai:
            check.append("Include AI credit/disclosure if publishing publicly")
    if disc.get("on_screen_label"):
        check.append(f"On-screen disclosure present: '{disc['on_screen_label']}'")
    lines += ["", "## Delivery checklist" if LIMITS[platform].get("direct") else "## Before posting"] + [f"- [ ] {c}" for c in check]
    if spec_data.get("claims"):
        lines += ["", "## Claims used (evidence)"] + [
            f"- {c.get('claim')} — {c.get('evidence') or c.get('source') or 'NO EVIDENCE'} ({c.get('status', '?')})"
            for c in spec_data["claims"]
        ]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--platforms", help="comma list (default: spec.platforms or general)")
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
             or ["general"])
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
        title = (p.get("title") or (S.get("title") if plat in ("youtube", "youtube-shorts") else "") or "").strip()
        text = (p.get("description") or p.get("caption") or p.get("text") or p.get("notes") or "").strip()
        if not text and not LIMITS[plat].get("direct"):
            issues.append(("WARN", plat, "no caption/description in packaging"))
        tags = norm_tags(p.get("hashtags"))
        lint(plat, title, text, tags, S, issues)
        md = render_md(plat, vid, p, tags, outputs, disc, S)
        out = spec.root / "post" / f"{vid}_{plat}.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(md, encoding="utf-8")
        posting["platforms"][plat] = {
            "file": spec.rel(out), "title": title or None, "caption": text, "hashtags": tags,
            "post_time": p.get("post_time"),
            "video": outputs.get("nomusic") if p.get("use_nomusic") else outputs.get("master"),
        }
        print(f"{plat:<15} -> {spec.rel(out)}")
    if not disc and not all(LIMITS.get(pl.strip().lower(), {}).get("direct") for pl in plats):
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
