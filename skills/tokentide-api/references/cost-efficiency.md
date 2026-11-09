# Cost efficiency

Rules for doing each task at the lowest cost on Tokentide without losing quality: the cheapest model that does
the job, an automatic task router, prompt caching, reasoning and output control, smaller context, reuse, and
measuring cost per task. Open it when choosing models for a feature, building a pipeline or an agent loop, or
when spend is higher than expected. Charges, the tide table and Low Tide: pricing-and-timing.md.

## Contents

- Levers, biggest saving first
- Frontier models only for hard work
- An automatic task router
- Prompt caching
- Reasoning effort and output control
- Context size
- Reuse: don't pay twice
- Batch work on Low Tide and later hours
- Measuring cost per task
- Checklist
- Further reading

## Levers, biggest saving first

A text request costs about `input tokens × input price + (reasoning + answer tokens) × output price`, at the
Venice list price times the multiplier. Input is everything you send, on every request: system prompt, tool
definitions, documents and every earlier turn. Output, reasoning included, costs two to six times as much per
token as input on most models. Repeated input costs less on models with a cached-input price.

| #   | Lever                                                         | What it saves, as the docs state it                                                                                                                                             |
| --- | ------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | The cheapest model that does each task well                   | Prices differ by more than 100×: a frontier model on a task a small model handles well costs 20 to 100 times more for the same result                                           |
| 2   | A router: rules, a decision model, escalation on failed check | In studies, a cascade matched the best single model at up to 98% lower cost (FrugalGPT); routers kept 95% of GPT-4's quality on MT Bench at more than 85% lower cost (RouteLLM) |
| 3   | Decision models for judgments, embeddings for search          | Ticket triage at list prices: about $40 per million tickets on `clef-api`, against about $115 on a small chat model and $4,600 on a frontier one (decision-models.md)           |
| 4   | Prompt caching                                                | 75% to 97% less on a long prefix sent with every request                                                                                                                        |
| 5   | Reasoning down or off on simple tasks                         | Reasoning is billed as output; on a simple task it can be most of the bill                                                                                                      |
| 6   | Short, structured answers                                     | Output tokens are the expensive and the slow ones: halving an answer roughly halves its time                                                                                    |
| 7   | Only the context the task needs                               | Every message is billed on every request, so each turn of a long conversation costs more                                                                                        |
| 8   | Reuse answers, remove duplicates                              | A request you don't send is never charged                                                                                                                                       |
| 9   | Low Tide and later hours for work that can wait               | Low Tide about 30% below Standard; Standard from about 25% below list at 00:00 UTC to about 47% just before midnight                                                            |
| 10  | Measure cost per task, check quality before every switch      | Shows which lever pays; a model that is cheaper per call but wrong more often can cost more overall                                                                             |

Media follow the same rules (prices within a type differ 10 to 100×): draft cheap and render the final on the
premium model, edit or upscale rather than regenerate, quote every video and music job before you queue it,
and cache what you have paid for (media.md).

Model ids in this file are examples from the docs: take current ids, prices and capabilities from
`GET /v1/models` with your key. Snippets without their own setup use this client:

```python
import os

from openai import OpenAI

tokentide = OpenAI(base_url="https://api.tokentide.app/v1", api_key=os.environ["TOKENTIDE_API_KEY"])
```

## Frontier models only for hard work

Keep frontier models for tasks that need them; cheaper models, decision models and plain code do the rest.

| Task                                                                                                                                    | Start with                                          | Examples on Tokentide                                                                                |
| --------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| Yes-or-no checks, classification, routing, scoring, moderation pre-checks                                                               | A decision model (decision-models.md)               | `clef-api`                                                                                           |
| Search, similarity, deduplication, clustering, retrieval for RAG                                                                        | An embedding model, not a chat model (retrieval.md) | `text-embedding-qwen3-0-6b`, `text-embedding-qwen3-8b`                                               |
| Extraction to JSON, tagging, formatting, short summaries, simple translation and rewriting                                              | A small, fast model, little or no reasoning         | `z-ai-glm-5-3-flash`, `deepseek-v4-1-flash`                                                          |
| Long summaries, answers from documents you provide, drafting, routine coding, tool use with clear steps                                 | A mid-tier model, low to medium reasoning           | `zai-org-glm-5-2`, `deepseek-v4-pro`                                                                 |
| Hard reasoning, ambiguous or novel problems, complex coding and debugging, system design, long multi-step agent work, high-stakes calls | A frontier model, more reasoning                    | `grok-4-7`, `kimi-k3` (Private); `claude-opus-5-5`, `openai-gpt-55` (Anonymized: privacy mode `all`) |

Venice list prices per million tokens when the docs were written (you pay them times the multiplier; live
prices on https://tokentide.app/models and in `GET /v1/models`):

| Model                       | Privacy    | Input   | Cached input | Output |
| --------------------------- | ---------- | ------- | ------------ | ------ |
| `openai-gpt-55`             | Anonymized | $5.00   | $0.50        | $30.00 |
| `claude-opus-5-5`           | Anonymized | $4.00   | $0.20        | $20.00 |
| `grok-4-7`                  | Private    | $2.27   | $0.57        | $6.80  |
| `zai-org-glm-5-2`           | Private    | $1.40   | $0.26        | $4.40  |
| `deepseek-v4-pro`           | Private    | $1.65   | $0.33        | $3.30  |
| `deepseek-v4-1-flash`       | Private    | $0.30   | $0.0075      | $1.20  |
| `z-ai-glm-5-3-flash`        | Private    | $0.15   | $0.03        | $0.50  |
| `claude-haiku-5-5`          | Anonymized | $0.10   | $0.01        | $0.50  |
| `text-embedding-qwen3-0-6b` | Private    | $0.0125 | –            | –      |
| `clef-api` (decisions)      | Private    | $0.05   | –            | $0.05  |

- **Start with the smallest model that might work.** Test it on your examples; move up only for what fails.
- **Lower the reasoning effort before you change models:** on many tasks that is the cheaper fix.
- **Spend on difficulty, not on volume.** A frontier model earns its price on hard tasks or where a mistake is
  expensive; high-volume, repetitive work rarely needs it.
- **Let a strong model plan and a cheap one do the steps:** one frontier call splits a job into clear steps.
- **Compare cost per task, not price per token:** models split text into different numbers of tokens, write
  answers of different lengths and need different numbers of retries.
- **Retest when new models arrive:** last year's frontier task may now run on one that costs a tenth as much.

## An automatic task router

A router sends each task to the cheapest model likely to do it well, without anyone choosing by hand:

1. **Rules first, they are free:** route by what you know: the feature, the input size, the user's plan.
2. **A decision model for the rest:** it scores how capable a model must be, for a fraction of a cent. When it
   isn't sure, start one tier higher: a wrong cheap answer usually costs more than the difference.
3. **Check the answer, then escalate:** validate the cheap answer with something you trust (a JSON schema,
   tests, required fields, a business rule, a decision-model check from decision-models.md). Escalate only
   failures, and stop at the top. Don't ask a model how confident it is: models rate themselves too highly.
4. **Measure and tune:** log each task's route, cost, escalations and outcome, review samples, and tune the
   thresholds on your own traffic: a router tuned on general data can be little better than chance on yours.

```python
import os

import httpx
from openai import OpenAI

API = "https://api.tokentide.app/v1"
KEY = os.environ["TOKENTIDE_API_KEY"]
tokentide = OpenAI(base_url=API, api_key=KEY)

# Cheapest first. Choose ids from GET /v1/models with your key, and test each tier on your own tasks.
TIERS = [
    {"name": "small", "model": "z-ai-glm-5-3-flash", "max_tokens": 1_000},
    {"name": "mid", "model": "zai-org-glm-5-2", "max_tokens": 4_000},
    {"name": "frontier", "model": "grok-4-7", "max_tokens": 16_000},  # or claude-opus-5-5 with privacy mode "all"
]

RULES = {"summary": 0, "tagging": 0}  # step 1: features whose starting tier you already know (yours to define)

DIFFICULTY = {
    "type": "score",
    "instructions": "How capable must an AI model be to do `task` well?",
    "criteria": [
        "Trivial: a lookup, reformatting, a label or a short factual answer",
        "Routine: a clear writing, summarizing or extraction job, or a simple code change",
        "Demanding: multi-step analysis, careful reasoning or non-trivial code",
        "Expert: a hard, ambiguous or novel problem, or a long chain of dependent steps",
    ],
}


def first_tier(task: str) -> int:
    """Step 2: pick the starting tier with a decision model, a fraction of a cent per task."""
    try:
        res = httpx.post(
            f"{API}/decisions",
            headers={"Authorization": f"Bearer {KEY}"},
            json={"model": "clef-api", "state": {"task": task[:20_000]}, "questions": {"difficulty": DIFFICULTY}},
            timeout=30,
        )
        res.raise_for_status()
    except httpx.HTTPError:
        return 1  # no answer from the router: start in the middle
    p = res.json()["answers"]["difficulty"]["probabilities"]  # {"0": 0.71, "1": 0.22, "2": 0.05, "3": 0.02}
    if p["0"] + p["1"] >= 0.8:
        return 0  # clearly easy
    if p["3"] >= 0.5:
        return 2  # clearly hard
    return 1  # in between, or unsure


def passes(answer: str, finish_reason: str) -> bool:
    """Step 3: your own check (a JSON schema, tests, required fields…). Keep it cheap and deterministic."""
    return finish_reason == "stop" and answer.strip() != ""


def run(task: str, feature: str = "") -> str:
    start = RULES[feature] if feature in RULES else first_tier(task)
    answer = ""
    for tier in TIERS[start:]:
        reply = tokentide.chat.completions.create(
            model=tier["model"],
            max_completion_tokens=tier["max_tokens"],
            messages=[{"role": "user", "content": task}],
        )
        choice = reply.choices[0]
        answer = choice.message.content or ""
        if passes(answer, choice.finish_reason):
            return answer  # step 4: log tier["name"] and the cost here
    return answer  # even the top tier failed the check: flag it for review
```

- **Write `passes()` for your task:** tests for code, the schema and required fields for extraction, supported
  claims for answers from documents. A check that lets bad answers through turns the savings into mistakes.
- **Keep one model per conversation.** Route at the start of a conversation or per independent task: switching
  models in the middle throws away the prompt cache.
- **Set an output limit per tier**, as the example does, and log which tier answered.
- **Watch the escalation rate.** If most tasks escalate, start them higher; if almost none do, try a cheaper
  first tier. The TypeScript version is on https://tokentide.app/docs/cost-efficiency#router.

## Prompt caching

Many models bill input that repeats the start of a recent request at a cached-input price: $0.20 instead of
$4.00 per million tokens on `claude-opus-5-5`, $0.0075 instead of $0.30 on `deepseek-v4-1-flash` (list
prices). A long system prompt, handbook or example set sent with every request then costs 75% to 97% less.
`GET /v1/models` shows each model's cached-input price (`cache_input`); Claude models also charge a little
more when a prompt is first written to the cache (`cache_write`), which pays for itself from the first reuse.

Caching is automatic on most models. Tokentide keeps prompt caches separate per account, never shared with
other customers; a `prompt_cache_key` you send (a conversation or user id) still groups your related requests.

- **Put what never changes first** (instructions, examples, tools, documents), the user's question last.
- **Keep it byte-identical:** no timestamps, request ids or shuffled examples near the top; same tool order.
- **Make it long enough:** caching starts at about 1,024 tokens of shared prefix on most models, more on some.
- **Reuse it soon:** caches usually expire after a few minutes without use.
- **Append to conversations** rather than rewriting earlier turns, and keep the same model throughout.

```python
HANDBOOK = open("support_handbook.md").read()  # thousands of tokens, identical on every request


def answer(conversation_id: str, question: str) -> str:
    reply = tokentide.chat.completions.create(
        model="deepseek-v4-1-flash",
        max_completion_tokens=800,
        messages=[
            {"role": "system", "content": "You answer questions about our product.\n\n" + HANDBOOK},  # unchanged: cached
            {"role": "user", "content": question},  # what changes goes last
        ],
        prompt_cache_key=conversation_id,  # groups related requests; your cache stays private to your account
    )
    details = reply.usage.prompt_tokens_details if reply.usage else None
    print("cached input tokens:", details.cached_tokens if details else 0)
    return reply.choices[0].message.content or ""
```

Hit rate: `usage.prompt_tokens_details.cached_tokens` / `usage.prompt_tokens`.

## Reasoning effort and output control

Reasoning is billed as output tokens (`usage.completion_tokens_details.reasoning_tokens`) and counts toward
`max_completion_tokens`; on a simple task it can be most of the bill.

- **Simple tasks** (extraction, classification, formatting, short answers): set `reasoning_effort` to `low`,
  or to `minimal` or `none` where the model offers them, or turn reasoning off with
  `"reasoning": {"enabled": false}` on models that allow it.
- **Hard tasks:** test `medium` against `high`; the maximum often adds a lot of cost for a small gain.
- **Check support:** `GET /v1/models` shows `supportsReasoningEffort`. Some models always reason.
- **Leave room for the reasoning** in `max_completion_tokens`: when the limit runs out mid-thought, the answer
  comes back short or empty, and you still pay for the reasoning.

```python
reply = tokentide.chat.completions.create(
    model="deepseek-v4-1-flash",
    reasoning_effort="low",  # a simple task: think briefly
    max_completion_tokens=500,
    messages=[{"role": "user", "content": "Extract the invoice number from this email: …"}],
)
details = reply.usage.completion_tokens_details if reply.usage else None
print("reasoning tokens (billed as output):", details.reasoning_tokens if details else 0)

reply = tokentide.chat.completions.create(  # reasoning off, on a model that allows it
    model="qwen3-6-35b-a3b",
    max_completion_tokens=300,
    messages=[{"role": "user", "content": "Translate to French: Your order has shipped."}],
    extra_body={"reasoning": {"enabled": False}},  # raw JSON body: "reasoning": {"enabled": false}
)
```

Output tokens are the expensive ones and the slow ones:

- **Ask only for what you use:** "Answer in at most three sentences", "Return only the JSON"; no explanations.
- **Use structured output** (`response_format`, JSON schema) on models with `supportsResponseSchema`: only the
  fields you need, and no paid retries after broken JSON (prompts-and-agents.md).
- **Set `max_completion_tokens` on every request** (`max_output_tokens` on `/v1/responses`), a little above
  the longest answer you expect. You pay for the tokens used either way; a realistic limit keeps the request's
  worst case small, so more of your requests pass the capacity, balance and spend-cap checks (reliability.md).

## Context size

Everything in `messages` is billed on every request.

- **Trim the history.** Keep recent turns, summarize older ones with a small model, drop tool results you no
  longer need. Summarize every few turns, not on every request: each rewrite misses the prompt cache once.
- **Retrieve, don't stuff.** Embed your documents once and send only the passages relevant to each question
  (retrieval.md). It costs less, and models get less reliable as their input grows.
- **Send only the tools a request needs:** tool definitions count as input on every call.
- **Clean your inputs:** strip HTML, boilerplate, signatures and repeated headers before sending text.
- **Group small items.** Classify 10 or 20 short items in one request, with one set of instructions, and get a
  JSON array back: you pay for the instructions once. Check accuracy on your data, because very large groups
  can hurt it. For judgments, a decision model does the same with typed answers.

## Reuse: don't pay twice

- **Cache answers on your side** for repeated requests on content that doesn't change (product descriptions,
  FAQ answers, document summaries): key on a hash of the model, messages and settings, and never store an
  answer that didn't end with `finish_reason` `stop`. Tokentide stores no answers: the cache is yours.
- **Be careful with semantic caching**, which reuses an answer for a question that is merely similar:
  questions that look alike can need different answers. Use a strict similarity threshold, only for content
  that isn't personal, and measure how often it is wrong.
- **Remove duplicates** from a batch before you send it.
- **Embed once:** re-embed only changed chunks (by hash) and cache query embeddings (retrieval.md).

## Batch work on Low Tide and later hours

Work no one waits for (non-streaming chat, embeddings, decisions) costs about 30% below Standard on Low Tide;
Standard falls from about 25% below list at 00:00 UTC to about 47% before midnight (default parameters). Price
limits (`X-Tokentide-Max-Multiplier`), the Tide Runner, sold-out days: pricing-and-timing.md.

## Measuring cost per task

- **Count cost per task, not per request:** retries, escalations, decision calls and fallbacks included. A
  feature's spend divided by the tasks that passed their check is its cost per successful task.
- **Read the charge on every response:** `X-Tokentide-Charge-USD` (what you paid) and
  `X-Tokentide-List-Cost-USD` (the list price) on non-streaming responses; on streams, the final usage chunk
  (`cost.usd`). Log them with `X-Request-Id`, the feature, the model and the provider that served the request
  (your fallback provider's answers carry no Tokentide headers: take their cost from that provider). Send your
  own `X-Client-Request-Id` so support can find a request that timed out before you saw its `X-Request-Id`.
- **One API key per feature:** the Usage dashboard (https://tokentide.app/app/usage) then breaks spend, list
  price and savings down by key, model, endpoint and lane, with CSV and JSON exports.
- **From code:** `GET /v1/account/usage` returns each key's own request rows, never content (example below).
- **Build a test set** per feature: 50 to 200 real examples with right answers or a rubric. Run the current
  and the cheaper setup on it, switch only when quality holds, and rerun it when models or prompts change.
- **Grade automatically where you can:** exact match for labels, schema checks and tests for structured output
  and code, a decision model or a strong model with a rubric for open text. Read a sample by hand too.
- **Put a price on mistakes** (support time, refunds, lost users), and watch production: the escalation rate,
  the fallback rate, user feedback and the cost of each feature.

A minimal ledger, metadata only:

```python
from collections import defaultdict
from decimal import Decimal


class Ledger:
    """Cost per successful task, per feature. Never record prompts or answers."""

    def __init__(self) -> None:
        self.paid = defaultdict(Decimal)  # USD over every attempt: retries, escalations, decision calls
        self.successes = defaultdict(int)

    def charge(self, feature: str, headers) -> None:  # OpenAI raw-response headers or httpx response headers
        self.paid[feature] += Decimal(headers.get("x-tokentide-charge-usd") or "0")

    def cost_per_success(self, feature: str):
        return self.paid[feature] / self.successes[feature] if self.successes[feature] else None


ledger = Ledger()
raw = tokentide.chat.completions.with_raw_response.create(
    model="deepseek-v4-1-flash",
    max_completion_tokens=200,
    messages=[{"role": "user", "content": "Extract the invoice number from this email: …"}],
    extra_headers={"X-Client-Request-Id": "invoice-7f3a"},  # your own id: support can find the request by it
)
ledger.charge("invoice-extraction", raw.headers)
if raw.parse().choices[0].finish_reason == "stop":  # use your real check here, as in passes()
    ledger.successes["invoice-extraction"] += 1
print(ledger.cost_per_success("invoice-extraction"))
```

In TypeScript, `const { data, response } = await tokentide.chat.completions.create({ … }).withResponse()`,
then `response.headers.get('x-tokentide-charge-usd')`.

Where past spend went, per model, from the usage API (paging details: api-reference.md):

```python
import os
from collections import Counter

import httpx


def spend_by_model(since: str) -> dict:
    """USD paid per model since a UTC time such as "2026-11-01T00:00:00Z" (this key's requests)."""
    micros, params = Counter(), {"from": since, "limit": 1000}
    while True:
        res = httpx.get("https://api.tokentide.app/v1/account/usage", params=params, timeout=30,
                        headers={"Authorization": f"Bearer {os.environ['TOKENTIDE_API_KEY']}"})
        res.raise_for_status()
        page = res.json()
        for row in page["data"]:  # rows also carry list_cost_micros, cached_tokens, reasoning_tokens, lane…
            micros[row["model_id"]] += int(row["charge_micros"])  # micro-USD, sent as a string
        if not page["has_more"]:
            return {model: m / 1_000_000 for model, m in micros.items()}
        params["before"] = page["next_before"]
```

## Checklist

- [ ] Each feature uses the smallest model that passes its test set; frontier models only for hard work.
- [ ] Classification, routing, scoring and yes-or-no checks use a decision model; search uses embeddings.
- [ ] Mixed traffic goes through a router: rules, a decision model, then a check that escalates failures.
- [ ] Stable content comes first, byte-identical; `prompt_cache_key` is set; the cache hit rate is tracked.
- [ ] `reasoning_effort` is set per task (low or off for simple work), with room for it in the output limit.
- [ ] `max_completion_tokens` on every request; short answers; a JSON schema where the model supports it.
- [ ] History is trimmed, documents are retrieved rather than stuffed, and only the needed tools are sent.
- [ ] Identical requests hit your own answer cache; batches are deduplicated; embeddings are computed once.
- [ ] Work that can wait runs on Low Tide or later in the UTC day, with a price limit.
- [ ] Charges are logged per feature, with one key per feature; cost per successful task is reviewed.
- [ ] A cheaper setup ships only after it holds quality on the feature's test set.

## Further reading

- https://tokentide.app/docs/cost-efficiency (with the TypeScript samples)
- https://tokentide.app/docs/decision-models
- https://tokentide.app/docs/choosing-models
- https://tokentide.app/docs/timing
- https://tokentide.app/docs/billing#usage-and-cost-tracking
- FrugalGPT (Chen, Zaharia and Zou): https://arxiv.org/abs/2305.05176
- RouteLLM (LMSYS): https://lmsys.org/blog/2024-07-01-routellm/
