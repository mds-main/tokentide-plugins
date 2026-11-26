---
name: professional-video
description: Universal studio-grade video director and producer for any kind of video — cinematic films, personal stories, commercials, product campaigns, app and software walkthroughs, tutorials, explainers, trailers, documentaries, music videos, YouTube long-form, Shorts, TikToks, Instagram Reels, X and LinkedIn — in 16:9, 9:16 or 1:1 through the Tokentide API (a Venice-compatible API) and FFmpeg. Grounds every visual anchor first to prevent hallucination by intelligently combining autonomous browser or computer-use capture (pausing cleanly at login screens when gated), user-supplied reference photos for max consistency, and locked style or character sheets. Users name the models or pick Essential, Pro or Max with the total price up front; handles right-sized research or creative treatment, storyboarding, keyframes, video takes, voice-over, original music and SFX, captions, visual QA and delivery. Works in any language.
license: Proprietary (Tokentide Plugin License, see LICENSE in the plugin root). Use only with the Tokentide service.
compatibility: The full pipeline needs a shell with Python 3.8+ and network access to api.tokentide.app, plus datasets-server.huggingface.co for model ratings (Claude Code, Codex, or a Claude/ChatGPT code environment that allows the domain) plus web search (and browser or computer-use tools when capturing live websites or apps). The scripts link their own key through the Tokentide connector and install FFmpeg themselves, so the user only signs in once. Without a shell, the connector's image, video and music tools cover planning and generation.
metadata:
  internal: true
---

# Professional Video Studio (Tokentide)

Universal studio-grade video production for **any kind of video** — cinematic stories, personal and
event films, commercials, product launches, software and web walkthroughs, tutorials, documentaries,
explainers, trailers, music videos, real estate or venue showcases, and high-performing social content —
in `16:9`, `9:16` or `1:1`, using Tokentide's image, video, voice and music models (a Venice-compatible
API) and FFmpeg. Tokentide specifics live in `references/tokentide-api.md`.

`SKILL_DIR` below means the folder containing this file, and `P` the project folder created in phase 0
(e.g. `projects/my-video`); write both out in full in every command, since shell state may not persist
between calls. Scripts are stdlib-only Python: run `python3 SKILL_DIR/scripts/<script>.py -h` for
options and treat them as tools — read their source only when debugging. Paths inside a spec are
relative to `P`. Open each phase's reference file when you reach it.

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
| Claude Code, Codex, Antigravity (shell on the user's computer) | 0–12 | scripts; link them in phase 0, `doctor.py --fix` sets up FFmpeg; use browser/computer use to capture live websites or apps |
| Claude / ChatGPT with code execution that allows api.tokentide.app | 0–12 | scripts, as above (link again in each new sandbox) |
| Claude / ChatGPT without a usable shell | 0 (models), 1–5, 6–7 via tools, 11 | connector tools: `list_models`/`get_model` for options, `price_video_job` quotes, `generate_image`/`edit_image`/`compose_images` for keyframes, `start_video_job` + `check_video_job` and `start_music_job` + `check_music_job` for clips and music (finished files come back as download links: one complete download each, within 6 hours). No assembly, captions, voice-over mix or QA renders: hand over the clips, music and the spec, and say the edit needs Claude Code, Codex or an editor |

## Core principles (why every video comes out extraordinary)
- **Zero hallucination — ground every visual anchor first (`references/visual-grounding.md`).** Before
  writing a spec or generating a frame, run a **Reality Inventory** of every real-world or recurring
  subject (people/beings, readable interfaces/data, physical products/brands, real places/events, or
  invented worlds/characters) and gather the exact visual anchors via the smartest path:
  - **Capture autonomously whenever possible** (agentic browser, Playwright, Chrome DevTools, Computer
    Use, local scripts/workspace). If a live web app or resource is gated behind login/SSO/2FA/paywall,
    open the login screen in the agent's interactive browser, pause cleanly for the user to sign in
    (never ask for passwords/tokens in chat), then resume in that same session and capture everything.
  - **Ask the user once, specifically, for references only they hold** (multi-angle photos of real people
    or groups, high-res product/location originals, logos, licensed fonts, personal footage).
  - **Lock Style Masters & Character Sheets** for purely creative/stylized worlds so every cut shares one
    cohesive visual DNA.
- **Pick the highest-craft visual modality per shot.** Mix real footage (`shots[].clip`), razor-sharp
  still captures/photos/diagrams animated with smooth focal Ken Burns motion (`shots[].image` +
  `edit.zoom` / `edit.fit`, `$0` gen cost — NEVER run `@i2v` on readable UI text!), and reference-locked
  generative cinema (`multi-edit` → side-by-side QA → `@i2v`/`@r2v` + `end_image`).
- **Direct with cinematic rigor.** Strong opening in 0–2 s, clear emotional or narrative arc, deliberate
  shot-size choreography (wide → medium → close-up → detail), consistent lighting/color world, purposeful
  pacing (visual change every 1.5–4 s), layered audio (clear narration or deliberate music-only space,
  custom ducked score, tactile SFX, −14 LUFS mastering), and typography that matches the genre and canvas.
- **Right-size pre-production to the request.** Full market/VOC/competitor research for growth campaigns;
  verified workflow/fact storyboard for tutorials, explainers and documentaries; creative treatment and
  visual bible for personal, narrative, artistic, event or commercial films. Never force irrelevant steps.
- **Default Pro tier & mandatory up-front whole-video quote.** Unless the user explicitly requests other
  models or another tier, ALWAYS propose **Pro (Recommended)** by default — **Seedance 2.5 Flash**
  (`seedance-2-5-flash-image-to-video-basic`) for video and **ElevenLabs TTS v4 Turbo**
  (`elevenlabs-tts-v4-turbo`) for voice-overs, paired with live Pro-level image and music models from
  Tokentide's catalog — alongside the full **Essential / Pro / Max** tiers or custom model selection.
  **NEVER start paid generation without first showing the itemized estimated quote (price in USD) for
  the WHOLE video** — video clips, images/keyframes, voice-over, music (if any), and SFX — and getting
  the user's OK. Specs use aliases (`@i2v`, `@tts`), never hard-coded ids.
- **Honest, lawful craft.** Disclose realistic AI when publishing, confirm consent for real people, prove
  factual claims, never leak secrets/PII in captures (`references/compliance.md`).
- **Spend deliberately.** Quote before queueing, respect budget caps, batch non-urgent generation late in
  the UTC day or with `--lane lowtide`.

## Choose the workflow depth (universal router)
| Goal / Request | Canvas default | Pre-production (Phases 1–4) | Production (Phases 5–12) |
|---|---|---|---|
| **Creative / narrative / personal / event / commercial / music / artistic film** | Match destination (`16:9`, `9:16`, or `1:1`; ask if unclear) | Phase 1 **Visual Grounding** (gather any real photos/clips + lock Visual Bible / Style Master) → concise **Creative Treatment & Shot List** → approval gate | 5–11 |
| **Walkthrough / video guide / tutorial / explainer / documentary / data story** | `16:9` (YouTube/web) and/or `9:16` (Shorts/Reels) | Phase 1 **Visual Grounding** (autonomous browser/computer-use capture with login handoff if gated, or crisp diagrams/real references) → **Storyboard & Accuracy Sheet** → approval gate | 5–11 |
| **Product / brand growth campaign ("make it go viral", "grow our channel")** | Platform-matched (`9:16`, `16:9`, or both) | Phase 1 **Visual Grounding** (product/brand kit) + **Full Market Research, VOC, Competitors & Virality Strategy** (`research-methodology.md`) → approval gate | 5–11, then 12 after posting |
| **New video / batch in an existing project** | Project default | Phase 0 (add "keep same models") → confirm/capture any new visual anchors | 5–11 |
| **Research, strategy, or storyboard only** | — | Phase 0 (skip model question) → Phases 1–4 | Deliver documents |
| **Post-publish analytics / iteration** | — | — | 12 → 5–11 |

## Master checklist (copy into your task list and adapt to the chosen workflow)
```
[ ] 0  Model proposal: propose Pro (default: Seedance 2.5 Flash video + ElevenLabs v4 Turbo VO + Pro images/music), or let user compare Essential / Pro / Max or choose custom
[ ] 0  Setup: doctor --fix · link scripts · smart brief · init project (--canvas, --type)
[ ] 0  Models & quote: models.py tiers → choose (--tier pro | essential|max | custom) → models.py cost → show FULL itemized quote for the whole video (video + images + VO + music + SFX) BEFORE any generation!
[ ] 1  Visual Grounding: complete Reality Inventory → capture autonomously (browser/computer use, pausing at login if gated) AND/OR gather user references AND/OR lock Style Master → inspect every anchor!
[ ] 2  Direction / Research: Creative Treatment & Storyboard (OR Full Research & Virality Strategy for marketing campaigns) → approval gate (plan + cost)
[ ] 5  Video specs (briefs/vNN.json — best visual modality per shot)
[ ] 6  Keyframes (subject/identity/style-locked stills, or verified real captures) → inspect side-by-side → select
[ ] 7  Video takes (quote → queue → poll for generative shots; skip for crisp real-still/clip shots) → inspect → select
[ ] 8  Audio: voice-over (if used) + word timings + original score & SFX
[ ] 9  Captions / overlays + assembly (focal Ken Burns, fit modes, loudness-normalized mix)
[ ] 10 Final QA (automated checks + frame sheet + visual fidelity & safe-zone gate)
[ ] 11 Packaging & delivery (YouTube / Shorts / TikTok / Instagram / X / LinkedIn / direct file)
[ ] 12 After posting (campaigns/channels): metrics → decisions → next batch
```

## Phase 0 — Setup
0. **Model proposal, before any paid generation** (`references/models.md` §1): in the user's language,
   with the multiple-choice question tool when available, ALWAYS propose the **Pro** tier by default
   unless the user already named different models or another tier:
   - **"Pro (Recommended)"**: **Seedance 2.5 Flash** (`seedance-2-5-flash-image-to-video-basic`) for
     video and **ElevenLabs TTS v4 Turbo** (`elevenlabs-tts-v4-turbo`) for voice-overs, paired with
     Tokentide's live Pro-level image and music models — and we show the full itemized price quote for
     the whole video before generating anything.
   - **"Compare Essential / Pro / Max levels"**: compare the newest Tokentide models (Arena leaderboard
     ratings for video and images; skill's estimate for voice and music) across all three price/quality
     tiers.
   - **"I'll choose my own models"**: the user names specific models; you verify Tokentide availability
     and show the full itemized quote first.
   For a new batch in an existing project, add "keep the same models as last time". Skip when the request
   is research/strategy only. User away → use `--tier pro` (Seedance 2.5 Flash + ElevenLabs v4 Turbo)
   if within budget, else Essential, and state the choice in one line. (When a video uses mostly real
   captures/footage with zero or few AI clips, note plainly that real visuals cost `$0` to generate and
   only audio plus any generative shots incur model spend.)
1. **Environment — sign in once, fix everything yourself** (user approves in browser at most once):
   - `python3 SKILL_DIR/scripts/doctor.py --fix`: verifies Python, FFmpeg filters, fonts, key and network,
     and installs a pinned, checksum-verified FFmpeg (libass, freetype, fontconfig, libx264) automatically
     with no admin rights. Re-run `doctor.py --project P` once `P` exists to cache account limits.
   - **No key linked yet**: call connector tool `link_local_scripts`, then immediately run
     `python3 SKILL_DIR/scripts/auth.py exchange --code <code>` (one use, 5 min). Never ask for or print a key.
   - **No connector tools**: guide the user to connect Tokentide once (Claude desktop: Customize >
     Connectors; Claude Code: `/mcp` → tokentide; Codex: `codex mcp login tokentide`) or run
     `python3 SKILL_DIR/scripts/auth.py login` (device flow; resume with `--resume`).
   - **Revoked key (401)**: call `link_local_scripts` again (reconnect connector first if its tools fail)
     and run `auth.py exchange`. Manage with `auth.py status|rotate|logout --revoke`.
   - Key lookup order: `TOKENTIDE_API_KEY`, `TOKENTIDE_API_KEY_FILE`, `~/.config/tokentide/api_key`
     (Windows `%APPDATA%\tokentide\api_key`), `./.tokentide_api_key`. Privacy mode **`all`** (or
     `private_text`) unlocks premium edit, video, cutout and music models (`private` hides them).
     Host: `https://api.tokentide.app/v1`.
   - First time in an environment, `python3 SKILL_DIR/scripts/selftest.py` verifies the full pipeline
     against a local mock API (no key, no cost).
2. **Smart brief** — ask once, in one concise message, ONLY for what isn't stated and cannot be discovered
   yourself: core intent/tone, canvas (`16:9` / `9:16` / `1:1`), target length, language & voice/music
   preference, destination(s), budget cap (default $50), and any **real visual references only the user
   possesses** (from your Reality Inventory in Phase 1). If the user is away, proceed with sensible
   defaults and list them.
3. **Project:** `python3 SKILL_DIR/scripts/init_project.py "<Title>" --type <general|campaign|guide|personal|commercial|explainer|story> --canvas <16:9|9:16|1:1> --platforms <...> --budget-usd 50 --languages en`
   creates `P = projects/<slug>/` with `assets/{people,captures,product,brand,fonts,references,footage,scenes,music,sfx}/`.
4. **Models & mandatory whole-video price quote — always from the live catalog** (`references/models.md`):
   - **Pro default (ALWAYS proposed first unless the user specifies otherwise):** run
     `models.py tiers --project P --videos <n>` then `models.py choose --project P --tier pro` (`--tier default`
     is an exact alias; sets `@i2v`/`@i2v_audio` = **Seedance 2.5 Flash**
     `seedance-2-5-flash-image-to-video-basic`, `@r2v` = `seedance-2-5-flash-reference-to-video-basic`,
     `@tts` = **ElevenLabs TTS v4 Turbo** `elevenlabs-tts-v4-turbo`, plus live Pro-level `@keyframe`,
     `@scene`, `@music`, `@sfx`).
   - **User's custom models** (§2): `models.py match "<name>" ... --project P` → fill any unnamed jobs
     from `--tier pro` (so unnamed video stays Seedance 2.5 Flash and unnamed voice-over stays
     ElevenLabs v4 Turbo) → `models.py choose --project P ...`.
   - **Compare levels** (§3–4): present **Essential**, **Pro** (recommended default) and **Max** from
     `P/model_tiers.md` in plain words in the user's language → `models.py choose --project P --tier <level>`.
   - **Capability notes (`references/models.md` §9):**
     - **Multi-reference compositing:** verify `maxInputImages` (`models.py show <id>`) when combining ≥3 inputs.
     - **Upstream 409 on person-bearing Seedance `-basic` shots:** if a specific shot with real faces
       triggers `409 needs_consent`, tell the user plainly and offer switching those shots to Kling V3/O3
       or Veo 3.1.
     - **Capture/footage-heavy videos:** pass the real count of generative shots (`--shots`, `--takes`,
       `--clip-seconds`, `--keyframes`, `--scenes`, `--vo-chars`, `--music-seconds`, `--sfx`, `--cutouts`)
       to `models.py cost` so the quote matches the actual video plan!
   - **MANDATORY whole-video estimated quote gate (§5 — NEVER skip!):** run
     `models.py cost --project P --videos <n> ...` with the real counts for the planned video(s) and show
     the user the **complete itemized price breakdown covering the entire video** (video clips, keyframes &
     scenes, voice-over, music if any, SFX, and total: `"Quote: $X"` or `"Estimated total: ~$X"` plus Low
     Tide price if cheaper), crediting Arena for image/video ratings. **Wait for the user's explicit OK
     before running ANY paid image, video, voice-over, or music generation** (re-quote at the Phase 4
     approval gate once exact shot counts and script/music length are finalized!).
5. Mention once for commercial/public releases: Tokentide's terms (draft 1 Nov 2026) grant output
   ownership *subject to upstream terms*, and Venice's public terms (Jun 2026) restrict their licence to
   personal, non-commercial use — advise getting written commercial terms before publishing brand content.
   Anonymized models pass media to third-party providers (use Private models for confidential material).

## Phase 1 — Visual Grounding & Reference Gathering (MANDATORY)
**Open `references/visual-grounding.md` now.** Run a **Reality Inventory** of every real or recurring
element in the video, then gather every anchor intelligently:
1. **Autonomous capture first** (websites, live apps, dashboards, docs, desktop apps, terminals, local
   code/data): use your environment's browser subagent, Playwright, Chrome DevTools MCP, Computer Use, or
   programmatic graphic rendering.
   - **Gated / login-protected apps or sites:** open the login screen in the agent's interactive browser →
     **pause and ask the user to log in there** (never request passwords/tokens in chat; never bypass
     auth/CAPTCHAs) → resume in that same authenticated browser session and capture the complete workflow!
   - Capture dense cause-and-effect states at sharp, legible retina dimensions (`1280×720 @ 1.5x` for
     `16:9`; `540×960 @ 2x` for `9:16`), clean of popups, spinners, dev overlays, secrets or PII. Save
     sequential PNGs + `INDEX.md` (with focal `(x, y)` coordinates) in `P/assets/captures/` and inspect
     every capture visually.
2. **User-supplied references (when only the user has them):** ask once clearly for multi-angle, well-lit
   photos of any real people/pets (2–4 per individual + together if multi-person, with consent →
   `P/assets/people/` + `IDENTITY.md`), high-res multi-angle photos of physical products/objects/places,
   transparent logos (`P/assets/brand/`), licensed fonts (`P/assets/fonts/`), or real clips (`P/assets/footage/`).
3. **Visual Bible for creative/stylized worlds:** lock 1–2 **Style Master** images + any **Character /
   Asset Sheets** in `P/assets/references/` (plus `STYLE_BIBLE.md`) so every generated shot shares one
   unmistakable aesthetic.

Pass the **Grounding Readiness Gate** (`visual-grounding.md` §9) before Phase 5.

## Phases 2–4 — Direction, Research & Storyboard (right-sized!)
- **Growth / product / brand campaign:** open `references/research-methodology.md` and complete the 4
  templates (`01-product-brand-dossier.md`, `02-audience-voc.md`, `03-competitors-trends.md`,
  `04-virality-strategy.md`; run 1–3 in parallel via subagents when available).
- **Walkthrough / tutorial / explainer / documentary:** write `P/strategy/storyboard.md` mapping every
  beat to its verified capture/visual/fact, focal zoom `(x, y)` coordinates, spoken script (2.3–2.6 w/s),
  text overlays (≤8 words), optional non-UI generative shots, and verified `claims[]`.
- **Film / commercial / personal / narrative / artistic / event video:** write `P/strategy/treatment.md`
  with the emotional/visual arc, shot-by-shot cinematography (shot size, camera move, lighting/palette,
  visual anchor per shot), optional narration or minimal title cards, and musical energy curve.

**Approval gate (MANDATORY before any paid generation):** present one concise screen with the creative
direction/storyboard, visual anchor map, script/beat outline, chosen models (defaulting to **Seedance 2.5
Flash** for video and **ElevenLabs TTS v4 Turbo** for voice-over unless the user chose otherwise), and the
**full itemized estimated quote for the whole video** from `models.py cost` (video clips + images/keyframes
+ voice-over + music if any + SFX = total USD). Do NOT start paid generation until the user approves the
plan and total price.

## Phase 5 — Video specs (`P/briefs/vNN.json`)
Copy `P/briefs/_example_spec.json` (`references/post-production.md` §1; storycraft & formats:
`references/hooks-formats.md`; cinematography & prompts: `references/prompting.md`).
- Set `canvas` / `aspect_ratio` (`16:9`, `9:16`, or `1:1`). Open strong at 0–2 s; vary shot sizes and
  visual rhythm every 1.5–4 s.
- **Real footage / screen recordings:** `shots[].clip`.
- **Crisp still captures, real photos & custom diagrams (`$0` gen cost, zero distortion):** `shots[].image`
  (or `keyframe.mode: "file"`/`"frame"` with no `video` block) + targeted Ken Burns `edit.zoom` (`push`,
  `pull`, `punch`, `pan-left|right|up|down`, or `{"type":"push","amount":0.22,"x":0.78,"y":0.30}`) +
  `edit.fit` (`"cover"`, `"contain"` with `bg`, or `"blur"` blurred-backdrop framing).
- **Generative cinema shots:** aliases (`@keyframe`, `@scene`, `@i2v`, `@i2v_audio`, `@r2v`, `@tts`);
  `keyframe.fidelity`: `"person"` (auto for `assets/people/`), `"product"` (auto for `assets/product/`),
  `"subject"` (places, pets, objects, characters), or `"none"` (pure backgrounds). Pass multi-shot
  continuity anchors via `video.reference_images`, `video.elements` (`@r2v`), and/or `video.end_image`
  (`video.py` auto-encodes local files within 4.5 MB).
- Record factual claims in `claims[]` with evidence/source and set honest `disclosure`.

## Phase 6 — Keyframes (cheap; lock likeness, subject & style HERE)
1. Product cutouts: `image.py bg-remove --image P/assets/product/<photo> --out P/assets/product/<name>_cutout.png`.
2. Subject-free scenes / Style Masters: `image.py generate --model @scene --prompt "..." --aspect-ratio <canvas> --n 2 --out P/assets/scenes/<name>`.
3. `image.py keyframes --spec P/briefs/vNN.json` — generates all spec keyframes in parallel (default 3
   variants; `multi-edit` takes 2–8 inputs), applies the right fidelity clause, auto-selects single real
   `file`/`frame` shots, and builds contact sheets in `P/qa/`. (New accounts allow 4 image requests/min —
   scripts pace automatically; inform the user if a large batch takes a few minutes.)
4. **Inspect side-by-side** against original references (`references/qa-rubric.md` §1; optional
   `qa.py vision --mode <auto|people|product|app|general>`). Select winners:
   `image.py select --spec P/briefs/vNN.json --shot s1 --k 2`. Fix visual flaws here before animating!

## Phase 7 — Video takes (generative shots only; skipped for real still/clip shots)
1. `python3 SKILL_DIR/scripts/video.py run --spec P/briefs/vNN.json --dry-run` → live quote & budget check.
2. `video.py run --spec P/briefs/vNN.json` → queues up to 6 takes (≤8 unfinished jobs/account; rest wait
   as "planned") and polls up to 240 s. Resume safely with `video.py poll --jobs P/logs/vNN_video_jobs.json`.
   Add `--lane lowtide` for cheaper non-urgent batches. Daily cutoff ~23:14 UTC until 00:00 UTC (music
   ~23:39 UTC); failed jobs refund automatically.
3. **Inspect** every take: `qa.py frames P/clips/<take>.mp4 --every 0.5`. Select the best clean window:
   `video.py select --spec P/briefs/vNN.json --shot s1 --take 2` and set `edit.in`/`out`.
4. Problems → decision tree in `references/qa-rubric.md` §4 (`409` on Seedance `-basic` = switch to Kling/Veo).

## Phase 8 — Voice-over, original score & sound design
- **Voice-over** (omit or set `voiceover.enabled: false` when pure music + visuals/titles hit harder):
  `audio.py tts --spec P/briefs/vNN.json` (2.3–3.0 w/s; `audio.py voices`; custom Voice IDs where
  supported). Never pick ElevenLabs TTS v4 by default (`elevenlabs-tts-v4-turbo` instead, unless v4 is
  explicitly requested). Never re-run queued TTS for the same take.
- **Never time-stretch speech (`atempo`):** adjust script length, use native speed control, or lengthen
  silent pauses only with `audio.py pace --spec P/briefs/vNN.json --target-wps 2.4`.
- **Word timings:** `audio.py transcribe --spec P/briefs/vNN.json` (defaults to `elevenlabs/scribe-v2`,
  fallback `nvidia/parakeet-tdt-0.6b-v3` on `private` keys; offline `audio.py align`). Snap any speech
  edits to real silence (`audio.py split` / `trim`).
- **Original music (rights-safe):** configure `music.generate` (genre, mood, bpm, instruments, build,
  `duration_seconds`, `force_instrumental: true`) and run `audio.py music --spec P/briefs/vNN.json` (or
  use user-licensed music).
- **SFX:** anchor subtle transitions, foley, UI clicks or impacts in `sfx[]` and run `audio.py sfx --spec`.
  (Music & SFX require privacy mode `all` or `private_text`.) Voice cloning isn't offered through Tokentide.

## Phase 9 — Captions, overlays & assembly
1. `captions.py --spec P/briefs/vNN.json` → ASS + `.srt` auto-scaled to `16:9`, `9:16` or `1:1` (uses
   `P/assets/fonts/` first, then bundled SIL OFL fonts; set `captions.enabled: false` for clean cinema
   while keeping title/label `overlays[]` and `.srt`).
2. `assemble.py --spec P/briefs/vNN.json --draft` to review pacing, then `assemble.py --spec P/briefs/vNN.json`
   → `P/renders/vNN_master.mp4` (H.264 High, 30 fps, −14 LUFS linear loudnorm or fixed gain + true-peak
   limiter), `_nomusic.mp4`, cover (+ 3:4 grid crop for `9:16`).

## Phase 10 — Final QA (mandatory gate)
1. `qa.py check P/renders/vNN_master.mp4 --spec P/briefs/vNN.json` — zero FAIL allowed.
2. `qa.py frames P/renders/vNN_master.mp4 --every 1` and `qa.py safezone P/renders/vNN_master.mp4 --spec P/briefs/vNN.json --t 1` —
   **open and inspect visually**: compelling opening at 0.3 s, real subjects match references, UI/text is
   razor-sharp, visual craft and lighting stay coherent, zero text/faces trapped in red/orange UI margins,
   zero PII/secrets leaked, honest disclosure present.
3. Optional second opinion: `qa.py vision --mode <auto|people|product|app|general> --images <frames> --reference <refs>`.
   Iterate until it passes `references/qa-rubric.md` §3.

## Phase 11 — Packaging & delivery
Populate `packaging` for the target destinations (`youtube`, `youtube-shorts`, `tiktok`, `instagram`, `x`,
`linkedin`, or `general`/`personal`/`web` for direct delivery — `references/platforms.md`), then run
`package.py --spec P/briefs/vNN.json`. Deliver: master video(s), `_nomusic` if applicable, cover/thumbnail,
`.srt` subtitles, platform/delivery files, and exact spend (`budget.py --project P`).

## Phase 12 — Learn and iterate (for channels & campaigns)
After 48–72 h: update `P/logs/performance.csv` from analytics, run `metrics.py analyze`, refine hooks and
plan the next batch (`references/growth-loop.md`), re-ask the model question (`models.py tiers`), and
offer a 🆕 model test take.

## Project layout
```
projects/<slug>/
  project.json          type, canvas, budget cap, platforms, languages, chosen models (@aliases)
  models.json           live catalog cache        arena.json          Arena ratings (CC BY 4.0)
  model_tiers.md        Essential / Pro / Max     cost_quote.json     total quoted to the user
  research/  strategy/  treatment.md / storyboard.md OR full dossier/VOC/competitors/virality strategy
  briefs/vNN.json       one spec per video (source of truth for every script)
  assets/{people,captures,product,brand,fonts,references,footage,scenes,music,sfx}/
  keyframes/ clips/ audio/ captions/ renders/ qa/ post/
  logs/ledger.jsonl     every API call + spend    logs/vNN_video_jobs.json   queue ids
```
Every generated file gets a `.json` sidecar with model, prompt and request id (provenance).

## When things go wrong
| Symptom | Do |
|---|---|
| "No Tokentide key is linked" | `link_local_scripts` → `auth.py exchange --code <code>` (phase 0); without connector, `auth.py login` |
| 401 invalid_api_key | key/connection revoked: link again (reconnect connector first if its tools fail) |
| ffmpeg missing / filter missing | `doctor.py --fix` |
| 403 model_not_allowed | privacy mode too strict → user sets mode `all` (or `private_text`) on the connection's key |
| Resource behind login / 2FA / paywall | Open login page in the agent's browser, pause for user to sign in, resume capture in that same session |
| Identity / subject drifts | Ground from multi-angle references in `multi-edit` (`fidelity: "person"`/`"subject"`), QA side-by-side, animate with Kling/Veo/`@r2v` + `end_image` |
| UI or readable text warps | Never pass readable UI/text to `@i2v`; use real captures (`shots[].image` + focal `edit.zoom` / `edit.fit`) |
| 409 needs_consent (Seedance) | Seedance `-basic` rejects people: switch video model to Kling or Veo |
| 400 on a parameter | Error names parameter & case-sensitive accepted values (`models.py show <id>`); fix spec |
| 429 spend velocity / running limit | Not a daily limit: scripts wait & retry automatically (large jobs start ~1/min) |
| 402 insufficient_balance / spend cap | Tell user: top up or raise cap; offer Essential / `--lane lowtide` / real-still shots |
| 503 epoch_rollover / queue closed | Daily reset: queue after 00:00 UTC (quotes still work) |
| 422 content violation | Remove third-party brand names or celebrity references; describe neutrally |
| Captions off-sync | Re-run `audio.py transcribe` (or `align`), then `captions.py` + `assemble.py` |

## Reference map
| File | Open when |
|---|---|
| `references/visual-grounding.md` | **phase 1 (ALWAYS)** — Reality Inventory, autonomous browser/computer-use capture + login handoff, multi-angle references, Visual Bible & hybrid directing |
| `references/models.md` | phase 0: first question, user's models, Essential/Pro/Max levels, total price, capability overrides |
| `references/prompting.md` | cinematography, keyframe grounding (`fidelity`), motion prompts, consistency & voice scripts (phases 5–7) |
| `references/post-production.md` | spec fields, still-image focal Ken Burns & pan, fit modes, transitions, captions, audio & export (phases 5, 9) |
| `references/qa-rubric.md` | visual look-and-select rubrics (identity, UI sharpness, subject accuracy, cinematic craft) & final gate (phases 6, 7, 10) |
| `references/hooks-formats.md` | universal directing, hooks, visual pacing & format beat sheets across genres (phases 2–5) |
| `references/platforms.md` | YouTube (long-form & Shorts), TikTok, Instagram Reels, X, LinkedIn & direct delivery specs (phases 4, 11) |
| `references/research-methodology.md` | phases 1–4 for product/brand marketing & viral growth campaigns |
| `references/compliance.md` | AI labels, EU AI Act, consent/likeness, claims, music rights, Tokentide/Venice terms |
| `references/growth-loop.md` | posting cadence, A/B testing, metrics & iteration (phase 12) |
| `references/tokentide-api.md` | hosts, privacy modes, limits, lanes, errors, jobs, payload caps, raw API calls |
