# Post-production: the video spec, still-image motion, assembly, captions, audio, export

## Contents
1. Video spec field reference
2. What assemble.py does
3. Edit grammar (still images, focal zoom/pan, fit modes, trim, speed, transitions, end card, loop)
4. Captions & text overlays
5. Audio mix
6. Outputs and export settings
7. Manual FFmpeg recipes (when you need something custom)
8. Troubleshooting

## 1. Video spec field reference
One JSON per video (`briefs/vNN.json`, start from `briefs/_example_spec.json`). Paths are relative to
the project root. Scripts write back `candidates`, `selected`, `file`, `words`.
| Field | Meaning |
|---|---|
| `id`, `title`, `status`, `canvas` / `aspect_ratio`, `target_duration_s`, `budget_usd`, `platforms` | identity, canvas (`16:9` 1920×1080, `9:16` 1080×1920 default, `1:1` 1080×1080; also settable in `project.json`), target length, per-video gen budget, destinations (`youtube`, `youtube-shorts`, `tiktok`, `instagram`, `x`, `linkedin`, `general`/`personal`/`web`) |
| `concept{objective, pillar, format, series, awareness_level, angle, hook{text,vo,visual}, beats[], cta, stepps{}, send_test}` | creative brief (optional fields for personal/tutorial videos; used by packaging when marketing) |
| `product_descriptor` / `subject_descriptor` | canonical visual descriptor reused consistently in prompts |
| `shots[].image` | **direct still-image shot** (real app screenshot, real photo, or title graphic) — animated directly by `assemble.py` with smooth Ken Burns zoom/pan at `$0` gen cost! |
| `shots[].clip` | existing video file (real footage or screen recording) OR still image path (`.png`/`.jpg`/`.webp`) |
| `shots[].keyframe{mode, model, inputs[], prompt, fidelity, aspect_ratio, resolution, quality, n, seed, lock_product, extra, candidates[], selected}` | `mode`: `multi-edit` (2–8 inputs, e.g. `[scene, person_a, person_b]` or `[scene, cutout]`), `edit` (1 input), `generate` (subject-free background/style), `frame` (fit real image to canvas, free), `file` (use as-is, free). `fidelity`: `"product"` \| `"person"` \| `"subject"` \| `"none"` (auto-detects `"person"` for `assets/people/`) |
| `shots[].video{model, prompt, negative_prompt, duration, resolution, aspect_ratio, audio, image, end_image, reference_images[], elements[], takes, extra, candidates[], selected}` | omit `video` on still-image shots! `image` defaults to `keyframe.selected`; `reference_images` and `elements` auto-encode local image paths to fit Tokentide's 4.5 MB limit |
| `shots[].edit{in, out, duration, fit, bg, speed, zoom, hflip, transition, clip_audio_volume, keep_slow_audio}` | how the clip or still is framed and cut (§3). `fit`: `"cover"` (default) \| `"contain"` \| `"blur"`. `transition`: `{"type":"fade","duration":0.25}` or shorthand `"fade"` |
| `voiceover{enabled, model, voice, speed, offset, volume, script, file, words}` | TTS + word timings (set `enabled: false` for music-only cinematic videos) |
| `music{file, volume, start, duck, fade_out, generate{model, prompt, duration_seconds, force_instrumental}}` | generated (`audio.py music`) or licensed track; ducked automatically under VO |
| `sfx[{file, at, offset, volume, generate{model, prompt, duration_seconds}}]` | `at` = seconds or a shot id; `generate` → `audio.py sfx` |
| `audio_mix{keep_clip_audio, clip_audio_volume, lufs, true_peak, lra}` | native model/clip audio + loudness targets |
| `captions{enabled, style, font, size, primary, highlight, outline, words_per_chunk, max_chars, position, uppercase, keep_punct, hook_size}` | §4 (set `enabled: false` for clean cinema/personal videos while still keeping `overlays[]`!) |
| `overlays[]` | `{"type":"text","style":"hook\|label\|title",...}` or `{"type":"image","file","position","width","start","end","opacity"}` |
| `end_card{file, duration, transition, fit, bg}` | image or video appended at the end |
| `loop`, `loop_fade` | crossfade back to the first frame for seamless replays |
| `cover{time, text}` | cover/thumbnail frame + optional title (`\N` = line break) |
| `packaging{keywords[], youtube{}, youtube-shorts{}, tiktok{}, instagram{}, x{}, linkedin{}, general{}}`, `claims[]`, `disclosure{}` | used by `package.py` |
Models may be aliases (`@i2v`, `@keyframe`, `@i2v_audio`, `@r2v`, `@scene`, `@tts`, `@music`, `@sfx`) set with `models.py choose`.

## 2. What assemble.py does
1. Resolves every shot's visual source (`shots[].clip`, `shots[].image`, `shots[].video.selected`, or
   `shots[].keyframe` for real-still shots) and normalizes it to the spec/project canvas (`16:9`
   1920×1080, `9:16` 1080×1920, or `1:1` 1080×1080), 30 fps, yuv420p — applying fit mode (`cover`,
   `contain`, or blurred backdrop `blur`), smooth focal-point Ken Burns zoom/pan on stills or clips,
   trim, speed, and flip. Slowed video clips (`speed < 1`) mute native audio by default so speech isn't
   time-stretched with `atempo`.
2. Joins segments: concat for straight cuts, `xfade` for transitions (timebases normalized).
3. Optional end card and seamless-loop tail.
4. If the voice-over runs longer than the edit, holds the last frame (and warns — adjust shot durations).
5. One high-quality encode with image overlays and burned ASS captions/titles/hook text (project brand
   fonts first, then bundled SIL OFL fonts), positioned cleanly inside the canvas safe zones.
6. Builds the audio mix (VO + ducked music + SFX + optional native clip audio), runs loudness
   normalization to −14 LUFS / −1.5 dBTP (checking pass-2 `normalization_type`: if `loudnorm` falls
   back to dynamic mode, switches to constant gain + oversampled true-peak `alimiter`), muxes; renders
   a `_nomusic` variant when music is set.
7. Cover/thumbnail (clean frame + optional title) and, for `9:16`, a 3:4 grid-crop preview; `_render.json`
   with the timeline, canvas and loudness path.
`--draft` is a fast preview (`<vid>_draft.mp4`) — use it to check timing before the final render.

## 3. Edit grammar
- **Still-image shots (UI screenshots, real photos, slides):**
  - Omit `shots[].video` and point `shots[].image` (or `keyframe.inputs[0]` with `mode: "file"`/`"frame"`)
    to the PNG/JPG/WebP.
  - Set duration with `edit.duration` (e.g. `4.5`) or `edit.out` (default `4.0` s).
  - Always give still shots subtle intentional motion (`zoom` push/pull/pan) so the video feels alive,
    never like a dead slideshow!
- **Focal-point Zoom & Pan (`edit.zoom`):**
  - `"push"` (smooth zoom-in, default 8%) · `"pull"` (smooth zoom-out) · `"punch"` (instant 12% static
    crop-in for a snappy pattern interrupt).
  - `"pan-left"` · `"pan-right"` · `"pan-up"` · `"pan-down"` (smoothly glides across wide photos, charts,
    or tall web pages).
  - **Targeted focal point (game-changer for app UI & portraits!):** pass an object with normalized
    `x`, `y` (`0.0–1.0`, default `0.5, 0.5`):
    - App button at top-right: `{"type": "push", "amount": 0.28, "x": 0.80, "y": 0.22}`
    - Couple's faces in upper third: `{"type": "push", "amount": 0.10, "x": 0.50, "y": 0.34}`
    - Punch straight into a metric card: `{"type": "punch", "amount": 0.25, "x": 0.32, "y": 0.58}`
    `assemble.py` uses supersampled sub-pixel `zoompan` on still images so focal zooms glide like butter
    with zero stepping jitter!
- **Fit modes (`edit.fit` & `edit.bg`):**
  - `"cover"` (default): scales to fill the canvas and center-crops (best when source matches canvas).
  - `"contain"`: fits the entire source inside the canvas without cropping a single pixel, padded with
    `edit.bg` (default `#0B0E14`). Ideal for wide dashboards or tightly cropped UI widgets!
  - `"blur"`: fills the canvas with a softly blurred, subtly darkened backdrop of the same photo/clip and
    places the sharp full image centered on top — makes portrait photos look cinematic on `16:9` (or
    desktop screenshots look pro on `9:16`) with zero ugly black bars and zero cropped heads/buttons!
- **Trim:** `in`/`out` seconds within a video take. Most AI takes have their best 2–4 s in the middle;
  trim the first 0.2–0.4 s (settling) and cut before late drift.
- **Speed:** `speed: 1.1–1.25` tightens pacing; `0.6–0.85` for dreamy/cinematic slow-motion payoffs.
  When `speed < 1`, native clip audio is muted automatically (`keep_slow_audio: true` only for non-speech).
- **Transitions** (into this shot): `{"type": "cut"}` default (or string shorthand `"fade"`). Short-form
  & tutorials favour clean cuts; `smoothleft` / `slideleft` (`0.15s`) feels natural when moving to the next
  app screen; `fade` / `dissolve` (`0.3–0.5s`) suits emotional couple/story beats and chapter shifts;
  `zoomin` (`0.2s`) punches big reveals. Any FFmpeg `xfade` name works.
- **End card:** branded PNG/MP4 matching the canvas for 1.5–2.5 s (skip when looping).
- **Loop:** `loop: true` crossfades the end back into frame 1 (best when the last shot uses `end_image`
  = frame 1).

## 4. Captions & text overlays
`captions.py --spec` turns `voiceover.words` into ASS + SRT. Styles: `highlight` (2–4 word chunks, active
word pops in highlight color — default), `karaoke`, `single`, `plain`. Defaults auto-scale to the canvas:
- **`16:9` (YouTube / web / personal):** 68 px, bottom margin 110 px clear of player scrub bars.
- **`9:16` (Shorts / TikTok / Reels / X):** 104 px, bottom margin 680 px clear of mobile UI overlays.
- **`1:1` (Square feed):** 76 px, bottom margin 140 px.
For cinematic personal/couple films or clean YouTube videos where burned captions aren't desired, set
`"captions": {"enabled": false}` — `captions.py` still generates `.srt` (if VO exists) and renders any
chapter/title `overlays[]` cleanly!
Brand fonts: put licensed `.ttf`/`.otf` files in `P/assets/fonts/` (or `P/assets/brand/`); they load
before the bundled SIL OFL fonts (`Anton`, `Montserrat ExtraBold`). Text overlays support styles `hook`,
`label` (e.g. `"AI-generated visuals"`), and `title`, at `top|upper|middle|lower|top-left|top-right`.
Emoji are stripped from burned text (libass can't render color emoji).

## 5. Audio mix
- **Never time-stretch speech (`atempo`):** if VO is too fast, shorten the script, use a model with native
  `speed`, or lengthen silent pauses only with `audio.py pace --spec briefs/vNN.json --target-wps 2.4`.
- **Snap every cut in speech to real silence:** use `audio.py split` / `audio.py trim` (aborts if any
  piece's 15 ms edge exceeds −50 dBFS).
- Levels: VO at `1.0`, music `0.20–0.28` with sidechain ducking (`duck: true`) under VO (or `0.85–1.0`
  for music-driven non-VO cinematic films!), SFX `0.45–0.85`, native clip audio `0.3–0.5`. All resampled
  to 48 kHz stereo.
- **Music:** generate an original rights-safe score (`music.generate` + `audio.py music --spec`) sized to
  `duration + 2 s`, matching the emotional arc (tempo, instruments, swell at climax).
- **Loudness:** two-pass linear `loudnorm` to −14 LUFS / −1.5 dBTP, automatically falling back to fixed
  gain + oversampled true-peak `alimiter` if `loudnorm` tries to switch to dynamic breathing mode.

## 6. Outputs and export settings
H.264 High, CRF 18 (slow preset), maxrate 12 Mbps, GOP 2 s, yuv420p, 30 fps, AAC 192 kbps 48 kHz,
`+faststart`. Files: `renders/<vid>_master.mp4`, `_nomusic.mp4`, `_cover.jpg`, `_cover_grid.jpg`
(9:16 only), `_render.json`.

## 7. Manual FFmpeg recipes
```bash
# smooth focal zoom on a still screenshot (16:9 1920x1080, 4s -> zoom 1.0 to 1.24 onto x=0.78, y=0.28)
ffmpeg -i screen.png -vf "scale=3840:2160:flags=lanczos,zoompan=z='min(1+0.24*on/119,1.24)':x='max(0,min(iw-iw/zoom,iw*0.78-iw/zoom/2))':y='max(0,min(ih-ih/zoom,ih*0.28-ih/zoom/2))':d=120:s=1920x1080:fps=30,setsar=1,format=yuv420p" -c:v libx264 -crf 18 out.mp4
# blurred-backdrop framing (e.g. vertical photo into 16:9 landscape cleanly)
ffmpeg -loop 1 -t 4 -i photo.jpg -filter_complex "[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,boxblur=28:2,eq=brightness=-0.12[bg];[0:v]scale=1920:1080:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p" -r 30 -c:v libx264 -crf 18 out.mp4
# VO + ducked music + loudness
ffmpeg -i video.mp4 -i vo.mp3 -i music.mp3 -filter_complex "[2]volume=0.25[m];[m][1]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=300[d];[1][d]amix=inputs=2:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11[a]" -map 0:v -map "[a]" -c:v copy -c:a aac -b:a 192k -ar 48000 final.mp4
```

## 8. Troubleshooting
| Symptom | Fix |
|---|---|
| captions use a fallback font | put the `.ttf`/`.otf` in `P/assets/fonts/` and match its exact family name; `captions.py` warns if missing |
| UI screenshot cropped on edges | set `edit.fit: "contain"` (with brand `bg`) or `"blur"`, or capture at exact canvas ratio |
| VO cut off / last frame held | increase shot `edit.duration` / `edit.out`, add an end card, or tighten the script |
| black first frame | trim `edit.in` by 0.1–0.3 s; frame 1 must be visually compelling |
| text under platform UI | run `qa.py safezone --spec ...`; adjust overlay/caption `position` or `size` |
