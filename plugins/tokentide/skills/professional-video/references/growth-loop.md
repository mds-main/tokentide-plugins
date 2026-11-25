# Growth loop: cadence, testing, metrics, decisions

## Contents
1. Cadence for new vs. established accounts
2. Testing (one variable at a time)
3. Metrics: definitions and where to find them
4. Decisions: scale / iterate / kill
5. Iteration recipes
6. Paid amplification
7. Community and collaboration
8. Weekly and monthly review

## 1. Cadence
| Platform | New account (first 4–6 weeks) | Established |
|---|---|---|
| TikTok | 1–2 posts/day | 4–7/week |
| Instagram | 4–7 Reels/week (+ Trial Reels for tests) | 3–5 Reels/week + carousels/stories |
| X | 1–3 video posts/day + active replies | daily posts + replies |
Hold an ~80/20 value-to-promotion ratio. Consistency beats bursts. Generate the next batch late in the
UTC day (Tokentide's tide is lowest then; video queue closes ~23:14 UTC) or on the Low Tide lane. Batch-produce: one research +
strategy pass feeds 2–3 weeks of content; each batch of 3–6 videos varies hooks on proven bodies.

## 2. Testing
- Change **one variable** per test, in this order: hook (biggest lever) → length → format → CTA →
  posting time.
- Hook test = same body, 2–3 different first 2 seconds (text + visual + spoken line). Instagram Trial
  Reels show to non-followers first — ideal for this. On TikTok, post variants on different days.
- Judge after 48–72 h, never in the first hours. Need ≥3 posts per platform for medians.
- Use Budget models at 720p for tests; regenerate winners on Balanced/Premium.

## 3. Metrics
| Metric | Formula | Where | Diagnoses |
|---|---|---|---|
| 3-s hold rate | viewers past 3 s / views | TikTok retention graph; IG (skip rate where shown) | hook |
| Avg watch % | avg watch time / duration | all three | body pacing |
| Completion | finished views / views | TikTok "watched full video" | length, payoff timing |
| Sends per reach | shares-to-DM / reach | IG insights (sends), TikTok shares, X DM shares (proxy: reposts+quotes) | shareability |
| Likes, comments, saves per reach | each / reach | all | resonance, practical value |
| Follows per 1k reach | follows / reach × 1000 | all | series / reason to follow |
| Profile visits, link clicks | — | all | intent |
Benchmarks are niche-dependent; heuristics used when data is thin: hold ≥60%, watch ≥50%,
sends/reach ≥1%, follows ≥3 per 1k reach.
Workflow: `metrics.py template --out logs/performance.csv`, fill from the user's analytics exports or
screenshots (one row per post), `metrics.py analyze --csv logs/performance.csv`.

## 4. Decisions (metrics.py compares each post with its platform median)
| Decision | Rule of thumb | Action |
|---|---|---|
| SCALE | sends ≥1.5× median and watch ≥0.9× | 3 new hooks on the same body, make it a series, consider Spark Ads / boosting |
| ITERATE-HOOK | hold low, watch fine | new opening (visual-first, payoff-first, callout) |
| ITERATE-BODY | hold fine, watch low | cut 20–30%, pattern interrupts every ~2 s, payoff earlier |
| ITERATE-PAYOFF | watched but not shared | sharper payoff, identity/social-currency angle, explicit send CTA |
| ITERATE-FOLLOW | shared, few follows | episodic framing ("part 2"), series branding |
| KILL | far below median on hook and shares | drop the angle; retire after two KILLs |
| HOLD | around median | keep format, test the next variable |
Add winners' hooks to the hook bank (strategy §4) marked ✅, losers marked ✖ with the reason.

## 5. Iteration recipes
- **New hook, same body:** change only shot 1 (+ its keyframe) and the hook text/VO line; re-assemble.
  Cheap: one new clip.
- **Remix a winner:** same structure, new product use/scene ("3 more ways"), same series title.
- **Comment-driven:** turn the best question into a video reply (TikTok) or a quote post (X).
- **Platform port:** a TikTok winner becomes a Trial Reel on Instagram with an IG-native caption
  and a send CTA.
- **Newer model check:** before a new batch, `models.py recommend`; if a 🆕 model appears, test one
  take of the winning shot with it.

## 6. Paid amplification
Promote only organic winners: TikTok Spark Ads (boost the original post with its social proof),
Instagram/Facebook boosted posts or partnership ads with creators. Paid versions can carry a harder
CTA and the offer; keep claims within the substantiated list and use the platforms' ad disclosures.
TikTok Shop / Instagram shopping tags where available shorten the path to purchase.

## 7. Community and collaboration
Reply to comments in the first hour (on X this is a primary ranking signal), pin the best comment,
answer objections with video replies, invite creators to collab posts (Instagram Collabs put the Reel
in both audiences), duet/stitch-friendly endings on TikTok.

## 8. Reviews
Weekly: run metrics, update the hook bank, plan next week's batch. Monthly: re-run research Phase 3
(trends, competitors), `models.py recommend` for new models and prices, and refresh the strategy.
