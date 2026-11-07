# Errors and limits

Every Tokentide error and what to do about it: the error envelope, each error code with its retry and fallback
rule, errors passed through from Venice, errors inside a stream, `Retry-After`, the rate limits by trust tier,
the other request limits, and a decision procedure to turn into code. Open it when you handle or debug an
error, write retry or fallback logic, or size the concurrency of a job. The complete fallback code is in
`reliability.md`.

## Contents

- [The error envelope](#the-error-envelope)
- [Error codes](#error-codes)
- [Errors from Venice](#errors-from-venice)
- [Errors inside a stream](#errors-inside-a-stream)
- [Retry-After](#retry-after)
- [Rate limits](#rate-limits)
- [Other limits](#other-limits)
- [Decision procedure](#decision-procedure)
- [Debugging a request](#debugging-a-request)
- [Further reading](#further-reading)

## The error envelope

Tokentide's own errors use the OpenAI-compatible envelope, so the OpenAI SDKs raise them as normal API errors:

```json
{
  "error": {
    "message": "Low Tide is closed right now. It is forecast to open at 19:40 UTC.",
    "type": "tokentide_error",
    "code": "lowtide_closed",
    "param": null,
    "request_id": "req_01JDV6Q7Z8R2M3N4P5Q6R7S8T9"
  }
}
```

- Match on `code`: it is stable. Never parse `message`: it is written for people and can change.
- `type` is always `tokentide_error` for errors Tokentide generates. Any other body is Venice's, passed
  through ([Errors from Venice](#errors-from-venice)).
- `param` names the offending field or header, when there is one. Log it with the `code`.
- `request_id` equals the `X-Request-Id` response header. Quote it to support.
- `Retry-After` (seconds) is set whenever waiting helps. A request refused before it runs is never charged.

```python
import os

import openai

client = openai.OpenAI(base_url="https://api.tokentide.app/v1", api_key=os.environ["TOKENTIDE_API_KEY"])
try:
    client.chat.completions.create(
        model="deepseek-v4-1-flash",  # model ids are examples: the current catalog is GET /v1/models
        messages=[{"role": "user", "content": "…"}],
        max_completion_tokens=500,
    )
except openai.APIStatusError as e:  # e.type == "tokentide_error" for Tokentide's own errors
    print(e.status_code, e.code, e.param, e.request_id, e.response.headers.get("retry-after"))
```

TypeScript (`openai` npm): `catch (e) { if (e instanceof OpenAI.APIError) … }` gives `e.status`, `e.code`,
`e.param`, `e.type`, `e.requestID` and `e.headers?.get('retry-after')`.

## Error codes

Retry: **never** = never unchanged (fix the request first), **wait** = after `Retry-After`, **backoff** =
exponential backoff with jitter. Fall back: what a Tokentide-first setup does with its fallback provider
(`reliability.md`).

| Code | HTTP | Meaning | Retry | Fall back | What to do |
| --- | --- | --- | --- | --- | --- |
| `invalid_request` | 400 | Failed validation: a header, query or upload-slot request, a field over a model limit (e.g. `max_completion_tokens`), TTS input over 4,096 characters, image `variants` outside 1–4, `X-Tokentide-Upload`, embeddings over 64 MB | never | no, alert | Fix the field named in `param`. Embeddings (`param: "encoding_format"`): `"encoding_format": "base64"`, a lower `dimensions` or a smaller batch |
| `lowtide_requires_non_streaming` | 400 | `X-Tokentide-Lane: lowtide` with `stream: true` (TTS: `streaming: true`) | never | no | Send `stream: false`, or use Standard |
| `invalid_api_key` | 401 | Key missing, malformed, unknown, revoked or expired; a Venice key; a `tt_test_` key in production or a `tt_live_` key outside it | never | yes, alert | A person must fix the key: `Authorization: Bearer tt_live_…` with an active key |
| `unauthorized` | 401 | Valid credentials of the wrong kind for this route | never | no | Use the credential type the route expects |
| `insufficient_balance` | 402 | Balance can't cover the worst-case cost. Chat and responses are first capped to what it covers (`X-Tokentide-Output-Capped`) and refused only below a 256-token answer (or your smaller limit); also an upload slot with no spendable balance | after a top-up (no `Retry-After`); after three refusals less than 10 s apart, requests are refused for 10 s without a new check | yes | Top up or turn on auto top-up; a lower `max_completion_tokens` shrinks the reservation |
| `spend_limit_reached` | 402 | A daily, weekly or monthly cap on the key or account is used up (or is 0), or this request's worst case exceeds the room left | wait: to the cap's reset, or 59 s when only this request was too large | yes | Raise the cap, wait, or lower `max_completion_tokens`. No `Retry-After`: the cap is 0 or smaller than the request |
| `model_not_allowed` | 403 | The model's privacy level is above the key's privacy mode, the model is not offered, or it is excluded from Low Tide | never | **no** | Use an allowed model, or a key with privacy mode `all` for Anonymized models; Low Tide: Standard or `X-Tokentide-Lowtide-Fallback: standard` |
| `ip_not_allowed` | 403 | Caller outside the key's IP allowlist | never | yes, alert | Call from an allowed address or update the allowlist |
| `account_restricted` | 403 | Account suspended, banned or closed | never | yes, alert | Contact `support@tokentide.app` |
| `forbidden` | 403 | Authenticated, but not allowed this resource | never | no | Access only your own resources |
| `not_found` | 404 | Unknown route or resource (Venice account routes are never proxied; unknown or expired uploads) | never | no, alert | Check the path or id |
| `method_not_allowed` | 405 | The route exists, not with this method | never | no | Use the method in the `Allow` header |
| `price_above_limit` | 409 | Price above `X-Tokentide-Max-Multiplier` or the key's maximum multiplier (also the higher price of a request that may run past 00:00 UTC) | wait: until the scheduled price falls below your limit | your choice | Wait, raise the limit, or fall back |
| `cost_above_limit` | 409 | The worst-case charge could exceed `X-Tokentide-Max-Cost-USD` | never | your choice | Lower `max_completion_tokens` or raise the limit |
| `lowtide_closed` | 409 | Low Tide closed: no spare capacity, 90% of the day sold (closed until the reset), congestion, the last 2 minutes before the reset, or paused | wait, or retry at `X-Tokentide-Lowtide-Opens-At` | no | Resend with `X-Tokentide-Lowtide-Fallback: standard` to run on Standard |
| `lowtide_cap_reached` | 409 | Hourly Low Tide cap or daily Low Tide allowance used up | wait (hourly cap only) | no | Standard, or the same fallback header; the allowance grows with Standard spend |
| `duplicate_request` | 409 | The `Idempotency-Key` was already accepted in the last 24 hours | never | no | An earlier attempt ran and was charged; results are never replayed (see `GET /v1/account/usage`) |
| `payload_too_large` | 413 | Body over 4.5 MB, or an upload over its declared or allowed size | never | no | Pass a public URL, or use the Large Payload Lane (≤ 25 MB) |
| `unsupported_media_type` | 415 | `Content-Type` or encoding not accepted on this route | never | no | Send `application/json` (`multipart/form-data` where documented) |
| `rate_limited` | 429 | A Tokentide rate limit, a congested model, the model's upstream limit, or the 4xx circuit breaker ([Rate limits](#rate-limits)) | wait, with jitter | yes (batch: wait) | Slow down; check the `X-RateLimit-*` headers and `GET /v1/account` |
| `internal_error` | 500 | Unexpected error at Tokentide | backoff | yes | Retry with the same `Idempotency-Key`; quote `request_id` if it persists |
| `upstream_unavailable` | 502 | Venice failed or was unreachable after Tokentide's retries (a model that keeps failing is skipped for up to 30 s, in `Retry-After`), or a non-streaming response over 64 MB | backoff | yes | Check https://tokentide.app/status. Over 64 MB fails again and is still charged: use `stream: true` or a smaller request |
| `capacity_unavailable` | 503 | Day sold out; less left than this request's worst case; sales paused; too many requests that may run past the reset; market briefly unavailable; the model paused, failing, unpriced or with no Venice key free | wait | yes, and skip Tokentide until `Retry-After` | Read the [Retry-After](#retry-after) value; for one unavailable model, `X-Tokentide-Fallback-Models` moves the request |
| `epoch_rollover` | 503 | Daily reset in progress: image endpoints and quotes wait for the new day | wait (usually under a minute) | yes, or wait | Retry after `Retry-After` |
| `service_unavailable` | 503 | A feature paused or not enabled (e.g. the Large Payload Lane), a dependency briefly unreachable, or busy relaying large embedding responses | later | yes | Retry later |
| `upstream_timeout` | 504 | Venice did not answer in time (mostly long non-streaming requests) | not blindly: it may have run | yes | Use `stream: true` for long generations; retry only with the same `Idempotency-Key`. If Venice answered, it is charged as reserved (never more), then corrected |

Only with x402 USDC top-ups (`POST /v1/x402/top-up`) or wallet sign-in (`SIGN-IN-WITH-X`):

| Code | HTTP | Meaning | Retry | What to do |
| --- | --- | --- | --- | --- |
| `payment_header_not_accepted` | 400 | `PAYMENT-SIGNATURE` or `X-PAYMENT` on an inference route | never | Send payments only to `POST /v1/x402/top-up` |
| `siwx_invalid` | 401 | Bad, expired or replayed `SIGN-IN-WITH-X`; `param` holds the reason (`stale`, `nonce_replayed`, `domain_mismatch`, …) | only with a newly signed header | Sign a fresh header for this host on every attempt: nonces are single use |
| `payment_in_progress` | 409 | The same x402 payment is still settling | after a few seconds | Check the balance; don't sign a new payment |
| `settlement_timeout` | 504 | An x402 top-up did not confirm in time | after checking the balance | Tokentide credits it within minutes if it landed; a new signature is a new payment and is not blocked |

On `POST /v1/x402/top-up`, `409 duplicate_request` means the payment was already credited once, to another
account.

## Errors from Venice

Venice's validation errors reach you **with Venice's own status and body**: `400`, `404`, `413`, `415` and
`422` (including the OpenAI-style `context_length_exceeded`). Recognise them:

- The body is not the Tokentide envelope: `{"error": "…"}` (sometimes with `details` and `issues`), or
  `{"error": {…}}` for context-length errors. `type` is never `tokentide_error`.
- `422` always comes from Venice: Tokentide has no `422` code.
- With the OpenAI SDKs, `e.type` is not `"tokentide_error"`, and `e.code` is empty for the string form.

Handle them like Tokentide's own `4xx`: fix the request, never retry it unchanged (they count towards the 4xx
circuit breaker), never fall back, and alert. `422` content-policy rejections are normally not charged. Images
that Venice flags as content violations come back as `200` with `x-venice-is-content-violation: true` and are
not charged.

Venice errors about Tokentide's supply, not your request, are never passed through:

| Venice answers | You receive |
| --- | --- |
| `402` (Tokentide's Venice balance or key spend limit) | `503 capacity_unavailable` |
| `401` / `403` caused by Tokentide's own key | `502 upstream_unavailable` |
| `403` because of the model's privacy level | `403 model_not_allowed` |
| `429` (rate limit or model overload) | `429 rate_limited` with `Retry-After` |
| `500` / `502` / `503` before any data reached you | retried by Tokentide, then `502` or `503` |
| `504` | `504 upstream_timeout` (not retried) |

## Errors inside a stream

Refusals (sold out, limits, caps, balance) always arrive as HTTP errors before the first token. Once a stream
has started, the status is already `200`: if Venice fails after that, its error arrives in-band, unchanged,
followed by the terminator:

```text
data: {"error":{"message":"…","type":"server_error","code":"model_overloaded","param":null,"retry_after":30}}

data: [DONE]
```

- Treat it as final: the stream is over. Tokentide never retries a request whose stream has started. If you
  still need the answer, send a new request (to Tokentide or to your fallback). The OpenAI SDKs raise it while
  you iterate, so put the `try` around the loop, not only around `create()`.
- Billing: a stream that ends without its final usage chunk (an in-band error, a dropped connection, your own
  disconnect) is charged provisionally at its worst case, never more than was reserved, then checked against
  Venice's records: anything Venice did not bill is credited back automatically.
- The same applies to a non-streaming response that Venice answered but that could not be delivered
  (connection cut, out of time, over 64 MB): charged provisionally, corrected to what Venice billed when the
  response carries Venice's id (chat completions and responses). It keeps its `Idempotency-Key`: a retry with
  that key gets `409 duplicate_request`.

## Retry-After

- Seconds. Sent on `409`, `429` and `503` when waiting helps, on `402 spend_limit_reached`, and on `502` while
  a failing model is skipped. Vercel's edge can also answer `429` without the JSON envelope: honor its
  `Retry-After` when present.
- A wait of about a minute is sent as **`Retry-After: 59`**: the OpenAI and Anthropic SDKs and the Vercel AI
  SDK only wait for values under 60 seconds, and otherwise retry within seconds.
- **Longer values are exact** (a sold-out day, a cap's reset, a paused model, a price limit). Those SDKs don't
  wait for them: handle them in your code. Never sleep through them in a request a user is waiting for: send
  it to your fallback, or pause the job until then.
- With a fallback, skip Tokentide until `Retry-After` has passed, and for about 30 seconds when there is none.

| `Retry-After` | Sent with | Do this |
| --- | --- | --- |
| `2` | `429`: running-requests limit | Wait: room comes back as your running requests finish |
| `10` | `503 capacity_unavailable`: too many requests that may run past the daily reset | Wait a few seconds |
| up to `30` | `429`: 4xx circuit breaker; `502` while a failing model is skipped | Fix the failing requests; fall back or wait |
| to the next minute | `429`: spending rate | Wait or fall back |
| `59` | `503 capacity_unavailable` while `GET /v1/market` shows `sold_out: false`; `402 spend_limit_reached` when only this request is too large for the room left | Smaller requests still pass: lower `max_completion_tokens`, retry after a minute, or fall back meanwhile |
| to 00:00 UTC (hours) | `503 capacity_unavailable`, sold out (`GET /v1/market`: `sold_out: true`, `reopens_at`) | Fall back until then; batch jobs pause |
| to the cap's reset | `402 spend_limit_reached` (daily, weekly or monthly cap) | Fall back or pause; or raise the cap |
| until the price falls | `409 price_above_limit` | Wait or fall back |
| none | `402 insufficient_balance`; `spend_limit_reached` with a cap of 0 or smaller than the request; client errors | Waiting won't help: top up, raise the cap or fix the request |

## Rate limits

Every rate limit answers `429 rate_limited` with `Retry-After`. Spend caps answer `402 spend_limit_reached`;
the Low Tide cap and allowance answer `409 lowtide_cap_reached`. All are Tokentide's own limits for your key
and trust tier, never those of a Venice key. Venice's rate-limit headers never reach you.

| Response header (key-authenticated requests) | Example | Meaning |
| --- | --- | --- |
| `X-RateLimit-Limit-Requests` | `600` | Requests per minute allowed for this key |
| `X-RateLimit-Remaining-Requests` | `0` | Requests left in the current window |
| `X-RateLimit-Reset-Requests` | `12s` | Time until the window resets (a duration) |
| `Retry-After` | `12` | Seconds to wait (on `429`) |

| Limit | new | verified | trusted | Notes |
| --- | --- | --- | --- | --- |
| Requests per minute, per API key | 300 | 1,500 | 6,000 | You can set a lower limit per key |
| Concurrent requests, per account | 16 | 64 | 256 | Requests in flight at once |
| Image requests per minute, per account | 4 | 10 | 20 | Venice allows about 20 image requests a minute for Tokentide's whole account |
| Spending rate, per account | 1% | 5% | 15% | Share of the day's capacity per minute, at list price; never below $0.10 a minute |
| Running requests, per account | 25% | 50% | 100% | Share of the day's capacity, each request at its worst case; at least $1 |
| Low Tide cap, per account | 2% | 5% | 10% | Share of the day's capacity per hour, at list price |
| Spend caps (day, week, month), per key or account | none | none | none | Set by you in the dashboard |
| Concurrent requests per wallet (SIWX only) | 5 | 5 | 5 | |

- **Tiers.** Accounts funded by card start as `new` until they are at least 7 days old and have paid $100 by
  card. Tiers rise with payment history and verification; above `verified` requires two-factor authentication.
  Business customers can ask for custom limits.
- **Read your current limits from `GET /v1/account`:** the money limits are shares of the day's capacity, so
  they move with supply. It returns `tier`; `limits` with `requests_per_minute_per_key`, `concurrency`,
  `image_requests_per_minute`, `spend_velocity_usd_per_minute`, `running_requests_usd` (USD as decimal
  strings), the key's `daily_cap_usd`, `weekly_cap_usd`, `monthly_cap_usd` and the account's
  `account_daily_cap_usd`, `account_weekly_cap_usd`, `account_monthly_cap_usd` (`null` = no cap); and
  `lowtide` with `allowance_usd`, `used_usd`, `cap_per_hour_usd` and `open`.
- **What counts.** Only requests that run a model (chat, responses, embeddings, decisions, images, audio, and
  queueing video and music). Free routes (`GET /v1/account`, `GET /v1/models`, the market endpoints, and the
  quote, retrieve and complete steps of jobs) don't count; job quotes and polling have their own limits
  ([Other limits](#other-limits)).
- **Image requests** are scarce upstream, so image endpoints can answer `429` sooner than text.
- **Spending rate** (`limits.spend_velocity_usd_per_minute`): what your requests that finish in a minute may
  cost, at their actual cost at list price, whatever you are charged (Low Tide, a lower tide price and free
  use included). A request counts when it finishes; a failed one counts nothing; the output limit doesn't
  change it. Over it: `429` with `Retry-After` until the next minute.
- **Running requests** (`limits.running_requests_usd`): what your running requests may hold at once, each at
  its worst case (for text without `max_completion_tokens`, the model's whole output limit). Over it: `429`
  with `Retry-After: 2`. One request always runs when none is running, so a large video or music job never
  gets stuck. A realistic `max_completion_tokens` lets more of your requests run at once. Tokentide can raise
  this limit per account.
- **Congestion.** When a model family nears Venice's limit, Tokentide first raises the price (a short, capped
  congestion surge), then at 97% turns away the lowest-priority traffic with `429` ("This model is at capacity
  right now"): Low Tide first, then new accounts.
- **The 4xx circuit breaker.** Too many failed requests would block a model at Venice for every customer, so a
  customer who causes more than **10 `4xx` errors at Venice within 30 seconds** gets `429 rate_limited` for 30
  seconds. Never retry a `4xx` unchanged.
- **Limited beta** (until general availability): one API key per account (keys the Tokentide plugin links for
  its local scripts don't count) and a daily spend limit across all keys and wallets, reported in
  `limits.account_daily_cap_usd`. Over it: `402 spend_limit_reached` with a `Retry-After` that counts down to
  00:00 UTC.

## Other limits

| Limit | Value |
| --- | --- |
| Request body, sent directly | 4.5 MB (`413 payload_too_large`); larger inputs: a public URL or the Large Payload Lane (≤ 25 MB) |
| Non-streaming JSON response | 64 MB (larger: `502 upstream_unavailable`, still charged); streams and binary media: no limit |
| Request duration | 800 seconds at most |
| Idle stream | Ends after 120 seconds without data from Venice; `: keep-alive` comments every 15 seconds meanwhile |
| Text-to-speech input | 4,096 characters |
| Embeddings inputs per request | 2,048 |
| `POST /v1/images/generations` prompt | 1,500 characters (any model) |
| Image `variants` | 1–4 |
| `Idempotency-Key` | ≤ 128 characters; duplicates detected for 24 hours |
| `X-Tokentide-Fallback-Models` | At most 3 models |
| Video and music jobs | Per account: 8 queued and not yet collected, 60 quotes a minute; poll a job at most once every 2 s |
| Upload slots (`/v1/uploads`) | 20 per 10 minutes per account, about 30 a minute per network; needs a positive balance or free use |
| Market stream (`/v1/market/stream`) | About 20 new connections a minute per network |
| Unknown API keys | About 60 sign-ins a minute per network with keys Tokentide doesn't know |

## Decision procedure

On a failed Tokentide call, take the first rule that matches:

1. **No response** (connection error, client timeout): the request may have run. Retry with the same
   `Idempotency-Key` (a `409 duplicate_request` then means the first attempt ran), or fall back and skip
   Tokentide for about 30 s.
2. **Error inside a started stream:** final. Don't retry that stream; send a new request if you still need the
   answer.
3. **`400`, `404`, `413`, `415` or `422` whose `type` is not `tokentide_error`** (Venice's body): fix the
   request. No retry, no fallback; alert.
4. **`model_not_allowed`:** no fallback. Use an allowed model or a key with the right privacy mode.
5. **`invalid_api_key`, `account_restricted`, `ip_not_allowed`:** fall back, and alert a person.
6. **Any other `400`, `401`, `403`, `404`, `405`, `413`, `415`:** fix the request (`param`). No retry, no
   fallback; alert.
7. **`lowtide_closed`, `lowtide_cap_reached`:** resend with `X-Tokentide-Lowtide-Fallback: standard`, or wait
   for `Retry-After` (or `X-Tokentide-Lowtide-Opens-At`).
8. **`price_above_limit`:** wait for `Retry-After`, or fall back. **`cost_above_limit`:** lower
   `max_completion_tokens` or raise the limit (or fall back). **`duplicate_request`:** an earlier attempt ran;
   don't send it again.
9. **`insufficient_balance`:** fall back; don't retry until the balance grows (top up, auto top-up) or with a
   lower `max_completion_tokens`. The OpenAI SDKs don't retry `402`.
10. **`spend_limit_reached`:** fall back, or pause until `Retry-After`. Without `Retry-After`: lower
    `max_completion_tokens` or raise the cap.
11. **`429`, `503`:** interactive traffic falls back and skips Tokentide until `Retry-After`. Batch work
    sleeps `Retry-After` plus jitter when it is short, and pauses (or falls back) when it is hours. `503` with
    `Retry-After: 59` and `sold_out: false`: lower `max_completion_tokens` or retry after a minute.
12. **`500`, `502`:** fall back, or retry with exponential backoff and jitter (0.5 s, 1 s, 2 s, 4 s … capped
    at 30 s; 3–5 attempts) and the same `Idempotency-Key`. A `502` for a response over 64 MB fails again:
    stream it.
13. **`504 upstream_timeout`:** fall back, or retry with the same `Idempotency-Key`; switch long generations
    to `stream: true`.

`reliability.md` has the code: Tokentide first with a fallback for interactive traffic, and a retry loop for
batch work.

## Debugging a request

- `X-Request-Id` (= `request_id`) is Tokentide's id for the request. Once it has settled, the dashboard's
  Request Inspector shows its metadata.
- Send your own `X-Client-Request-Id` (1–128 letters, digits and `. _ : / + = -`, for example a UUID): it is
  echoed back and stored only as a keyed hash, so support can find a request that timed out before you saw its
  `X-Request-Id`. CDN-cached public answers (`GET /v1/market`, `GET /v1/models` without a key, …) don't echo
  it.
- `X-Tokentide-Debug: 1` adds, on errors too, `X-Tokentide-Debug-Timings` (ms: `auth`, `admit`, `lease`,
  `upstream_ttfb`, `overhead`, `total`), `X-Tokentide-Debug-Upstream-Status`, `X-Tokentide-Debug-Retries` and
  `X-Tokentide-Debug-Upstream-Id`. Nothing extra is stored.
- To `support@tokentide.app`, send the `X-Request-Id` (or your `X-Client-Request-Id`), the time in UTC, the
  host you called and the error `code`. Never send prompts or outputs.

## Further reading

- https://tokentide.app/docs/errors (one anchor per code: https://tokentide.app/docs/errors#lowtide_closed)
- https://tokentide.app/docs/rate-limits
- https://tokentide.app/docs/best-practices#retries
- https://tokentide.app/docs/billing#handling-402-errors
- https://tokentide.app/docs/fallback#when-to-fall-back
- https://tokentide.app/docs/lanes#low-tide-lane
- https://tokentide.app/status
