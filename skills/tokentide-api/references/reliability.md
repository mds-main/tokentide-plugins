# Reliability

How to keep a Tokentide integration working when a request is refused or fails: an output limit on every
request, Tokentide first with a fallback provider (complete Python and TypeScript code, streaming included),
retries, `Retry-After`, idempotency, backup models, streaming, the balance, cost records and tests. Open it
when you write or review production integration code. Every error code and limit is in `errors-and-limits.md`.

## Contents

- [Set an output limit on every request](#set-an-output-limit-on-every-request)
- [Tokentide first, with a fallback provider](#tokentide-first-with-a-fallback-provider)
- [Retries](#retries)
- [Backup models on Tokentide](#backup-models-on-tokentide)
- [Streaming](#streaming)
- [Balance, costs and model ids](#balance-costs-and-model-ids)
- [Test the whole setup before you need it](#test-the-whole-setup-before-you-need-it)
- [Further reading](#further-reading)

## Set an output limit on every request

Set `max_completion_tokens` on every text request (`max_tokens` works too; `/v1/responses` takes
`max_output_tokens`), a little above the longest answer you expect.

**Why.** Before a request runs, Tokentide counts it at its **worst case**: its input plus the longest answer
it may write, which without a limit is the model's whole output limit (often tens of thousands of tokens, even
when the real answer is a few hundred). Every check below uses the worst case:

| Check | When the worst case doesn't fit |
| --- | --- |
| The day's capacity, shared by all customers | `503 capacity_unavailable` with `Retry-After: 59`, even while `GET /v1/market` shows the day open; smaller requests still pass |
| Your running-requests limit | `429 rate_limited` with `Retry-After: 2`: fewer of your requests run at once |
| Your balance | The output limit is lowered to what the balance covers (`X-Tokentide-Output-Capped`), or `402 insufficient_balance` |
| Your spend caps | `402 spend_limit_reached`, even when the request would have cost less than what is left |
| The Low Tide hourly cap and daily allowance | `409 lowtide_cap_reached` |
| `X-Tokentide-Max-Cost-USD` | `409 cost_above_limit` |
| The daily reset | Near 00:00 UTC, a request that might finish after the reset pays the higher of today's and tomorrow's price |

The limit **doesn't change what you pay**: you pay for the tokens used, and the worst case is held only while
the request runs (illustration from the docs: a 128,000-token worst case at $50 per million output tokens
holds $6.40, so 3 requests fit in a $20 running-requests limit; with `max_completion_tokens: 8000`, 50 fit).

- Set it comfortably above the largest `usage.completion_tokens` you see in real responses, for example twice.
- Reasoning models count their reasoning in `max_completion_tokens`: leave room for it, or the answer can come
  back short or empty.
- An answer that reaches the limit stops with `finish_reason: "length"` (`status: "incomplete"` on
  `/v1/responses`). If that happens often, raise the limit for that kind of request.
- A limit above the model's own maximum output is a `400 invalid_request`; `GET /v1/models` lists the limits.

```python
import os

from openai import OpenAI

client = OpenAI(base_url="https://api.tokentide.app/v1", api_key=os.environ["TOKENTIDE_API_KEY"])
completion = client.chat.completions.create(
    model="zai-org-glm-5-2",  # model ids are examples: the current catalog is GET /v1/models
    messages=[{"role": "user", "content": "Summarize this support ticket in three bullet points: …"}],
    max_completion_tokens=800,  # a little above the longest answer you expect
)
if completion.choices[0].finish_reason == "length":
    print("The answer hit the limit: raise it for this kind of request.")
```

## Tokentide first, with a fallback provider

Tokentide sells a limited daily supply shared by all customers: once it is used up, it is sold out until the
00:00 UTC reset, and your balance, spend caps and rate limits can stop a request too. For production, send
every request to Tokentide first and keep the provider you use today as the fallback. Tokentide refuses before
anything runs, so a refusal is never charged; the fallback bills only what it serves.

- **Fall back** when the request was fine but Tokentide can't serve it now: `402`, `429`, `500`, `502`, `503`,
  `504`, a timeout or a connection error.
- **Fall back and alert a person** on `401 invalid_api_key`, `403 account_restricted`, `403 ip_not_allowed`.
- **Never fall back** on `403 model_not_allowed` (it would send the request where the key's privacy mode says
  no) or other `4xx` (`400`, `404`, `413`, `415`, `422`): the request is wrong and the fallback would hide the
  bug. Fix it and alert.
- **`409` comes from your own limits:** on `lowtide_closed` or `lowtide_cap_reached`, resend with
  `X-Tokentide-Lowtide-Fallback: standard`; on `price_above_limit` or `cost_above_limit`, wait (`Retry-After`)
  or fall back, as you choose. The code below raises them.
- **Remember `Retry-After`** (a small circuit): after a refusal, send requests straight to the fallback until
  `Retry-After` has passed (30 s when there is none); after a sold-out day, that is the 00:00 UTC reset. Each
  process learns from its own first refusal: servers don't need to share this state.
- **Mind privacy:** what the fallback serves follows that provider's terms. Keep requests that must stay on
  Private models off the fallback (queue them until `Retry-After`), or fall back only to a provider whose
  terms meet your requirements.

**Pick the model pairs in advance:** the same model on both routes (Claude, GPT and Gemini are in the
Tokentide catalog as Anonymized models, so the Tokentide key needs privacy mode `all`), or a Private model on
Tokentide with a vendor model of the same class (answers differ a little). Ids differ, except at Venice. Check
both catalogs before you ship:

| Model | Id on Tokentide | Fallback provider | Id at the fallback |
| --- | --- | --- | --- |
| Claude Opus 5.5 | `claude-opus-5-5` | Anthropic | `claude-opus-5-5` |
| GPT-5.5 | `openai-gpt-55` | OpenAI | `gpt-5.5` |
| GLM 5.2 | `zai-org-glm-5-2` | Venice | `zai-org-glm-5-2` |
| Gemini 3.8 Flash | `gemini-3-8-flash` | Google (Gemini API) | `gemini-3.8-flash` |
| DeepSeek V4.1 Flash | `deepseek-v4-1-flash` | Vercel AI Gateway | `deepseek/deepseek-v4.1-flash` |

### Python implementation

OpenAI as the fallback (`pip install openai`; `TOKENTIDE_API_KEY`, `OPENAI_API_KEY`). `stream=True` works too:
a refusal still comes before the first token. For another provider, change `fallback` and `MODELS`.

```python
import logging
import os
import time

import openai
from openai import OpenAI

tokentide = OpenAI(
    base_url="https://api.tokentide.app/v1",
    api_key=os.environ["TOKENTIDE_API_KEY"],  # privacy mode "all" reaches GPT models
    max_retries=0,  # hand over to the fallback at once instead of retrying
)
fallback = OpenAI()  # reads OPENAI_API_KEY; keeps the SDK's default retries

MODELS = {"tokentide": "openai-gpt-55", "fallback": "gpt-5.5"}  # one model, each provider's id
FALL_BACK_ON = {402, 429, 500, 502, 503, 504}  # sold out, no credit, caps, limits, incidents
BLOCKED = {"invalid_api_key", "account_restricted", "ip_not_allowed"}  # fall back, and alert someone
skip_until = 0.0  # after a refusal, go straight to the fallback until Retry-After has passed


def chat(messages: list[dict], **params):
    global skip_until
    if time.time() >= skip_until:
        try:
            # A refusal (a sold-out day included) is raised here, as an HTTP error, before the first token.
            return tokentide.chat.completions.create(model=MODELS["tokentide"], messages=messages, **params)
        except openai.APIStatusError as e:
            blocked = e.code in BLOCKED  # the key or the account: a person has to fix it
            if e.status_code not in FALL_BACK_ON and not blocked:
                raise  # a problem with the request itself (or a 409): fix it rather than hide it
            if blocked:
                logging.error("Tokentide refused the key or the account: %s", e.code)
            retry_after = e.response.headers.get("retry-after", "")
            skip_until = time.time() + (int(retry_after) if retry_after.isdigit() else 30)
        except openai.APIConnectionError:  # no answer at all, timeouts included
            skip_until = time.time() + 30
    return fallback.chat.completions.create(model=MODELS["fallback"], messages=messages, **params)


if __name__ == "__main__":
    question = [{"role": "user", "content": "Why do tides happen? One sentence."}]
    print(chat(question, max_completion_tokens=1000).choices[0].message.content)
    chunks = chat(question, stream=True, max_completion_tokens=1000)  # refusals were handled in chat()
    try:  # an error inside a started stream is raised while you iterate: it is final
        for chunk in chunks:
            if chunk.choices:
                print(chunk.choices[0].delta.content or "", end="", flush=True)
            elif chunk.usage:  # Tokentide's final usage chunk carries the cost
                print("\ncost:", (chunk.model_extra or {}).get("cost"))
    except openai.APIError as e:
        logging.error("The stream ended with an error; send a new request if needed: %s", e)
```

### TypeScript implementation

The same rules as a wrapper around any call (`npm install openai`; an ES module, for the top-level `await`):

```ts
import OpenAI from 'openai';

const tokentide = new OpenAI({
  baseURL: 'https://api.tokentide.app/v1',
  apiKey: process.env.TOKENTIDE_API_KEY, // privacy mode "all" reaches GPT models
  maxRetries: 0, // hand over to the fallback at once instead of retrying
});
const fallback = new OpenAI(); // reads OPENAI_API_KEY; keeps the SDK's default retries

const MODELS = { tokentide: 'openai-gpt-55', fallback: 'gpt-5.5' }; // one model, each provider's id
const FALL_BACK_ON = new Set([402, 429, 500, 502, 503, 504]); // sold out, no credit, caps, limits, incidents
const BLOCKED = new Set(['invalid_api_key', 'account_restricted', 'ip_not_allowed']); // alert someone too
let skipUntil = 0; // after a refusal, go straight to the fallback until Retry-After has passed

/** Sends a request to Tokentide first, and to the fallback when Tokentide can't serve it. */
export async function withFallback<T>(send: (client: OpenAI, model: string) => Promise<T>): Promise<T> {
  if (Date.now() >= skipUntil) {
    try {
      // A refusal (a sold-out day included) rejects here, as an HTTP error, before the first token.
      return await send(tokentide, MODELS.tokentide);
    } catch (e) {
      const blocked = e instanceof OpenAI.APIError && BLOCKED.has(e.code ?? ''); // the key or the account
      if (e instanceof OpenAI.APIConnectionError) {
        skipUntil = Date.now() + 30_000; // no answer at all, timeouts included
      } else if (e instanceof OpenAI.APIError && (FALL_BACK_ON.has(e.status ?? 0) || blocked)) {
        if (blocked) console.error(`Tokentide refused the key or the account: ${e.code}`);
        skipUntil = Date.now() + (Number(e.headers?.get('retry-after')) || 30) * 1000;
      } else {
        throw e; // a problem with the request itself (or a 409): fix it rather than hide it
      }
    }
  }
  return send(fallback, MODELS.fallback);
}

const messages: OpenAI.ChatCompletionMessageParam[] = [{ role: 'user', content: 'Why do tides happen?' }];
const reply = await withFallback((client, model) =>
  client.chat.completions.create({ model, messages, max_completion_tokens: 1000 }),
);
console.log(reply.choices[0]?.message.content);

const chunks = await withFallback((client, model) =>
  client.chat.completions.create({ model, messages, max_completion_tokens: 1000, stream: true }),
);
try {
  // An error inside a started stream rejects while you iterate: it is final.
  for await (const chunk of chunks) process.stdout.write(chunk.choices[0]?.delta?.content ?? '');
} catch (e) {
  console.error('\nThe stream ended with an error; send a new request if needed:', e);
}
```

### Other fallback providers

The Tokentide side and the rules stay the same; change only the fallback client and the ids (in TypeScript,
pass the same `baseURL` and `apiKey` to `new OpenAI({ … })`):

| Fallback | Client (Python) | Model ids | What differs |
| --- | --- | --- | --- |
| Anthropic | `anthropic.Anthropic()` (`pip install anthropic` or `npm install @anthropic-ai/sdk`; reads `ANTHROPIC_API_KEY`) | `claude-opus-5-5` on both routes | Its own API: `claude.messages.create(model=..., max_tokens=16000, system=system, messages=[...])` takes the system prompt in `system`, requires `max_tokens`, keeps `user` and `assistant` turns in `messages`. Handle `stop_reason == "refusal"` (Claude declined), join the `text` blocks of `message.content`, stream with `claude.messages.stream(...)` |
| Venice (your own account) | `OpenAI(base_url="https://api.venice.ai/api/v1", api_key=os.environ["VENICE_API_KEY"])` | The same id on both routes, e.g. `zai-org-glm-5-2` | Private models stay Private; `venice_parameters` and the E2EE headers work on both. Venice bills what it serves and sees your IP address and account. It runs the models on both routes, so chain a second fallback after it for a Venice incident |
| Gemini | `OpenAI(base_url="https://generativelanguage.googleapis.com/v1beta/openai/", api_key=os.environ["GEMINI_API_KEY"])` (a Google AI Studio key) | `gemini-3-8-flash` → `gemini-3.8-flash` | Google calls this OpenAI compatibility beta; to use Google's own SDK, replace only the fallback call |
| Vercel AI Gateway | `OpenAI(base_url="https://ai-gateway.vercel.sh/v1", api_key=os.environ["AI_GATEWAY_API_KEY"])` (`VERCEL_OIDC_TOKEN` can replace the key on a Vercel deployment) | Lab in front: `deepseek/deepseek-v4.1-flash`, `anthropic/claude-opus-5.5`, `openai/gpt-5.5`, `google/gemini-3.8-flash` | One fallback for every pair, open-weight models included. Runs at a provider it picks, billed by Vercel; according to Vercel's documentation it keeps no prompts or responses. For zero-data-retention providers only: Zero Data Retention in its settings, or `providerOptions: { gateway: { zeroDataRetention: true } }` (paid Vercel plans). Its own fallbacks don't cover a Tokentide sold-out day |

Behind a gateway or router of your own, add Tokentide as an OpenAI-compatible provider (base URL
`https://api.tokentide.app/v1`), first, with your current provider as its fallback, and check that it falls
back on `429`, `5xx` and timeouts and waits for `Retry-After` before it tries Tokentide again.

## Retries

### SDK retries and timeouts

- Set `max_retries=0` (Python) or `maxRetries: 0` (TypeScript) on the Tokentide client: the OpenAI SDKs retry
  `429` and `5xx` twice before they raise, which only delays the fallback. Keep the default on the fallback.
- If you set a client timeout, make it longer than your slowest request: requests can run for up to 800
  seconds (for example `timeout=900`). A request you stop waiting for may still run to the end and be charged,
  and the fallback would bill the same work again. For long generations, stream.

### Honor Retry-After and back off (no fallback)

Batch jobs: wait for `Retry-After` on `429` and `503`; retry `500` and `502` with exponential backoff (0.5 s,
1 s, 2 s, 4 s … up to 30 s) plus a small random delay, 3–5 attempts, one `Idempotency-Key` for all of them.
`Retry-After: 59` means about a minute; longer values are exact (hours when sold out): pause the job until
then (`reopens_at` in `GET /v1/market`). The OpenAI SDKs don't retry `402`: on `spend_limit_reached`, pause
until `Retry-After`; on `insufficient_balance`, stop until the balance grows.

```python
import os
import random
import time
import uuid

import openai
from openai import OpenAI

# max_retries=0: this loop retries and honors long Retry-After values; timeout above the 800 s maximum.
client = OpenAI(base_url="https://api.tokentide.app/v1", api_key=os.environ["TOKENTIDE_API_KEY"],
                max_retries=0, timeout=900)


def create_with_retry(max_attempts: int = 5, max_wait: float = 120.0, **params):
    """Raises 4xx, 402, 504, the last failure, and a Retry-After above max_wait (pause the job until then)."""
    headers = {**params.pop("extra_headers", {}), "Idempotency-Key": str(uuid.uuid4())}  # one key per request
    delay = 0.5
    for attempt in range(1, max_attempts + 1):
        try:
            return client.chat.completions.create(**params, extra_headers=headers)
        except openai.APIConnectionError:  # no answer (timeouts too): it may have run; the key covers that
            if attempt == max_attempts:
                raise
            wait = delay
        except openai.APIStatusError as e:
            retry_after = e.response.headers.get("retry-after", "")
            wait = float(retry_after) if retry_after.isdigit() else delay
            if e.status_code not in (429, 500, 502, 503) or attempt == max_attempts or wait > max_wait:
                raise  # 4xx: fix it; 402: money; 409 duplicate_request: an earlier attempt ran
        time.sleep(wait + random.random() * 0.25)
        delay = min(delay * 2, 30)


review = [{"role": "user", "content": "Classify this review as positive or negative: …"}]
completion = create_with_retry(model="deepseek-v4-1-flash", messages=review, max_completion_tokens=1000)
print(completion.choices[0].message.content)
```

For large batches, the Tide Runner of the Tokentide SDKs (publication to npm and PyPI is planned) does this
and can schedule work into Low Tide: https://tokentide.app/docs/sdk#tide-runner.

### Never retry a 4xx unchanged

`400`, `401`, `403`, `404`, `405`, `413`, `415` and `422` can't succeed if sent again, and repeating them
costs you: more than 10 `4xx` errors at Venice within 30 seconds get you `429 rate_limited` for 30 seconds.
Log the `code` and `param`, fix the request, and alert. `402` and `409` follow their own rules (above).

### Send an Idempotency-Key

A network error or a timeout doesn't tell you whether the request ran. Create one key per logical request (up
to 128 characters, such as `invoice-summary-{invoice_id}` or a UUID) and send the same key on every retry:
`extra_headers={"Idempotency-Key": key}` in Python, `{ headers: { 'Idempotency-Key': key } }` as the second
argument of `create` in TypeScript. Keys are remembered for 24 hours. If an earlier attempt ran, the retry
gets `409 duplicate_request` instead of running, and being charged, twice; if none ran, the retry runs
normally. The first result is never replayed (Tokentide doesn't store it): treat the earlier attempt as the
one that ran (`GET /v1/account/usage` lists it).

## Backup models on Tokentide

`X-Tokentide-Fallback-Models` lists up to 3 other Tokentide models, tried in order when the requested model is
offline or overloaded: `extra_headers={"X-Tokentide-Fallback-Models": "deepseek-v4-1-flash,z-ai-glm-5-3"}`
(TypeScript: `{ headers: { … } }` as the second argument of `create`). It is never silent: the response's
`model` field and `X-Tokentide-Model-Fallback` show the model that ran. Pick backups of the same privacy level
with the features you use (tools, structured output, vision). Only the first 3 ids are tried, and it is never
used for E2EE, multipart or `/v1/image/multi-edit` requests. It doesn't help on a sold-out day: the fallback
provider does.

## Streaming

- Stream long chat answers (`"stream": true`): non-streaming JSON is relayed in one piece up to 64 MB, and a
  larger one fails after Venice has already run and billed it. Streaming also shows the first tokens sooner.
- Refusals arrive as HTTP errors before the first token, so the fallback decision happens when the request is
  sent, as in the code above. A stream that has started is not affected when the day sells out.
- The cost arrives in the final usage chunk, before `data: [DONE]`, whether or not you set
  `stream_options.include_usage`, and not in headers: `cost.usd` is what you paid; `tokentide` holds
  `list_cost_usd`, `multiplier`, `lane`, `epoch` and `savings_usd`. Python: `chunk.model_extra`; TypeScript:
  `(chunk as unknown as { tokentide?: unknown }).tokentide`.
- `: keep-alive` comments arrive every 15 seconds while a model thinks silently, so your idle timeouts don't
  cut the stream (SSE clients ignore them); 120 seconds without data from Venice ends it.
- An error inside a started stream is final, and Tokentide never retries it: catch it around the loop and send
  a new request if you still need the answer. Low Tide takes only non-streaming requests.

## Balance, costs and model ids

**Keep the balance from running out.** A request whose worst case the balance can't cover gets
`402 insufficient_balance`; before that, chat answers are shortened to what the balance covers
(`X-Tokentide-Output-Capped`; such an answer may stop with `finish_reason: "length"`). Turn on auto top-up
with a monthly maximum, and a low-balance alert, at https://tokentide.app/app/billing; if an automatic top-up
fails (an expired card), the fallback keeps the app running. A spend cap's `402 spend_limit_reached` also
sends requests to the fallback: you can cap Tokentide spend without stopping the app.

**Record what each request cost.** Non-streaming responses carry `X-Tokentide-Charge-USD` (what you paid) and
`X-Tokentide-List-Cost-USD` (the list price); streams, the final usage chunk. Log them with `X-Request-Id`,
the feature and the provider that served the request. Send your own `X-Client-Request-Id`: support can then
find a request that timed out before you saw its `X-Request-Id`.

```python
import logging
import uuid

raw = client.chat.completions.with_raw_response.create(  # `client` as in the output-limit example
    model="zai-org-glm-5-2",
    messages=[{"role": "user", "content": "Summarize this support ticket in three bullet points: …"}],
    max_completion_tokens=800,
    extra_headers={"X-Client-Request-Id": str(uuid.uuid4())},  # your own id: support can find the request
)
completion = raw.parse()
logging.info("provider=tokentide feature=ticket-summary request_id=%s charge_usd=%s list_usd=%s",
             raw.headers.get("x-request-id"), raw.headers.get("x-tokentide-charge-usd"),
             raw.headers.get("x-tokentide-list-cost-usd"))
```

In TypeScript, `const { data, response } = await client.chat.completions.create(…).withResponse()` gives the
headers. The Usage dashboard (https://tokentide.app/app/usage), its exports and `GET /v1/account/usage` break
costs down by key and model: one key per app or feature makes that useful.

**Keep model ids current.** Take them from `GET /v1/models` with your key: it lists only the models the key's
privacy mode allows, with their prices and limits. Models due for retirement show their date and replacement
at https://tokentide.app/models, and Venice's deprecation headers (`x-venice-deprecated*`,
`x-venice-model-deprecation-*`) reach you on responses: alert on them and switch before the date. Keep model
ids and fallback pairs in configuration, so a switch is one change.

## Test the whole setup before you need it

A fallback you have never run fails on the day you need it. In staging:

1. Force the fallback: set `skip_until` (`skipUntil`) far in the future, or point the Tokentide client at an
   address where nothing listens, such as `http://127.0.0.1:9/v1`. Check that every request comes back from
   the fallback with the model you expect.
2. Give staging its own API key, with a small daily spend cap.
3. Check the refusal handling: `402`, `409` and `429` with and without `Retry-After`, a `4xx` that must not
   fall back, and a stream that ends with an error.
4. Record which provider served each request, and `X-Tokentide-Charge-USD` for Tokentide's, to see your
   savings and how often you fall back.

Before a large batch, check `GET /v1/market` (`sold_out`, `reopens_at`, `lowtide.open`) and `GET /v1/account`
(your limits and Low Tide allowance); planning is in `pricing-and-timing.md`.

## Further reading

- https://tokentide.app/docs/best-practices
- https://tokentide.app/docs/fallback
- https://tokentide.app/docs/errors
- https://tokentide.app/docs/rate-limits
- https://tokentide.app/docs/lanes#streaming-responses
- https://tokentide.app/docs/billing#auto-top-up
- https://tokentide.app/docs/sdk#tide-runner
