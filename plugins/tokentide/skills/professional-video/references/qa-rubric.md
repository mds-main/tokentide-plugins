# QA rubric and regenerate rules

QA runs at **four gates**: (0) visual anchors & captures before spec writing, (1) keyframes (cheap — fix
identity, subject, UI or aesthetic flaws here), (2) generated video takes (before editing), and (3) final
rendered master (before delivery). Visual inspection is always decisive: open contact sheets and
safe-zone frames side by side with the real references. `qa.py vision --mode <auto|general|people|product|app>`
provides a structured second opinion for batch runs.

## 1. Anchor & keyframe rubric (score 0–5; inspect side-by-side against references)

### 1A. Universal craft & subject fidelity (`qa.py vision --mode general` — applies to EVERY video)
| Criterion | 5 means | Reject if |
|---|---|---|
| Subject / style fidelity | faithfully matches reference photos, Style Master, or Character Sheet | < 4 |
| Visual craft & realism | intentional framing, coherent light direction & color palette, zero cheap "AI sheen" | < 4 |
| Anatomy & geometry | natural hands, faces, architecture, perspective and proportions | < 4 (people) / < 3 (background) |
| Artifacts & stray text | zero melting, duplicates, warped edges, floating objects or invented text | < 4 |
| Composition & safe area | clear focal hierarchy, room for titles/captions, nothing clipped | < 3 |

### 1B. Additional checks for identifiable real beings (`qa.py vision --mode people`)
- **Facial / subject likeness (≥4 required):** unmistakable match to each reference photo (eyes, nose,
  jawline, hair, age, skin tone, or pet markings).
- **Group proportions & rapport (≥4):** relative height, build and natural posture match real photos.
- **Naturalism:** realistic skin texture and eye-line; zero plastic airbrushing.

### 1C. Additional checks for readable interfaces, documents & data (`qa.py vision --mode app`)
- **Pixel-accurate UI/text fidelity (5/5 required):** zero AI-warped buttons, labels, code or numbers.
- **Mobile legibility (≥4):** focal controls and numbers remain readable at 50% scale (or paired with a
  tight zoomed crop).
- **Clean viewport & zero privacy leaks (5/5 required):** zero loading spinners, cookie popups, dev
  toolbars, real personal emails, API keys, tokens or private records.
- **Flow continuity (≥4):** consecutive captures progress logically without missing steps.

### 1D. Additional checks for physical products & brands (`qa.py vision --mode product`)
- **Shape, proportions, materials & color match (≥4):** indistinguishable from the real product photos.
- **Label & logo accuracy (≥4):** exact text/logo placement (or composite the real logo cleanly in post).

Pass → `image.py select`. Fail → regenerate with a concrete fix (§4). After two failed rounds, change
strategy (different edit model, better reference photo, simpler scene, or real photo/footage).

## 2. Generated clip rubric (`qa.py frames clip.mp4 --every 0.5`, inspect the sheet)
Same criteria per frame, plus:
| Criterion | Reject if |
|---|---|
| Temporal & identity stability | face/character drifts, product/architecture morphs, flicker or popping |
| Motion matches direction | awkward gesture, wrong camera move, or unnatural speed |
| Physics & naturalism | impossible hair/liquid/hand/cloth motion or stiff uncanny animation |
| Usable clean window | fewer than ~2 clean seconds to cut from |

Pick the take with the cleanest 2–5 s window (`video.py select --shot sN --take K`) and trim `edit.in/out`.

## 3. Final render checks (mandatory gate before delivery)
1. `qa.py check renders/<vid>_master.mp4 --spec briefs/<vid>.json` → **zero FAIL**: exact target canvas
   (`1920×1080`, `1080×1920`, or `1080×1080`), 30 fps, H.264/yuv420p, audio present, duration near target,
   zero black frames at 0 s, loudness within ±2 LU of target (−14 LUFS), true peak ≤ −1 dBTP. Check any
   frozen-frame warnings (ensure still shots have subtle smooth Ken Burns motion!).
2. `qa.py frames renders/<vid>_master.mp4 --every 1` → watch the entire story across the contact sheet:
   compelling frame 1 at 0.3 s, real subjects unmistakable, readable screens razor-sharp, coherent palette
   and pacing across cuts, captions synced to speech (when enabled), zero PII/watermark leaks.
3. `qa.py safezone renders/<vid>_master.mp4 --spec briefs/<vid>.json --t 1.0` (plus a captioned frame and
   ending frame) → zero text, faces or logos trapped inside red/orange UI margins.
4. Audio check: clear VO above ducked music (or balanced standalone score), zero `atempo` stutters, clean
   cuts, smooth fade-out.
5. Compliance check: realistic AI disclosed when publishing, consent confirmed for real people, factual
   claims documented in `claims[]`.

## 4. Regenerate decision tree
```
problem in reference / capture? ── yes ─▶ re-capture cleanly (fix zoom/crop/chrome) or request clearer photo
        │ no
problem in keyframe? ── yes ─▶ fix keyframe first (cheapest: refine prompt, add reference angle, switch edit model)
        │ no
identity / subject drifts in clip ─▶ lock start + end keyframes via multi-edit, use Kling/Veo/@r2v (elements /
                                     reference_images), keep 4–5 s, gentle front/3-4 camera motion
UI / readable text warps ─▶ STOP using @i2v on UI/text! Use shots[].image + targeted focal edit.zoom / edit.fit
product / object morphs ─▶ shorten to 4–5 s, slower/locked camera, single action, hands off label ─▶ Alt premium model
wrong motion ─▶ rewrite motion prompt with timed beats (0–2s / 2–4s); add end_image for landing pose
422 content violation ─▶ remove third-party brands or celebrity references; describe neutrally
409 needs_consent (Seedance) ─▶ Seedance -basic rejects people: switch video model to Kling or Veo!
2 failed takes with same approach ─▶ change strategy, never blindly re-roll
```

## 5. Cost guardrails
- Quote first (`video.py run --dry-run`); aborts above `budget_usd` or project cap.
- Real captures, authentic photos and crisp custom graphics animated with `assemble.py` cost **$0** in
  visual generation — invest budget where generative cinema genuinely adds magic!
- Spend per generative shot ≤ 3× its quoted price; beyond that, change strategy or ask the user.
- Batch non-urgent work late in the UTC day or with `--lane lowtide`; always finish polling retrieved jobs.
- `budget.py --project P` reports exact spend vs. cap.
