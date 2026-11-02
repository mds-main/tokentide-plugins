# QA rubric and regenerate rules

QA happens three times: keyframes (cheap — fix problems here), clips (before editing), final render
(before packaging). The decisive check is visual: open the contact sheets and safe-zone frames and
compare them with the real product photos. `qa.py vision` gives a second opinion for batch runs.

## 1. Keyframe rubric (score 0–5; view the sheet next to the reference photo)
| Criterion | 5 means | Reject if |
|---|---|---|
| Product shape & proportions | indistinguishable from the photo | < 4 |
| Label & logo | text and logo correct, legible, right place | < 4 (or composite the real logo/packshot later) |
| Colour match | matches the hex palette under the scene light | < 4 |
| Hands / people | natural anatomy, no extra fingers | < 3 |
| Artifacts | no melting, duplicates, warped edges, floating objects | < 4 |
| Stray text | no invented text anywhere | < 4 |
| Composition | clear subject, room for captions, works as frame 1 | < 3 |
Pass → `image.py select`. Fail → regenerate with a fix (below). After two failed rounds change the
approach: different edit model (Alt premium), simpler scene, product photo from a better angle, or
`frame` mode with the real photo.

## 2. Clip rubric (`qa.py frames clip.mp4 --every 0.5`, view the sheet)
Same criteria per frame, plus:
| Criterion | Reject if |
|---|---|
| Temporal stability | product morphs, label crawls, flicker, popping between frames |
| Motion matches the prompt | wrong action or camera move that breaks the beat |
| Physics | liquids/fabric/objects behave impossibly (unless intended) |
| Usable window | fewer than ~2 clean seconds to cut from |
| Faces/people | uncanny, identity drift, or resembles a real person |
A take is usable if it has a clean 2–4 s window — set `edit.in/out` around it. Pick with
`video.py select --shot sN --take K`.

## 3. Final render checks
1. `qa.py check renders/<vid>_master.mp4 --spec briefs/<vid>.json` → no FAIL: 1080×1920, 30 fps,
   H.264/yuv420p, audio present, duration near target, no black frames at the start, loudness
   −14 ± 2 LUFS, true peak ≤ −1 dBTP. Frozen-frame warnings: look at that span.
2. `qa.py frames … --every 1` → watch the story in the sheet: hook visible at 0.3 s, payoff by ~70%,
   CTA, captions matching speech, logo/label placement.
3. `qa.py safezone … --t 1.0` (and a frame with the CTA) → no text or logo in red/orange zones.
4. Listen (or check waveform via loudness): VO clear above music, no clipping, no abrupt cuts.
5. Compliance pass: AI label/disclosure present when realistic AI is used; every claim in VO/captions
   is in `claims[]` with evidence (package.py blocks unsubstantiated wording).

## 4. Regenerate decision tree
```
problem in keyframe? ── yes ─▶ fix keyframe first (cheapest) ─▶ re-animate
        │ no
product morphs / label crawls ─▶ shorter duration (4–5 s), slower or locked-off camera,
                                 one action, hands away from label ─▶ still bad: Alt premium model
wrong motion ─▶ rewrite motion prompt with timed beats; add end_image for the landing pose
people look uncanny ─▶ crop tighter on product/hands, or switch to a people-strong family (Kling/Veo)
422 content violation ─▶ remove brand names/real people from the prompt; describe generically
409 needs_consent (Seedance) ─▶ remove faces or switch family
2 failed takes with the same approach ─▶ change the approach, don't re-roll
```

## 5. Cost guardrails
- Quote first (`video.py run --dry-run`); the run aborts above `budget_usd` or the project cap.
- Spend per shot ≤ 3× its quoted price; beyond that, change approach or ask the user.
- Draft on Budget models at 720p for hook tests; re-generate winners on Balanced/Premium at 1080p.
- Tokentide: non-urgent batches are cheapest late in the UTC day or on `--lane lowtide`; failed jobs
  are refunded automatically, but a job that's never retrieved stays charged — always finish polling.
- `budget.py --project …` shows spend (video quotes + image estimates) vs. the cap.
