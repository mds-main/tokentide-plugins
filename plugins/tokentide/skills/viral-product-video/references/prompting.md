# Prompting: keyframes, edits, motion, voice

## Contents
1. The image-first workflow (why)
2. Keyframe prompts (edit / multi-edit / generate)
3. Motion prompts for image-to-video
4. Camera & light vocabulary
5. Consistency toolkit
6. Artifact avoidance rules
7. Model-specific notes
8. Native audio cues
9. Voice-over scripts
10. Worked examples

## 1. The image-first workflow
Text-to-video re-imagines the product every take: shape, label and logo drift. Image-to-video locks
composition, lighting and — most important — the product in frame 1. So: real product photo →
cutout (`bg-remove`) → keyframe composite (`multi-edit` / `edit`) → QA the still (cheap) →
animate (`video.py`) → QA the clip → add text, logos and captions in post. Never ask a model to
render label text or a logo; composite the real asset instead.

## 2. Keyframe prompts
**Multi-edit (product into a scene)** — inputs `[scene, product_cutout]` (optionally a third style
reference). Structure:
```
Place the [product descriptor] from image 2 [position/action] in the scene of image 1.
[Lighting matching the scene: direction, quality, time of day]. [Camera: phone shot / 50mm, shallow DoF].
[Mood/style: UGC phone look | premium studio | editorial].
```
The script appends the fidelity clause automatically: keep shape, proportions, colors, label text,
logo and placement identical; no added text. Keep it.

**Edit (one real photo)** — restyle background/lighting/context of a real product photo:
"Same bottle, now on a gym bench with condensation droplets, harsh overhead gym light, phone photo."

**Generate (no product)** — scenes, backgrounds, environments, props, B-roll without the product:
"Empty sunlit car dashboard, heat haze, afternoon, shot from the passenger seat, photoreal, 9:16."
Then composite the product with multi-edit. Avoid generating the product itself: it will be invented.

**Prompt hygiene:** one subject, one action, one light direction. Specify the time of day and light
direction so frames match across shots. Ask for 3 variants and pick, rather than over-prompting.
Use `--resolution 2K` for keyframes (animation models downscale anyway; 2K keeps label detail).

## 3. Motion prompts for image-to-video
The image already defines the content: **describe motion, camera and timing**, not the scene.
Venice's docs say this explicitly for image-to-video.
```
[SHOT] Vertical 9:16, [shot size], [camera move], [lens feel].
[ACTION, timed] 0–1s: [hook action]. 1–3s: [secondary action]. 3–5s: [settle / end pose].
[SUBJECT LOCK] The [product descriptor] stays rigid; label, logo and proportions do not change.
[LIGHT/STYLE] [keep lighting], [photoreal phone footage | premium commercial].
[AUDIO] [ambient cues, no music, no speech]   ← only for models with native audio
```
Negative prompt (if supported): `morphing, warping product, warped label, extra fingers, distorted
hands, melting, flicker, text, subtitles, watermark, logo changes, extra objects, low quality, jitter`.
Keep prompts short (2–5 sentences). Length limits are per model (read `models.py --show`).

## 4. Camera & light vocabulary the models follow
Shot size: extreme close-up/macro · close-up · medium · wide · top-down/flat lay · POV/first-person.
Moves: locked-off · slow push-in · pull-out · orbit 20–30° left/right · tilt up/down · pan · crane up ·
handheld micro-jitter (UGC feel) · whip pan (for transitions) · dolly-zoom (sparingly).
Lens feel: 24 mm wide · 50 mm natural · 85–100 mm macro/portrait · shallow depth of field · rack focus.
Light: soft window light from left · golden hour backlight · hard noon sun · overhead fluorescent ·
studio softbox with rim light · neon/RGB practicals · candle-lit.
Look: shot on a phone · UGC selfie · documentary · commercial studio · editorial · stop-motion · claymation.

## 5. Consistency toolkit
- **Product bible descriptor** reused verbatim in every keyframe and motion prompt.
- **Same reference photos** for every shot; same light direction & time of day across shots.
- **Fixed seed** for scene series (image `--seed`; keyframes add +i per variant).
- **First/last frames:** `end_image` to land a shot exactly (match cuts, loops: end on the first frame).
- **Characters:** a character sheet image reused as reference — Kling O3 reference-to-video `elements`
  (up to 4), Seedance R2V for non-human characters (no human faces on Seedance basic models).
- **Continuity across clips:** Seedance R2V Extend/Stitch modes (prompt-driven, e.g.
  `‹Video 1› + a smooth seamless cut + followed by ‹Video 2›`).

## 6. Artifact avoidance rules
- One main action per shot; 4–6 s clips (quality drops with length).
- Slow camera moves for products; fast moves only for transitions.
- Keep hands away from labels; or show the product alone and cut to hands separately.
- No model-rendered text; all text in post.
- Liquids, fabric, hair, pours: generate 3 takes and pick.
- Transparent/reflective products: simplify the background, avoid complex reflections.
- If a take morphs the product twice in a row: shorten, simplify motion, or switch model —
  don't keep re-rolling the same prompt (qa-rubric.md has the decision tree).

## 7. Family-specific notes (pick the actual model with `models.py recommend`)
These describe model *families* as of Nov 2026; the newest version in a family usually keeps the
same behaviour. Check the live options table for current versions, durations and prices.
- **Kling (V3 / O3):** strong product motion and physics; image-to-video supports an end frame;
  up to ~15 s. O3 reference-to-video takes `elements` (≤4) for consistent characters/objects.
- **Seedance (2.x):** first + last frame, native stereo audio, long takes (2.5: up to 30 s).
  Image/reference-to-video take the aspect ratio from the input image (the script drops
  `aspect_ratio`). `-basic` models reject person-bearing inputs. R2V supports Extend/Stitch.
- **Veo (3.x Full/Fast):** premium realism and native audio incl. dialogue; short clips (4–8 s);
  priciest — hero shots and paid ads.
- **Wan, LTX:** cheaper drafts and tests; LTX also high resolutions.
- **Grok Imagine:** prefer `-private` variants (zero retention; no charge on moderation rejections).
- **Topaz upscale:** finishing step for a final master only (`video.py upscale`).
- **Image edit families:** Nano Banana (Pro) — best all-round product fidelity; Seedream — cheap and
  strong; GPT Image — crisp detail and text; Qwen/Flux — alternatives. Multi-edit compositing
  needs ≥2 input images (the recommender filters for it).

## 8. Native audio cues (Veo, Seedance, Kling with audio)
Describe diegetic sound only: "ice cubes clink, water pours, room tone, no music, no speech".
Music and VO are added in post (licensing + control). If the model adds unwanted music or speech,
set `audio: false` or keep clip audio low (`audio_mix.keep_clip_audio`, volume 0.3–0.5).

## 9. Voice-over scripts
- 2.3–3.0 spoken words per second (≈35 words for 13 s). `audio.py tts` prints the pace.
- Front-load the hook; one idea per sentence; contractions; second person; numbers as words the TTS
  reads naturally ("forty-one degrees").
- Write for the ear in the target language; for other languages pick a native voice
  (Kokoro voice IDs are prefixed by language, e.g. `af_`/`am_` American English, `bf_` British,
  `ef_`/`em_` Spanish, `ff_` French, `if_` Italian, `pf_` Portuguese, `jf_` Japanese, `zf_` Chinese —
  confirm with `audio.py voices`).
- Avoid claims you can't prove (compliance.md). No fake first-person customer testimonials.

## 10. Worked examples
**Keyframe (multi-edit):** "Place the matte sage-green 750 ml steel bottle with white NOVA wordmark
from image 2 upright on the sunny car dashboard in image 1, hard afternoon sunlight from the left,
heat haze, shallow depth of field, shot on a phone."
**Motion (Kling V3 Pro):** "Vertical close-up, handheld micro-jitter. 0–1s: a hand grabs the bottle
and shakes it toward camera. 1–4s: slow push-in as it settles back. The bottle stays rigid; label and
logo unchanged. Hard afternoon light, photoreal phone footage."
**Motion (Veo 3.1, with audio):** "Locked-off macro. 0–3s: water and ice pour into a glass, cubes clink.
3–5s: condensation drips down the glass. Bottle unchanged. Audio: pouring water, ice clinks, kitchen
room tone, no music, no speech."
