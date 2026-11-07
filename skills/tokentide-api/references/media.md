# Media: images, speech, transcription, video and music

How to call Tokentide's media endpoints: image generation and editing, text to speech, transcription, queued
video and music jobs, inputs over 4.5 MB, the privacy mode each needs, cost, and labelling generated media.
Open it when you write code that creates or processes media; choosing a model type is in choosing-models.md.
Model ids here are examples from the docs: take current ids, and the resolutions, aspect ratios, durations,
voices and formats each model accepts (case-sensitive), from `GET /v1/models?type=…` called with your key.

## Contents

- Images
- Speech and transcription
- Video and music jobs
- Large inputs
- Privacy and cost
- Label generated media
- Further reading

## Images

|            | `POST /v1/image/generate` (native: control over cost and quality)                                                                                                                                         | `POST /v1/images/generations` (OpenAI-compatible: existing OpenAI code)                    |
| ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| Settings   | `resolution` (`1K`, `2K`, `4K`), `quality` (`low`, `medium`, `high`), `aspect_ratio` or `width` and `height` (per model), `variants` (1–4, each billed), `seed`, `style_preset`, `format`, `transparent_background`, `enhance_prompt`, `hide_watermark` | OpenAI's fields; `quality` is accepted but ignored                                         |
| Prompt     | Up to the model's limit                                                                                                                                                                                    | 1,500 characters, any model                                                                |
| Moderation | `safe_mode`, always on                                                                                                                                                                                     | `safe_mode` on, plus `moderation: "auto"`                                                  |
| Response   | JSON with `images` (base64 strings)                                                                                                                                                                        | OpenAI's format: with the OpenAI SDK, `response_format="b64_json"`, then `data[0].b64_json` |

- **Pace image requests:** 4, 10 or 20 per minute per account by trust tier (`limits.image_requests_per_minute`
  in `GET /v1/account`), about 20 per minute across all customers; honor `Retry-After`, also on
  `503 epoch_rollover` during the daily reset.
- **A flagged image** comes back as `200` with `x-venice-is-content-violation: true` and isn't charged; flagged
  variants can be dropped, so you may get fewer images than `variants`.
- **Prompt as a scene** (subject and action, setting, style, lighting, composition), most important first; say
  what you want rather than what you don't, keep text in the image short and quoted, set the aspect ratio.

```python
# The later Python blocks in this file build on this one (imports, API, HEADERS, save_image).
import base64
import os

import httpx

API = "https://api.tokentide.app/v1"
HEADERS = {"Authorization": f"Bearer {os.environ['TOKENTIDE_API_KEY']}"}
PROMPT = "A ceramic coffee cup on a sunlit oak table, soft morning light, shallow depth of field, product photo"

def save_image(res: httpx.Response, path: str) -> None:
    """Save the first image of a response: JSON `images` (base64) or the image bytes themselves."""
    res.raise_for_status()  # 429: wait for Retry-After
    if res.headers.get("x-venice-is-content-violation") == "true":
        raise ValueError("flagged as a content violation (not charged): change the prompt or the input")
    raw = res.headers.get("content-type", "").startswith("image/")
    data = res.content if raw else base64.b64decode(res.json()["images"][0].split(",", 1)[-1])
    with open(path, "wb") as f:
        f.write(data)

draft = {"model": "z-image-turbo", "prompt": PROMPT, "format": "webp", "seed": 42}  # fast model, fixed seed
save_image(httpx.post(f"{API}/image/generate", headers=HEADERS, json=draft, timeout=180), "draft.webp")
final = {**draft, "model": "flux-3-image", "resolution": "1K"}  # render the approved prompt once
save_image(httpx.post(f"{API}/image/generate", headers=HEADERS, json=final, timeout=180), "final.webp")
```

### Edit, compose, upscale, remove a background

| Task                                  | Endpoint                           | Main body fields                                | Notes                                                                                             |
| ------------------------------------- | ---------------------------------- | ----------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| Change one thing, keep the rest       | `POST /v1/image/edit`              | `model` (an `inpaint` model), `prompt`, `image` | Short, local prompt ("replace the mug with a glass"); for broader edits, say what must not change |
| Edit with style or subject references | `POST /v1/image/multi-edit`        | `modelId` (not `model`), `prompt`, `images`     | The first image is the one edited; extra input images can cost extra; no backup models            |
| Enlarge 2× or 4×                      | `POST /v1/image/upscale`           | `image`, `scale`                                | $0.02 (2×) or $0.08 (4×) at list price; adds pixels, not new detail; Private                      |
| Cut out the subject                   | `POST /v1/image/background-remove` | `image_url` (public URL) or `image`             | Runs on `bria-bg-remover` (Anonymized): key mode `all` or `private_text`                          |
| List style presets                    | `GET /v1/image/styles`             | none                                            | No key needed; the values `style_preset` accepts                                                  |

Bodies are Venice's. Send input images as a public `https://` URL where accepted (see Large inputs), so the
file never passes through Tokentide; otherwise base64 within the 4.5 MB body limit (base64 adds a third).

```python
body = {"model": "…",  # an inpaint model from GET /v1/models?type=inpaint that your key may call
        "image": "https://example.com/photos/cup.jpg",  # public https URL: Venice fetches it
        "prompt": "Replace the mug with a glass of water. Keep everything else unchanged."}
save_image(httpx.post(f"{API}/image/edit", headers=HEADERS, json=body, timeout=180), "edited.png")
```

## Speech and transcription

**Text to speech, `POST /v1/audio/speech`:**

- **Up to 4,096 characters per request** (more gets `400 invalid_request`): split long text at sentence or
  paragraph boundaries, with the same model, voice, speed and format for every part. Voices are the model's
  own (`GET /v1/models?type=tts`); voice cloning and voice changing are not offered.
- **`response_format`:** `mp3` for playback, `opus` for low-latency streaming, `aac` for mobile, `flac` for
  archiving, `wav` or `pcm` for the fastest start. Stream (`streaming: true`) when a person is listening; Low
  Tide needs `streaming: false`.
- **Priced per character:** about $3.50 per million on `tts-kokoro` (Private), over $100 on premium voices; a
  full request costs about $0.014 or up to $0.77 (list). Try cheaper voices first; cache audio you replay.

```python
from openai import OpenAI

client = OpenAI(base_url="https://api.tokentide.app/v1", api_key=os.environ["TOKENTIDE_API_KEY"])
speech = client.audio.speech.create(
    model="tts-kokoro", voice="af_sky", response_format="mp3",
    input="This is an automated message with an AI-generated voice. Your order has shipped.",
    # Narration nobody waits for: extra_body={"streaming": False},
    # extra_headers={"X-Tokentide-Lane": "lowtide", "X-Tokentide-Lowtide-Fallback": "standard"},
)
speech.write_to_file("message.mp3")
```

**Speech to text, `POST /v1/audio/transcriptions`:**

- **Multipart, as in OpenAI's API:** up to 4.5 MB directly, 25 MB through the Large Payload Lane. Priced per
  second of audio: about $0.11 per hour (`stt-xai-v1`, Private) to $0.60; `openai/whisper-large-v3` (Private)
  about $0.36 (list). Choose on your own recordings (accents, noise, jargon), not on headline numbers.
- **Send compact audio:** 4.5 MB holds about 2 minutes of 16 kHz mono WAV but about 19 minutes of Opus or MP3
  at 32 kbit/s (about 100 minutes in 25 MB); FLAC is lossless at about half the size of WAV. Trim silence: you
  pay for it, and long silences can make some models invent words.
- **Split long recordings at pauses** with a second or two of overlap, and join them with `timestamps`. Set
  `language` where supported; ask for `timestamps` (through `extra_body`) only when needed. There is no speaker
  labelling: fix speakers, names and jargon afterwards with a small chat model.

```bash
# Mono, 16 kHz, Opus at 32 kbit/s (about 4 KB per second); leading and trailing silence trimmed.
ffmpeg -i meeting.m4a -ac 1 -ar 16000 \
  -af "silenceremove=start_periods=1:start_threshold=-45dB,areverse,silenceremove=start_periods=1:start_threshold=-45dB,areverse" \
  -c:a libopus -b:a 32k meeting.ogg
```

```python
with open("meeting.ogg", "rb") as audio:
    transcript = client.audio.transcriptions.create(
        model="openai/whisper-large-v3", file=audio, response_format="json", language="en")
print(transcript.text)
```

## Video and music jobs

| Step     | Video                                                            | Music and sound effects                                                          | Cost                                                                                                                        |
| -------- | ---------------------------------------------------------------- | -------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| Quote    | `POST /v1/video/quote`                                           | `POST /v1/audio/quote`                                                           | Free. `quote` is what queueing now would cost; `tokentide` adds `list_cost_usd`, `charge_usd`, `multiplier`, `lane`, `queue_open`, `queue_closes_at` |
| Queue    | `POST /v1/video/queue` → `{model, queue_id}`                     | `POST /v1/audio/queue` → `{model, queue_id, status: "QUEUED"}`                   | Charged once, now: Venice's exact list price for the parameters × the multiplier locked at queueing                         |
| Retrieve | `POST /v1/video/retrieve` → JSON while running, then `video/mp4` | `POST /v1/audio/retrieve` → JSON, then `audio/mpeg`, `audio/wav` or `audio/flac` | Free; at most once every 2 s per job (every 5 s is enough)                                                                  |
| Complete | `POST /v1/video/complete` with `queue_id`                        | `POST /v1/audio/complete` with `model`, `queue_id`                               | Free; only needed after retrieving with `delete_media_on_completion: false`                                                 |

- **Bodies are Venice's.** Quote, then queue soon: prices move during the day. On `queue`, cap the price
  (`X-Tokentide-Max-Cost-USD` or `X-Tokentide-Max-Multiplier`; refusals are never charged) and send an
  `Idempotency-Key`; a retry with the same key gets `409 duplicate_request` and the first response is not
  replayed, so give `queue` a generous timeout. Low Tide (`X-Tokentide-Lane: lowtide`) works where allowed.
- **Send a fixed video `duration`** (`"5s"`): with `reference_video_urls`, `"auto"` or `"-1"` is refused, and a
  duration, resolution or aspect ratio the model doesn't offer gets `400 invalid_request` listing the accepted
  values. `audio` is on by default where offered; for image-to-video, pass the frame as `image_url`.
- **Collect with `retrieve`** (`queue` never returns a download link): JSON with `status: "PROCESSING"` while it
  runs, then the file, deleted upstream as it is delivered (`delete_media_on_completion` defaults to `true`).
  For expensive jobs, retrieve with `false`, check the saved file, then `complete`. Other accounts get `404`.
- **Failures:** rejected at queue time: not charged. Failed while running (`500` on `retrieve` for over a
  minute, or a content-policy rejection with refunded credits): refunded automatically, then `404`. Never
  collected: stays charged.

```python
import time
import uuid

PRICED_BY = {"video": ("model", "duration", "resolution", "aspect_ratio", "audio"), "audio": ("model", "duration_seconds")}

def run_job(family: str, body: dict, path: str) -> None:
    """family: "video", or "audio" for music and sound effects. Quote, queue once, poll politely, save."""
    with httpx.Client(base_url=f"{API}/{family}", headers=HEADERS, timeout=httpx.Timeout(30, read=300)) as http:
        quote = http.post("/quote", json={k: body[k] for k in PRICED_BY[family] if k in body})
        quote.raise_for_status()
        tt = quote.json()["tokentide"]
        if not tt["queue_open"]:
            raise RuntimeError("queueing is closed (daily cutoff or sold out): try again later")
        job = http.post("/queue", json=body, headers={
            "Idempotency-Key": str(uuid.uuid4()),  # reuse the same key if you retry this call
            "X-Tokentide-Max-Cost-USD": f"{float(tt['charge_usd']) * 1.1:.4f}",  # the quote plus a margin
        })
        job.raise_for_status()  # 503 epoch_rollover after the cutoff; 429 with 8 jobs uncollected
        queue_id = job.json()["queue_id"]
        for _ in range(720):  # about an hour at 5 s; a video's worst-case run time is 45 minutes
            r = http.post("/retrieve", json={"model": body["model"], "queue_id": queue_id})
            if r.status_code == 429 or r.status_code >= 500:  # too fast, or failing (refunded, then 404)
                time.sleep(float(r.headers.get("retry-after", "10")))
                continue
            r.raise_for_status()  # 404: refunded or not this account's job; 422: rejected
            if not r.headers.get("content-type", "").startswith("application/json"):  # the file itself
                with open(path, "wb") as f:
                    f.write(r.content)  # deleted upstream on delivery: this is the only copy
                return
            time.sleep(5)  # {"status": "PROCESSING", "average_execution_time": …, "execution_duration": …}
        raise TimeoutError(f"{queue_id} not finished: retrieve it later (it stays charged until collected)")

run_job("video", {"model": "grok-imagine-text-to-video-private", "duration": "5s", "resolution": "720p",
                  "prompt": "A lighthouse at dusk, waves rolling in, slow aerial shot"}, "lighthouse.mp4")
run_job("audio", {"model": "elevenlabs-music", "duration_seconds": 60, "force_instrumental": True,
                  "prompt": "Calm instrumental piano for focus, soft and warm"}, "focus.mp3")
```

Music bodies follow Venice's schema, which rejects unknown fields: lyrics go in `lyrics_prompt` (on models whose
`GET /v1/models?type=music` entry reports `supports_lyrics`), never `lyrics`.

**The daily cutoff.** The capacity Tokentide sells renews at 00:00 UTC, and a job is accepted only if it would
finish before then in the worst case: video (45 minutes) until about 23:14 UTC, music and sound effects (20
minutes) until about 23:39 UTC. After that, `queue` answers `503 epoch_rollover` with `Retry-After` until
shortly after midnight; quotes still work and report `queue_open: false`; running jobs are not affected.

- **Limits:** 8 jobs queued and not yet collected per account (`429 rate_limited` above it; a job stops
  counting once collected, refunded or past its worst-case run time); polling at most every 2 s per job; 60
  quotes per minute per account, including the quote each `queue` makes; video prompts up to 32,000
  characters. A large job can fill your per-minute spending rate alone: large jobs start about one per minute.
- **Download links:** the API returns files, never links. Only the connector's `check_video_job` and
  `check_music_job` (on `https://api.tokentide.app/mcp/studio`) return one, `GET /v1/media/{token}`: sealed to
  one job of one account, it is the only credential (keep it secret), expires after 6 hours and serves one
  complete download, after which the media is deleted upstream. An interrupted download can be retried.

## Large inputs

Request bodies are limited to 4.5 MB (`413 payload_too_large` above it). Prefer a public `https://` URL (edit,
multi-edit, background removal, `style_references`, every video job input): Venice fetches it (no redirects, at
most 25 MB). Otherwise use the Large Payload Lane (preview) for transcription audio and image files up to
25 MiB. For transcription, Opus compression is often enough.

- **Slot:** `POST /v1/uploads` with `purpose` (`audio_transcription`, `image_edit`, `image_multi_edit`,
  `image_upscale`, `image_background_remove`) and the `bytes` and `sha256` of the ciphertext, never of the
  plaintext. Single use, valid 10 minutes, your account only; 20 per 10 minutes, with a positive balance.
- **Format:** AES-256-GCM, a new random 32-byte key and 12-byte nonce, no AAD, framed `nonce ‖ ciphertext ‖ tag`
  (16-byte tag), then `X-Tokentide-Upload: <upload_id>; key=<standard base64 of the key>`. `PUT` with only the
  returned `headers`, never your key, and never log the header value: it holds the key.
- **Errors:** `400 invalid_request` (bad header or key, checksum mismatch, wrong purpose),
  `402 insufficient_balance`, `404 not_found` (unknown, expired or used slot, or unfinished `PUT`),
  `413 payload_too_large`, `429 rate_limited`, `503 service_unavailable` (lane not enabled: use a URL). Any
  failure uses the slot up. The SDK helpers (`upload_large_payload`, `largePayload`) are planned for PyPI and
  npm; until then:

```python
import hashlib

from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # pip install cryptography

def stage(path: str, purpose: str, content_type: str) -> str:
    """Encrypt locally, upload the ciphertext to a one-time slot, return the X-Tokentide-Upload value."""
    key, nonce = AESGCM.generate_key(bit_length=256), os.urandom(12)
    with open(path, "rb") as f:
        framed = nonce + AESGCM(key).encrypt(nonce, f.read(), None)  # the ciphertext ends with the 16-byte tag
    slot = httpx.post(f"{API}/uploads", headers=HEADERS, timeout=30, json={
        "purpose": purpose, "bytes": len(framed), "sha256": hashlib.sha256(framed).hexdigest(),
        "filename": "input" + os.path.splitext(path)[1], "content_type": content_type})
    slot.raise_for_status()
    s = slot.json()
    httpx.put(s["upload_url"], headers=s["headers"], content=framed, timeout=300).raise_for_status()
    return f"{s['upload_id']}; key={base64.b64encode(key).decode()}"  # holds the key: never log it

upload = stage("meeting.m4a", "audio_transcription", "audio/mp4")
res = httpx.post(f"{API}/audio/transcriptions", headers={**HEADERS, "X-Tokentide-Upload": upload}, timeout=300,
                 json={"model": "openai/whisper-large-v3", "response_format": "json"})  # fields only, no file part
res.raise_for_status()
print(res.json()["text"])
```

## Privacy and cost

- **Privacy:** images, edits, speech and transcription have Private and Anonymized models; upscaling is Private
  only; background removal and all music models are Anonymized; most video models are Anonymized, but the
  `grok-imagine-*-private` family works with any key. Anonymized models need `all` or `private_text` (else
  `403 model_not_allowed`); `private_text` keeps text, embeddings and decisions on Private models.
- **An Anonymized provider sees** your prompts, images and audio and may keep them under its own policy, never
  your identity; faces, voices and documents still identify people, so use Private models for confidential
  inputs. Files pass through unchanged, and `X-Tokentide-Model-Privacy` names each model's privacy level.
- **Price first:** `GET /v1/market/estimate?model=…&units=…` (public) prices a number of the model's `unit`
  (image, edit, upscale, second of audio, million characters) now and through the UTC day.
- **Images (list prices):** draft on a fast $0.01 model or at low quality with a fixed `seed`, then render once
  on the premium model (`gpt-image-2`: $0.02 at low, $0.26 at high quality for 1K). Upscale instead of
  generating large (`flux-3-image`: 1K plus a 4× upscale $0.20, native 4K $0.98); edit rather than regenerate;
  ask for `transparent_background` (PNG or WebP, where supported) rather than pay for background removal; one
  variant until the prompt works; leave `enhance_prompt` (extra charge, up to about 30 s) and web search off.
- **Video:** audio off for drafts; compose on stills, then animate the approved frame; draft short, small and
  fast; one action and one camera move per clip; join short clips rather than make one long, busy one.
- **Music:** preview a short version first; length-banded prices round up (30 seconds on a 60-second band costs
  the full band); keep sound effects tight (often per second). Prompt with genre, instruments, mood, tempo.
- **Timing and reuse:** work that can wait can run on Low Tide where `tokentide.lowtide.eligible` is true, and
  the Standard price falls through the UTC day (pricing-and-timing.md). Cache every file you paid for.

## Label generated media

General information, not legal advice: get advice from a qualified specialist. The rest of the EU AI Act:
eu-ai-act.md.

- **Marking (EU AI Act Article 50(2), providers of generative systems):** generated images, video, audio and
  text need a machine-readable mark that lets them be detected as AI-generated, as far as technically
  feasible, from 2 August 2026 (2 December 2026 for systems on the market before then). The Code of Practice
  the Commission found adequate asks for at least two layers on images, video and audio: signed metadata and
  an imperceptible watermark.
- **Labels (Article 50(4), deployers):** a deepfake (content resembling real people, places, objects or events
  that could falsely appear authentic) needs a visible or audible label: "AI-generated" at the start of videos
  and at intervals, a spoken disclaimer at the start of audio.
- **Keep and add marks:** Tokentide strips no metadata or watermarks; leave a model's visible watermark on where
  you can (`hide_watermark: false`). Add IPTC "trained algorithmic media" metadata and C2PA content credentials
  where your tools support them, after the last re-encode (which usually strips metadata). Don't use
  `embed_exif_metadata`: it writes the generation details, prompt included, into the image. A missing
  watermark never proves content is real.
- **Respect likeness and voice:** no content that impersonates real people without their documented consent;
  in the United States, calls that use AI-generated voices need the recipient's prior consent.

```bash
# Images: the IPTC digital source type that tools read as "generated by AI", and a description.
exiftool -overwrite_original \
  -XMP-iptcExt:DigitalSourceType=http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia \
  -XMP-dc:Description="AI-generated image" banner.png
# Video and audio: a metadata label without re-encoding; then a visible label for video that could pass as real.
ffmpeg -i clip.mp4 -c copy -metadata comment="AI-generated video" clip-labelled.mp4
ffmpeg -i clip.mp4 -vf "drawtext=text='AI-generated':x=w-tw-24:y=h-th-24:fontsize=28:fontcolor=white:box=1:boxcolor=black@0.5" \
  -c:a copy clip-visible-label.mp4
```

## Further reading

- https://tokentide.app/docs/video-and-music
- https://tokentide.app/docs/choosing-models#images
- https://tokentide.app/docs/large-payloads
- https://tokentide.app/docs/mcp#media-links
- https://tokentide.app/docs/security#responsible-use
- https://tokentide.app/docs/eu-ai-act#mark-and-label
