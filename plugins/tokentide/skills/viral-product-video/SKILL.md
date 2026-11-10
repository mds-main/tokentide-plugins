---
name: viral-product-video
description: Researches any product or brand in depth (positioning, proof, customer reviews and language, competitors, ads, trends), turns it into a virality strategy (hero moments, angles, hook bank, series, calendar), then plans, generates, edits, quality-checks and packages short-form vertical videos for TikTok, Instagram Reels and X through the Tokentide API, a Venice-compatible API (live model recommendations with tide prices, product-accurate keyframes, image-to-video, original music and sound effects, voice-over, transcription) plus FFmpeg (captions, audio mix, export). Use it whenever the user wants to promote, launch, market, grow an account for, or go viral with a product, app, service or brand on social media, or asks for TikToks, Reels, Shorts-style or X videos, AI video ads, UGC-style content, hooks, scripts or a short-form content plan. Works in any language.
license: Proprietary (Tokentide Plugin License, see LICENSE in the plugin root). Use only with the Tokentide service.
compatibility: The full pipeline needs a shell with Python 3.8+ and network access to api.tokentide.app (Claude Code, Codex, or a Claude/ChatGPT code environment that allows the domain) plus web search. The scripts link their own key through the Tokentide connector and install FFmpeg themselves, so the user only signs in once. Without a shell, the connector's image, video and music tools cover research, strategy and generation.
metadata:
  internal: true
---

# Viral Product Video Studio (Tokentide)

Turns a product into (1) a deep, evidence-based understanding of the product, its buyers and its
market, (2) a strategy for what will spread and why, and (3) finished, platform-ready vertical
videos made with Venice models through Tokentide (a Venice-compatible API) and FFmpeg —
then learns from the results. Tokentide specifics live in references/tokentide-api.md.

`SKILL_DIR` below means the folder containing this file, and `P` the project folder created in phase 0
(e.g. `projects/acme-bottle`); write both out in full in every command, since shell state may not
persist between calls. Scripts are stdlib-only Python: run `python3 SKILL_DIR/scripts/<script>.py -h`
for options and treat them as tools — read their source only when debugging. Paths inside a spec are
relative to `P`. Each phase names the reference file to open when you reach it.

This skill ships in the Tokentide plugin next to the **Tokentide connector**. The user signs in to
Tokentide once, when the connector asks; everything else is your job. Use the connector's tools for
quick answers in the conversation: `explain_pricing` (tide prices, Low Tide, quotes, job cutoffs),
`get_market` (live multipliers and the tide table), `estimate_cost`, `price_video_job` /
`price_music_job` (free quotes) and `get_account` (balance, caps, limits). The scripts do the generation
steps with their own key, which you link through the connector in phase 0 (`link_local_scripts`), so the
user never creates, copies or pastes a key. Never ask for one, and never print it.

**What each app can run** (the connector the plugin installs serves the media tools too):
| App | Phases | How |
|---|---|---|
| Claude Code, Codex (shell on the user's computer) | 0–12 | scripts; link them in phase 0, `doctor.py --fix` sets up FFmpeg |
| Claude / ChatGPT with code execution that allows api.tokentide.app | 0–12 | scripts, as above (link again in each new sandbox) |
| Claude / ChatGPT without a usable shell | 0 (models), 1–5, 6–7 via tools, 11 | connector tools: `list_models`/`get_model` for options, `price_video_job` quotes, `generate_image`/`edit_image`/`compose_images` for keyframes, `start_video_job` + `check_video_job` and `start_music_job` + `check_music_job` for clips and music (finished files come back as download links: one complete download each, within 6 hours). No assembly, captions, voice-over mix or QA renders: hand over the clips, music and the spec, and say the edit needs Claude Code, Codex or an editor |

## Principles (and why they matter)
- **Research decides the creative.** Most failed videos fail on the idea, not the pixels. Angles and
  hooks come from customer language and proven competitor formats, so research comes first.
- **The real product must look right.** Viewers and brands notice a wrong logo instantly. Build
  keyframes from real product photos (edit/multi-edit), animate image-to-video, and add all text,
  logos and captions in post. Never let a model invent label text.
- **Always the best current models, chosen by the user.** Models change weekly. Recommend from the
  live catalog with real quotes, give quality/price options, and let the user pick. Specs use
  aliases (`@i2v`), never hard-coded ids.
- **Honest content travels further.** Label AI, never fake customers or reviews, prove every claim.
  Platforms demote or remove deceptive content, and fines are real (references/compliance.md).
- **Spend deliberately.** Quote before queueing, respect the budget cap, test hooks cheaply, scale
  winners. Ask before the first paid batch unless the user said to proceed. Tokentide prices fall
  through the UTC day and the Low Tide lane is cheaper still: batch non-urgent generation late in the
  UTC day or with `--lane lowtide`.
- **Native and specific beats glossy and generic.** Lo-fi framing, one idea per video, a 1-second
  visual hook, burned captions, a reason to send it to a friend.

## Choose the mode
| Situation | Run |
|---|---|
| New product/brand, "make it go viral", "grow our account" | Full campaign: phases 0–11, then 12 after posting |
| Project research exists, "make another video / a new batch" | 0 (re-run model recommendations) → 5–11 |
| "Just the research / strategy / content plan" | 0 (skip models) → 1–4 |
| User shares analytics or results | 12, then 5–11 for the next batch |
| "Quick test, skip research" | 0 → mini-research (dossier essentials + 15 VOC quotes, ~10 searches) → 5–11, labelled as a test |

## Master checklist (copy into your task list and tick as you go)
```
[ ] 0  Setup: doctor --fix · link scripts · brief · project · model options → user picks → choose
[ ] 1  Product & brand dossier
[ ] 2  Audience & voice of customer
[ ] 3  Competitors, ads & trends
[ ] 4  Virality strategy → approval gate (concepts + cost)
[ ] 5  Video specs (briefs/vNN.json)
[ ] 6  Keyframes → look → select
[ ] 7  Video takes (quote → queue → poll) → look → select
[ ] 8  Voice-over + word timings
[ ] 9  Captions + assembly
[ ] 10 Final QA (checks + frames + safe zones)
[ ] 11 Packaging + delivery
[ ] 12 After posting: metrics → decisions → next batch
```

## Phase 0 — Setup
1. **Environment — sign in once, then fix everything yourself** (the user approves in the browser at
   most once and runs nothing):
   - `python3 SKILL_DIR/scripts/doctor.py --fix`. It checks Python, FFmpeg filters, fonts, the key and
     network, and repairs what it can: without a suitable FFmpeg it installs a pinned, checksum-verified
     static build (libass, freetype, fontconfig, libx264) into the plugin's tools folder, with no admin
     rights; the scripts find it automatically. Re-run it as `doctor.py --project P` once the project
     exists: it also caches the account limits used for pacing.
   - **No key linked yet** (doctor or any script says so): call the connector's `link_local_scripts`
     tool, then run the command it returns right away:
     `python3 SKILL_DIR/scripts/auth.py exchange --code <code>` (one use, 5 minutes). It stores the
     scripts' own key (same privacy mode and caps as the connection, grouped under it in the dashboard)
     in the user's config folder with owner-only permissions and prints only `linked: key …abcd`,
     its privacy mode and daily cap. No approval is needed: the user already signed in to the connector.
   - **No connector tools** (not installed, or no sign-in yet): ask the user to connect Tokentide once —
     Claude desktop app: Customize > Connectors (or the plugin's Connectors tab) → Connect; Claude Code
     terminal: `/mcp` → tokentide; Codex: `codex mcp login tokentide` — or run
     `python3 SKILL_DIR/scripts/auth.py login`, which prints a tokentide.app link and code for one
     approval in the browser (it waits ~2 minutes per run; continue with `auth.py login --resume`).
   - **A linked key stops working** (401; revoking the connection revokes its scripts key): scripts say
     so and what to run. Call `link_local_scripts` again (if the connector's tools also fail, ask the user
     to reconnect it first, as above) and run the new exchange command. `auth.py status` shows which key
     is used (masked); `auth.py rotate` replaces it; `auth.py logout --revoke` ends it.
   - Key lookup order: env `TOKENTIDE_API_KEY`, `TOKENTIDE_API_KEY_FILE`, the file `auth.py` writes
     (`~/.config/tokentide/api_key`; Windows `%APPDATA%\tokentide\api_key`), then `./.tokentide_api_key`.
     An env var wins over the linked key; a key file in the project folder does not. Never print a key, paste it into chat or write it into
     deliverables. Venice keys don't work here.
   - **Privacy mode `all`** (or `private_text`) is what the user picks when connecting, and the scripts'
     key inherits it. The default `private` mode hides background removal, most premium edit and video
     models and all music models; doctor and the recommender warn when this is the case, and the user can
     change the connection's key in the dashboard.
   - Host: `https://api.tokentide.app/v1` (default; sign-in calls go to the same host, so a sandbox only
     needs that domain). `TOKENTIDE_BASE_URL` overrides it, but the key only goes to Tokentide hosts
     (`*.tokentide.app`) or this machine; a `tt_test_` key may also go to a Vercel preview. `tt_test_` keys
     only work on preview/staging deployments and return mock output.
   - If the API is unreachable (sandbox allowlist; on Team/Enterprise plans owners control this in Admin
     settings → Capabilities), say so, use the connector's tools where they cover the phase, still do
     research, strategy and specs, and hand those over.
   - First time in an environment, `python3 SKILL_DIR/scripts/selftest.py` runs the whole pipeline
     against a local mock API (no key, no cost) in ~1 minute, including the sign-in flow.
2. **Brief** — ask once, in one message, only for what you can't find yourself: product name + URL,
   offer/price, target markets and languages, platforms (default: all three), goal (awareness /
   followers / sales), budget cap (default $50), brand assets (high-res product photos from several
   angles on plain backgrounds, transparent logo, brand colours/fonts), existing account handles,
   no-go claims or topics. If the user is away, proceed with sensible defaults and list them.
3. **Project:** `python3 SKILL_DIR/scripts/init_project.py "<Product>" --budget-usd 50 --languages en`
   creates `P = projects/<slug>/` with templates. Put photos in `P/assets/product/`, logo in `P/assets/brand/`,
   brand fonts (.ttf/.otf) in `P/assets/fonts/` (captions and overlays can then use them by family name).
4. **Models — always from the live catalog** (references/models.md):
   `python3 SKILL_DIR/scripts/models.py recommend --project P`
   It refreshes `models.json`, prices video and music models with free quotes, and writes
   `model_options.md` with Premium / Alt premium / Balanced / Budget / Newest 🆕 / Private options per
   job (keyframe, scene, i2v, i2v_audio, r2v, tts, music, sfx), each with max duration, resolution,
   audio, end-frame support, privacy, Tokentide price (with Venice list price), Low Tide eligibility and
   ≈ cost per finished video. Add `--lane lowtide` to see Low Tide prices.
   - For a campaign, first spend 2–3 searches on a current quality leaderboard and pass it with
     `--ranks` (format in references/models.md §3), so "Premium" reflects today's best models.
   - Present 3–4 options per job (multiple-choice question tool if available, else a compact table):
     video model (i2v) and keyframe model at minimum. Then
     `models.py choose --project P keyframe=<id> scene=<id> i2v=<id> i2v_audio=<id> tts=<id> music=<id> sfx=<id>`.
   - User away → choose Balanced everywhere, say so in one line, mention the Premium alternative.
5. Mention once: Tokentide's terms (a draft dated 1 Nov 2026) say you own outputs *subject to the
   upstream terms*, and Venice's public terms (Jun 2026) restrict their licence to personal,
   non-commercial use, so the user should get written commercial terms before publishing. Anonymized
   models pass media to third-party providers (use Private options for unreleased products).

## Phases 1–4 — Deep product & brand research → virality strategy
Read `references/research-methodology.md` now. Fill the four templates in `P`:
| Phase | File | Minimum bar |
|---|---|---|
| 1 Product & brand | research/01-product-brand-dossier.md | every field sourced or UNKNOWN; ≥10 sources; complete product bible (descriptor, exact on-pack text, never-change list, hero angles); social audit |
| 2 Audience & VOC | research/02-audience-voc.md | ≥50 verbatim quotes from ≥4 source types; top 7 pains/desires/objections; 2–4 segments with JTBD + awareness level; language bank |
| 3 Competitors & trends | research/03-competitors-trends.md | 5–10 competitors/creators with top posts and verbatim hooks; ≥10 ads (long-running = validated); dated trends; 8-week cultural calendar; white space |
| 4 Virality strategy | strategy/04-virality-strategy.md | ranked hero moments; ≥10 angles; ≥30 hooks in customer words; 3–5 pillars; ≥2 series; first batch scored on STEPPS with a send test; 2-week calendar; KPIs; risk register |
- Search widely (25–60 searches/fetches for a campaign), in the market's language, citing URL + date.
- With a subagent tool, run phases 1–3 in parallel (one agent per template; give each the template
  path, its methodology section and the evidence rules), then write phase 4 yourself.
- Platforms block some fetches: use TikTok Creative Center, Meta Ad Library, `site:` searches, review
  sites and Reddit; ask the user for screenshots/exports when stuck. Use a browser only if available
  and the user allows it.
- **Approval gate:** one screen with the positioning line, top 3 angles, top 10 hooks, series ideas,
  and the first 3–6 concepts with estimated cost at the chosen model tier. Get a go-ahead before paid
  generation unless the user asked you to run autonomously. Deliver research and strategy as
  documents the user can keep (the environment's document/artifact features if present).

## Phase 5 — Video specs
One JSON per video in `P/briefs/vNN.json`, copied from `P/briefs/_example_spec.json` (field reference:
references/post-production.md §1; formats and beat sheets: references/hooks-formats.md; prompts:
references/prompting.md).
- One idea per video. Hook in the first 1–2 s on three layers: visual (frame 1 = motion or payoff),
  on-screen text ≤8 words (`overlays` hook), spoken line ≤12 words. Payoff by ~70% of runtime, then a
  platform-matched CTA (send / reply / comment / follow).
- 7–15 s for reach tests, 20–45 s for demos. 3–7 shots of 1.5–5 s. VO at 2.3–3.0 words/s.
- Models as aliases: `"@keyframe"`, `"@i2v"`, `"@i2v_audio"` (shots that need real sound), `"@tts"`.
- Real footage or photos the user has beat AI for credibility: use `shots[].clip` or keyframe `frame` mode.
- Every claim in VO/captions/posts goes in `claims[]` with evidence; set `disclosure` (AI, paid).
- First batch: 3–6 videos; vary hooks on the strongest bodies to learn fast (references/growth-loop.md).

## Phase 6 — Keyframes (cheap; fix problems here)
1. Cutout: `python3 SKILL_DIR/scripts/image.py bg-remove --image P/assets/product/<photo> --out P/assets/product/<name>_cutout.png`
2. Scenes without the product: `image.py generate --model @scene --prompt "..." --n 2 --out P/assets/scenes/<name>`
3. `image.py keyframes --spec P/briefs/vNN.json` — runs every shot's keyframe job in parallel (default 3
   variants; `multi-edit` with [scene, cutout] for product shots), appends a product-fidelity clause, and
   writes a contact sheet per shot to `P/qa/`.
   Tokentide allows 4 image requests/min on new accounts (10 verified, 20 trusted): the scripts pace
   themselves, so a 9–15 image batch takes several minutes — say so rather than waiting silently.
   Inputs are shrunk automatically to fit Tokentide's 4.5 MB request limit; public https URLs pass through.
4. **Look** at each sheet next to the real product photo; score with references/qa-rubric.md §1.
   `image.py select --spec P/briefs/vNN.json --shot s1 --k 2`. Regenerate failures with a concrete fix;
   after two failed rounds change approach (Alt premium model, simpler scene, `frame` with the real photo).

## Phase 7 — Video takes
1. `python3 SKILL_DIR/scripts/video.py run --spec P/briefs/vNN.json --dry-run` → quote per take and total.
   It stops above the video's `budget_usd` or the project cap; ask the user before raising either.
2. `video.py run --spec P/briefs/vNN.json` → queues up to 6 takes (Tokentide allows 8 unfinished jobs per
   account; the rest wait as "planned"), then polls for up to 240 s. If jobs are still pending, run
   `video.py poll --jobs P/logs/vNN_video_jobs.json` again (safe to repeat; it never re-submits and it
   queues planned takes as slots free). Jobs typically take 1–6 minutes; failed jobs are refunded.
   - Add `--lane lowtide` for non-urgent batches (cheaper; falls back to standard when closed).
   - Daily cutoff: the video queue closes ~23:14 UTC until the 00:00 UTC reset (music/SFX ~23:39 UTC);
     the script stops with a clear message — queue again after midnight UTC.
3. **Look** at every take: `qa.py frames P/clips/<take>.mp4 --every 0.5`. Pick the take with the best clean
   2–4 s window: `video.py select --spec P/briefs/vNN.json --shot s1 --take 2`, and set `edit.in/out` around it.
4. Problems → the decision tree in references/qa-rubric.md §4 (shorten, simplify motion, end frame,
   Alt premium model). 422 = rephrase; 409 = faces on Seedance → other family.

## Phase 8 — Voice-over and word timings
- `audio.py tts --spec P/briefs/vNN.json` → `P/audio/vNN_vo.mp3`; it prints words/second (aim 2.3–3.0).
  Choose a voice matching brand and language (`audio.py voices --lang <prefix>`).
- `audio.py transcribe --spec P/briefs/vNN.json` → word timings aligned to the script (exact spelling);
  offline fallback: `audio.py align --spec P/briefs/vNN.json`.
- **Music (rights-safe):** generate an original track — add `music.generate {"model": "@music",
  "prompt": "<genre, mood, bpm, instruments>", "duration_seconds": <video length + 2>, "force_instrumental": true}`
  to the spec and run `audio.py music --spec P/briefs/vNN.json` (quote → queue → collect; sets `music.file`).
  Or use a track the user has rights to. For TikTok/Reels library sounds, post the `_nomusic` render.
- **SFX:** `sfx[].generate {"model": "@sfx", "prompt": "short airy whoosh", "duration_seconds": 1}` →
  `audio.py sfx --spec P/briefs/vNN.json`. Music and SFX models are Anonymized (key mode `all`).
- Voice cloning isn't offered through Tokentide; use a stock voice or a real recorded voice-over.

## Phase 9 — Captions and assembly
1. `captions.py --spec P/briefs/vNN.json` → burned-caption ASS (+ SRT) with word highlight, hook text
   and labels (brand colours via `captions.primary/highlight`).
2. `assemble.py --spec P/briefs/vNN.json --draft` to check timing, then `assemble.py --spec P/briefs/vNN.json`
   → `P/renders/vNN_master.mp4` (1080×1920, 30 fps, −14 LUFS), `_nomusic.mp4` when music is set, cover +
   grid preview. Edit grammar (trim, speed, zoom, transitions, end card, loop): references/post-production.md §3.

## Phase 10 — Final QA (gate)
1. `qa.py check P/renders/vNN_master.mp4 --spec P/briefs/vNN.json` — no FAIL allowed.
2. `qa.py frames P/renders/vNN_master.mp4 --every 1` and `qa.py safezone P/renders/vNN_master.mp4 --t 1` —
   look: hook visible at 0.3 s, product correct in every frame, captions match speech, nothing in the
   red/orange UI zones, CTA readable, disclosure present.
3. Fix and re-render until it passes references/qa-rubric.md §3. Optional second opinion:
   `qa.py vision --images <frames> --reference P/assets/product/<photo>`.

## Phase 11 — Packaging & delivery
Fill `packaging` (per-platform caption, ≤5 Instagram hashtags, 3–5 TikTok, 0–2 X, alt text, post time)
using references/platforms.md, then `package.py --spec P/briefs/vNN.json` → `P/post/vNN_{tiktok,instagram,x}.md`
with copy and a pre-post checklist (AI label, disclosure, sound, cover). It blocks unsubstantiated
claims and >5 Instagram hashtags. Deliver: master video(s), covers, post files, the calendar, and
`budget.py --project P` spend. You don't post on the user's behalf unless they ask and
the environment supports it.

## Phase 12 — Learn and iterate
After 48–72 h: fill `P/logs/performance.csv` (created by init; `metrics.py template` makes a fresh one) from
the user's analytics (exports or screenshots), run `metrics.py analyze --csv P/logs/performance.csv` → SCALE / ITERATE-HOOK /
-BODY / -PAYOFF / -FOLLOW / KILL per post. Update the hook bank, plan the next batch with
references/growth-loop.md, re-run `models.py recommend` for newer models, and offer a 🆕 model test take.

## Project layout
```
projects/<slug>/
  project.json         budget cap, platforms, languages, chosen models (@aliases)
  models.json          live catalog cache        model_options.md   options shown to the user
  research/  strategy/ the four filled templates
  briefs/vNN.json      one spec per video (source of truth for every script)
  assets/{product,brand,fonts,scenes,music,sfx}/   real photos, logo, brand fonts (.ttf/.otf), scenes, licensed audio
  keyframes/ clips/ audio/ captions/ renders/ qa/ post/
  logs/ledger.jsonl    every API call + spend     logs/vNN_video_jobs.json   queue ids (resume polling)
```
Every generated file has a `.json` sidecar with model, prompt and request id (provenance).

## When things go wrong
| Symptom | Do |
|---|---|
| "No Tokentide key is linked" | `link_local_scripts` → `auth.py exchange --code <code>` (phase 0); without the connector, `auth.py login` |
| 401 invalid_api_key | key revoked (or its connection was): link again as above; the user reconnects the connector only if its tools fail too |
| ffmpeg missing / filter missing | `doctor.py --fix` |
| 403 model_not_allowed | the connection's privacy mode is too strict → the user sets mode `all` on the connection's key in the dashboard (or pick a Private option) |
| network error | allowlist api.tokentide.app (or the `TOKENTIDE_BASE_URL` host); meanwhile finish research/specs |
| 400 on a parameter | the error names the parameter and the accepted values (case-sensitive, e.g. `1080P`); `models.py show <id>` lists them; fix the spec. Unknown optional fields are dropped automatically |
| 429 "Spend velocity limit reached" / "Running requests limit reached" | not a daily limit: the account's finished requests may cost a list-price amount per minute, and its running requests may hold a list-price amount at their worst case (`get_account`, doctor). A queued video/music job counts at its quoted price when it is queued, so large jobs start about one per minute: let the scripts wait and retry, and plan batches with that pace in mind (the video queue closes ~23:14 UTC) |
| 402 insufficient_balance / spend_limit_reached | tell the user: top up or raise the cap; offer Budget/Low Tide |
| 413 payload_too_large | inputs are auto-shrunk; for video inputs pass a public https URL |
| 503 epoch_rollover / queue closed | daily reset: queue after 00:00 UTC (quotes still work) |
| 409 duplicate_request | the first attempt went through but its response was lost; check `GET /account/usage` |
| 422 content violation | remove brand names/real people from prompts; describe generically |
| alias not set (`@i2v`) | `models.py recommend` → user picks → `models.py choose` |
| quote over budget | fewer takes, shorter clips, 720p drafts, Budget model, `--lane lowtide`, later in the UTC day, or ask to raise the cap |
| product drifts in clips | fix keyframe, shorten to 4–5 s, lock camera, add end frame, try Alt premium |
| captions off-sync | re-run `audio.py transcribe` (or `align`), then captions + assemble |

## Reference map
| File | Open when |
|---|---|
| references/research-methodology.md | phases 1–4 (always for a campaign) |
| references/models.md | phase 0 model options; whenever choosing or switching models |
| references/platforms.md | strategy (§4) and packaging (phase 11) |
| references/hooks-formats.md | hooks, formats, beat sheets, shareability (phases 4–5) |
| references/prompting.md | writing keyframe and motion prompts (phases 5–7) |
| references/post-production.md | spec fields, edit grammar, captions, audio (phases 5, 9) |
| references/qa-rubric.md | every look-and-select step and the final gate (phases 6, 7, 10) |
| references/compliance.md | claims, AI labels, endorsements, likeness, music, Tokentide/Venice terms |
| references/growth-loop.md | cadence, testing, metrics, next batches (phase 12) |
| references/tokentide-api.md | hosts, privacy modes, limits, lanes, errors, jobs, gaps vs Venice, manual calls |
