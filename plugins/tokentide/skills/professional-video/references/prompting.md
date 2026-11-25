# Prompting & cinematography: visual grounding, keyframes, motion & sound

## Contents
1. The grounded image-first workflow
2. Keyframe prompts (multi-edit, edit, generate & fidelity modes)
3. Motion prompts for image-to-video & reference-to-video
4. Cinematography, framing, lighting & visual coherence
5. Cross-shot consistency toolkit
6. Artifact avoidance rules
7. Model-family notes
8. Native audio cues
9. Voice-over & narration scripts
10. Worked examples across genres

## 1. The grounded image-first workflow
Pure text-to-video re-invents faces, objects, logos, places and art styles on every take. Lock the visual
truth in still frames FIRST, inspect visually (cheap), and only then animate:
- **Real beings (people, groups, pets):** real multi-angle photos (`assets/people/`) → `multi-edit`
  (`fidelity: "person"` or `"subject"`) → side-by-side likeness QA → animate with person-safe `@i2v` or
  `@r2v` (Kling / Veo) + optional `end_image`.
- **Real readable interfaces, code, charts & documents:** crisp real captures (`assets/captures/`) →
  **NEVER run `@i2v` on readable UI text**; animate directly in `assemble.py` (`shots[].image` + focal
  Ken Burns `edit.zoom` / `edit.fit`) at `$0` gen cost!
- **Real physical products, objects & places:** real photos (+ `bg-remove` cutout for products) →
  `multi-edit` / `edit` (`fidelity: "product"` or `"subject"`) → side-by-side QA → animate `@i2v` → add
  typography and logos in post.
- **Original / stylized / narrative worlds:** approve 1–2 **Style Master** frames + **Character/Asset
  Sheets** first (`assets/references/`), then reuse them as anchors on every shot so the entire video
  shares one unified film grammar.

Never ask an image or video model to spell label text, UI menus, code, titles or logos; render crisp
typography in post (`overlays[]` / `captions.py`) or programmatic PNGs.

## 2. Keyframe prompts (and `fidelity` modes)
`image.py` supports `keyframe.fidelity`: `"product"` (auto for `assets/product/`), `"person"` (auto for
`assets/people/`), `"subject"` (default for any other real reference: places, pets, vehicles, character
sheets), or `"none"` (pure environments / unconstrained creative transforms).

**Multi-edit (2–8 input images depending on model `maxInputImages`)** — explicitly map every image index:
- *Real subject(s) into a scene* (`[scene, ref_1, ref_2…]`):
  `"Place [subject 1 from image 2] and [subject 2 from image 3] naturally into the setting of image 1,
  [action/pose/expression]. Match image 1's light direction and color temperature. [Lens & style]."`
- *Real photo restyled with a Style/Scene anchor* (`[real_photo, scene_or_style_ref]`): preserves natural
  posture, relative scale and geometry automatically while elevating environment or lighting.
- *Stylized world continuity* (`[style_master, character_sheet]`): locks palette, brush/lens texture and
  character proportions across every scene of an animated film, explainer or trailer.

**Edit (1 input image)** — shift lighting, weather, time of day, styling or background of a single real
reference photo while keeping the subject faithful.

**Generate (`mode: "generate"`)** — empty environments, establishing vistas, atmospheric B-roll, abstract
metaphors, Style Masters and Character Sheets. Never use `generate` to invent a real person, real app UI
or real product.

**Prompt hygiene:** one clear focal subject, one primary action, one explicit light direction and color
temperature, consistent lens feel across shots in the same scene. Use `--resolution 2K` and generate
3–4 variants to pick the strongest composition and likeness.

## 3. Motion prompts for image-to-video & reference-to-video
The input keyframe already establishes the scene: **direct motion, camera, pacing and subject stability**,
rather than re-describing every static detail.
```
[SHOT] [16:9 widescreen | 9:16 vertical | 1:1 square], [shot size], [camera move], [lens feel].
[ACTION, timed] 0–2s: [opening motion]. 2–4s: [peak beat]. 4–5s: [settle / end pose].
[SUBJECT LOCK] Keep [faces, hair, outfits | product silhouette, label and logo | architecture | character
design] completely faithful and rigid throughout; zero morphing.
[LIGHT/STYLE] [keep lighting & palette], [35mm cinema | editorial commercial | documentary | 3D tactile].
[AUDIO] [diegetic ambient cues only, no music, no speech]   ← only when audio: true
```
Negative prompt (when supported): `morphing, face distortion, identity drift, warped label, extra fingers,
distorted hands, melting, flicker, unintended text, subtitles, watermark, logo changes, extra limbs, jitter`.
Keep prompts crisp (2–5 sentences); check per-model length limits via `models.py show <id>`.

## 4. Cinematography, framing, lighting & visual coherence
What elevates a video from "AI clips" to cinema is **deliberate directing across shots**:
- **Shot-size rhythm:** alternate establishing wide → medium interaction/action → tight close-up/reaction
  → macro detail/payoff. Never stack three identical static medium shots in a row.
- **Purposeful camera language:** locked-off (clarity/authority) · slow dolly push-in (intimacy, focus,
  building tension) · gentle pull-out (scale reveal) · 20–30° orbit (dimensional hero) · crane/tilt
  (grandeur) · subtle handheld drift (human documentary warmth) · whip pan (kinetic transition only).
- **Lens & depth:** 24 mm expansive architecture/landscape · 35 mm classic cinema · 50 mm natural eye ·
  85 mm flattering portraits/interviews · 100 mm tactile macro · shallow DoF · rack focus.
- **Lighting continuity:** commit to ONE lighting grammar per scene (e.g. golden-hour backlight, crisp
  overcast daylight, soft window key from camera-left, tungsten practical glow, neon rain reflections,
  clean studio softbox + subtle rim) so consecutive cuts feel shot on the same day with the same camera.
- **Aesthetic range:** adapt freely to the request — 35 mm cinema, documentary realism, high-fashion
  editorial, sleek studio commercial, clean 3D motion graphics, hand-drawn/anime, stop-motion/claymation,
  archival film, or clean minimalist product demo.

## 5. Cross-shot consistency toolkit
- **Real people / animals:** multi-angle photos in `assets/people/` + `IDENTITY.md` + `multi-edit`
  (`fidelity: "person"` / `"subject"`) + `@r2v` (`video.reference_images` or Kling O3 `video.elements`) +
  start/end locked keyframes (`image` + `end_image`).
- **Real products / objects / places:** canonical descriptor (≤25 words) + cutout/reference photos +
  consistent light direction.
- **Creative / animated / narrative films:** approved Style Master + Character/Asset Sheets passed into
  `multi-edit`, `--style-ref`, or `@r2v` on every shot; fixed `seed` for matching series.
- **Seamless transitions & loops:** set `end_image` to match the opening composition of the next shot (or
  frame 1 for seamless short-form loops).

## 6. Artifact avoidance rules
- **Short beats (4–6 s):** temporal drift climbs rapidly on long generative clips.
- **Human faces:** keep well-lit, front or 3/4 facing; avoid rapid 180° turns, extreme whip pans across
  faces, or hands/objects passing over eyes.
- **Readable UI, code, charts & text:** NEVER pass through `@i2v` — keep pixel-perfect with `shots[].image`
  + focal Ken Burns motion (`assemble.py`).
- **Products & intricate logos:** slow camera moves; keep hands clear of labels; add crisp logos in post.
- **Complex physics (water, hair, fabric, crowds):** generate 2–3 takes and trim `edit.in`/`out` to the
  cleanest 2–4 s window.
- **Rule of two:** after two failed attempts with one approach, switch strategy (simpler motion, `end_image`,
  different model family, or real photo/clip) rather than blindly re-rolling (`qa-rubric.md`).

## 7. Model-family notes (always select live models with `models.py tiers` / `recommend`)
- **Kling (V3 / O3):** versatile all-rounder for realistic people, products and cinema; V3 I2V supports
  `end_image` (up to ~15 s); O3 Pro R2V supports `elements` (up to 4 consistent people/characters/objects).
- **Veo (3.x Full / Fast):** top-tier photorealism, nuanced human expression, cinematic lighting and rich
  native audio (4–8 s); ideal for hero shots.
- **Seedance (2.5 Flash — default video model / 2.x):** fast, high-value motion, 4–30 s takes, native
  audio, R2V support (`seedance-2-5-flash-reference-to-video-basic`). Note: if a `-basic` variant rejects
  a person-bearing input with `409 needs_consent`, offer Kling V3/O3 or Veo 3.1 for those shots.
- **Wan, LTX, Grok Imagine:** fast/affordable drafts and B-roll; Grok `-private` keeps zero retention.
- **Topaz upscale:** finishing pass on a master (`video.py upscale`).
- **Image edit families:** Nano Banana (Pro / 2.x), Seedream (V5 Pro), GPT Image, Qwen/Flux — check
  `maxInputImages` via `models.py show <id>` when compositing ≥3 inputs.

## 8. Native audio cues (Veo, Seedance, Kling with audio)
Prompt diegetic sound only: "distant rain on glass, soft footsteps on wood, quiet room tone, no music, no
speech." Add voice-over and original score in post for exact mix balance and ducking; disable `audio` on
silent shots to save cost.

## 9. Voice-over & narration scripts
- Pace at **2.3–3.0 words/second** (2.3–2.6 for calm explainers, tutorials and documentaries; 2.6–3.0 for
  high-energy shorts). **Never time-stretch speech (`atempo`):** adjust text, use native speed control, or
  lengthen silent pauses via `audio.py pace`.
- Write for the ear: active verbs, conversational rhythm, spoken-out numbers/acronyms, deliberate pauses.
- Match voice warmth/authority/language (`audio.py voices`), or skip VO completely when pure visuals,
  custom music and minimal titles deliver a stronger emotional impact.

## 10. Worked examples across genres
- **Documentary / Architecture / Real Place (`edit` + `@i2v`, 16:9):**
  Keyframe (`fidelity: "subject"`): *"Same modernist glass courtyard from image 1, transformed to tranquil
  blue-hour twilight with warm interior lights glowing through the windows, calm water reflection, 24mm
  architectural cinema lens."*
  Motion: *"Widescreen 16:9 slow crane glide upward over the courtyard. 0–3s: water ripples gently as warm
  interior light reflects on glass. 3–5s: camera settles framing the full roofline against twilight sky.
  Architecture and geometry stay completely rigid."*
- **Stylized Narrative / Explainer (`multi-edit` + `@r2v`, 16:9):**
  Keyframe (`fidelity: "subject"`, inputs `[style_master, character_sheet]`): *"Place the courier character
  from image 2 standing on a sunlit rooftop overlooking a miniature clockwork city in the tactile stop-motion
  craft style and warm teal-amber palette of image 1, 50mm macro tilt-shift lens."*
- **Personal / Portrait Scene (`multi-edit` `fidelity: "person"` + Kling/Veo I2V):**
  Inputs `[scene_bg, person_a, person_b]` with explicit image-number mapping, verified side-by-side before
  animating with gentle 4–5 s motion and locked `end_image`.
- **Crisp Digital Interface / Data Beat (`shots[].image`, `$0` gen):**
  `"image": "assets/captures/05_result_dashboard.png"`, `"edit": {"duration": 4.2, "fit": "cover",
  "zoom": {"type": "push", "amount": 0.22, "x": 0.76, "y": 0.34}, "transition": "smoothleft"}`.
