# Tokentide API — reference for this skill

Tokentide is an independent, Venice-compatible proxy (not affiliated with Venice.ai) that resells
Venice inference at a daily "tide" discount. Same models and request bodies as Venice, different host,
key, limits and billing. Snapshot from tokentide.app/docs, 2 Nov 2026 (private beta,
changelog entries from 31 Oct–1 Nov 2026) — re-check the changelog when something behaves oddly.

## Contents
1. Hosts, keys, privacy modes
2. Endpoints the skill uses
3. Limits
4. Pricing, lanes and cost headers
5. Errors and retries
6. Video and music jobs
7. Large payloads
8. Gaps vs. calling Venice directly (and how the skill copes)
9. Raw examples

## 1. Hosts, keys, privacy modes
| | Value |
|---|---|
| Production base URL | `https://api.tokentide.app/v1` (the scripts' default; `TOKENTIDE_BASE_URL` overrides it). The website is `https://tokentide.app`; the Vercel dev URL `tokentide-app.vercel.app/v1` reaches the same deployment |
| Venice path alias | every host also serves `/api/v1/*`, so Venice SDKs work by changing host + key |
| Auth | `Authorization: Bearer tt_live_…` (production rejects `tt_test_…` keys, which only work on preview/staging deployments). Venice keys are rejected. |
| The scripts' key | linked by the agent, never typed by the user (below). Stored in `~/.config/tokentide/api_key` (`$XDG_CONFIG_HOME/tokentide`; Windows `%APPDATA%\tokentide\api_key`), mode 0600 / owner-only ACL |
| Status | `GET /v1/status` (no auth); status page https://tokentide.app/status |

**Linking the scripts (sign in once, ADR-0029).** The connector holds its own key, which its app keeps
and the scripts must never read. Instead:
1. The agent calls the connector tool `link_local_scripts`. It returns a one-time link code
   (`ttlink_…`: one use, 5 minutes, bound to the account and the connection; at most 20 per account per
   hour) and the command to run. A code is not a key, so it may appear in the conversation.
2. `auth.py exchange --code <code>` sends `POST /api/plugin/exchange` `{"code", "hostname"}` (JSON only,
   TLS only, rate-limited per address) to the API host. The answer carries a new key **once**:
   `{object: "plugin_key", key, key_id, masked, name, privacy_mode, daily_cap_usd, origin}`. The script
   writes the key to the key file and prints only `…last4`, the privacy mode and the daily cap.
3. The key is named "Local scripts (plugin) · <app> · <machine>", copies the connection's privacy mode,
   caps, lane and limits, and is listed under the connection in the dashboard. **Revoking the connection
   revokes it**; the next script call then answers 401 and prints the re-link steps.
Without the connector, `auth.py login` runs an OAuth device flow (RFC 8628): `POST /api/plugin/device`
→ `device_code`, `user_code` (XXXX-XXXX), `verification_uri_complete` (tokentide.app/link, where the user
approves once and picks the privacy mode and cap); the script polls `POST /api/plugin/device/token`
(`authorization_pending`, `slow_down` + new `interval`, `access_denied`, `expired_token`, then the key
once). `auth.py rotate` (`POST /api/plugin/keys/rotate`, Bearer = the plugin key) swaps the key for a new
one with the same settings; `auth.py logout --revoke` (`POST /api/plugin/keys/revoke`) ends it. Only
plugin keys can rotate or revoke themselves this way; every linking, rotation and revocation appears in
the dashboard's API keys activity. Errors: `{"error": code, "message"}` with `invalid_code`,
`connection_revoked`, `account_restricted`, `rate_limited`, `invalid_api_key`.

**Apps without a shell.** The plugin's connector (`https://api.tokentide.app/mcp/studio`) adds
`generate_image`, `edit_image`, `compose_images`, `upscale_image`, `remove_image_background`,
`start_video_job`/`check_video_job` and `start_music_job`/`check_music_job`. Inputs are public URLs,
data URLs or files the app passes (`{download_url}`); Tokentide stores none. A finished job comes back
as `GET /v1/media/{token}`: the file streams from Venice when opened, the link expires after 6 hours,
and the media is deleted upstream after one complete download (an interrupted download can be retried).
There is no hosted assembly: editing, captions and the mix need the scripts.

**Privacy mode is set per key** and filters what the key can see and call:
- `private` (default for new keys): Private, TEE and E2EE models only. In Nov 2026 that view had a few
  private edit models (FireRed, Grok Imagine edit), **no background removal** (`bria-bg-remover` is
  anonymized) and only private video models (Grok Imagine, MiniMax H3 Max, LongCat, Flux 3 Max video,
  Ovi) — not enough for premium, product-accurate keyframes and clips, and no music.
- `private_text`: text, embedding and decision models must be private; image, edit, video, voice and
  music models may be anonymized. That covers every media model this skill uses (the vision QA step
  then needs a Private vision model).
- `all`: everything, including Anonymized models (Kling, Veo, Seedance, Nano Banana, GPT Image,
  Seedream, all music models). **Use a key in mode `all` (or `private_text`) for this skill**, and
  Private options when a product is confidential. A blocked model returns `403 model_not_allowed`.
Data: Tokentide stores no prompts, inputs or outputs; it keeps account data, request metadata and
the ledger in AWS US East. Anonymized models' providers may retain content under their own policies.

## 2. Endpoints the skill uses
| Method + path | Purpose / notes |
|---|---|
| `GET /models?type=image|inpaint|video|tts|music|text` | Venice catalog (edit models are type `inpaint`; `type` defaults to `text`) + a `tokentide` object per model: `privacy_tier`, `standard.multiplier`, `lowtide.{multiplier,open,eligible}`, `epoch`, `price_locked_until`. Filtered by the key's privacy mode. Also `/models/traits`, `/models/compatibility_mapping`. |
| `POST /image/generate`, `/images/generations` | `safe_mode` always on (can't be disabled) |
| `POST /image/edit`, `/image/multi-edit`, `/image/background-remove`, `/image/upscale` | Venice bodies; public image URLs preferred for big inputs (Venice fetches up to 25 MB) |
| `GET /image/styles` | style presets |
| `POST /audio/speech` | TTS, input ≤ 4,096 chars |
| `POST /audio/transcriptions` | ≤ 4.5 MB direct (25 MB via the Large Payload Lane) |
| `POST /video/{quote,queue,retrieve,complete}` | queued video (§6) |
| `POST /audio/{quote,queue,retrieve,complete}` | queued **music and sound effects** (§6) — new vs. the Venice skill |
| `POST /chat/completions` | vision QA; `venice_parameters` pass through unchanged |
| `GET /account` | balance (`available_usd`, `promo_usd`, `spendable_usd`), `spend_today`, `tier`, `limits`, `free_use` (true: every request and quote is charged $0, no balance needed) |
| `GET /account/usage` | per-request metadata (never content), CSV export |
| `GET /market` (no auth), `POST /market/quote` | live multipliers, Low Tide status, tide table; lock a multiplier for 60 s |
| `POST /uploads` | Large Payload Lane slot (§7) |
| `POST /api/plugin/{exchange,device,device/token,keys/rotate,keys/revoke}` | the scripts' sign-in (§1); not under `/v1`, no `Venice` equivalent |
Not offered: voice cloning (`/audio/voices`) and voice changer. Not proxied: Venice account routes
(`/api_keys`, `/billing`). `GET /v1/openapi.json` documents paths but says bodies are "same as Venice".

## 3. Limits
| Limit | new | verified | trusted |
|---|---|---|---|
| Requests/min per key | 60 | 600 | 3,000 |
| Concurrent in-flight requests per account | 4 | 32 | 128 |
| **Image requests/min per account** | **2** | 6 | 12 |
| Spend velocity (list-$/min, share of day's capacity, ≥ $0.10) | 0.2% | 1% | 5% |
**Spend velocity** (`/account` → `limits.spend_velocity_usd_per_minute`) counts every request at the **list**
price, whatever it is charged (Low Tide, the tide and free use included): at its worst case while it runs, at its
actual cost once it finishes. A request of any size passes while the minute holds less than the limit (a $3.55
video clip on a $0.69/min limit); after that, requests get `429 rate_limited` ("Spend velocity limit reached …
this minute holds $X …") with `Retry-After: 2` while requests still running hold the room, else until the next
minute. A queued video or music job counts at its quoted price, so a batch of large jobs starts about one per
minute: the scripts wait and retry by themselves; don't stop them, and don't treat it as a daily limit.
Also: request body 4.5 MB (direct) · max request duration 800 s · ≤ 8 unfinished video/music jobs per
account · video/music polling ≥ 2 s apart (≈5 s is enough) · quotes 60/min per account (each queue call
also counts one) · video prompt
≤ 32,000 chars · image `variants` 1–4 · Idempotency-Key ≤ 128 chars (dupes detected 24 h) · uploads
20 per 10 min. Rate-limit headers: `X-RateLimit-Limit-Requests`, `X-RateLimit-Remaining-Requests`,
`X-RateLimit-Reset-Requests` (e.g. `12s`), `Retry-After` on 429. More than 10 upstream 4xx errors in
30 s triggers a 30-second 429 for the customer.
The scripts pace image calls to the account's `image_requests_per_minute` (read from `/account`,
override with `TOKENTIDE_IMAGE_RPM`), pace quotes to 50/min, and keep ≤ 6 video jobs in flight.

## 4. Pricing, lanes and cost headers
- Charge = Venice list price × the multiplier locked when the request is admitted. Standard lane is
  at most 0.90× list; the **tide table** lowers it through the UTC day (2 Nov 2026: 0.72 at 00:00 UTC →
  ~0.50 at 24:00 UTC), so batch generation is cheapest late in the UTC day.
- **Low Tide lane** (`X-Tokentide-Lane: lowtide`, non-streaming, best-effort, ~30% below Standard,
  floor 0.20×): the scripts' `--lane lowtide` sends it with `X-Tokentide-Lowtide-Fallback: standard`.
- Price guards: `X-Tokentide-Max-Multiplier` (env `TOKENTIDE_MAX_MULTIPLIER`) → `409 price_above_limit`;
  `X-Tokentide-Max-Cost-USD` → `409 cost_above_limit` (video.py sends quote + 10% on every queue).
- Response headers (non-streaming): `X-Tokentide-Charge-USD`, `X-Tokentide-List-Cost-USD`,
  `X-Tokentide-Multiplier`, `X-Tokentide-Lane`, `X-Tokentide-Epoch`, `X-Tokentide-Cross-Epoch`,
  `X-Tokentide-Model-Privacy`, `X-Request-Id`. The ledger records the exact charge of every call.
  There are **no balance headers** — use `GET /account` (`budget.py --live`).
- Billing: prepaid card credit, $10 minimum top-up, optional auto top-up, daily/weekly/monthly caps
  (`402 spend_limit_reached`). Requests Venice doesn't bill are never charged.

## 5. Errors and retries
Tokentide errors use `{"error": {"message", "type": "tokentide_error", "code", "param", "request_id"}}`;
Venice's 400/404/413/415/422 bodies pass through unchanged.
| Code | HTTP | Script behaviour |
|---|---|---|
| `invalid_request` | 400 | a value the model doesn't list (video `duration`, `resolution`, `aspect_ratio`) is refused before Venice with `param` and the accepted values, e.g. "resolution must be one of 480P, 768P, 1080P … (values are case-sensitive: use 1080P)": fix the value, never drop it. An unknown optional field (`param`, or Venice's `issues[].path`) is dropped/renamed and retried |
| `invalid_api_key` / `unauthorized` | 401 | stop: fix the key |
| `insufficient_balance` / `spend_limit_reached` | 402 | stop: top up or raise cap |
| `model_not_allowed` | 403 | stop: key privacy mode too strict (use mode `all`) |
| `payload_too_large` | 413 | checked locally before sending; images are shrunk |
| `price_above_limit` / `cost_above_limit` | 409 | wait (price) or raise the cap |
| `duplicate_request` | 409 | the first attempt went through; its response was lost (not replayed) |
| `rate_limited` | 429 | wait `Retry-After` (+ jitter), retry; the message names the limit (spend velocity: about one large job per minute, see §3) |
| `internal_error` / `upstream_unavailable` | 500 / 502 | exponential backoff 0.5→30 s |
| `capacity_unavailable` / `epoch_rollover` | 503 | wait `Retry-After` if short; daily reset at 00:00 UTC |
| `upstream_timeout` | 504 | not retried blindly |
Content violations on images return `200` with `x-venice-is-content-violation: true` (not charged).

## 6. Video and music jobs
| Step | Video | Music / SFX |
|---|---|---|
| Quote (free) | `POST /video/quote` | `POST /audio/quote` |
| Queue (charged once, at queue time) | `POST /video/queue` → `{model, queue_id}` | `POST /audio/queue` → `{model, queue_id, status: "QUEUED"}` |
| Retrieve | `POST /video/retrieve` → JSON `PROCESSING` or the MP4 itself | returns the audio file (mpeg/wav/flac) |
| Complete (free) | `POST /video/complete` `{queue_id}` | `POST /audio/complete` |
- Quote response: `quote` (list × current multiplier) and `tokentide: {list_cost_usd, charge_usd,
  multiplier, lane, queue_open, queue_closes_at, retry_after_seconds?}`. Prices move, so queue soon
  after quoting. `queue_open: false` means the daily cutoff has passed (`queue_closes_at` is then
  `null`) or capacity is sold out, paused or shed; `retry_after_seconds` says when to try again.
- Quote bodies take only the pricing fields: video `model`, `duration`, `aspect_ratio`, `resolution`,
  `upscale_factor`, `enhancement_model`, `target_fps`, `slowdown_factor`, `audio`, `video_url`; music
  `model`, `duration_seconds` and `character_count` (models priced per thousand characters). Venice
  rejects any other field, so video.py builds the quote body from the queue body.
- `X-Tokentide-Max-Cost-USD` also holds for the Standard re-price when a Low Tide job falls back, so
  with `--lane lowtide` video.py caps each queue at the Standard quote + 10%.
- **No download URL** — retrieve streams the file; media is deleted after delivery unless
  `delete_media_on_completion: false`. The skill sends `false`, verifies the file, then calls complete.
- Durations must be fixed (`"5s"`); `"auto"`/`"-1"` are refused with `reference_video_urls`.
- Music body: `model` (e.g. `elevenlabs-music`), `prompt`, `duration_seconds`, `force_instrumental`
  (queue only; other fields depend on the model). All music models are Anonymized (key mode `all` or
  `private_text`).
- **Daily cutoff:** capacity resets at 00:00 UTC; last queue ≈ 23:14 UTC for video (45-min worst-case
  run), ≈ 23:39 UTC for music/SFX. After the cutoff, queue returns `503 epoch_rollover`; quotes show
  `queue_open: false`. video.py checks this before queueing and stops with a clear message.
- Failures: rejected before start → not charged; failed while running → refunded automatically (the
  job then returns 404); never retrieved → stays charged and expires upstream.
- Only the queuing account can retrieve/complete a job. Send `Idempotency-Key` on queue (the scripts do).

## 7. Large payloads
Direct bodies are capped at 4.5 MB (Venice accepts 25 MB). Options, in order of preference:
1. **Compression** — the scripts shrink images (resolution and JPEG quality) until the whole body fits;
   e.g. one image ≤ ~3.1 MB, two images ≤ ~1.5 MB each, three ≤ ~1.0 MB each.
2. **Public https URLs** for image inputs (edit, multi-edit, background-remove, style references) and
   for any video input — Venice fetches them directly (up to 25 MB). The scripts pass URLs through.
3. **Large Payload Lane** (Preview): client-side AES-256-GCM (32-byte key, 12-byte nonce, framing
   `nonce‖ciphertext‖tag`), `POST /uploads` with `purpose` (`audio_transcription`, `image_edit`,
   `image_multi_edit`, `image_upscale`, `image_background_remove`), `bytes`, `sha256` of the ciphertext,
   PUT to `upload_url`, then send the request with `X-Tokentide-Upload: <upload_id>; key=<base64 K>`.
   It replaces the multipart file part only, is single-use, valid 10 minutes, and needs the
   `cryptography` package — the skill doesn't use it (compression covers its cases); there is **no
   video purpose**, so video inputs must be URLs.

## 8. Gaps vs. calling Venice directly (and how the skill copes)
| Gap | Impact | Skill behaviour |
|---|---|---|
| 4.5 MB body limit (Venice 25 MB) | big keyframes, two-frame I2V, video inputs | images auto-shrunk to fit; local video inputs over ~3 MB refused with "use a public URL" |
| No upload path for video (Large Payload Lane has no video purpose) | Topaz upscale, video-to-video, Seedance extend/stitch need hosted files | `video.py upscale --video https://…` |
| Default privacy mode hides background removal, most premium edit and video models, all music | premium keyframes, cutouts and music impossible with a default key | doctor and recommender warn; use a key in mode `all` (or `private_text`) |
| Image requests 2/min on new accounts (6 verified, 12 trusted) | 9–15 keyframes ≈ 5–8 min | client-side pacing; ask Tokentide for a higher tier for volume |
| ≤ 8 unfinished jobs, 4 concurrent requests (new tier) | big batches queue slowly | ≤ 6 in flight; the rest wait as "planned" and are queued by `poll` |
| Daily cutoff ~23:14 UTC (video) / ~23:39 UTC (music) until ~00:00 UTC | late-night batches stall | checked before queueing; queue after midnight UTC |
| No download URLs; media deleted after delivery by default | a failed transfer could lose a paid clip | `delete_media_on_completion: false` → verify → complete |
| Idempotency results not replayed; no job listing | a lost queue response = paid job without a queue_id | idempotency key prevents double charges; long timeouts; the gap remains |
| Voice cloning / voice changer not offered | no custom brand voice | stock voices, or a real recorded voice-over |
| Venice account routes not proxied, no balance headers | no `/api_keys/rate_limits` | `GET /account` (doctor, budget --live) |
| `safe_mode` always on for images; adult-purpose models not offered | occasional blurring on skin-heavy shots | regenerate/reframe; check `x-venice-is-blurred` in sidecars |
| TTS ≤ 4,096 chars; transcription ≤ 4.5 MB | long VO | short-form VO is far below; audio auto-compressed to Opus |
| Request schemas undocumented in Tokentide's OpenAPI ("same as Venice"); data URLs not mentioned | parameter drift is invisible | Venice docs are the reference; adaptive retries on `param` |
| Terms are a draft "pending review by counsel"; outputs owned "subject to upstream terms" | Venice's personal/non-commercial licence question flows down | get written commercial terms before publishing |
What Tokentide adds: exact per-request charges, 10–50% lower prices (tide + Low Tide), server-side
price caps, idempotent queueing, automatic refunds for failed jobs, and music/SFX generation.

## 9. Raw examples
```bash
B=https://api.tokentide.app/v1
curl -s $B/video/quote -H "Authorization: Bearer $TOKENTIDE_API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"kling-v3-pro-image-to-video","duration":"5s","resolution":"1080p","aspect_ratio":"9:16"}'
curl -s $B/video/queue -H "Authorization: Bearer $TOKENTIDE_API_KEY" -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" -H "X-Tokentide-Max-Cost-USD: 0.80" -H "X-Tokentide-Lane: lowtide" \
  -H "X-Tokentide-Lowtide-Fallback: standard" \
  -d '{"model":"kling-v3-pro-image-to-video","prompt":"...","duration":"5s","image_url":"https://…/keyframe.jpg"}'
curl -s $B/video/retrieve -H "Authorization: Bearer $TOKENTIDE_API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"kling-v3-pro-image-to-video","queue_id":"<id>","delete_media_on_completion":false}' --output clip_or_status
curl -s $B/video/complete -H "Authorization: Bearer $TOKENTIDE_API_KEY" -H "Content-Type: application/json" -d '{"queue_id":"<id>"}'
curl -s $B/audio/queue -H "Authorization: Bearer $TOKENTIDE_API_KEY" -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" -d '{"model":"elevenlabs-music","prompt":"upbeat minimal electronic, 110 bpm","duration_seconds":20,"force_instrumental":true}'
```
