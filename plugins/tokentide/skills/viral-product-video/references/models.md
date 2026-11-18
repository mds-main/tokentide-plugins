# Choosing models (always from the live catalog)

New image, video, voice and music models land on Venice almost every week, and Tokentide's prices move
through the UTC day. So the skill never hard-codes a model: every new request starts by asking the user how
to choose them, checks the live catalog, prices the choice, and tells the user the total before anything is
made. Specs then refer to the choice by alias (`@i2v`, `@keyframe`, …).

## Contents
1. The first question
2. Path A: the user names the models
3. Path B: recommended levels (Essential / Pro / Max) from Artificial Analysis
4. Presenting the levels and announcing the models
5. The total price: quote or estimate
6. How the levels are picked
7. Apps without a shell
8. Detailed options per job and switching later
9. Capability rules that override ratings
10. Cost model
11. Fallback snapshot (Nov 2026) — only if the API is unreachable

## 1. The first question
Ask it **first, before anything else** in a new request that will make media, in the user's language, with
the multiple-choice question tool when the app has one. Plain words, no model jargon:

> Before I start: how would you like to choose the AI models that will make your videos (the video itself,
> the images, the voice and the music)?
> 1. **I'll choose them.** Tell me which models you'd like; I'll check they're available on Tokentide and
>    give you the total price before anything is made.
> 2. **Recommend them for me.** I'll compare the newest models on Tokentide using independent quality ratings
>    from Artificial Analysis and offer you three levels: Essential, Pro and Max, each with its price.

- For a new batch in a project that already has models, add a third option: **keep the same models as last time**
  (then re-price them with `models.py cost`, §5).
- Skip the question when the user already named models or a level in the request (follow it), or when the
  request is research or strategy only (ask when production starts).
- User away (said to proceed without them): take path B, choose Pro if its total fits the budget cap, else
  Essential, and say so in one line.

## 2. Path A: the user names the models
1. Find each name in the live catalog (names as the user wrote them, any spelling):
   ```bash
   python3 SKILL_DIR/scripts/models.py match "Kling 3 Pro" "nano banana 2.1" "ElevenLabs v4" --project P
   ```
   It answers AVAILABLE (with the model ids and the jobs each can do: `i2v` video, `keyframe` product images,
   `scene` backgrounds, `tts` voice, `music`, `sfx`) or NOT AVAILABLE on Tokentide, with the closest models.
2. Use only models Tokentide offers. For one that isn't available, say so plainly ("Sora 2 isn't available on
   Tokentide") and offer the closest available models, or the recommended level for that part (path B).
   One name can cover several jobs (Kling makes video and images): use it only for the jobs the user meant.
3. Jobs the user didn't name: fill them from the Pro level of `models.py tiers` (path B, no question needed)
   and say which models you added, so the user can change them.
4. `python3 SKILL_DIR/scripts/models.py choose --project P i2v=<id> keyframe=<id> scene=<id> tts=<id> music=<id> sfx=<id>`
   (`i2v_audio`, for shots with real sound, defaults to a video model that makes sound: the user's video model
   when it does).
5. Give the total (§5) and wait for an OK before the first paid step.

## 3. Path B: recommended levels from Artificial Analysis
Quality ratings come from **Artificial Analysis** (artificialanalysis.ai), whose leaderboards rank models by
blind human preference votes (Elo). Prices come from Tokentide. Read the five leaderboards with your web tools,
one page each (find a moved page from artificialanalysis.ai's menu: Image, Speech, Video, then the leaderboards):

| Board key | What it rates | Page (Nov 2026) |
|---|---|---|
| `video` | turning an image into video (Overall) | https://artificialanalysis.ai/video/leaderboard/image-to-video |
| `image_edit` | editing images: product shots | https://artificialanalysis.ai/image/leaderboard/editing |
| `image` | creating images from text: backgrounds | https://artificialanalysis.ai/image/leaderboard/text-to-image |
| `tts` | voices (text to speech, providers' voices) | https://artificialanalysis.ai/text-to-speech/leaderboard/provider-voice |
| `music` | instrumental music | https://artificialanalysis.ai/music/leaderboard/instrumental |

Save what you read to `P/ranks.json`, names exactly as the leaderboard writes them (all rows, or at least the
top 40 of each board); the script matches them to Tokentide's models ("Dreamina Seedance 2.5" → Seedance 2.5,
"Eleven v4" → ElevenLabs TTS v4):
```json
{"source": "Artificial Analysis", "date": "2026-11-18",
 "boards": {
   "video": {"url": "https://artificialanalysis.ai/video/leaderboard/image-to-video",
             "entries": [{"rank": 1, "name": "Dreamina Seedance 2.5", "elo": 1161},
                         {"rank": 4, "name": "MiniMax H3 (768p)", "elo": 1134}]},
   "image_edit": {"entries": [{"rank": 1, "name": "MAI-Image-2.7", "elo": 1215}]},
   "image": {"entries": []}, "tts": {"entries": []}, "music": {"entries": []}}}
```
Then:
```bash
python3 SKILL_DIR/scripts/models.py tiers --project P --ranks P/ranks.json --videos <n>
```
- It takes the **30 most recent models** per job from the live catalog, attaches the ratings, prices the rated
  ones (free quotes for video and music, catalog prices for images and voices) and writes `P/model_tiers.md`
  (read it) and `.json`: per job the Essential, Pro and Max model, and per level the cost per video and for the
  batch, marked quote or estimate.
- **Not rated yet** lists recent models without a rating. If one appears on a leaderboard under another name,
  add an entry with its Tokentide `id` (`{"name": "Kokoro 82M v1.0", "id": "tts-kokoro", "elo": 1060}`) and
  run `tiers` again. Never invent a score: unrated models are not offered as levels (offer a brand-new one as a
  test take instead, §8).
- Reuse `P/ranks.json` when it is less than 7 days old; read the leaderboards again for an older file. Read only
  these pages, as a person would; don't crawl the site. Credit Artificial Analysis whenever you show ratings.
- No web access: run `tiers` without `--ranks`; the levels then rest on the skill's own estimate. Tell the user
  the levels are "estimated, without independent ratings".
- Then ask the user to pick a level (§4) and `python3 SKILL_DIR/scripts/models.py choose --project P --tier <level>`.

## 4. Presenting the levels and announcing the models
Ask in the user's language, in plain words: no Elo, no frontier, no per-second prices. Use the batch totals
from `model_tiers.md`:

> Here are three levels for your 3 videos. Quality ratings come from Artificial Analysis; prices are
> Tokentide's prices right now.
> - **Essential**: the best-rated models among the most affordable ones. Ideal for testing ideas and posting
>   often. Quote: $5.80.
> - **Pro**: higher-rated models at a higher price, the best value in the middle of the range. For your main
>   posts and ads. Quote: $36.
> - **Max**: the highest-rated models on Tokentide today, whatever the price. For launches and hero videos.
>   Quote: $38.
> Which level would you like?

- Write "Quote: $X" when the table says quote, and "About $X (estimate)" when it says estimate (§5).
- When two levels use the same model for a job, say it in one line: "For music, all three levels use the same
  model: it is both the best rated and the most affordable." That is accurate, not a gap.
- Name the levels like this, and keep them the same throughout the conversation:

| Language | Essential | Pro | Max |
|---|---|---|---|
| English, German | Essential | Pro | Max |
| Spanish | Esencial | Pro | Max |
| French | Essentiel | Pro | Max |
| Portuguese | Essencial | Pro | Max |
| Italian | Essenziale | Pro | Max |
| Japanese | エッセンシャル | プロ | マックス |
| Chinese | 基础版 | 专业版 | 旗舰版 |
Other languages: translate "Essential" naturally and keep "Pro" and "Max".

Once the user picks (and after `choose`), tell them the models in plain words, one line per part, saying only
what the data supports (its rating, sound included, price), then the total from `models.py cost` (§5):

> Pro it is. These are the models that will make your videos:
> - **Video:** Seedance 2.5 (rated #1 by Artificial Analysis for turning images into video; sound included)
> - **Product images:** Kling Image 4.0 (rated #6 for editing images: it places your real product in new scenes)
> - **Backgrounds:** MAI Image 2.7 Flash
> - **Voice:** ElevenLabs v4 Turbo (rated #2 for voices)
> - **Music:** Lyria 3 Pro (an original track for each video)
>
> **Quote: $35.98 for 3 videos** at today's prices. Extra retakes would cost more. Shall I start?

(The models and prices in these examples are illustrative; use the ones in `model_tiers.md` and `cost`.)

## 5. The total price: quote or estimate
Always give the user a total in dollars before anything is made:
```bash
python3 SKILL_DIR/scripts/models.py cost --project P --videos <n>          # the chosen models
python3 SKILL_DIR/scripts/models.py cost --project P --tier pro --videos <n>   # a level, before choosing
```
It prices a plan (§10; override with `--shots`, `--takes`, `--clip-seconds`, `--resolution`, `--music-seconds`, …)
line by line and prints **QUOTE** or **ESTIMATE**:
- **QUOTE**: every line is a live Tokentide price: a free quote for video, music, sound effects and queued
  voices, the catalog price × today's multiplier for images and other voices. Tell the user "Quote: $X for N
  videos at today's prices", and that retakes beyond the plan cost extra. Prices change through the UTC day (they
  fall towards 00:00 UTC) and are locked when each job is queued.
- **ESTIMATE**: a price couldn't be fetched live (a quote failed, a model has no price; the output says which),
  so an earlier price stands in or the line is missing. Say it plainly: "About $X. This is an estimate: the final
  price may vary."
- It also compares the total with the project's budget cap (ask before raising it) and, when cheaper, shows the
  Low Tide price (slower, best-effort: offer it for batches that can wait).
- Once the specs exist, `video.py run --spec … --dry-run` quotes each video exactly; re-quote before a big batch.

## 6. How the levels are picked
- Per job: the 30 most recent models of that kind in the live catalog (image-to-video models for video, image
  editors with ≥ 2 input images for product shots, image generators for backgrounds, voices from both
  `/audio/speech` and the queued audio route, music models).
- Only rated, priced models count. They form a **price/quality frontier**: the models no other model beats on
  both price and quality. Its price range is split in three equal steps (on a log scale):
  **Essential** = the best rated in the cheapest third; **Pro** = the best rated up to the second third;
  **Max** = the best rated at any price. With three or more frontier models the levels are three different models;
  with fewer, levels share a model (§4 says how to explain it). A model off the frontier is never offered: some
  other model is both cheaper and better rated.
- Unit prices: per second of video (at the planned resolution, or the nearest one the model offers), per image,
  per 1,000 characters of voice, per track.
- Clips with real sound use the level's video model when it makes sound, else the best-rated one with sound that
  costs no more. Sound effects use the music model's maker when it has one.

## 7. Apps without a shell
Same flow with the connector's tools: `list_models` (types `video`, `inpaint`, `image`, `tts`, `music`) for the
available models and their prices, `get_model` for a model's release date and details, `price_video_job` /
`price_music_job` for free quotes, and the leaderboards above. Pick the three levels by the same rules (§6) among
recent, rated models, add up the plan (§10) by hand, and call the total a quote only if every line came from a
quote or a listed price; otherwise an estimate.

## 8. Detailed options per job and switching later
`models.py recommend --project P [--ranks P/ranks.json]` lists Premium / Alt premium / Balanced / Budget / Newest
🆕 / Private options per job (including `r2v` and `t2v`) with max duration, resolution, sound, end frame, privacy
and price. Use it to switch one job, to find a Private model for a confidential product, or when a 🆕 model
appears: offer one test take next to the current pick. Switch with `models.py choose --project P <job>=<id>`;
never switch silently mid-batch. Re-run `tiers` (or `recommend`) before each new batch.

## 9. Capability rules that override ratings
- People on screen → Kling or Veo families; Seedance `-basic` models reject person-bearing inputs.
- Diegetic sound needed (pour, fizz, crunch, ambience) → an `i2v_audio` pick with sound; otherwise silent clips
  (cheaper) and voice/music in post.
- Exact first and last frames (loops, match cuts) → a model with end-frame support.
- Consistent character/mascot across shots → `r2v` pick (e.g. Kling O3 `elements`).
- Product compositing needs an edit model that takes ≥ 2 input images (the keyframe job filters for it).
- Confidential product → Private option, or the client's explicit OK for Anonymized models.
- Long single takes (10–30 s) → check the max duration (`models.py show <id>`).
- Voice-over in another language → check the voice model speaks it (`audio.py voices`); the speech leaderboard is
  mostly English.
- A key in privacy mode `private` hides background removal, most premium edit and video models and every music
  model (the reports warn at the top): the user sets mode `all` or `private_text` in the dashboard.

## 10. Cost model
The plan `cost` and `tiers` price, per video: 3 shots × 2 takes of 5 s at 1080p (1 shot with real sound), 3
product images per shot, 3 backgrounds, ~260 characters of voice-over (~15 s), a 20 s music track and 2 sound
effects of 2 s; plus 2 product cut-outs for the project. Pass the brief's numbers (`--videos`, `--clip-seconds`,
…). At Venice list prices (Nov 2026) budget levels cost ≈ $1–3 per video and top video models ≈ $10–25;
Tokentide's multiplier (0.50–0.90× through the UTC day, Low Tide down to 0.20×) takes 10–50% off list.
`budget.py --live` shows real charges and savings afterwards.

## 11. Fallback snapshot (Nov 2026) — use only if the API is unreachable
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
Audio: tts-kokoro (default), tts-chatterbox-hd / tts-minimax-speech-02-hd, elevenlabs-tts-v4 (queued audio
route, per 1,000 characters), nvidia/parakeet-tdt-0.6b-v3 (transcription).
Any total from this snapshot is an **estimate** (§5).
