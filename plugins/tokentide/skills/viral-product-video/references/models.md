# Choosing models dynamically (always from the live catalog)

New image and video models land on Venice almost every week, and Tokentide's prices move every 15
minutes with the tide. So the skill never hard-codes a model: it reads Tokentide's live catalog
(Venice models + Tokentide multipliers), prices candidates with free quotes, proposes a spread of
options, and lets the user choose. Specs then refer to the choice by alias.

## Contents
1. The routine (every project, and before every new batch)
2. Reading the options
3. Adding a current quality leaderboard (recommended for campaigns)
4. Presenting the choice to the user
5. How the recommender scores models
6. Capability rules that override scores
7. Cost model
8. Fallback snapshot (Nov 2026) — only if the API is unreachable

## 1. The routine
```bash
python3 SKILL_DIR/scripts/models.py recommend --project projects/<slug>          # live catalog + quotes
python3 SKILL_DIR/scripts/models.py choose --project projects/<slug> \
        keyframe=<id> scene=<id> i2v=<id> i2v_audio=<id> tts=<id> music=<id> sfx=<id>   # user's picks
```
- `recommend` refreshes `models.json`, writes `model_options.md/.json`, and covers the jobs
  `keyframe, scene, i2v, i2v_audio, r2v, tts, music, sfx` (add `--jobs t2v,upscale` when needed).
- Video and music prices are **real Tokentide quotes** (`POST /video/quote`, `/audio/quote`, free; 60/min)
  for a standard clip — default 5 s at 1080p, 9:16 (`--duration`, `--resolution`) / a 30 s track.
  Image prices are the catalog's Venice list price × the model's current Tokentide multiplier (2K tier
  when tiered). Each price shows the Venice list price next to it; `LT` marks Low Tide eligibility, and
  `--lane lowtide` prices everything for that lane.
- **Privacy mode decides what you see.** A key in Tokentide's default `private` mode hides background
  removal, most premium edit and video models and every music model; the report warns at the top. Use
  a key in mode `all` or `private_text` (Private options stay available for confidential products).
- Specs use `"model": "@i2v"`, `"@keyframe"`, `"@i2v_audio"`, `"@scene"`, `"@tts"`, `"@music"`, `"@sfx"`; scripts resolve
  them from `project.json` → `models`. To switch the whole campaign, re-run `choose`.
- Re-run `recommend` before each new batch (or when the user asks "is there anything better?"). If a
  model flagged 🆕 appears in a job you use, offer one test take with it next to the current pick.

## 2. Reading the options
| Label | Meaning | Typical use |
|---|---|---|
| Premium | highest expected quality | hero shots, paid ads, final masters |
| Alt premium | best model from a *different family* | second opinion when Premium struggles with a product/motion |
| Balanced | best quality per dollar | default for organic batches |
| Budget | ≥25% cheaper than Balanced, still acceptable | drafts, hook A/B tests, volume |
| Newest 🆕 | released ≤60 days ago | one test take to see if it beats the current pick |
| Private | zero data retention | confidential / pre-launch products |
Columns show max duration, max resolution, native audio, end-frame support, privacy, quoted price
and ≈ cost per finished video (3 shots × 2 takes; images 3 shots × 3 variants).

## 3. Adding a current quality leaderboard
Catalog data can't measure visual quality. For a campaign (or whenever the shortlist is close),
spend 2–3 searches on a current public preference leaderboard — e.g. Artificial Analysis'
image-to-video, text-to-video, text-to-image and image-editing arenas, or LMArena — and map the
leaderboard names to Venice ids yourself (you're better at that than string matching). Save:
```json
{"source": "Artificial Analysis image-to-video arena", "date": "2026-11-02",
 "entries": [{"match": "kling-v3-pro", "score": 1302}, {"match": "veo3.1-full", "score": 1288},
             {"match": "seedance-2-5", "score": 1271}]}
```
`match` is a substring of the Venice model id (longest match wins); `score` is the arena Elo or any
higher-is-better number. Run `recommend --ranks projects/<slug>/ranks.json`. Cover the main candidates
of each job; unranked models fall back to the prior. Note the leaderboard date in the strategy doc.

## 4. Presenting the choice
Show a compact table (or use the interface's multiple-choice question tool when available) with
3–4 options per job — Premium, Balanced, Budget, plus Newest if present — each with price per clip
and ≈ per video. Ask once for the video model (i2v) and once for the keyframe model; default the rest
(scene → Balanced, i2v_audio → Balanced, tts → first listed) unless the user cares. If the user is
away, pick Balanced for everything, say so in one line, and mention the Premium alternative.
Record the choice with `choose`; never silently switch models mid-batch.

## 5. How the recommender scores models
- **Capability filter** per job from ids and `model_spec` (mode: image-to-video, reference-to-video,
  text-to-video, upscale; edit vs. generation; audio, end-frame, durations, resolutions, privacy).
  Offline or deprecated models are dropped.
- **Recency:** family and version are parsed from ids (`veo3.1-full` → veo 3.1, `kling-v3-pro` →
  kling 3, `seedance-2-5` → seedance 2.5). Only the newest two versions per family stay; the newest
  gets a bonus; models created ≤60 days ago are flagged 🆕 and get a small bonus.
- **Tier** from id words: pro/full/max/ultra/premium → premium; fast/turbo/flash/mini/lite → fast.
- **Quality** = leaderboard score when `--ranks` matches, else a small dated family prior (only a
  tie-breaker; unknown new families start mid-pack so they aren't buried) + tier + recency.
- **Price:** per second for video (so 4 s and 5 s quotes compare), per image for images.

## 6. Capability rules that override scores
- People on screen → Kling or Veo families; Seedance `-basic` models reject person-bearing inputs.
- Diegetic sound needed (pour, fizz, crunch, ambience) → an `i2v_audio` pick with `audio: true`;
  otherwise `audio: false` (cheaper) and VO/music in post.
- Exact first and last frames (loops, match cuts) → a model with end-frame support.
- Consistent character/mascot across shots → `r2v` pick (e.g. Kling O3 `elements`).
- Product compositing needs an edit model that takes ≥2 input images (the keyframe job filters for it).
- Confidential product → Private option, or the client's explicit OK for Anonymized models.
- Long single takes (10–30 s) → check `max dur` in the table.

## 7. Cost model
Per finished ~15 s video: 3 shots × 2 takes × (quoted clip price) + 9 keyframes × (image price) +
cents for TTS/QA/music. At Venice list prices (Nov 2026) Balanced tiers ≈ $5–8 per video and
Veo-class Premium ≈ $15–25; Tokentide's multiplier (0.50–0.90× through the UTC day, Low Tide down to
0.20×) takes 10–50% off that. `video.py run --dry-run` shows the exact quote before anything is spent,
and `budget.py --live` shows real charges and savings afterwards.

## 8. Fallback snapshot (Nov 2026) — use only if the API is unreachable
Image edit (keyframes): nano-banana-pro-edit (1K $0.18 · 2K $0.23 · 4K $0.35), seedream-v5-pro-edit
($0.06 + $0.00345/extra image), gpt-image-2-edit (high 1K $0.34), qwen-image-3-pro-edit ($0.05),
flux-2-max-edit ($0.12), firered-image-edit ($0.04, Private, single input).
Image generation: seedream-v5-pro (1K $0.06 · 2K $0.11), nano-banana-2 (1K $0.10), nano-banana-pro
(1K $0.18), gpt-image-2 (1K high $0.26), qwen-image-2-1-turbo ($0.02), z-image-turbo ($0.01).
Video: veo3.1-full-image-to-video (from $1.76 per 4 s at 720p/1080p, $2.64 at 4K), veo3.1-fast
(from $0.66), kling-v3-pro/standard-image-to-video (end frame, ≤15 s), kling-o3-pro-reference-to-video
($0.112/s silent, $0.140/s with audio), seedance-2-0/2-5 image-to-video (first+last frame, native
audio, 4–15 s / 4–30 s), wan-2.6–3.0, ltx-2.3/2.5, grok-imagine-*-private (R2V ≈ $0.063/s 480p,
$0.088/s 720p), runway-gen4-5, gemini-omni-flash-1-1, topaz-video-upscale (≈ $0.013/s 720p,
$0.025/s 1080p, $0.10/s 4K). Sora 2 is not on Venice (OpenAI removed its Sora 2 API on 24 Sep 2026).
Audio: tts-kokoro (default), tts-chatterbox-hd / tts-minimax-speech-02-hd (cloning),
nvidia/parakeet-tdt-0.6b-v3 (transcription).
