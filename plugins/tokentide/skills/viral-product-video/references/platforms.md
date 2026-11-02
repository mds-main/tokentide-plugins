# Platforms: what drives reach on TikTok, Instagram Reels and X

Snapshot: Nov 2026. Algorithms and limits change; before a campaign, spend 2–3 searches checking
for changes in the last 60 days (e.g. "Instagram ranking update", "TikTok For You changes",
"X algorithm update") and trust official sources (Instagram @creators / Adam Mosseri, TikTok
Newsroom / Creator Academy, X engineering / xai-org/x-algorithm) over blogs.

## Contents
1. Universal export & layout specs
2. Instagram Reels
3. TikTok
4. X
5. Cross-posting rules
6. What gets suppressed everywhere

## 1. Universal export & layout specs
| Item | Value | Note |
|---|---|---|
| Canvas | 1080×1920, 9:16 | one master works on all three |
| Video | H.264 High, yuv420p, 30 fps, CRF 18, maxrate 12 Mbps, `+faststart` | assemble.py does this |
| Audio | AAC 48 kHz 192 kbps, −14 LUFS integrated, ≤ −1.5 dBTP | industry convention; platforms normalise anyway |
| Safe area | keep text/logos ≥250 px from top, ≥650 px from bottom, ≥150 px from right, ≥60 px from left | conservative union of TikTok/Reels UI; check with `qa.py safezone` |
| Cover | 1080×1920; key text inside the centre 1080×1350 | survives the 4:5 feed and 3:4 profile-grid crops |
| Burned captions | yes, always | most short-form starts muted; on-screen words also feed search |

Lengths by goal: **7–15 s** for reach tests and loops · **20–45 s** for demos/education ·
**>60 s** only for proven series or stories. Shorter is not automatically better — completion rate
and rewatches matter, so cut everything that doesn't earn its second.

## 2. Instagram Reels
**Ranking signals.** Mosseri (Jan 2025): the top three signals are watch time, likes and sends;
track *average watch time, likes per reach, sends per reach*; sends weigh slightly more for reaching
non-followers. Oct 2026: he again said sends to a friend matter more than comments. His Sept 2026
series named four further principles: originality, recency (feed roughly chronological), surfacing
"breaking" content to non-followers, and larger AI ranking models.

**Originality enforcement.** Accounts posting ≥10 reposts of others' content in 30 days lose
recommendation eligibility (2024 rule), extended to photos/carousels from 30 Apr 2026; eligibility
returns once most recent posts are original. Never post TikTok-watermarked files. Don't reuse the
identical video repeatedly as Trial Reels.

**Practical rules.**
- **Max 5 hashtags** per post/Reel (hard cap since 18 Dec 2025; tags in comments count). Use 3–5
  specific ones; hashtags are for categorisation, not reach.
- Caption up to 2,200 chars; put the search keyword in the first line; add alt text.
- **Trial Reels** show to non-followers first — use them to A/B test hooks (schedulable since Feb 2026).
- Reels up to 3 min; recommendations favour shorter, high-retention pieces.
- AI label: turn on Instagram's AI label for realistic AI imagery. Fully virtual personas can carry
  the "AI-generated profile" label (launched 31 Aug 2026).
- CTA that matches the top signal: "send this to…", "save for later".
- Collabs (co-authored posts) put a Reel in both audiences; good for creator partnerships.

## 3. TikTok
**Context.** The TikTok USDS Joint Venture closed 22–23 Jan 2026 (Oracle, Silver Lake, MGX 15% each;
ByteDance 19.9%) and said it will retrain the US recommendation algorithm on US data under Oracle
oversight. No technical documentation or switch date was published; claims like "70% completion
threshold" or a specific switch month have no TikTok source — ignore them. Analysts reported the
experience felt largely unchanged in early 2026.

**What still drives the For You feed** (TikTok's long-standing guidance): watch time & completion,
rewatches, shares, comments, follows from the video, plus search relevance (spoken words, on-screen
text, captions) and the topic/interest graph.

**AI content.**
- Realistic AI content must be labeled (TikTok's AI-generated content setting, or your own clear
  caption/sticker/watermark). Unlabeled realistic AIGC can be removed under the Community Guidelines
  section "Edited Media and AI-Generated Content" (updated 24 Sep 2026).
- TikTok reads C2PA Content Credentials and auto-labels; it adds invisible watermarks to content made
  with its tools and to credentialed uploads; >3 billion videos labeled AIGC (Jul 2026).
- Viewers can turn AIGC down via Manage Topics → AI-looking content faces a reach headwind. Lean on
  real product footage/photos + honest, creative use of AI.

**Practical rules.**
- 3–5 relevant hashtags; caption up to 4,000 chars; put keywords in the first line, on screen and in
  the voice-over (TikTok search is a major discovery path).
- Business accounts: use the **Commercial Music Library** (or original/licensed audio). Many trending
  commercial tracks are not licensed for brand use. Ship `_nomusic.mp4` and add the sound in-app at
  low volume when you want a library track.
- Content disclosure setting: mark posts promoting your own brand; use Branded content for paid
  creator partnerships.
- Reply to comments with video replies — cheap content that reuses proven demand.

## 4. X
**Ranking.** xAI open-sourced a Grok-based ranker (`xai-org/x-algorithm`) on 20 Jan 2026, expanded
15 May 2026. It predicts ~15 engagement actions. One reading of published defaults: replies 5.0
(15.0 between mutual follows), quotes and DM shares 5.0, follows 4.0, reposts 2.0, link opens 0.2.
Posts older than ~48 h drop out of For You. Treat exact weights as indicative.

**Disputed points (test, don't assume).**
- Old blog numbers ("author reply = 150× a like", fixed 4×/2× Premium boosts) come from 2023 code.
  An Oct 2026 code review found no Premium multiplier in For You defaults; X's help centre only
  confirms reply prioritisation for paid tiers.
- Links: X staff said in Jul 2026 that links no longer need to go in replies and weren't penalised;
  many blogs still claim heavy link penalties. A/B test link-in-post vs link-in-first-reply.

**Practical rules.**
- Non-Premium: 280 chars, video up to 2:20 (longer for Premium); non-Premium accounts were capped
  at ~50 posts and 200 replies/day from ~May 2026.
- 0–2 hashtags. Native video upload. Upload the `.srt` as captions if useful.
- The text is the hook: a question, a bold claim you can back, or a "watch till the end" setup.
  Then **stay in the replies** for the first hour — replies and quotes are the heavy signals.
- Disclose AI in the text or on screen.

## 5. Cross-posting rules
- Export a clean master per video (no platform watermarks) and post it natively on each platform.
- Change the first line of text, hashtags and CTA per platform; keep the visual hook.
- Stagger by a few hours; reuse the best-performing variant, not every variant.
- Instagram counts reposts of others' content against originality; your own original video posted
  natively is fine.

## 6. What gets suppressed everywhere
Engagement bait ("comment YES", "like if…"), misleading or unsubstantiated claims, unlabeled realistic
AI, reposted/watermarked content, deceptive AI people posing as customers, copyrighted music without
a licence, sudden bursts of near-identical posts, and anything violating community guidelines
(dangerous acts, sensitive health claims, hate, adult content). Regulated categories (health,
finance, alcohol, supplements, weight loss) have extra ad and content rules — check them per market.
