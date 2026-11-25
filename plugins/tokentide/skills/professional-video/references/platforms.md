# Platforms & delivery: YouTube, Shorts, TikTok, Instagram Reels, X, LinkedIn & direct

Snapshot: Nov 2026. Algorithms and limits evolve; for major growth campaigns, run 2–3 searches checking
recent platform updates (last 60 days) from official sources (YouTube Creator Insider, Instagram @creators,
TikTok Newsroom, X engineering, LinkedIn Help).

## Contents
1. Universal export & canvas specs (`16:9`, `9:16`, `1:1`)
2. YouTube (Long-Form 16:9 & Shorts 9:16)
3. Instagram Reels
4. TikTok
5. X
6. LinkedIn
7. Direct / Website / Personal / Client Delivery (`general`)
8. Cross-posting rules & what gets suppressed

## 1. Universal export & canvas specs
| Destination | Canvas | Resolution | Safe area (keep text/logos clear) | Burned captions? |
|---|---|---|---|---|
| **YouTube Long-Form / Web / Personal Cinema** | `16:9` | `1920×1080` | ≥60 px top, ≥140 px bottom (scrub bar), ≥96 px left/right | Optional (often cleaner OFF on YouTube/cinema; upload `.srt` instead, or subtle lower captions for tutorials) |
| **YouTube Shorts / TikTok / Instagram Reels / X vertical** | `9:16` | `1080×1920` | ≥250 px top, ≥650 px bottom, ≥150 px right, ≥60 px left | Yes (most mobile feeds start muted + captions aid search) |
| **Square Feed (LinkedIn / IG / X / Ads)** | `1:1` | `1080×1080` | ≥80 px top/sides, ≥160 px bottom | Usually yes |

Master encoding (`assemble.py`): H.264 High, yuv420p, 30 fps, CRF 18, maxrate 12 Mbps, `+faststart`,
AAC 48 kHz 192 kbps, −14 LUFS integrated, ≤ −1.5 dBTP. Check every master with `qa.py safezone`.

## 2. YouTube (Long-Form `16:9` & Shorts `9:16`)
**YouTube Long-Form (`youtube`):**
- **Discovery levers:** click-through rate (title + clean `1280×720`/`1920×1080` thumbnail with 2–4 bold
  words max) + first-30-second retention + average percentage viewed + session satisfaction. Also one of
  the strongest drivers of organic search & AI-assistant visibility for apps and products!
- **Title:** ≤100 chars (aim **50–65 chars** so nothing truncates on mobile); lead with the exact problem,
  app name, or outcome.
- **Description:** ≤5,000 chars. Put the primary value proposition and canonical link (with UTM params
  for apps/brands) in the **top 2 lines** (visible above "Show more"). Include **exact-second chapters**
  starting at `0:00` (≥3 chapters, ≥10 s each) — chapters earn Google Search Key Moments!
- **Captions & audio:** upload the generated `.srt` file (improves accessibility, search indexing and
  auto-translation) instead of relying solely on auto-captions.
- **Altered / synthetic content disclosure:** turn on YouTube Studio's **"Altered or synthetic content"**
  toggle whenever realistic AI visuals or voices could appear authentic (real-UI captures with AI voice
  only: check current YouTube guidance and note clearly in description).
- **Engagement:** write a helpful **pinned comment** with the primary link or quick-start steps.

**YouTube Shorts (`youtube-shorts`):**
- `9:16` (`1080×1920`), up to 3 minutes (sweet spot **20–55 s** for tutorials and hooks).
- Pair every `16:9` YouTube walkthrough with 1–3 vertical Shorts built from the sharpest single payoff
  beat, using YouTube's **"Related video"** link to feed viewers into the full tutorial.
- Put 3–5 focused hashtags at the end of the description; keep key visuals inside the central 9:16 safe area.

## 3. Instagram Reels (`instagram`)
- **Top ranking signals:** watch time, likes per reach, and **sends per reach** (especially for reaching
  non-followers). Originality is strictly enforced (never upload TikTok-watermarked files).
- **Hard limits:** **max 5 hashtags** per post/Reel (hard cap; `package.py` blocks >5); caption up to
  2,200 chars; keyword in line 1; add alt text.
- **Cover:** `1080×1920` with key subject/text centered in `1080×1350` (survives 4:5 feed and 3:4 grid
  crops; inspect `_cover_grid.jpg`).
- **Tactics:** use **Trial Reels** to A/B test hooks with non-followers; use explicit send/save CTAs;
  enable Instagram's **AI label** for realistic AI imagery.

## 4. TikTok (`tiktok`)
- **Signals:** watch time & completion, rewatches, shares, comments, follows, plus search keywords
  (spoken words, on-screen text, caption line 1).
- **AI content:** realistic AI content **must** be labeled (TikTok AI-generated content toggle; TikTok
  also reads C2PA credentials). Real product/app visuals + honest AI outperform pure AI looks.
- **Practical rules:** 3–5 targeted hashtags; caption up to 4,000 chars; business accounts must use
  original/licensed music (`audio.py music`) or ship `_nomusic.mp4` and add Commercial Music Library audio
  in-app. Mark self-promotion / Branded Content honestly. Reply to top comments with video replies.

## 5. X (`x`)
- **Signals:** replies, quotes, DM shares, follows and reposts dominate; fresh posts (<48 h) get reach.
- **Practical rules:** non-Premium 280 chars & video up to 2:20 (longer for Premium); 0–2 hashtags; upload
  natively (`16:9`, `9:16`, or `1:1`); optional `.srt` upload; lead post copy with a sharp takeaway or
  question and stay active in replies for the first hour. Disclose realistic AI in text or on screen.

## 6. LinkedIn (`linkedin`)
- **Best for:** B2B SaaS walkthroughs, founder stories, launch demos, architecture explainers (`16:9` or
  `1:1` or `9:16`, 30–120 s).
- **Practical rules:** caption up to 3,000 chars (hook cleanly in the first 2 lines before "...see more");
  3–5 focused hashtags; upload natively with `.srt` captions (most LinkedIn video plays muted at work);
  keep tone helpful and substantive rather than clickbaity.

## 7. Direct / Website / Personal / Client Delivery (`general`, `personal`, `web`)
For personal couple/family films, event tributes, hero website embeds, pitch decks, or client deliverables:
- Set `platforms: ["general"]` (or `["personal"]` / `["web"]`).
- `package.py` skips social hashtag lint and writes a clean delivery summary listing the master MP4,
  `_nomusic.mp4` (if music generated), cover frame, `.srt` subtitle file, technical specs, and provenance
  notes.
- For website embeds, suggest a fast click-to-play poster (`_cover.jpg`) or YouTube facade embed +
  `VideoObject` JSON-LD when public.

## 8. Cross-posting rules & what gets suppressed
- Export clean masters with **zero platform watermarks** and upload natively to each platform.
- Never blindly crop a `16:9` desktop app walkthrough into `9:16`: capture a native mobile `9:16` set or
  re-frame with `edit.fit: "blur"` / tight focal crops so every button stays readable.
- **Suppressed everywhere:** engagement bait ("comment YES"), unsubstantiated claims, unlabeled realistic
  AI, fake AI testimonials posing as real buyers, copyrighted unlicensed music, and watermarked reposts.
