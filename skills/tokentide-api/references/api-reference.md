# Tokentide API reference

Every Tokentide endpoint, every request and response header, the streaming format, the model catalog and the
market, account and usage APIs. Open it when you write, review or debug code that calls the API and need an
exact path, header, field or response shape. Error codes and limits are in `errors-and-limits.md`, pricing
rules in `pricing-and-timing.md`, media jobs and uploads in `media.md`.

## Contents

- [Base URLs and compatibility](#base-urls-and-compatibility)
- [Authentication](#authentication)
- [Endpoint catalog](#endpoint-catalog)
- [Request and response headers](#request-and-response-headers)
- [Streaming](#streaming)
- [Models](#models)
- [Market API](#market-api)
- [Account and usage](#account-and-usage)
- [Large inputs and E2EE](#large-inputs-and-e2ee)
- [Further reading](#further-reading)

## Base URLs and compatibility

| Base URL                           | Path layout | Use with                                                                                                   |
| ---------------------------------- | ----------- | ---------------------------------------------------------------------------------------------------------- |
| `https://api.tokentide.app/v1`     | OpenAI      | OpenAI SDKs (`openai` on PyPI and npm), Vercel AI SDK (`@ai-sdk/openai-compatible`), LangChain, LlamaIndex |
| `https://api.tokentide.app/api/v1` | Venice      | Venice SDKs and raw Venice clients; every route also answers here                                          |

- Change only the base URL and the key: bodies, streaming, tools, structured output, model ids,
  `venice_parameters` and E2EE headers stay the same; responses are the usual objects (`chat.completion`, …).
- Send Tokentide headers with `extra_headers` (Python) or the `headers` request option (TypeScript),
  Venice-only body fields with `extra_body` (Python: `extra_body={"venice_parameters": {…}}`).
- Tokentide sets `venice_parameters.include_venice_system_prompt` to `false` on chat completions and responses
  (your other `venice_parameters` pass through) and, where a route accepts them, `user`, `anon_user_id` (an
  opaque hash of your account) and a per-account `prompt_cache_key`; never on E2EE requests.
- Not available: Venice's `/api_keys` and `/billing` (see https://tokentide.app/app/keys, `GET /v1/account`),
  voice cloning and the voice changer. Venice API keys and x402 credentials are never accepted.
- Model ids here (`deepseek-v4-1-flash`, `zai-org-glm-5-2`, …) are examples; current ids: `GET /v1/models`.
- Tokentide's own helpers, `@tokentide/sdk` (TypeScript) and `tokentide` (Python), are not on npm or PyPI yet
  (publication is planned): use the OpenAI SDK and plain HTTP.

## Authentication

- Send `Authorization: Bearer $TOKENTIDE_API_KEY` from server-side code only, never in a URL, query string,
  browser bundle, log or chat. The user keeps the key in `TOKENTIDE_API_KEY` or a secret manager.
- `tt_live_…`: production only. `tt_test_…`: preview and staging only, answered by a deterministic mock.
- Public routes need no key (catalog Auth column); send it to `GET /v1/models` anyway to list what it may call.
- Refusals: missing or unknown key `401 invalid_api_key`; caller outside the key's IP allowlist
  `403 ip_not_allowed`; model outside the key's privacy mode `403 model_not_allowed`.
- Wallets can sign a fresh `SIGN-IN-WITH-X` header (CAIP-122, single-use nonce) per request instead of a key,
  paying from the wallet account: https://tokentide.app/docs/x402#accountless-inference-with-sign-in-with-x.

## Endpoint catalog

Billed: list price × the multiplier locked at admission, never for what Venice does not bill. Key: an API key
or a `SIGN-IN-WITH-X` header. Bodies are Venice's (OpenAI-compatible where applicable).

| Area         | Method | Path                                                    | What it does                                                                                              | Billed               | Auth                                    |
| ------------ | ------ | ------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- | -------------------- | --------------------------------------- |
| Text         | `POST` | `/v1/chat/completions`                                  | Chat completions: streaming, tools, structured output; E2EE passthrough on `e2ee-*` models                | Billed               | Key                                     |
|              | `POST` | `/v1/responses`                                         | Responses API, typed SSE events, no E2EE; output limit `max_output_tokens`                                | Billed               | Key                                     |
| Decisions    | `POST` | `/v1/decisions`, `/v1/systemone`                        | Typed judgments about a state (`model`, `state`, `questions`); `/v1/systemone` is an alias                | Billed               | Key                                     |
| Embeddings   | `POST` | `/v1/embeddings`                                        | Text embeddings, up to 2,048 inputs per request                                                           | Billed               | Key                                     |
| Images       | `POST` | `/v1/image/generate`, `/v1/images/generations`          | Generate images: Venice format (`safe_mode` is always on), or OpenAI format (prompt ≤ 1,500 characters)   | Billed               | Key                                     |
|              | `POST` | `/v1/image/edit`, `/v1/image/multi-edit`, `/v1/image/upscale` | Edit an image; compose several images; upscale an image                                             | Billed               | Key                                     |
|              | `POST` | `/v1/image/background-remove`                           | Remove the background (an Anonymized model: privacy mode `all` or `private_text`)                         | Billed               | Key                                     |
|              | `GET`  | `/v1/image/styles`                                      | Style presets for `style_preset`                                                                          | Free                 | Public                                  |
| Audio        | `POST` | `/v1/audio/speech`                                      | Text to speech, input ≤ 4,096 characters                                                                  | Billed               | Key                                     |
|              | `POST` | `/v1/audio/transcriptions`                              | Speech to text: ≤ 4.5 MB direct, ≤ 25 MB through an upload                                                | Billed               | Key                                     |
| Video, music | `POST` | `/v1/video/quote`, `/v1/audio/quote`                    | Price a video, or a music or sound-effect job, now (`quote` plus a `tokentide` object)                    | Free                 | Key                                     |
|              | `POST` | `/v1/video/queue`, `/v1/audio/queue`                    | Queue a job (music: `music` models); returns `queue_id`, never a download URL                             | Once, when queued    | Key                                     |
|              | `POST` | `/v1/video/retrieve`, `/v1/audio/retrieve`              | Poll (at most every 2 s): JSON status, then the file (`video/mp4`; `audio/mpeg`, `audio/wav`, `audio/flac`) | Free               | Key                                     |
|              | `POST` | `/v1/video/complete`, `/v1/audio/complete`              | Delete the media; needed only after retrieving with `delete_media_on_completion: false`                   | Free                 | Key                                     |
| Models       | `GET`  | `/v1/models`                                            | Catalog with Venice list prices and live Tokentide prices; filter with `?type=`                           | Free                 | Public; a key filters the list          |
|              | `GET`  | `/v1/models/traits`, `/v1/models/compatibility_mapping` | Suggested model per role (trait → model id); model names other APIs use → catalog ids                     | Free                 | Public                                  |
| Market       | `GET`  | `/v1/market`                                            | Live multipliers, Low Tide status, state of the day, tide tables                                          | Free                 | Public                                  |
|              | `GET`  | `/v1/market/stream`                                     | SSE snapshot of `/v1/market` every 15 s                                                                   | Free                 | Public                                  |
|              | `GET`  | `/v1/market/rules`                                      | Every pricing rule with live values (JSON, or `?format=markdown`)                                         | Free                 | Public                                  |
|              | `GET`  | `/v1/market/estimate`                                   | Cost of one request now, at each remaining hour, at tomorrow's opening                                    | Free                 | Public                                  |
|              | `POST` | `/v1/market/quote`                                      | The multiplier an admission would lock now, held 60 s                                                     | Free                 | Key                                     |
| Account      | `GET`  | `/v1/account`, `/v1/account/usage`                      | Balance, spend today, tier, limits, spend caps, Low Tide allowance; request metadata (never content)      | Free                 | Key                                     |
| Payments     | `POST` | `/v1/x402/top-up`                                       | USDC top-up over x402 v2: a `402` challenge, then the same call with `PAYMENT-SIGNATURE`                  | Adds credit          | Public; a key or SIWX picks the account |
|              | `GET`  | `/v1/x402/balance`                                      | Balance of the wallet that signed the `SIGN-IN-WITH-X` header                                             | Free                 | SIWX                                    |
|              | `GET`  | `/v1/x402/balance/{wallet}`                             | Deprecated (`Deprecation`, `Sunset`); answers `404 not_found` from 2026-12-01                             | Free                 | SIWX                                    |
| Uploads      | `POST` | `/v1/uploads`                                           | One-time private slot for a client-side encrypted file (Large Payload Lane, preview)                      | Free; needs balance  | Key                                     |
| Media        | `GET`  | `/v1/media/{token}`                                     | One download of a finished video or music job, from a connector link                                      | Free (paid at queue) | The link is the credential              |
| Service      | `GET`  | `/v1/status`, `/v1/openapi.json`                        | Health of Tokentide and Venice and state of the day (`status`: `operational`, `degraded`, `paused`); the OpenAPI 3.1 document | Free | Public                       |

Jobs (`media.md`): quote → queue (charged once) → retrieve every ~5 s. At most 8 uncollected jobs per account
(`429 rate_limited`); queueing closes before the reset (`503 epoch_rollover`). All music and most video models
are Anonymized: privacy mode `all` or `private_text`.

## Request and response headers

### Request headers

All optional; header names are case-insensitive.

| Header                                                                                   | Values                                           | Effect                                                                                                                                                                                                         |
| ---------------------------------------------------------------------------------------- | ------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `X-Tokentide-Lane`                                                                       | `standard` (default) \| `lowtide`                | Lane. Low Tide is cheaper, best effort and non-streaming only (`400 lowtide_requires_non_streaming`). A key can default to `lowtide`                                                                          |
| `X-Tokentide-Lowtide-Fallback`                                                           | `standard` \| `none` (default)                   | `standard`: run on Standard, at the Standard price, when Low Tide is closed or your Low Tide caps are used up, instead of `409 lowtide_closed` or `409 lowtide_cap_reached`                                    |
| `X-Tokentide-Max-Multiplier`                                                             | decimal above 0, at most 1, ≤ 6 decimals: `0.55` | Highest multiplier you accept: above it `409 price_above_limit`, with a `Retry-After` computed from the tide table. Also blocks the cross-epoch price rise. The key's own maximum still applies; the lower wins |
| `X-Tokentide-Max-Cost-USD`                                                               | decimal, e.g. `0.25`                             | Refuse at admission if the worst-case charge could exceed it: `409 cost_above_limit`. For chat the worst case is the input plus `max_completion_tokens` (or the model's maximum output) |
| `X-Tokentide-Fallback-Models`                                                            | comma list, at most 3 model ids                  | Backup models tried in order when the requested model is offline or overloaded; extra ids are ignored. Never silent (see `X-Tokentide-Model-Fallback`). Not used for E2EE, multipart or `/v1/image/multi-edit` |
| `X-Tokentide-Debug`                                                                      | `1`                                              | Adds the debug response headers below, on errors too. Nothing extra is stored                                                                                                                                  |
| `X-Client-Request-Id`                                                                    | 1–128 of `A-Z a-z 0-9 . _ : / + = -`             | Your correlation id: echoed back, recorded only as a keyed hash, so support can find a call that never got a response. Other values are ignored, never rejected                                                 |
| `Idempotency-Key`                                                                        | ≤ 128 characters                                 | The same key again within 24 h gets `409 duplicate_request` instead of running twice. The first result is never replayed (nothing is stored). Create one per logical request; reuse it on every retry        |
| `X-Tokentide-Upload`                                                                     | `<upload_id>; key=<base64>`                      | References a Large Payload Lane upload ([Large inputs](#large-inputs-and-e2ee))                                                                                                                                |
| `SIGN-IN-WITH-X`                                                                         | base64 CAIP-122 payload                          | Wallet authentication instead of an API key; a new signature for every request                                                                                                                                 |
| `PAYMENT-SIGNATURE` (`X-PAYMENT` for older clients)                                      | base64 x402 payload                              | Only on `POST /v1/x402/top-up`; on inference routes `400 payment_header_not_accepted`                                                                                                                          |
| `X-Venice-TEE-Client-Pub-Key`, `X-Venice-TEE-Model-Pub-Key`, `X-Venice-TEE-Signing-Algo` | as Venice defines them                           | Forwarded unchanged for E2EE. Your `Authorization`, cookies, IP address and `User-Agent` never reach Venice                                                                                                   |

### Response headers

Names arrive in lowercase; on a stream, all but the two cost headers arrive before the first event.

| Header                                                                                       | When                                              | Meaning                                                                                                                                            |
| -------------------------------------------------------------------------------------------- | ------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| `X-Request-Id`                                                                               | always                                            | `req_` + ULID, equal to `error.request_id`. Quote it to support; find the request with `GET /v1/account/usage?request_id=…`                         |
| `X-Client-Request-Id`                                                                        | you sent a valid one                              | Your id, echoed back. Never on CDN-cached public answers, whose `X-Request-Id` can be that of the request that filled the cache                    |
| `Link`                                                                                       | always                                            | Terms of Service and Privacy Policy, as `rel="terms-of-service"` and `rel="privacy-policy"` links                                                   |
| `X-Tokentide-Multiplier`                                                                     | priced requests                                   | The multiplier locked at admission, e.g. `0.655078`                                                                                                |
| `X-Tokentide-Lane`                                                                           | priced requests                                   | `standard` or `lowtide` (`standard` when a Low Tide request fell back)                                                                             |
| `X-Tokentide-Epoch`                                                                          | priced requests                                   | The UTC day the request counts towards, e.g. `2026-10-31`                                                                                          |
| `X-Tokentide-Cross-Epoch`                                                                    | priced requests                                   | `true` when the request may run past 00:00 UTC and was priced by the cross-epoch rule (its epoch is then tomorrow)                                 |
| `X-Tokentide-List-Cost-USD`, `X-Tokentide-Charge-USD`                                        | non-streaming                                     | What the request costs at the Venice list price; what was deducted from your balance (decimal strings)                                             |
| `X-Tokentide-Model-Privacy`                                                                  | model routes                                      | `private`, `tee`, `e2ee` or `anonymized`                                                                                                           |
| `X-Tokentide-Model-Fallback`                                                                 | a backup model ran                                | The `X-Tokentide-Fallback-Models` candidate that served it; the body's `model` and `x-venice-model-id` show it too                                 |
| `X-Tokentide-Output-Capped`                                                                  | your balance limited the output                   | The output limit (tokens: at least 256, or your smaller limit) the chat completion or response ran with; it may end with `finish_reason: "length"` |
| `X-Tokentide-Lowtide-Opens-At`                                                               | `409 lowtide_closed`                              | Forecast opening of Low Tide (ISO 8601, UTC), when known                                                                                           |
| `X-RateLimit-Limit-Requests`, `X-RateLimit-Remaining-Requests`, `X-RateLimit-Reset-Requests` | key-authenticated requests                        | Tokentide's per-minute limit for this key (never Venice's), e.g. `600`; requests left in the window; time to the reset, a duration such as `12s`   |
| `Retry-After`                                                                                | 402 (spend cap), 409, 429, 503 when waiting helps | Seconds to wait. About a minute is sent as `59`; long waits (a sold-out day, a cap reset) are exact. See `errors-and-limits.md`                    |
| `PAYMENT-REQUIRED`, `PAYMENT-RESPONSE`                                                       | `POST /v1/x402/top-up`                            | x402 v2 challenge and settlement receipt (base64 JSON)                                                                                             |
| `Deprecation`, `Sunset`                                                                      | `GET /v1/x402/balance/{wallet}`                   | The route is deprecated and retired on 2026-12-01: use `GET /v1/x402/balance`                                                                       |
| `X-Tokentide-Debug-Timings`, `X-Tokentide-Debug-Upstream-Status`, `X-Tokentide-Debug-Retries`, `X-Tokentide-Debug-Upstream-Id`, `x-venice-version`, `cf-ray` | `X-Tokentide-Debug: 1` | Server-Timing in ms (`auth`, `admit`, `lease`, `upstream_ttfb`, `overhead`, `total`); Venice's HTTP status and response `id` (non-streaming), when the response relays them (left out on Tokentide's own errors); Tokentide's retries towards Venice; Venice's API version and ray id |

From Venice: `Content-Type`, `x-venice-is-content-violation`, `x-venice-is-blurred`, `x-venice-enhanced-prompt`,
`x-venice-model-id`, `x-venice-model-name`, `X-Venice-TEE`, `X-Venice-TEE-Provider` and the deprecation headers
`x-venice-deprecated*`, `x-venice-model-deprecation-*` (alert on them; switch models before the date). Never
exposed: Venice's `x-ratelimit-*` and `x-venice-balance-*`, `set-cookie`, `cf-*`.

### Read the cost of a request

```python
import os
from decimal import Decimal

from openai import OpenAI

client = OpenAI(base_url="https://api.tokentide.app/v1", api_key=os.environ["TOKENTIDE_API_KEY"])
raw = client.chat.completions.with_raw_response.create(
    model="deepseek-v4-1-flash",
    messages=[{"role": "user", "content": "Explain the tides in one sentence."}],
    max_completion_tokens=200,
    extra_headers={"X-Tokentide-Max-Multiplier": "0.70"},  # refuse rather than pay more than 0.70 x list
)
print(raw.parse().choices[0].message.content)  # parse() returns the usual ChatCompletion
charge = Decimal(raw.headers.get("x-tokentide-charge-usd") or "0")  # decimal strings: keep them exact
saved = Decimal(raw.headers.get("x-tokentide-list-cost-usd") or "0") - charge
print(raw.headers.get("x-request-id"), raw.headers.get("x-tokentide-multiplier"), charge, saved)
print("output limit lowered to:", raw.headers.get("x-tokentide-output-capped"))  # None unless the balance capped it
```

In TypeScript, read `response.headers.get('x-tokentide-charge-usd')` after
`const { data, response } = await client.chat.completions.create(body, { headers }).withResponse()`.

## Streaming

- Format: server-sent events, one `data: <JSON chunk>` line per event, ending with `data: [DONE]`. Chunks are
  Venice's, unchanged except the final usage chunk. `/v1/responses` streams typed SSE events.
- Cost: a stream has no cost headers. The final usage chunk, sent before `data: [DONE]` whether or not you set
  `stream_options.include_usage`, carries it:

```json
{
  "object": "chat.completion.chunk",
  "choices": [],
  "usage": { "prompt_tokens": 14, "completion_tokens": 31, "total_tokens": 45 },
  "cost": { "usd": 0.000028, "diem": 0 },
  "tokentide": { "list_cost_usd": "0.000042", "multiplier": "0.655078", "lane": "standard", "epoch": "2026-10-31", "savings_usd": "0.000014" }
}
```

- `cost.usd` is your charge in USD (a JSON number; `diem` is always `0`); `tokentide` holds decimal strings:
  the Venice list cost, the locked multiplier, the lane, the epoch and your saving. In the OpenAI Python SDK,
  read both from `chunk.model_extra` on the chunk whose `chunk.usage` is set. Non-streaming chat completion
  and response bodies carry the same rewritten `cost` and added `tokentide` object.
- Keep-alive: `: keep-alive` comment lines every 15 s while a model thinks silently. SSE clients ignore them;
  a hand-written parser must skip lines that start with `:`.
- Limits: a stream with no data from Venice for 120 s times out; a request may run for at most 800 s. Low Tide
  refuses `stream: true`; E2EE requires it.
- Errors inside a stream: the status is already `200`, so Venice's error arrives unchanged as
  `data: {"error": {"message": …, "type": …, "code": …}}`, then `data: [DONE]`. Treat it as final: Tokentide
  never retries a started stream. A stream that ends without its usage chunk is charged provisionally at its
  worst case (never more than was reserved), then corrected to what Venice billed.

## Models

`GET /v1/models` returns the Venice catalog with list prices (`model_spec.pricing`), capabilities such as
`supportsVision` or `supportsFunctionCalling`, limits (context length, output limit), retirement dates, and a
`tokentide` object with your current prices on both lanes.

- Send your key: the list then holds only what its privacy mode allows. `private` (new keys' default) lists
  Private, TEE and E2EE models; `private_text` adds Anonymized image, video and audio models; `all` lists all,
  including Anonymized models such as Claude, GPT and Gemini models. Others answer `403 model_not_allowed`.
- `?type=` takes `text`, `decision`, `embedding`, `image`, `inpaint`, `upscale`, `video`, `music`, `tts`, `asr`.

```json
{
  "id": "deepseek-v4-1-flash",
  "type": "text",
  "model_spec": { "privacy": "private", "pricing": { "input": { "usd": 0.3 }, "output": { "usd": 1.2 } } },
  "tokentide": {
    "privacy_tier": "private",
    "standard": { "multiplier": "0.655078", "input_per_1m": "0.196524", "output_per_1m": "0.786094", "per_unit": null, "unit": null },
    "lowtide": { "open": true, "eligible": true, "multiplier": "0.458555", "input_per_1m": "0.137567", "output_per_1m": "0.550266", "per_unit": null, "unit": null },
    "price_locked_until": null,
    "epoch": "2026-10-31"
  }
}
```

- `standard` and `lowtide` give the multiplier now and your prices in USD per 1M tokens (`input_per_1m`,
  `output_per_1m`) or per `unit` (`per_unit`: images, edits, seconds of audio, characters), rounded up.
  `lowtide.eligible` is `false` for models excluded from Low Tide; `lowtide.open` is the lane's status now.
- `GET /v1/models/traits` suggests a model per role (`most_intelligent`, `default_reasoning`, `default_code`,
  `default_vision`, `fastest`, …): explore, then pin explicit ids, as a trait can move to another model.
  `GET /v1/models/compatibility_mapping` maps model names other APIs use to catalog ids.

## Market API

The market reads are public; quotes need a key. Multipliers are decimal strings, each with an integer `*_ppm`
twin (parts per million: `1000000` = the Venice list price). Times are ISO 8601, UTC.

```bash
curl https://api.tokentide.app/v1/market                          # CDN-cached 5 s
curl -N https://api.tokentide.app/v1/market/stream                # SSE
curl "https://api.tokentide.app/v1/market/rules?format=markdown"  # CDN-cached 15 s; JSON without format
curl "https://api.tokentide.app/v1/market/estimate?model=zai-org-glm-5-2&input_tokens=1200&output_tokens=800&at=2026-11-02T22:00:00Z"
```

### `GET /v1/market`

| Field                                     | Meaning                                                                                                                                                                                                                                                                       |
| ----------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `epoch`                                   | The UTC day: `id`, `state` (`open`; `closing` in the last 10 min; `rolling` from 00:00 UTC until Venice confirms the reset; `degraded` if unconfirmed after 90 s), `starts_at`, `ends_at`, `seconds_to_reset`, `tau` (fraction of the day elapsed)                            |
| `standard`, `next_epoch`                  | `multiplier`, `multiplier_ppm`, `savings_pct`: live, surges included, so it can sit above the table (a lower bound); while `rolling`, the new day's opening. `next_epoch`: `id`, `open_multiplier`, `open_multiplier_ppm` (tomorrow's opening price) |
| `lowtide`                                 | `open`, `multiplier` (shown while closed too: the price if it opened now), `multiplier_ppm`, `savings_pct`, `opens_at` (forecast or `null`), `reason` when closed: `disabled`, `killed`, `no_spare`, `congested`, `guard_window`, `nearly_sold_out` (closed until the reset), `epoch_state`, `no_discount` |
| `tide_table.today`, `tide_table.tomorrow` | `level`, `decay_depth`, `gamma`, `m_min`, `m_max`, `lowtide_lambda`, `lowtide_floor`, `published`, `hash`, `curve` (97 points `{t, m_ppm}`, every 15 min from 00:00 to the next 00:00 UTC). `tomorrow` is `null` until published at 12:00 UTC; once published it never changes |
| `sales_paused`, `sold_out`, `reopens_at`, `updated_at` | `sales_paused`: sales are paused. `sold_out: true` once today's discounted capacity is used up, and `reopens_at` is then the next reset: inference answers `503 capacity_unavailable` with a `Retry-After` counting down to 00:00 UTC. `updated_at`: snapshot time |

### Stream, rules, estimate, quote

- `GET /v1/market/stream`: `event: tick` every 15 s with the `GET /v1/market` JSON in `data:`; reconnect on
  `event: reconnect` (after about 13 min). ~20 new connections a minute per network, then `429 rate_limited`.
- `GET /v1/market/rules`: every rule that decides a price, with live values (`charge`, `standard`, `surge`,
  `lowtide`, `quotes`, `queued_jobs` cut-offs, …). `?format=markdown` gives the same as `text/markdown`, ready
  for a model that must reason about prices.
- `GET /v1/market/estimate` (CDN-cached 5 s) prices one request with the billing arithmetic. Pass `model` (id or
  alias) and `input_tokens` and/or `output_tokens` (integers; reasoning tokens count as output), or `units` for
  per-unit models (a decimal string in `tokentide.standard.unit`: images, edits, upscales, seconds of audio, or
  millions of characters: 3,500 characters = `0.0035`). Optional `at`: an ISO 8601 time later than now, today or
  tomorrow once its table is published. Errors: `400 invalid_request` with the field in `error.param` (unknown
  model, no quantity, tokens for a per-unit model, `at` outside the tables); `403 model_not_allowed` (a model
  Tokentide does not offer). `now` is live; `schedule` (each remaining UTC hour), `last_same_day` and
  `tomorrow_open` come from the published tables, which surges can only raise. Excerpt (illustrative values):

```json
{
  "list_cost_usd": "0.0052",
  "now": {
    "standard": { "multiplier": "0.6175", "charge_usd": "0.003211", "savings_usd": "0.001989", "savings_pct": 38.2 },
    "lowtide": { "multiplier": "0.43225", "charge_usd": "0.002248", "eligible": true, "open": true, "reason": null, "opens_at": null }
  },
  "at_time": { "at": "2026-11-02T22:00:00.000Z", "standard": { "multiplier": "0.576693", "charge_usd": "0.002999" } },
  "schedule": [{ "at": "2026-11-02T21:00:00.000Z", "standard_charge_usd": "0.003117", "lowtide_charge_usd": "0.002182" }],
  "tomorrow_open": { "epoch": "2026-11-03", "standard": { "multiplier": "0.75", "charge_usd": "0.0039" } }
}
```

`POST /v1/market/quote` returns the multiplier an admission would lock now, held 60 s, never past the reset.
Optional body `{"lane": "standard"}` (default) or `{"lane": "lowtide"}`, else `400 invalid_request`; during
the reset `503 epoch_rollover` (retry in about 30 s); Low Tide while closed `409 lowtide_closed`. Each request
is still priced at its own admission: cap it with `X-Tokentide-Max-Multiplier`.

```bash
curl https://api.tokentide.app/v1/market/quote -H "Authorization: Bearer $TOKENTIDE_API_KEY" \
  -H "Content-Type: application/json" -d '{"lane": "lowtide"}'
# {"object": "quote", "account": "…", "lane": "lowtide", "epoch": "2026-10-31", "multiplier": "0.458555",
#  "multiplier_ppm": 458555, "locked_at": "2026-10-31T18:00:03.000Z", "expires_at": "2026-10-31T18:01:03.000Z"}
```

## Account and usage

Money fields are exact decimal USD strings: sum them as `Decimal`, never as floats. `*_micros` and other
64-bit integers arrive as strings: convert them with `int` (Python) or `BigInt` (TypeScript).

```bash
curl https://api.tokentide.app/v1/account -H "Authorization: Bearer $TOKENTIDE_API_KEY"
curl -G https://api.tokentide.app/v1/account/usage -H "Authorization: Bearer $TOKENTIDE_API_KEY" \
  --data-urlencode "from=2026-10-01T00:00:00Z" -d limit=100
curl -G https://api.tokentide.app/v1/account/usage -H "Authorization: Bearer $TOKENTIDE_API_KEY" \
  -d format=csv -d limit=1000 -o tokentide-usage.csv
```

### `GET /v1/account`

| Field         | Meaning                                                                                                                                                                                                                                                 |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `principal`, `tier` | `key` (API key) or `wallet` (`SIGN-IN-WITH-X`); trust tier `new`, `verified`, `trusted` or `custom`                                                                                                                                               |
| `free_use`    | `true`: every request and quote is charged $0 and needs no balance; rate limits and the spending rate still apply                                                                                                                                      |
| `balance`     | `available_usd` (paid credit, never expires), `promo_usd` (promotional credit, expires 12 months after it is granted), `leased_usd` (set aside for fast admission, still yours), `spendable_usd` (what new requests can use now)                       |
| `spend_today` | Since 00:00 UTC: `charged_usd` (what you paid), `list_usd` (the same requests at the Venice list price), `savings_usd`                                                                                                                                  |
| `limits`      | Integers `requests_per_minute_per_key`, `concurrency`, `image_requests_per_minute`; strings `spend_velocity_usd_per_minute`, `running_requests_usd`; caps of the calling key (`daily_cap_usd`, `weekly_cap_usd`, `monthly_cap_usd`) and of the whole account (`account_daily_cap_usd`, `account_weekly_cap_usd`, `account_monthly_cap_usd`) |
| `lowtide`     | `allowance_usd`, `used_usd`, `cap_per_hour_usd`, `open`                                                                                                                                                                                                 |

Caps apply per UTC day, per ISO week (from Monday 00:00 UTC) and per UTC calendar month; `null` means no cap
and `"0"` blocks all spend. A request that would exceed a cap gets `402 spend_limit_reached`.

### `GET /v1/account/usage`

Request metadata, newest first, kept 90 days; a key sees its own requests, a SIWX wallet its account's.

| Parameter    | Default | Meaning                                                                                                       |
| ------------ | ------- | ------------------------------------------------------------------------------------------------------------- |
| `limit`      | `100`   | Rows per page, 1 to 1,000                                                                                     |
| `before`     | —       | Cursor: rows older than this request id. Pass the previous page's `next_before`                              |
| `from`, `to` | —       | UTC timestamps such as `2026-10-01T00:00:00Z`, compared with `received_at` (`from` inclusive, `to` exclusive) |
| `model`, `endpoint`, `request_id` | — | Filters: one model, one endpoint (e.g. `chat_completions`, `audio_transcriptions`), one request (its `X-Request-Id`) |
| `format`     | `json`  | `json`, or `csv` for the same columns as a CSV file                                                           |

Each row is one request's metadata (`request_id`, times, `endpoint`, `model_id`, `lane`, `status_code`, token
counts, `epoch_id` as a timestamp at 00:00 UTC, …) and cost: `list_cost_micros`, `charge_micros` (both `0` when
Venice did not bill), `multiplier_ppm` (`655078` = `0.655078`), `settlement` (`final`, or `provisional` while
reconciled). Page with `next_before` until `has_more` is `false`. A CSV answer is one page without them: when it
has `limit` rows, request the next page with `before` set to its last `request_id`.

```python
import os

import httpx

params = {"from": "2026-10-01T00:00:00Z", "to": "2026-11-01T00:00:00Z", "limit": 1000}
headers = {"Authorization": f"Bearer {os.environ['TOKENTIDE_API_KEY']}"}
paid_micros = 0
with httpx.Client(base_url="https://api.tokentide.app/v1", headers=headers) as http:
    while True:
        res = http.get("/account/usage", params=params)
        res.raise_for_status()
        page = res.json()
        paid_micros += sum(int(row["charge_micros"]) for row in page["data"])  # strings: exact integer sums
        if not page["has_more"]:
            break
        params["before"] = page["next_before"]
print(f"paid ${paid_micros / 1e6:.2f}")
```

## Large inputs and E2EE

### Large inputs

Request bodies go direct up to 4.5 MB (above: `413 payload_too_large`); non-streaming JSON responses up to
64 MB (larger ones fail after Venice billed them: stream). For inputs of 4.5 to 25 MB, in this order:

1. **Public URL** for `/v1/image/edit`, `/v1/image/multi-edit`, `/v1/image/background-remove` and
   `style_references`: Venice fetches it (no redirects, at most 25 MB), so the bytes skip Tokentide.
2. **Large Payload Lane (preview)** for `/v1/audio/transcriptions` and image files without a URL: encrypt the
   file on your side (AES-256-GCM), get a single-use, 10-minute slot from `POST /v1/uploads` (20 per 10 minutes
   per account; positive balance needed), `PUT` the ciphertext to its `upload_url`, then call the endpoint with
   `X-Tokentide-Upload: <upload_id>; key=<base64 key>` instead of the file. At most 25 MiB of plaintext. The
   header holds the key: never log it. Format, fields and errors: `media.md`.
3. **Compression.** Opus at 24 kbps fits about 3 minutes of speech per MB.

**Media links.** `GET /v1/media/{token}` is the link that the connector's `check_video_job` and
`check_music_job` tools return for a finished job. The sealed token names one job of one account, expires after
6 hours and is the only credential: treat the URL as a secret. The file streams from Venice (nothing is kept);
after one complete download it is deleted upstream and the link answers `404` (as while the job still runs).

### E2EE

- Venice's end-to-end encrypted inference, relayed: you encrypt `user` and `system` messages to a public key in
  an attested hardware enclave, and Tokentide sees only ciphertext.
- Only `POST /v1/chat/completions` (not `/v1/responses`), `e2ee-*` models (e.g. `e2ee-glm-5-3-p`), `stream:
  true`, Standard lane; the default `private` key mode allows them (`X-Tokentide-Model-Privacy: e2ee`).
- Fetch and verify the model's attestation directly from Venice, never via a proxy (Tokentide included), then
  send the three `X-Venice-TEE-*` headers. A stale attestation fails in-stream (`e2ee_attestation_stale`):
  verify a new one and retry. More: `security-and-privacy.md` and https://tokentide.app/docs/e2ee.

## Further reading

- https://tokentide.app/docs/api (interactive reference with a console; OpenAPI at `GET /v1/openapi.json`)
- https://tokentide.app/docs/quickstart, https://tokentide.app/docs#status, https://tokentide.app/models
- https://tokentide.app/docs/lanes#request-headers, https://tokentide.app/docs/lanes#response-headers
- https://tokentide.app/docs/lanes#streaming-responses, https://tokentide.app/docs/lanes#market-api
- https://tokentide.app/docs/billing#checking-your-balance, https://tokentide.app/docs/billing#usage-api
- https://tokentide.app/docs/errors#errors-inside-a-stream, https://tokentide.app/docs/errors#debugging-a-request
- https://tokentide.app/docs/privacy#privacy-modes-per-api-key, https://tokentide.app/docs/changelog
- https://tokentide.app/docs/choosing-models#find-models, https://tokentide.app/docs/large-payloads
- https://tokentide.app/docs/rate-limits#body-duration-and-stream-limits, https://tokentide.app/docs/x402
- https://tokentide.app/docs/video-and-music, https://tokentide.app/docs/sdk
