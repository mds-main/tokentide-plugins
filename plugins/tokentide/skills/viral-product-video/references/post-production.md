# Post-production: the video spec, assembly, captions, audio, export

## Contents
1. Video spec field reference
2. What assemble.py does
3. Edit grammar (trim, speed, zoom, transitions, end card, loop)
4. Captions & text overlays
5. Audio mix
6. Outputs and export settings
7. Manual FFmpeg recipes (when you need something custom)
8. Troubleshooting

## 1. Video spec field reference
One JSON per video (`briefs/vNN.json`, start from `briefs/_example_spec.json`). Paths are relative
to the project root. Scripts write back `candidates`, `selected`, `file`, `words`.
| Field | Meaning |
|---|---|
| `id`, `title`, `status`, `target_duration_s`, `budget_usd`, `platforms` | identity, target length, per-video video-gen budget (enforced by `video.py run`) |
| `concept{objective, pillar, format, series, awareness_level, angle, hook{text,vo,visual}, beats[], cta, stepps{}, send_test}` | the creative brief (documentation + packaging) |
| `product_descriptor` | canonical product bible descriptor, reused in prompts |
| `shots[].keyframe{mode, model, inputs[], prompt, aspect_ratio, resolution, quality, n, seed, lock_product, extra, candidates[], selected}` | `mode`: `multi-edit` (scene + cutout), `edit` (one real photo), `generate` (product-free), `frame` (fit a real photo to 9:16, free), `file` (use as-is) |
| `shots[].video{model, prompt, negative_prompt, duration, resolution, aspect_ratio, audio, image, end_image, takes, extra, candidates[], selected}` | `image` defaults to `keyframe.selected`; `extra` passes new API fields (e.g. `elements`, `bitrate_mode`) |
| `shots[].edit{in, out, speed, zoom, hflip, transition{type,duration}, clip_audio_volume}` | how the clip is cut into the edit (§3) |
| `shots[].clip` | use an existing file instead of a generated take (real footage!) |
| `voiceover{enabled, model, voice, speed, offset, volume, script, file, words}` | TTS + timing |
| `music{file, volume, start, duck, fade_out, generate{model, prompt, duration_seconds, force_instrumental}}` | generated (`audio.py music`) or licensed track; ducked under VO |
| `sfx[{file, at, offset, volume, generate{model, prompt, duration_seconds}}]` | `at` = seconds or a shot id; `generate` → `audio.py sfx` |
| `audio_mix{keep_clip_audio, clip_audio_volume, lufs, true_peak, lra}` | native model audio + loudness targets |
| `captions{enabled, style, font, size, primary, highlight, outline, words_per_chunk, max_chars, position, uppercase, keep_punct, hook_size}` | §4 |
| `overlays[]` | `{"type":"text","style":"hook|label|title",...}` or `{"type":"image","file","position","width","start","end","opacity"}` |
| `end_card{file, duration, transition, fit}` | image or video appended at the end |
| `loop`, `loop_fade` | crossfade back to the first frame for seamless replays |
| `cover{time, text}` | cover frame + title (`\N` = line break) |
| `packaging{keywords[], tiktok{}, instagram{}, x{}}`, `claims[]`, `disclosure{}` | used by package.py |
Models may be aliases (`@i2v`, `@keyframe`, `@i2v_audio`, `@scene`, `@tts`) set with `models.py choose`.

## 2. What assemble.py does
1. Normalises every selected take to 1080×1920, 30 fps, yuv420p (cover-crop), applying trim, speed,
   zoom and flip.
2. Joins segments: concat for straight cuts, `xfade` for transitions (timebases normalised).
3. Optional end card and seamless-loop tail.
4. If the voice-over runs longer than the edit, holds the last frame (and warns — fix the edit).
5. One high-quality encode with image overlays and burned ASS captions/hook text (project brand fonts,
   then the bundled fonts).
6. Builds the audio mix (VO + ducked music + SFX + optional native clip audio), two-pass loudnorm
   to −14 LUFS / −1.5 dBTP, muxes; renders a `_nomusic` variant when music is set.
7. Cover (clean frame + title) and a 3:4 grid-crop preview; `_render.json` with the timeline.
`--draft` is a fast preview (`<vid>_draft.mp4`) — use it to check timing before the final render.

## 3. Edit grammar
- **Trim:** `in`/`out` seconds within the take. Most AI takes have their best 2–3 s in the middle;
  cut the first 0.2–0.5 s (settling) and stop before late drift/morphing.
- **Speed:** `speed: 1.1–1.3` tightens pacing; `0.5–0.8` for satisfying slow-motion payoffs.
- **Zoom:** `"punch"` (static 1.12× crop — instant pattern interrupt), `"push"` (slow zoom-in),
  `"pull"` (slow zoom-out), or `{"type": "push", "amount": 0.06}`.
- **Transitions** (into this shot): `{"type": "cut"}` default. Short-form favours cuts; use
  `slideleft`/`slideup`/`smoothleft` (0.12–0.2 s) as whip-like moves, `fade`/`fadeblack` for story
  beats, `zoomin` for reveals. Any FFmpeg `xfade` name works.
- **End card:** a branded 1080×1920 PNG (logo + CTA) for 1–1.5 s. Skip it when looping.
- **Loop:** `loop: true` crossfades the end into the first frame. Best when the last shot was generated
  with `end_image` = the first keyframe.
- **Real footage:** set `shots[].clip` to any real product video — real demos beat AI for credibility.

## 4. Captions & text overlays
`captions.py --spec` turns `voiceover.words` into ASS + SRT. Styles: `highlight` (2–4 word chunks, the
spoken word pops in the highlight colour — default), `karaoke` (fill), `single` (one big word),
`plain`. Defaults: Anton 104 px, uppercase, white with black outline, highlight #FFE14D, lower
position (bottom edge 680 px above the frame bottom, clear of TikTok/Reels UI).
Brand it: `primary`/`highlight` from the brand palette; `font` is a font family name. Put brand
fonts (.ttf/.otf) in the project's `P/assets/fonts/` (font files in `P/assets/brand/` work too): captions,
overlays and the cover use them first, then the bundled fonts (Anton, Montserrat ExtraBold, both SIL OFL
in the skill's `assets/fonts/`), then fonts installed system-wide. Check the font's licence allows video use.
Text overlays: `hook` (boxed, top, first ~2.5 s), `label` (small, top-left — e.g. "AI-generated"),
`title`; positions `top|upper|middle|lower|top-left|top-right`. Emoji are stripped from burned text
(libass can't render colour emoji) — keep emoji for post captions.
Caption timing comes from `audio.py transcribe` (speech-to-text via Tokentide, aligned to the known script) or
`audio.py align` (offline, silence-based). Check a few frames: words must match the audio.

## 5. Audio mix
- VO at 1.0, music 0.2–0.3 with sidechain ducking under the VO, SFX 0.5–0.9, native clip audio
  0.3–0.5 (`keep_clip_audio`). Everything is resampled to 48 kHz stereo.
- Music: generate an original track (`music.generate` + `audio.py music --spec`) sized to the video
  length + 2 s, or use a track the user has the rights to. Prompt with genre, mood, tempo (bpm),
  instruments and energy curve (e.g. "minimal electronic, bright plucks, 110 bpm, builds at 6 s,
  instrumental"). For TikTok/Reels library sounds, post the `_nomusic` file and add the sound in-app.
- Loudness: two-pass `loudnorm` to −14 LUFS integrated, −1.5 dBTP, LRA 11 (change in `audio_mix`).

## 6. Outputs and export settings
H.264 High, CRF 18 (slow preset), maxrate 12 Mbps, GOP 2 s, yuv420p, 30 fps, AAC 192 kbps 48 kHz,
`+faststart`. ~5 MB per 10 s. Same master for TikTok, Reels and X. Files: `renders/<vid>_master.mp4`,
`_nomusic.mp4`, `_cover.jpg`, `_cover_grid.jpg`, `_render.json`.

## 7. Manual FFmpeg recipes
```bash
# normalise a clip to the master format
ffmpeg -i in.mp4 -vf "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30,format=yuv420p" -c:v libx264 -crf 18 -an norm.mp4
# crossfade two normalised clips (offset = first clip length − fade)
ffmpeg -i a.mp4 -i b.mp4 -filter_complex "[0][1]xfade=transition=fade:duration=0.25:offset=4.75,format=yuv420p" ab.mp4
# logo top-right inside the safe area
ffmpeg -i v.mp4 -i logo.png -filter_complex "[1]scale=180:-1[l];[0][l]overlay=W-w-150:260" -c:a copy out.mp4
# burn ASS captions with bundled fonts
ffmpeg -i v.mp4 -vf "ass=captions.ass:fontsdir=P/assets/fonts" -c:a copy captioned.mp4   # or SKILL_DIR/assets/fonts
# VO + ducked music + loudness
ffmpeg -i video.mp4 -i vo.mp3 -i music.mp3 -filter_complex "[2]volume=0.3[m];[m][1]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=300[d];[1][d]amix=inputs=2:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11[a]" -map 0:v -map "[a]" -c:v copy -c:a aac -b:a 192k -ar 48000 final.mp4
# freeze the last frame for 1 s
ffmpeg -i v.mp4 -vf "tpad=stop_mode=clone:stop_duration=1" out.mp4
```

## 8. Troubleshooting
| Symptom | Fix |
|---|---|
| captions use a fallback font | `font` must be the family name inside a file in P/assets/fonts/, P/assets/brand/ or the bundled fonts (e.g. "Anton", "Montserrat ExtraBold"); `captions.py` warns when it finds no match |
| VO cut off / last frame held | lengthen shots (`out`, `speed` < 1), add an end card, or shorten the script |
| xfade error about timebase/size | re-run; all segments are normalised — check a custom `clip` isn't corrupt (`qa.py check clip.mp4`) |
| music too loud | lower `music.volume` (0.15–0.25); keep `duck: true` |
| black first frame | trim `in` by 0.1–0.3 s; first frame must be the hook |
| text under the UI | `qa.py safezone`; move overlays/captions (`position`, `size`) |
