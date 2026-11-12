---
name: tokentide-api
description: Set up, build on and optimize the Tokentide API, the OpenAI- and Venice-compatible inference API at https://api.tokentide.app/v1 that sells Venice AI models (text, reasoning, decision models, embeddings, images, speech, transcription, video and music) from a limited daily supply below list price, with a price that falls through the UTC day and a cheaper Low Tide lane for work that can wait. Guides the user through creating an account, an API key and adding credit, then covers the first call with the OpenAI SDKs, model choice, cost control (output limits, task routing with decision models, caching, Low Tide, price and spend caps), reliability (a fallback provider for sold-out days, retries, idempotency), every error code, privacy levels, security and EU AI Act transparency duties. Use it whenever the user mentions Tokentide, api.tokentide.app, TOKENTIDE_API_KEY or a tt_live_ key, or is integrating, debugging, securing or cutting the cost of an app that calls the Tokentide API.
license: Proprietary (Tokentide Plugin License, see LICENSE). Use only with the Tokentide service.
compatibility: Any agent that can write code or make HTTPS requests to api.tokentide.app. The optional helper script needs Python 3.8+ (standard library only) and network access to api.tokentide.app.
metadata:
  version: "1.0.8"
  author: Tokentide
  homepage: https://tokentide.app/docs/best-practices
---

# Tokentide API

Tokentide is an inference API compatible with the OpenAI API and the Venice API. It sells Venice AI models from a
limited daily supply below the Venice list price: a Standard price that falls through the UTC day on a published
tide table, an opt-in Low Tide lane that is cheaper still for non-streaming work that can wait, and zero data
retention at Tokentide on every model. This skill helps you set the user up, write the integration, and keep it
reliable, cheap and secure.

Paths below (`scripts/…`, `references/…`) are relative to the folder that contains this file. Open a reference file
only when the task needs it; the table at the end says which.

## Facts to keep in mind

- **Base URL** `https://api.tokentide.app/v1` (the Venice path layout also works under `/api/v1`). **Auth**
  `Authorization: Bearer $TOKENTIDE_API_KEY`, a key that starts with `tt_live_`. Request bodies, streaming, tools,
  structured output and `venice_parameters` work as with OpenAI or Venice: change the base URL and the key.
- **Price** = Venice list price × a multiplier that is locked when the request starts and returned in
  `X-Tokentide-Multiplier`; the charge comes back in `X-Tokentide-Charge-USD` (or the final usage chunk of a stream).
  With the default parameters, Standard runs from about 25% below list at 00:00 UTC to about 47% just before
  midnight; Low Tide is about 30% below Standard. Refused requests are never charged.
- **Supply is limited each day.** When it is sold out, requests get `503 capacity_unavailable` until the 00:00 UTC
  reset, so production apps keep their current provider as a fallback.
- **Prepaid credit** that doesn't expire at midnight, spend caps per key and per account, price and cost limits per
  request.
- **Privacy**: Tokentide never stores prompts or outputs. Each model has a privacy level (Private, TEE, E2EE or
  Anonymized); each key a privacy mode (`private` by default, `private_text` or `all`) that limits which levels it may
  call. Anonymized models (Claude, GPT, Gemini and others) need `all`.
- **The catalog changes.** Take model ids from `GET /v1/models` (filtered to what the key may call); the ids in this
  skill are examples.

## First: make sure the user is set up

Run the read-only check (it never spends credit and never prints the key):

```sh
python3 scripts/tokentide.py check
```

Exit `0` means ready. Otherwise walk the user through the missing step below, in their language, one step at a time.
You cannot create accounts, keys or payments for them, and **you must never ask them to paste the key into the chat**:
they set `TOKENTIDE_API_KEY` themselves and you run the check again.

1. **Create an account** at https://tokentide.app/sign-up (email and password, an email link, GitHub or a wallet
   where offered), then open the verification email. Adding a passkey is recommended.
2. **Create an API key**: the guided page https://tokentide.app/app/onboarding, or **API keys** at
   https://tokentide.app/app/keys. The key is shown **once**: copy it straight into a password manager or secret
   store. Keep privacy mode `private` unless the app needs Anonymized models (`all`), or Anonymized image, video and
   audio models with private text (`private_text`).
3. **Add credit** under **Billing** at https://tokentide.app/app/billing: by card through Stripe from $10 (new
   accounts can add up to $50 by card per 24 hours), or with USDC where the page offers it. Set spend caps and alerts
   there too; auto top-up becomes available once the account is 7 days old and has added $100 by card.
4. **Store the key** in the environment, never in code: `export TOKENTIDE_API_KEY="tt_live_…"` (macOS and Linux),
   `$env:TOKENTIDE_API_KEY = "tt_live_…"` (PowerShell), a `.env` file listed in `.gitignore`, or the platform's secret
   store in production.
5. **Verify**: `python3 scripts/tokentide.py check` again.

Exit codes: `2` no key, `3` key rejected, `4` no credit (or a cap of 0), `5` network or API error. Details, key
settings, limits for new accounts and troubleshooting: `references/setup.md`.

## Make the first call

Python (`pip install openai`):

```python
import os
from openai import OpenAI

client = OpenAI(
    base_url="https://api.tokentide.app/v1",
    api_key=os.environ["TOKENTIDE_API_KEY"],
    max_retries=0,  # with a fallback provider, refusals should reach it at once (see the rules)
)

raw = client.chat.completions.with_raw_response.create(
    model="zai-org-glm-5-2",  # example id: list current ones with GET /v1/models
    messages=[{"role": "user", "content": "Explain the tides in one sentence."}],
    max_completion_tokens=300,  # a little above the longest answer you expect
)
completion = raw.parse()
print(completion.choices[0].message.content)
print("charged USD", raw.headers.get("x-tokentide-charge-usd"), "request", raw.headers.get("x-request-id"))
```

TypeScript (`npm install openai`):

```ts
import OpenAI from 'openai';

const client = new OpenAI({
  baseURL: 'https://api.tokentide.app/v1',
  apiKey: process.env.TOKENTIDE_API_KEY,
  maxRetries: 0,
});

const { data, response } = await client.chat.completions
  .create({
    model: 'zai-org-glm-5-2', // example id: list current ones with GET /v1/models
    messages: [{ role: 'user', content: 'Explain the tides in one sentence.' }],
    max_completion_tokens: 300,
  })
  .withResponse();
console.log(data.choices[0]?.message.content, response.headers.get('x-tokentide-charge-usd'));
```

curl:

```sh
curl https://api.tokentide.app/v1/chat/completions \
  -H "Authorization: Bearer $TOKENTIDE_API_KEY" -H "Content-Type: application/json" \
  -d '{"model": "zai-org-glm-5-2", "max_completion_tokens": 300,
       "messages": [{"role": "user", "content": "Explain the tides in one sentence."}]}'
```

Other OpenAI-compatible clients (LangChain, LlamaIndex, the Vercel AI SDK, Venice SDKs) work the same way: set the base
URL and the key. Venice-only fields go in the body as with Venice (`extra_body` in the OpenAI Python SDK). Every
endpoint, header and response field: `references/api-reference.md`.

## The rules for a production integration

Apply these by default in code you write, and check for them in code you review.

**Reliability**

1. **Set `max_completion_tokens` on every text request** (`max_output_tokens` on `/v1/responses`), about twice the
   longest answer you see in `usage.completion_tokens`. Admission counts each request at its worst case, so without a
   limit fewer requests run at once and big ones are refused first late in the day. It doesn't change the price.
   Reasoning models spend part of it on reasoning; `finish_reason: "length"` means it was too low.
2. **Tokentide first, the user's current provider as the fallback.** Fall back on `503`, `429`, `402`, `500`, `502`,
   `504`, timeouts and connection errors (refused before anything runs, so never charged). Fall back and alert on
   `401` and on `403 ip_not_allowed` or `account_restricted`. Never fall back on `403 model_not_allowed` or other
   `4xx`: the request itself is wrong. Full code for OpenAI, Anthropic, Gemini, Venice and Vercel AI Gateway as the
   fallback: `references/reliability.md`.
3. **Retry well.** `max_retries=0` on the Tokentide client when there is a fallback. Remember `Retry-After` and send
   traffic straight to the fallback until it passes (the 00:00 UTC reset on a sold-out day). Without a fallback, wait
   for `Retry-After` on `429` and `503` and back off with jitter on `500` and `502`. Never resend a `4xx` unchanged.
   Client timeouts must exceed the slowest request (up to 800 seconds).
4. **Send an `Idempotency-Key`** (created once per logical request, reused on every retry): a retry of a request
   that already ran gets `409 duplicate_request` instead of being charged twice.
5. **Name backup models on Tokentide** with `X-Tokentide-Fallback-Models` (up to 3, same privacy level and features)
   for when one model is down. The response's `model` field says which one ran.
6. **Stream interactive and long answers** (`"stream": true`); the cost arrives in the final usage chunk. An error
   inside a stream ends it: send a new request if the answer is still needed.

**Cost**

7. **Use the cheapest model that passes a quick eval** for each task, and frontier models only for hard work.
   Classification, routing, triage, scoring and yes-or-no checks go to **decision models** (`POST /v1/decisions`) at a
   fraction of a chat model's cost; search goes to embeddings. Route automatically: rules first, a decision model that
   scores difficulty, escalation when a cheap answer fails a check (`references/cost-efficiency.md`,
   `references/decision-models.md`).
8. **Send work no one is waiting for to Low Tide**: `X-Tokentide-Lane: lowtide` on non-streaming requests, plus
   `X-Tokentide-Lowtide-Fallback: standard` when the work must finish. Not urgent but needs Standard? Run it in the
   evening (UTC), when the tide table is lowest (`references/pricing-and-timing.md`).
9. **Cut tokens**: a stable prompt prefix and `prompt_cache_key` for caching, `reasoning_effort` as low as the task
   allows, trimmed history, retrieval instead of stuffing context, and reuse of answers and embeddings.
10. **Put a ceiling on everything**: `X-Tokentide-Max-Cost-USD` (worst-case charge per request) and
    `X-Tokentide-Max-Multiplier` (price per request) return a `409` that is never charged; daily, weekly and monthly
    caps per key and per account return `402 spend_limit_reached`; alerts warn before that.
11. **Check the market before a large batch**: `GET /v1/market` (public: `sold_out`, `reopens_at`, prices, whether Low
    Tide is open) and `GET /v1/market/estimate` (the batch priced at every remaining hour), or
    `python3 scripts/tokentide.py market` and `… estimate`.
12. **Record what every request cost** (`X-Tokentide-Charge-USD`, `X-Tokentide-List-Cost-USD`, `X-Request-Id`), with
    the feature and the provider that served it, and send your own `X-Client-Request-Id`. Optimize cost per
    successful task, not per token.

**Security and operations**

13. **One key per app and environment** with the narrowest privacy mode, a daily cap and, where addresses are fixed,
    an IP allowlist. Keys only in server-side environment variables or a secret store; never in client code, URLs,
    logs, repositories or chat. Rotate on a schedule; rotate with no overlap on a suspected leak.
14. **Treat model output as untrusted** (validate, escape, never execute it unchecked), defend against prompt
    injection from documents, web pages and tool results, and bound agents with step limits, budgets and human
    approval for risky actions (`references/security-and-privacy.md`, `references/prompts-and-agents.md`).
15. **Keep model ids in configuration**, refresh them from `GET /v1/models`, and alert on the deprecation headers
    (`x-venice-deprecated*`, `x-venice-model-deprecation-*`).
16. **Test the fallback in staging** before you need it: point the Tokentide client at an address where nothing
    listens and check that every request comes back from the fallback.

## Choose the model

| Task                                                   | Model type (`GET /v1/models?type=…`) | Endpoint                                      |
| ------------------------------------------------------ | ------------------------------------ | --------------------------------------------- |
| Chat, writing, extraction, code, tools, agents         | `text` (reasoning models for hard multi-step work) | `POST /v1/chat/completions`, `POST /v1/responses` |
| Classify, route, triage, score, rerank, check          | `decision`                           | `POST /v1/decisions`                          |
| Semantic search, RAG, clustering, deduplication        | `embedding`                          | `POST /v1/embeddings`                         |
| Generate images                                        | `image`                              | `POST /v1/image/generate`, `POST /v1/images/generations` |
| Edit images, remove backgrounds, upscale               | `inpaint`, `upscale`                 | `POST /v1/image/edit`, `/v1/image/multi-edit`, `/v1/image/background-remove`, `/v1/image/upscale` |
| Text to speech, transcription                          | `tts`, `asr`                         | `POST /v1/audio/speech`, `POST /v1/audio/transcriptions` |
| Video and music                                        | `video`, `music`                     | Asynchronous jobs (quote, queue, retrieve, complete): `POST /v1/video/queue`, `POST /v1/audio/queue` and their siblings |

Pick by requirements first (privacy level, context window, tools, vision, structured output), then by measured
quality, then by price (`python3 scripts/tokentide.py models --type text`). Details and examples:
`references/choosing-models.md`; images, audio, video and music: `references/media.md`; search and RAG:
`references/retrieval.md`.

## Handle errors

Errors use the OpenAI envelope: `{"error": {"message", "type": "tokentide_error", "code", "param", "request_id"}}`.
Match on `code`, never on `message`; quote `request_id` (= `X-Request-Id`) to support.

| HTTP | Code                                   | Retry the same request?                       | Fall back? | What to do                                                               |
| ---- | -------------------------------------- | --------------------------------------------- | ---------- | ------------------------------------------------------------------------ |
| 400  | `invalid_request`                      | No                                            | No         | Fix the field named in `param`                                           |
| 400  | `lowtide_requires_non_streaming`       | No                                            | No         | Send `stream: false`, or use Standard                                    |
| 401  | `invalid_api_key`                      | No                                            | Yes, alert | The key is wrong, revoked or expired: a person must fix it              |
| 402  | `insufficient_balance`                 | After a top-up                                | Yes        | Add credit, turn on auto top-up, or lower `max_completion_tokens`       |
| 402  | `spend_limit_reached`                  | After `Retry-After` (the cap's reset)         | Yes        | Wait, or raise the cap                                                   |
| 403  | `model_not_allowed`                    | No                                            | No         | Use a model the key's privacy mode allows (`GET /v1/models`)             |
| 403  | `ip_not_allowed`, `account_restricted` | No                                            | Yes, alert | Fix the allowlist or the account                                         |
| 404  | `not_found`                            | No                                            | No         | Check the path and the model id                                          |
| 409  | `price_above_limit`                    | After `Retry-After`                           | Your call  | Wait for the price to fall under `X-Tokentide-Max-Multiplier`, or raise it |
| 409  | `cost_above_limit`                     | No                                            | No         | Lower `max_completion_tokens` or raise `X-Tokentide-Max-Cost-USD`        |
| 409  | `lowtide_closed`, `lowtide_cap_reached`| After `Retry-After` / `X-Tokentide-Lowtide-Opens-At` | Standard | Add `X-Tokentide-Lowtide-Fallback: standard` to run on Standard instead |
| 409  | `duplicate_request`                    | No                                            | No         | The first attempt with this `Idempotency-Key` already ran                |
| 413  | `payload_too_large`                    | No                                            | No         | Send large inputs through `POST /v1/uploads`                             |
| 429  | `rate_limited`                         | After `Retry-After`                           | Yes        | Lower concurrency; never retry `4xx` in a loop (it trips a breaker)      |
| 500, 502, 504 | `internal_error`, `upstream_unavailable`, `upstream_timeout` | With backoff and jitter | Yes | Retry 3 to 5 times, or fall back                                    |
| 503  | `capacity_unavailable`                 | After `Retry-After`                           | Yes        | Sold out (until 00:00 UTC) or too little left for this request's worst case |
| 503  | `epoch_rollover`, `service_unavailable`| After `Retry-After`                           | Yes        | The daily reset or a short outage                                        |

`402` errors are never retried by the OpenAI SDKs: handle them in your code. Every code, the rate limits by trust
tier and upstream errors: `references/errors-and-limits.md`.

## Plan around the tide

- `python3 scripts/tokentide.py market` shows the live Standard and Low Tide prices, whether today is sold out, and
  the cheapest times left today; tomorrow's table is published at 12:00 UTC.
- `python3 scripts/tokentide.py estimate --model <id> --input-tokens N --output-tokens N` prices a request now, at
  every remaining hour and at tomorrow's opening (`GET /v1/market/estimate`, public).
- Interactive traffic: Standard, streaming, any time. Batch work: Low Tide, or Standard in the evening (UTC). Work
  that must finish: Low Tide with `X-Tokentide-Lowtide-Fallback: standard`, or the fallback provider on sold-out days.
- Near 00:00 UTC, a request that might run past the reset pays the higher of today's and tomorrow's price.

Lanes, the tide table, Low Tide limits, quotes and workload timing: `references/pricing-and-timing.md`.

## Privacy, security and the EU AI Act

- Match the key's privacy mode to the data: `private` for personal or confidential text; `all` only for keys that
  need Anonymized models. `X-Tokentide-Model-Privacy` on every response says which level served it.
- Send only what the task needs; redact personal data before it reaches any model; log metadata, not content.
- For EU users, the EU AI Act adds transparency duties (tell people they are talking to an AI, mark synthetic media,
  label deepfakes), AI literacy and, for high-risk uses, much more. `references/eu-ai-act.md` has the timeline,
  roles and concrete API examples. It is general information, **not legal advice**: say so, and recommend a
  qualified specialist for the user's specific case.

## The helper script

`scripts/tokentide.py` (Python 3.8+, standard library only) makes free, read-only `GET` calls to the Tokentide API,
reads the key from `TOKENTIDE_API_KEY`, refuses to send it to any other host and never prints it. Add `--json` for
machine-readable output.

| Command                                                         | What it answers                                                   |
| --------------------------------------------------------------- | ----------------------------------------------------------------- |
| `check`                                                         | Is the key set and valid? Credit, caps, rate limits, callable models |
| `market`                                                        | Live prices, Low Tide status, sold out or not, cheapest times left |
| `models [--type text\|decision\|embedding\|image\|…\|all]`       | Models this key may call, with Standard and Low Tide prices       |
| `estimate --model ID --input-tokens N --output-tokens N` (or `--units N`) | What a request costs now, through the day and tomorrow    |
| `usage [--days 7] [--model ID]`                                 | What this key spent in the last days, by model                    |

## Reference files

| Open                                  | When                                                                                         |
| ------------------------------------- | -------------------------------------------------------------------------------------------- |
| `references/setup.md`                 | The user has no account, key or credit; a setup check fails; preparing an account for production |
| `references/api-reference.md`         | Writing a call: endpoints, request and response headers, streaming, models, market, account, usage |
| `references/errors-and-limits.md`     | Handling or debugging an error; rate limits and trust tiers                                  |
| `references/reliability.md`           | Production code: output limits, fallback provider (complete code), retries, idempotency, tests |
| `references/pricing-and-timing.md`    | How charges work; the tide table; Low Tide; scheduling and pricing batch work                |
| `references/choosing-models.md`       | Picking a model for a feature; privacy levels and key modes; reading the catalog             |
| `references/media.md`                 | Images, speech, transcription, video and music; uploads; labelling generated media           |
| `references/cost-efficiency.md`       | Lowering cost: task router, caching, reasoning and output control, cost per task             |
| `references/decision-models.md`       | Classification, routing, triage, scoring or reranking with `/v1/decisions`                   |
| `references/retrieval.md`             | Search and RAG with embeddings                                                               |
| `references/prompts-and-agents.md`    | Prompts, structured output, tool calling, workflows, agents, evals                           |
| `references/security-and-privacy.md`  | Keys, data protection, privacy levels, E2EE, prompt injection, security review               |
| `references/eu-ai-act.md`             | The user or their customers are in the EU (general information, not legal advice)           |

## Working alongside the Tokentide plugin

The Tokentide plugin for Claude, ChatGPT and Codex adds a connector and a short-form video skill. If its tools are
available (`get_market`, `estimate_cost`, `get_account`, `explain_pricing`, …), use them for quick answers in the
conversation; use this skill and the REST API for code. For short-form social videos, the plugin's video skill runs
the whole pipeline. Both read `TOKENTIDE_API_KEY` when it is set, so the same key serves both (the video models need
privacy mode `private_text` or `all`).

Docs: https://tokentide.app/docs · Status: https://tokentide.app/status · Models and live prices:
https://tokentide.app/models · Tokentide is an independent service, not affiliated with or endorsed by Venice.ai.
