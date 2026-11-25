# Choosing models (always from the live catalog)

New image, video, voice and music models land on Venice almost every week, and Tokentide's prices move
through the UTC day. So the skill never hard-codes a model: every new request starts by asking the user how
to choose them, checks the live catalog, prices the choice, and tells the user the total before anything is
made. Specs then refer to the choice by alias (`@i2v`, `@keyframe`, …).

## Contents
1. The first question
2. Path A: the user names the models
3. Path B: recommended levels (Essential / Pro / Max): Arena ratings and the skill's estimate
4. Presenting the levels and announcing the models
5. The total price: quote or estimate
6. How the levels are picked
7. Apps without a shell
8. Detailed options per job and switching later
9. Capability rules that override ratings
10. Cost model
11. Fallback snapshot (Nov 2026) — only if the API is unreachable

## 1. Default proposal & the first question
Unless the user explicitly states different models in their request, **ALWAYS propose by default**:
- **Video:** **Seedance 2.5 Flash** (`seedance-2-5-flash-image-to-video-basic`, native sound included;
  `seedance-2-5-flash-reference-to-video-basic` for R2V)
- **Voice-over:** **ElevenLabs TTS v4 Turbo** (`elevenlabs-tts-v4-turbo`)
- **Images & Music:** live Pro-level picks from `models.py tiers` (Arena-rated for images; skill estimate
  for music)

Ask in the user's language, with the multiple-choice question tool when the app has one (plain words, no
model jargon):

> Before we generate anything: by default I recommend **Seedance 2.5 Flash** for video and **ElevenLabs
> TTS v4 Turbo** for voice-over (paired with the best-value live image and music models on Tokentide), and
> I'll show you the full itemized estimated quote for the whole video (video, images, voice-over, music and
> SFX) before spending anything. How would you like to choose the models?
> 1. **Use the recommended defaults (Recommended).** Seedance 2.5 Flash for video + ElevenLabs v4 Turbo for
>    voice-over + live Pro image & music models.
> 2. **Compare Essential / Pro / Max levels.** Show three price/quality tiers from Tokentide's live catalog
>    (rated by the Arena leaderboard for video & images).
> 3. **I'll choose my own models.** Tell me which models you'd like; I'll check Tokentide availability and
>    give you the full itemized quote first.

- For a new batch in a project that already has models, add: **keep the same models as last time**
  (then re-price the whole video with `models.py cost`, §5).
- Skip the question when the user already explicitly named models or a level in the request (follow their
  exact choice, filling any unnamed jobs from the default stack), or when the request is research/strategy
  only (ask and quote before production starts).
- User away (said to proceed without them): use `--tier default` (Seedance 2.5 Flash + ElevenLabs v4 Turbo)
  if its total fits the budget cap, else Essential, and say so in one line.
- **Hard gate:** NEVER run any paid image, video, voice-over, or music generation until you have shown the
  user the full itemized estimated quote for the whole video (§5) and received confirmation!

## 2. Path A: the user names the models
1. Find each name in the live catalog (names as the user wrote them, any spelling):
   ```bash
   python3 SKILL_DIR/scripts/models.py match "Kling 3 Pro" "nano banana 2.1" "ElevenLabs v4 Turbo" --project P
   ```
   It answers AVAILABLE (with the model ids and the jobs each can do: `i2v` video, `keyframe` product images,
   `scene` backgrounds, `tts` voice, `music`, `sfx`) or NOT AVAILABLE on Tokentide, with the closest models.
2. Use only models Tokentide offers. For one that isn't available, say so plainly ("Sora 2 isn't available on
   Tokentide") and offer the closest available models, or the recommended level for that part (path B).
   One name can cover several jobs (Kling makes video and images): use it only for the jobs the user meant.
   **ElevenLabs TTS v4 is never a default:** when the user says "ElevenLabs v4", use ElevenLabs TTS v4 Turbo
   (`match` suggests it); choose `elevenlabs-tts-v4` only if they explicitly want that exact, non-Turbo model.
3. Jobs the user didn't name: fill them from the **default stack** (`models.py tiers` → `--tier default`:
   **Seedance 2.5 Flash** for video, **ElevenLabs TTS v4 Turbo** for voice-over, Pro-level images & music)
   and state every model you filled in, so the user can change any of them.
4. `python3 SKILL_DIR/scripts/models.py choose --project P --tier default <user_overrides...>`
   (`i2v_audio`, for shots with real sound, defaults to the video model when it makes sound — Seedance 2.5
   Flash includes native audio).
5. Show the **complete itemized estimated quote for the whole video** (§5: video + images + voice-over +
   music + SFX = total) and wait for an OK before the first paid step.

## 3. Path B: recommended levels: Arena ratings and the skill's estimate
```bash
python3 SKILL_DIR/scripts/models.py tiers --project P --videos <n>
```
- **Video and images** are rated by the **Arena leaderboard** (arena.ai): Bradley-Terry scores from blind,
  pairwise votes by real people. Arena publishes its leaderboards as an open dataset under **CC BY 4.0**
  (https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset), which allows commercial reuse with credit.
  The script reads it through Hugging Face's dataset viewer (plain JSON, no website scraping) and keeps it a day
  in `P/arena.json`. Boards: image to video (video clips), multi-image editing (product images: a real product
  placed into a scene; image editing overall when that category can't be read), text to image (backgrounds).
- **Voice and music** have no open leaderboard the skill may use, so their levels come from **the skill's own
  estimate**: a rough prior per maker or model family, adjusted for recency (newest version first, 🆕) and
  tier words (HD/Max vs Turbo/Flash). Present those as "our recommendation", never as independent ratings.
- It takes the **30 most recent models** per job from the live catalog, prices them (free quotes for video and
  music, catalog prices for images and voices) and writes `P/model_tiers.md` (read it) and `.json`: per job the
  Essential, Pro and Max model, and per level the cost per video and for the batch, marked quote or estimate.
- **Not rated by Arena** lists recent video and image models Arena doesn't rate yet (new, or not on its
  leaderboard): they are not offered as levels. Offer a brand-new one as a test take instead (§8).
- **Credit Arena** whenever you show its ratings, with the credit line at the top of `model_tiers.md` (or in
  short: "Quality ratings: Arena leaderboard (arena.ai), CC BY 4.0; combined with Tokentide prices; Arena doesn't
  endorse these recommendations"). Don't use Arena's logo.
- Arena's dataset unreachable (no network, or a sandbox that allows only api.tokentide.app: allow
  `datasets-server.huggingface.co`): the script uses an older `arena.json` if there is one (it says so), else
  every level rests on the estimate and `model_tiers.md` says "No leaderboard ratings this time"; tell the user
  the levels are "estimated, without independent ratings". `--ratings none` does the same on purpose;
  `--refresh-ratings` reads the dataset again; `--ranks FILE` uses a hand-made ratings file instead.
- Then ask the user to pick a level (§4) and `python3 SKILL_DIR/scripts/models.py choose --project P --tier <level>`.

## 4. Presenting the levels and announcing the models
Ask in the user's language, in plain words: no scores, no frontier, no per-second prices. Use the batch totals
from `model_tiers.md`:

> Here are three levels for your 3 videos. Video and image models are rated by the Arena leaderboard
> (arena.ai, blind votes by real people); for voice and music it's our own recommendation. Prices are Tokentide's
> prices right now.
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
> - **Video:** Seedance 2.5 (rated #2 on the Arena leaderboard for turning images into video; sound included)
> - **Product images:** Grok Imagine 2.0 (rated #7 on Arena for editing with several images: it places your real
>   product in new scenes)
> - **Backgrounds:** Grok Imagine 2.0
> - **Voice:** Inworld TTS 1.5 Max (our recommendation at this level)
> - **Music:** Sonilo V1.1 (an original track for each video)
>
> Quality ratings: Arena leaderboard (arena.ai), CC BY 4.0.
>
> **Quote: $35.98 for 3 videos** at today's prices. Extra retakes would cost more. Shall I start?

(The models and prices in these examples are illustrative; use the ones in `model_tiers.md` and `cost`.)

## 5. Mandatory whole-video estimated quote (ALWAYS before any generation!)
**NEVER start paid generation (keyframes, video clips, voice-over, music, or SFX) without first showing
the user the itemized estimated quote for the WHOLE video and getting confirmation.** Run:
```bash
python3 SKILL_DIR/scripts/models.py cost --project P --videos <n>          # the chosen models
python3 SKILL_DIR/scripts/models.py cost --project P --tier default --videos <n>   # default stack before choosing
```
Pass the **real planned numbers** for this specific video (`--shots`, `--takes`, `--clip-seconds`,
`--resolution`, `--audio-shots`, `--keyframes`, `--scenes`, `--vo-chars`, `--music-seconds`, `--sfx`,
`--cutouts` — set any unused part to `0`, e.g. `--vo-chars 0` for a music-only film or `--shots 0` for a
pure real-screenshot guide). Show the user every cost component cleanly:
- **Video clips** (model, count × length, subtotal)
- **Images / keyframes & scenes** (model, count, subtotal — or `$0` if using real captures/photos)
- **Voice-over** (model, approximate character count, subtotal — or `$0` if none)
- **Music & SFX** (model, duration/count, subtotal — or `$0` if none)
- **Total estimated quote** (`QUOTE` vs `ESTIMATE`, plus Low Tide price when cheaper)
It prints **QUOTE** or **ESTIMATE**:
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
- Only rated (Arena, or the estimate for voice and music) and priced models count. They form a **price/quality frontier**: the models no other model beats on
  both price and quality. Its price range is split in three equal steps (on a log scale):
  **Essential** = the best rated in the cheapest third; **Pro** = the best rated up to the second third;
  **Max** = the best rated at any price. With three or more frontier models the levels are three different models;
  with fewer, levels share a model (§4 says how to explain it). A model off the frontier is never offered: some
  other model is both cheaper and better rated.
- Unit prices: per second of video (at the planned resolution, or the nearest one the model offers), per image,
  per 1,000 characters of voice, per track.
- Some models are never picked by default (ElevenLabs TTS v4: the skill uses ElevenLabs TTS v4 Turbo instead), so
  they never appear as a level or an option.
- Clips with real sound use the level's video model when it makes sound, else the best-rated one with sound that
  costs no more. Sound effects use the music model's maker when it has one.

## 7. Apps without a shell
Same flow with the connector's tools: `list_models` (types `video`, `inpaint`, `image`, `tts`, `music`) for the
available models and their prices, `get_model` for a model's release date and details, `price_video_job` /
`price_music_job` for free quotes. For ratings, read Arena's dataset with your web tool as JSON, e.g.
`https://datasets-server.huggingface.co/first-rows?dataset=lmarena-ai/leaderboard-dataset&config=image_to_video&split=latest`
(configs `image_to_video`, `image_edit`, `text_to_image`; use the `overall` rows, or `multi_image_edit` for product
images), and judge voice and music yourself (say it's your recommendation). Pick the three levels by the same rules
(§6) among recent models, add up the plan (§10) by hand, credit Arena, and call the total a quote only if every
line came from a quote or a listed price; otherwise an estimate.

## 8. Detailed options per job and switching later
`models.py recommend --project P` lists Premium / Alt premium / Balanced / Budget / Newest
🆕 / Private options per job (including `r2v` and `t2v`) with max duration, resolution, sound, end frame, privacy
and price. Use it to switch one job, to find a Private model for a confidential product, or when a 🆕 model
appears: offer one test take next to the current pick. Switch with `models.py choose --project P <job>=<id>`;
never switch silently mid-batch. Re-run `tiers` (or `recommend`) before each new batch.

## 9. Capability rules & defaults
- **Required defaults (always propose first unless the user specifies otherwise):** **Seedance 2.5 Flash**
  (`seedance-2-5-flash-image-to-video-basic`) for video and **ElevenLabs TTS v4 Turbo**
  (`elevenlabs-tts-v4-turbo`) for voice-overs.
- **If Seedance `-basic` returns `409 needs_consent` on a person-bearing shot** → explain plainly to the
  user and offer switching those shots to **Kling (V3 / O3)** or **Veo (3.x)** (and `@r2v` with `elements`
  for multi-shot facial continuity). Never silently override the user's model choice without telling them.
- **Web apps / SaaS / software video guides** → real captured UI screenshots animated by `assemble.py`
  (`shots[].image` + focal zoom/pan) cost **$0** in image/video generation. Pass the actual number of
  generative shots to `models.py cost` (e.g. `--shots 0` or `--shots 1` if only adding a conceptual intro,
  plus `--music-seconds` and `--vo-chars`) so the quote reflects real spend accurately!
- **Multi-person / multi-reference compositing** → check `maxInputImages` (`models.py show <id>`):
  compositing a scene + two people needs an edit model supporting ≥3 input images (some support up to 8).
- Diegetic sound needed (pour, ocean, footsteps, ambience) → an `i2v_audio` pick with sound; otherwise
  silent clips (cheaper) and voice/music in post.
- Exact first and last frames (loops, match cuts, facial anchoring) → a model with end-frame support.
- Consistent character/person/mascot across shots → `r2v` pick (e.g. Kling O3 `elements`).
- Confidential or unreleased material → Private option, or the user's explicit OK for Anonymized models.
- Long single takes (10–30 s) → check the max duration (`models.py show <id>`).
- Voice-over in another language → check the voice model speaks it (`audio.py voices`): the voice levels are
  an estimate and don't check languages.
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
Audio: tts-kokoro (default), tts-chatterbox-hd / tts-minimax-speech-02-hd, elevenlabs-tts-v4-turbo (queued audio
route, per 1,000 characters), elevenlabs/scribe-v2 (transcription default; fallback nvidia/parakeet-tdt-0.6b-v3).
Any total from this snapshot is an **estimate** (§5).
