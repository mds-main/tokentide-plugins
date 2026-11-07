# Pricing and timing

How Tokentide prices requests: the charge formula, the Standard tide table through the UTC day, the Low Tide
lane, the daily reset, price limits, and pricing, scheduling and budgeting batches with the market API. Open
it to pick a lane or an hour, plan a batch, explain a charge, or handle a price, Low Tide or capacity refusal.
"Defaults" can change: read the values in force from `GET /v1/market/rules` (`?format=markdown` for prose).

## Contents

- [The model in five lines](#the-model-in-five-lines)
- [How a charge is computed](#how-a-charge-is-computed)
- [The Standard lane and the tide table](#the-standard-lane-and-the-tide-table)
- [The Low Tide lane](#the-low-tide-lane)
- [Price limits and spend caps](#price-limits-and-spend-caps)
- [Which lane and which hour](#which-lane-and-which-hour)
- [Price work before you send it](#price-work-before-you-send-it)
- [Waiting for a price](#waiting-for-a-price)
- [Monthly budgets and forecasting](#monthly-budgets-and-forecasting)
- [Further reading](#further-reading)

## The model in five lines

1. **Limited daily supply** of discounted Venice capacity, shared by all; renews at 00:00 UTC, can sell out.
2. **Venice list price × a multiplier**, locked at admission; Standard follows the tide table, at most `0.90`.
3. **Same price for everyone at once:** surges only raise it; caps and allowances limit quantity, never price.
4. **Refusals are free:** no charge for a request refused before it runs, or for one Venice does not bill.
5. **Prepaid USD balance**, priced when spent (when you top up never changes the price); never below zero.

## How a charge is computed

```text
charge_usd = ceil_to_micro_usd(list_cost_usd × multiplier)        minimum $0.000010 when anything is billable
```

- `list_cost_usd` is the `cost` Venice reports for chat, otherwise usage (tokens, characters, seconds, images)
  × Venice's published prices. The multiplier is the one in force at admission (`X-Tokentide-Multiplier`);
  every payment method buys at the same prices.
- Examples: list $0.0100 at `0.65` → $0.0065; list $0.0052 at `0.43225` → $0.0022477, rounded up to $0.002248;
  anything billable below $0.000010 pays $0.000010. Failed requests, empty responses and images flagged as
  content violations cost nothing.
- Read it back: `X-Tokentide-List-Cost-USD` and `X-Tokentide-Charge-USD` on non-streaming responses; on
  streams, the final usage chunk before `data: [DONE]`, sent even without `stream_options.include_usage`
  (`cost.usd` is your charge; `tokentide` holds `list_cost_usd`, `multiplier`, `lane`, `savings_usd`).
- **Worst case first.** Admission reserves the locked multiplier × the list price of the most the request
  could use (input plus `max_completion_tokens`, or the model's output limit), then charges actual usage.
  Balance, caps, `X-Tokentide-Max-Cost-USD` and capacity are checked against it: set `max_completion_tokens`.
- Per-model prices for both lanes, rounded up: `GET /v1/models` → `tokentide.standard` and `tokentide.lowtide`
  (`multiplier`, `input_per_1m`, `output_per_1m`, or `per_unit` and `unit`).
- Money and multipliers are decimal strings (multipliers also as `*_ppm` integers): add them with `Decimal`.

## The Standard lane and the tide table

Standard is the default lane: every kind of request, streaming included, at the highest priority.

```text
m_std(t) = clamp( L_e · (1 − d · τ^γ) · g_inv(t) · g_cong,f(t),  m_min,  m_max )      τ = share of the UTC day elapsed
```

Defaults: the opening level `L_e` is learned (initially 0.75, within 0.40–0.90, moving at most 0.05 a day);
the day closes at `L_e · (1 − d)` with `d` = 0.30; `γ` = 3 pushes the fall towards midnight; `m_min` = 0.15
and `m_max` = 0.90 (always at least 10% below Venice); the table never falls faster than 3% of list per hour.

| UTC time (defaults) | 00:00 | 06:00 | 12:00 | 18:00 | 21:00 | 23:00 | 23:58 |
| ------------------- | ----- | ----- | ----- | ----- | ----- | ----- | ----- |
| Standard multiplier | 0.750 | 0.746 | 0.722 | 0.655 | 0.599 | 0.552 | 0.526 |
| Savings vs. Venice  | 25%   | 25%   | 28%   | 34%   | 40%   | 45%   | 47%   |

- **Published ahead, never changed.** Tomorrow's table is published at **12:00 UTC** (at least 12 hours
  ahead): `GET /v1/market` (public, cached 5 s) → `tide_table.tomorrow` (with a `hash`; `null` before 12:00
  UTC) and `next_epoch.open_multiplier`. Today's: `tide_table.today` (`curve`: 97 points, every 15 minutes,
  `m_ppm`), https://tokentide.app/pricing#tide-table and https://tokentide.app/app/market.
- **Surges only raise the price**, never above `m_max`: inventory (up to 1.5×, recomputed every 60 s) when
  forecast demand outruns the capacity left, congestion (up to 1.5×, per model family) near Venice's rate
  limits. The live price is `standard.multiplier` in `GET /v1/market`; the table is a lower bound.

### Daily capacity and sold-out days

- **Sold out:** `GET /v1/market` shows `sold_out: true` and `reopens_at` (the next 00:00 UTC); inference
  answers `503 capacity_unavailable` with a `Retry-After` counting down to the reset. Don't retry: send
  interactive traffic to your fallback provider (reliability.md); batches and Private-only work wait.
- **Too big for what is left:** `503 capacity_unavailable` with `Retry-After: 59` while `sold_out` is `false`;
  smaller requests pass: lower `max_completion_tokens` or retry in a minute. Paused sales: the same code.

### The daily reset and the cross-epoch rule

Each UTC day is an **epoch** (`X-Tokentide-Epoch`). Around 00:00 UTC the market goes through these states:

| `epoch.state` | When                                  | What happens                                                                                                                         |
| ------------- | ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `open`        | most of the day                       | Normal pricing                                                                                                                       |
| `closing`     | the last 10 minutes before 00:00      | Requests sure to finish ≥ 15 s before the reset pay the current price; the rest follow the cross-epoch rule; Low Tide closes at 23:58 |
| `rolling`     | 00:00 until Venice confirms the reset | Only cross-epoch admissions, at the new day's opening multiplier; image endpoints answer `503 epoch_rollover` with `Retry-After`      |
| `degraded`    | reset still unconfirmed after 90 s    | Same as `rolling`                                                                                                                    |

**Cross-epoch rule.** Tokentide estimates each request's latest finish (for chat: time to first token plus
`max_completion_tokens` at a slow token rate). A request that might finish after the reset pays
`max(current multiplier, tomorrow's opening multiplier)`, counts towards tomorrow and carries
`X-Tokentide-Cross-Epoch: true` and `X-Tokentide-Epoch: <tomorrow>`. Avoid it with a lower
`max_completion_tokens`, or send `X-Tokentide-Max-Multiplier` to get `409 price_above_limit` instead. Too many
such requests at once: a new one gets `503 capacity_unavailable` with `Retry-After: 10`.

- Image generation and edits run near the reset only if today's capacity covers them, else
  `503 epoch_rollover` with `Retry-After` (they wait for the new day; during the reset, usually under a
  minute). Video queueing closes at about 23:14 UTC, music at about 23:39 UTC. Quotes never cross the reset.
  Start big jobs well before 23:30 UTC or after 00:05 UTC.

## The Low Tide lane

Low Tide is opt-in and best-effort: it sells only capacity forecast to go unused that day. Requests stay
synchronous, with the lowest priority and no latency target, and may be refused with a `409` (never charged).

```text
m_lowtide(t) = max( 0.20,  0.70 × m_std(t) )        defaults: 30% below Standard, never below 0.20 × list
```

With the defaults that is about 0.42 → 0.37 × list in the UTC evening (58–63% below Venice). `GET /v1/market`
shows `lowtide.multiplier` even while the lane is closed: the price if it opened now.

| Rule               | Detail                                                                                                                                                                                         |
| ------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Opt in             | `X-Tokentide-Lane: lowtide` per request, or an API key whose default lane is `lowtide`. Most models are eligible (`tokentide.lowtide.eligible` in `GET /v1/models`)                           |
| Non-streaming only | `stream: true` → `400 lowtide_requires_non_streaming`; text-to-speech must send `streaming: false`; E2EE models need streaming, so they always run on Standard                                 |
| Opens              | Only while spare capacity is forecast, rate limits have room and the reset is more than 2 minutes away                                                                                        |
| Closes             | At 90% of the day's capacity sold, until 00:00 UTC (`reason: nearly_sold_out`, `opens_at: null`); 2 minutes before the reset; on congestion or no spare capacity. Standard can still sell out |
| Hourly cap         | Per account, in list-price dollars: new 2%, verified 5%, trusted 10% of the day's capacity per hour ([trust tiers](https://tokentide.app/docs/rate-limits#limits-by-trust-tier))              |
| Daily allowance    | `tier base + 0.5 × your average daily Standard spend (list-$, last 7 days)`: regular Standard spend earns more Low Tide                                                                         |

`lowtide.reason` (in `GET /v1/market`) explains a closure: `disabled`, `killed` (sales paused), `no_spare`,
`congested`, `guard_window` (reset under 2 minutes away), `nearly_sold_out`, `epoch_state` (reset in progress)
or `no_discount` (floor not cheaper than Standard); `lowtide.opens_at` is the forecast opening. Yours:
`GET /v1/account` → `lowtide.allowance_usd`, `used_usd`, `cap_per_hour_usd` (list-price dollars).

### Headers and the key's default lane

| Header                         | On                   | Meaning                                                                                                                                                         |
| ------------------------------ | -------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `X-Tokentide-Lane`             | request, response    | Request: `lowtide` or `standard`, overriding the key's default lane. Response: the lane that served it (`standard` when it fell back)                           |
| `X-Tokentide-Lowtide-Fallback` | request              | `standard`: when Low Tide is closed, your caps are used up or the model is excluded, run on Standard at the Standard price. `none` (default): return the error |
| `X-Tokentide-Lowtide-Opens-At` | `409 lowtide_closed` | Forecast opening (ISO 8601, UTC), when known                                                                                                                    |

Default lane `lowtide` (API keys → Edit settings, https://tokentide.app/app/keys) suits batch-only keys; that
key's streaming requests then need `X-Tokentide-Lane: standard`, or get `400 lowtide_requires_non_streaming`.
While an account can have only one key (limited beta), set the lane per request instead.

### Low Tide errors

| Answer                               | Cause                                                              | Do                                                                                                                              |
| ------------------------------------ | ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------- |
| `400 lowtide_requires_non_streaming` | Streaming request on Low Tide                                      | Send it non-streaming, or on Standard. Never retry unchanged                                                                    |
| `409 lowtide_closed`                 | Lane closed (see `lowtide.reason`)                                 | Wait for `Retry-After` / `X-Tokentide-Lowtide-Opens-At`, or send the fallback header. `nearly_sold_out`: closed until 00:00 UTC |
| `409 lowtide_cap_reached`            | Hourly cap or daily allowance used up                              | Hourly cap: retry after `Retry-After`. Otherwise run on Standard (or send the fallback header)                                  |
| `403 model_not_allowed`              | Model excluded from Low Tide, or the key's privacy mode forbids it | Final: use Standard or the fallback header. A privacy-mode refusal is the user's choice: never route around it                 |
| `409 price_above_limit`              | Low Tide price above your maximum multiplier                       | Wait for `Retry-After`, or raise the limit                                                                                      |
| `429 rate_limited`                   | Model congested: Low Tide is shed first, then new accounts         | Wait for `Retry-After`                                                                                                          |

Model ids in this file are examples: take the current catalog from `GET /v1/models`. A batch request sent to
Low Tide that runs on Standard when Low Tide can't take it:

```python
import os

from openai import OpenAI

client = OpenAI(base_url="https://api.tokentide.app/v1", api_key=os.environ["TOKENTIDE_API_KEY"],
                max_retries=0, timeout=900)  # handle refusals yourself; requests can run up to 800 s
raw = client.chat.completions.with_raw_response.create(
    model="deepseek-v4-1-flash",
    messages=[{"role": "user", "content": "Classify this support ticket: …"}],
    max_completion_tokens=200,  # and never stream=True on Low Tide
    extra_headers={
        "X-Tokentide-Lane": "lowtide",
        "X-Tokentide-Lowtide-Fallback": "standard",  # closed, capped or excluded: run on Standard instead
        "X-Tokentide-Max-Multiplier": "0.70",  # optional ceiling on either lane (409 price_above_limit above it)
    },
)
completion = raw.parse()
print(raw.headers.get("x-tokentide-lane"), raw.headers.get("x-tokentide-charge-usd"))  # lane that ran it, cost
```

## Price limits and spend caps

Refused requests are never charged. Cap the price of each request and the spend of each period:

| Control                                                       | Effect                                                                                                                                                                        | Refusal                                                                                                                                                       |
| ------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `X-Tokentide-Max-Multiplier` (decimal in (0, 1], e.g. `0.55`)  | Never pay more than this share of list, on either lane; also blocks the cross-epoch price-up                                                                                  | `409 price_above_limit`, with a `Retry-After` until the table falls under it                                                                                  |
| `X-Tokentide-Max-Cost-USD` (decimal, e.g. `0.25`)              | Refuse at admission if the worst-case charge could exceed it                                                                                                                  | `409 cost_above_limit`: lower `max_completion_tokens` or raise it; never retry unchanged                                                                      |
| The key's **Max multiplier** (API keys → Edit settings)       | The key's own ceiling; with the header, the lower wins (the header can't raise it)                                                                                            | `409 price_above_limit`                                                                                                                                       |
| Spend caps per UTC day, ISO week (from Monday) and UTC month  | Account (Billing → Budgets and alerts) and per key (API keys → Edit settings → Spending limits); a request must fit every cap; daily ≤ weekly ≤ monthly; `0` blocks all spend | `402 spend_limit_reached`: `Retry-After` until the reset, `59` when only this request was too large, none when the cap is `0` or below the request's worst case |

- Caps count requests at their worst case until they end: leave headroom, and near a cap lower
  `max_completion_tokens`. The OpenAI SDKs don't retry `402`: pause the job until `Retry-After`. Every code in
  detail: errors-and-limits.md; key settings: security-and-privacy.md.

## Which lane and which hour

| Workload                                                 | Lane                                         | How                                                                                                           |
| -------------------------------------------------------- | -------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| Chat and anything a user waits for                       | Standard, streamed                           | An output limit and a fallback provider (reliability.md)                                                      |
| Quick calls inside a request (classify, extract, route)  | Standard                                     | Small models or decision models (decision-models.md), short output limits                                     |
| Batch work with a deadline (nightly enrichment, reports) | Low Tide, falling back to Standard           | `X-Tokentide-Lowtide-Fallback: standard`, or the deadline loop in [Waiting for a price](#waiting-for-a-price) |
| Batch work with no deadline (backfills, re-indexing)     | Low Tide only, with a price limit            | `X-Tokentide-Max-Multiplier`, and wait for `Retry-After` on `409`                                             |
| Video, music and image jobs                              | Standard, or Low Tide where the model allows | Quote first; queue video and music before the daily cut-off (media.md)                                        |
| Work that must stay on Private models                    | Either lane, Private models only             | On a sold-out day, queue it until the reset rather than send it to a vendor                                   |

- **The cheapest hours are the riskiest.** By the UTC evening a busy day may be sold out and Low Tide closed
  (at 90% sold): start work that must finish today early enough to finish on Standard, or give it a fallback.
- **Waiting is never free.** The table falls at most 3% of list per hour: if an hour's delay costs more than
  that (a user, a deadline, a stale result), send now.
- **Where the savings are (defaults).** Standard barely moves before 12:00 UTC (0.750 → 0.722), then falls to
  0.599 at 21:00 (20% less than at 00:00); evening Low Tide (0.37–0.42), when open, costs about half the
  morning Standard price.

## Price work before you send it

`GET /v1/market/estimate` (public, cached 5 s) prices one request on both lanes now, at every remaining UTC
hour, at the last same-day moment, at tomorrow's opening and at an optional `at`.

| Parameter                       | Value                                                                                                                                                                                      |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `model`                         | Required: a model id (or alias) as listed by `GET /v1/models`                                                                                                                              |
| `input_tokens`, `output_tokens` | Integers 0–100,000,000, for token-priced models (text, embeddings, decisions); reasoning tokens count as output                                                                           |
| `units`                         | For per-unit models: a decimal (up to 6 places) in the model's `tokentide.standard.unit`: images, edits, upscales, seconds of audio, or millions of characters (3,500 characters = `0.0035`) |
| `at`                            | Optional ISO 8601 time, priced from the published table: today, or tomorrow once its table is out (12:00 UTC)                                                                             |

It returns `list_cost_usd`, then `multiplier` and `charge_usd` for `now` (live, surges included; `now.lowtide`
adds `eligible`, `open`, `reason`, `opens_at`), `schedule` (per remaining hour: `standard_multiplier`,
`standard_charge_usd` and the `lowtide_` pair, valid only if Low Tide opens), `last_same_day`, `tomorrow_open`
and `at_time` (`null` without `at`). Table values are lower bounds. Errors: `400 invalid_request` (`param`
names the bad field) and `403 model_not_allowed` (a model Tokentide does not offer).

Worked example (the docs' sample, taken at 20:07 UTC; values illustrative):

```bash
curl "https://api.tokentide.app/v1/market/estimate?model=zai-org-glm-5-2&input_tokens=1200&output_tokens=800&at=2026-11-02T22:00:00Z"
```

`list_cost_usd` is `0.0052`; multiplier → charge: `now.standard` 0.6175 → $0.003211, `now.lowtide` 0.43225 →
$0.002248, `at_time` (22:00) 0.576693 → $0.002999, `last_same_day` (23:59:45) 0.525117 → $0.002731,
`tomorrow_open` 0.75 → $0.0039. Waiting until 22:00 saves $0.000212 per request; Low Tide now beats every
Standard moment left today. Costs are linear: price a batch by its token totals.

```python
import httpx  # pip install httpx

# Nightly job: 20,000 documents, about 2,000 tokens in and 400 out each. Costs are linear: pass the totals.
est = httpx.get("https://api.tokentide.app/v1/market/estimate", timeout=30,
                params={"model": "deepseek-v4-1-flash", "input_tokens": 40_000_000, "output_tokens": 8_000_000}).json()
now = est["now"]
print("list price:", est["list_cost_usd"], "| now, Standard:", now["standard"]["charge_usd"])
print("Low Tide:", now["lowtide"]["charge_usd"] if now["lowtide"]["open"] else f"closed ({now['lowtide']['reason']})")
if est["schedule"]:  # one entry per remaining UTC hour today
    cheapest = min(est["schedule"], key=lambda hour: float(hour["standard_charge_usd"]))
    print("cheapest Standard hour left today:", cheapest["at"], cheapest["standard_charge_usd"])
print("tomorrow's opening:", est["tomorrow_open"]["standard"]["charge_usd"])
```

Then check the market and your Low Tide allowance before you start:

```python
import os

import httpx  # pip install httpx

API = "https://api.tokentide.app/v1"
market = httpx.get(f"{API}/market", timeout=10).json()  # public, no key
mine = httpx.get(f"{API}/account", timeout=10,
                 headers={"Authorization": f"Bearer {os.environ['TOKENTIDE_API_KEY']}"}).json()["lowtide"]
left, lt = float(mine["allowance_usd"]) - float(mine["used_usd"]), market["lowtide"]  # left: list-price dollars
if market["sold_out"] or market["sales_paused"]:
    print("no sales until", market["reopens_at"], "- pause the batch or use your fallback provider")
elif lt["open"] and left > 0:
    print(f"Low Tide at {lt['multiplier']} x list; ${left:.2f} allowance left, cap ${mine['cap_per_hour_usd']}/hour")
else:
    print(f"Low Tide closed ({lt['reason']}, opens {lt['opens_at']}); Standard at {market['standard']['multiplier']}")
```

**Quotes.** `POST /v1/market/quote` with your key and an optional `{"lane": "lowtide"}` (default `standard`)
returns `multiplier`, `multiplier_ppm`, `epoch`, `locked_at` and `expires_at` (60 s later, never across the
reset). It is free and changes nothing: for a firm price, quote, then send the request with
`X-Tokentide-Max-Multiplier` set to the quoted `multiplier` (it runs at that price or lower, or is refused
free). During the reset: `503 epoch_rollover` (retry in about 30 s); Low Tide closed: `409 lowtide_closed`.
Media jobs: `POST /v1/video/quote`, `POST /v1/audio/quote` (media.md).

## Waiting for a price

- **Poll** `GET /v1/market` at most every 15 s, or **subscribe** to `GET /v1/market/stream`: `event: tick`
  every 15 s with the same JSON, `event: reconnect` after about 13 minutes (reconnect then), about 20 new
  connections per minute per network (then `429 rate_limited`).
- **Predict** when Standard reaches a cap: the first future point of `tide_table.today.curve` whose `m_ppm` is
  at or below it (a lower bound: surges only raise the live price).
- **Or let the API tell you.** Send with `X-Tokentide-Max-Multiplier`: above it you get
  `409 price_above_limit` with a `Retry-After` computed from the table. Every Low Tide `409` (closed, cap
  reached, price) carries `Retry-After` and costs nothing. Sleep for it, bounded by your deadline:

```python
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import openai
from openai import OpenAI

client = OpenAI(base_url="https://api.tokentide.app/v1", api_key=os.environ["TOKENTIDE_API_KEY"],
                max_retries=0, timeout=900)
WAIT = {"lowtide_closed", "lowtide_cap_reached", "price_above_limit", "rate_limited", "capacity_unavailable"}


def run_by_deadline(body, deadline, cap="0.45", standard_cap="0.70", lead=600.0):
    """Low Tide (<= cap) until `lead` s before the deadline, then Standard (<= standard_cap); lead=0: Low Tide only."""
    key = str(uuid.uuid4())
    while time.time() < deadline:
        lowtide = time.time() < deadline - lead
        switch_at, limit = (deadline - lead, cap) if lowtide else (deadline, standard_cap)
        headers = {"X-Tokentide-Lane": "lowtide" if lowtide else "standard", "Idempotency-Key": key}
        if limit:
            headers["X-Tokentide-Max-Multiplier"] = limit
        try:
            return client.chat.completions.create(**body, extra_headers=headers)
        except openai.APIConnectionError:  # network error or timeout: it may have run, so keep the same key
            time.sleep(10)
            continue
        except openai.APIStatusError as e:
            if e.code == "model_not_allowed" and lowtide:
                lead = float("inf")  # excluded from Low Tide: Standard from now on
            elif e.code in WAIT:  # refusals are never charged: wait as long as the API says
                time.sleep(max(1.0, min(float(e.response.headers.get("retry-after") or 60), switch_at - time.time())))
            else:
                raise  # 402 (balance, cap), 409 duplicate_request (it already ran), a bad request, other 5xx
            key = str(uuid.uuid4())  # refused before running: the next attempt gets a new key
    return None  # too late: send it to your fallback provider, or run it tomorrow


deadline = time.time() + 8 * 3600
bodies = [{"model": "deepseek-v4-1-flash", "max_completion_tokens": 400,
           "messages": [{"role": "user", "content": f"Summarize:\n{doc}"}]} for doc in ["…", "…"]]  # your inputs
with ThreadPoolExecutor(max_workers=4) as pool:  # stay under limits.concurrency from GET /v1/account
    results = list(pool.map(lambda body: run_by_deadline(body, deadline), bodies))
```

A request that already ran before a network error answers its retry with `409 duplicate_request` (raised)
instead of being charged twice; its result is gone, because Tokentide stores no responses, so keep the process
running until the batch ends. Other `5xx` propagate: retry them as in reliability.md.

**Tide Runner: planned, not installable yet.** `TideRunner` and the market helpers (`firstTimeAtOrBelow`,
`waitForPrice`, `lowTideWindow`) belong to the Tokentide SDKs (`@tokentide/sdk`, Python `tokentide`), whose
npm and PyPI publication is planned: don't install those packages until https://tokentide.app/docs/sdk says
they are published. The loop above follows its rules; the runner also moves to Standard earlier when its pace
requires, retries `500`/`502`/`503` failures with the same key, and stops on `insufficient_balance`,
`spend_limit_reached` or `invalid_api_key`.

## Monthly budgets and forecasting

- **Forecast** each workload: daily token totals through `GET /v1/market/estimate` at the hour it runs (`at`,
  or that hour in `schedule`), times its days in the month, plus the share your fallback provider serves
  (sold-out hours, refusals) at its price. Your saving is the share Tokentide serves times its discount.
- **Bound it.** Standard never exceeds 0.90 × list, surges included. Defaults give 0.750 → 0.526 through the
  day and evening Low Tide about 0.37–0.42, but the opening level is learned (0.40–0.90, at most 0.05 a day):
  exact prices exist only for today and, from 12:00 UTC, tomorrow. Re-estimate daily.
- **Enforce it** with an account monthly cap (the budget), a daily cap (stops runaways early), per-key caps,
  cap warnings (80% default) and auto top-up with a monthly maximum (setup.md). Paid credit never expires.
- **Track it.** Log `X-Tokentide-Charge-USD` and `X-Tokentide-List-Cost-USD` (streams: the usage chunk) with
  `X-Request-Id` and the serving provider. `GET /v1/account` → `spend_today` (`charged_usd`, `list_usd`,
  `savings_usd`); `GET /v1/account/usage` → per-request `charge_micros`, `list_cost_micros` (strings), `lane`.
  https://tokentide.app/app projects the month; https://tokentide.app/app/usage breaks spend down.

## Further reading

- https://tokentide.app/docs/lanes: charge formula, tide table, Low Tide, headers, daily reset
- https://tokentide.app/docs/lanes#market-api: market, stream, quote, rules, estimate, prices per model
- https://tokentide.app/docs/timing: lanes by workload, pricing work first, the reset and sold-out days
- https://tokentide.app/docs/billing#spending-limits and https://tokentide.app/docs/billing#per-request-limits
- https://tokentide.app/docs/best-practices#low-tide and https://tokentide.app/docs/best-practices#ceilings
- https://tokentide.app/docs/sdk#tide-runner: the Tide Runner (SDK publication planned)
- https://tokentide.app/pricing#tide-table: today's tide table
