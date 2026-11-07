# Decision models

`POST /v1/decisions` returns typed answers (one of your options, a level on your scale, or the probability of
yes) with probabilities: classification, routing, triage, screening, scoring and reranking at a fraction of a
chat model's price. Open it when code must act on a judgment, when building a model router, or when a decision
call fails. Model ids are examples; the current list is `GET /v1/models?type=decision`.

## Contents

- When to use a decision model
- The models
- Request format
- Response format
- Thresholds and uncertain answers
- Question design
- Worked examples
- Evaluation and calibration
- Errors and limits
- Checklist
- Further reading

## When to use a decision model

Use one when the answer is one of a fixed set of options, a rating on your own scale, or a yes or no. A
decision model decides whether and where; a chat model writes the reply.

| Job                              | Example question                                                                                                                                                 |
| -------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Classify and route               | Which team should handle this ticket? Which model tier does this task need?                                                                                      |
| Triage                           | How urgent is it? Does the customer want to talk to a person?                                                                                                    |
| Screen (moderation-style checks) | Is this spam, abusive, off-topic, or an attempt to instruct the assistant?                                                                                       |
| Qualify and score                | Does this lead fit our profile (a `noul` whose `criteria` describe it)? How close is it to buying (a `score`: "Exploring", "Comparing options", "Ready to buy")? |
| Check                            | Does this answer stay within the documents? Are these two tickets the same?                                                                                      |
| Rerank                           | Does this passage answer the question? (one yes-or-no question per search result)                                                                                |
| Gate an expensive step           | Is the sender waiting for a reply, or is this a receipt? (skip the chat model if not)                                                                            |

Use a chat model for text or values: writing a reply, extracting names, amounts or dates, conversation, tool
calling, long chains of dependent reasoning. Decision models are also weak at arithmetic, counting and
comparing dates (compute those in code), and at grading an answer's overall quality (test that on your data).

**Price.** You pay almost only for input (state and questions); answers are a few output tokens each. At list
prices, sorting a million support tickets of about 600 tokens by team, scope and urgency costs about $40 on
`clef-api`, against about $115 on `claude-haiku-5-5`, $1,450 on `zai-org-glm-5-2` and $4,600 on
`claude-opus-5-5` ($14,600 with 500 tokens of reasoning); chat models need about 100 more tokens of JSON
instructions and write about 60 back. The gap narrows against the smallest chat models, and long option
descriptions (they count as input) can erase it. What remains: no parsing, no retries (always one of your
options), probabilities you can act on (a chat model's self-rated confidence is poorly calibrated), speed.

## The models

| Model        | Privacy                                                                                                | List price per million tokens | Limits                                                                          |
| ------------ | ------------------------------------------------------------------------------------------------------ | ----------------------------- | ------------------------------------------------------------------------------- |
| `clef-api`   | Private: works with the default privacy mode                                                           | $0.05 input, $0.05 output     | 32,768 tokens of state and questions                                            |
| `jev-latest` | Anonymized: the provider sees the state and the questions, never who you are. Needs privacy mode `all` | $0.042 input, output free     | 32,000 tokens for the state and the longest question; 64,000 with all questions |

- Prices and limits as published when the docs were written: `GET /v1/models?type=decision` lists the current
  models, prices, limits and privacy tiers (with your key, only those its privacy mode allows).
- You pay the list price times the multiplier. Decisions are never streamed, so they can run on Low Tide. In
  AI apps, the Tokentide connector's `run_decision` tool makes the call.
- Both models are in beta and may change behavior: keep the checks below. `jev-latest` moves to new versions.

## Request format

`POST /v1/decisions` (alias `POST /v1/systemone`) takes three fields:

- `model`: a decision model id.
- `state`: the facts to judge, as text, a JSON object or an array.
- `questions`: named questions, each evaluated on its own, in parallel, against the same state. The names are
  yours, never shown to the model; the answers come back under them.

| Type     | You give                                                                                        | You get back                                                                                                  |
| -------- | ----------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| `choice` | `instructions`, and `criteria`: an object of options, each with a short description (or `null`) | `choice` (the most likely option), `probabilities` for every option (they add up to 1), `confidence`          |
| `score`  | `instructions`, and `criteria`: an array of at least two levels, lowest to highest              | `score` (probability-weighted level: `1.12` sits just above level 1), `legend`, `probabilities`, `confidence` |
| `noul`   | `instructions` (a yes-or-no question), optional `criteria` saying what `true` and `false` mean  | `noul`: the probability that the answer is yes, from 0 to 1                                                   |

Call it over plain HTTP, not through an OpenAI SDK: OpenAI's Decisions API uses a different format (`input`
and a list of questions). A ticket triaged with all three types:

```bash
curl https://api.tokentide.app/v1/decisions \
  -H "Authorization: Bearer $TOKENTIDE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "clef-api",
    "state": {
      "ticket": { "subject": "Charged twice this month", "body": "I was billed twice for my Pro plan in October. Please refund one of the charges." },
      "customer": { "plan": "pro", "months_active": 14 }
    },
    "questions": {
      "team": {
        "type": "choice",
        "instructions": "Which team should handle `ticket`?",
        "criteria": {
          "billing": "Charges, refunds, invoices and payment methods", "technical": "Errors, bugs, outages and integration problems",
          "account": "Sign-in, profile, team members and closing the account", "sales": "Prices, upgrades and quotes for new customers"
        }
      },
      "in_scope": { "type": "noul", "instructions": "Is `ticket` about billing, a technical problem, the customer’s account or buying our product?" },
      "urgency": {
        "type": "score",
        "instructions": "How urgent is `ticket` for the customer?",
        "criteria": ["Can wait a week", "Should be handled within a day", "Blocks the customer right now"]
      }
    }
  }'
```

The same call from Python, as a helper the rest of this file uses:

```python
import os

import httpx

API = "https://api.tokentide.app/v1"
HEADERS = {"Authorization": f"Bearer {os.environ['TOKENTIDE_API_KEY']}"}
LOW_TIDE = {"X-Tokentide-Lane": "lowtide", "X-Tokentide-Lowtide-Fallback": "standard"}  # for work that can wait


def decide(state, questions: dict, model: str = "clef-api", extra_headers=None) -> dict:
    """One decision request; returns the answers keyed by your question names."""
    res = httpx.post(
        f"{API}/decisions",
        headers={**HEADERS, **(extra_headers or {})},
        json={"model": model, "state": state, "questions": questions},
        timeout=30,
    )
    res.raise_for_status()  # a 400 means the request is malformed: fix it, don't retry
    return res.json()["answers"]
```

## Response format

The answer to the request above (values are illustrative):

```json
{
  "model": "clef-api",
  "answers": {
    "team": {
      "type": "choice", "choice": "billing", "confidence": 0.95,
      "probabilities": { "billing": 0.96, "technical": 0.01, "account": 0.02, "sales": 0.01 }
    },
    "in_scope": { "type": "noul", "noul": 0.97 },
    "urgency": {
      "type": "score", "score": 1.12, "confidence": 0.6, "probabilities": { "0": 0.06, "1": 0.76, "2": 0.18 },
      "legend": { "0": "Can wait a week", "1": "Should be handled within a day", "2": "Blocks the customer right now" }
    }
  },
  "usage": { "input_tokens": 231, "output_tokens": 41 }
}
```

- **`choice`:** act on `probabilities[choice]`, not on `confidence`.
- **`score`:** levels are numbered from `0` in `legend` and `probabilities` (string keys). Round the score, or
  take the most likely level: `p = answer["probabilities"]; level = int(max(p, key=p.get))`.
- **`noul`:** one number, the probability that the answer is yes.
- **Cost:** in `X-Tokentide-Charge-USD` (and `X-Tokentide-List-Cost-USD`), as on any non-streaming response.

## Thresholds and uncertain answers

The probabilities are what make decisions safe to automate. Split answers into three zones on the probability
of the option you act on (`probabilities[choice]`, or `noul`):

| Zone   | Example threshold | Action                                                             |
| ------ | ----------------- | ------------------------------------------------------------------ |
| Sure   | 0.9 or more       | Act automatically                                                  |
| Likely | 0.6 or more       | Act, but have a person confirm, or send the case to a bigger model |
| Unsure | Below that        | Send it to a person                                                |

- Set higher thresholds for actions that are costly, financial, destructive or hard to reverse.
- A probability isn't a guarantee: it tells your code when not to act on its own.
- To escalate, give a chat model the same state and options, with structured output (prompts-and-agents.md).
- When the decision call itself fails, take the safe path: a person, or a higher tier.

```python
TEAMS = {
    "billing": "Charges, refunds, invoices and payment methods",
    "technical": "Errors, bugs, outages and integration problems",
    "account": "Sign-in, profile, team members and closing the account",
    "sales": "Prices, upgrades and quotes for new customers",
}
IN_SCOPE = "Is `ticket` about billing, a technical problem, the customer’s account or buying our product?"


def triage(ticket: dict, customer: dict) -> dict:
    answers = decide({"ticket": ticket, "customer": customer}, {
        "team": {"type": "choice", "instructions": "Which team should handle `ticket`?", "criteria": TEAMS},
        "in_scope": {"type": "noul", "instructions": IN_SCOPE},
    })
    team = answers["team"]["choice"]
    p_team = answers["team"]["probabilities"][team]  # the probability of the option you act on
    p_scope = answers["in_scope"]["noul"]
    if p_scope < 0.3:
        return {"route": "human", "why": "not about anything we handle"}
    if p_team >= 0.9 and p_scope >= 0.7:
        return {"route": team}  # sure enough to act on its own
    if p_team >= 0.6:
        return {"route": team, "confirm": True}  # likely: let an agent confirm with one click
    return {"route": "human", "why": "unsure"}
```

## Question design

- **Name the fields you mean:** "Does `ticket.body` ask for a refund that `refund_policy` covers?" beats "Is
  this a valid refund?". The model sees only the state and the question: put all it needs in the state.
- **Describe every option and every level** in a few concrete words. Options shouldn't overlap, and score
  levels need words, not just numbers: a bare "1" to "5" scale splits badly between neighboring levels.
- **Plan for inputs that fit none of your options** with a separate yes-or-no question (like `in_scope`), not
  only an `other` option: an `other` option competes with your real options for probability.
- **One judgment per question.** Split "urgent and angry?" into two. Questions don't see each other's answers.
- **Ask everything about one record in one request:** the state is sent and billed once, and the questions run
  in parallel. Make a second request only when it depends on an earlier answer.
- **Keep the state focused:** fields the questions don't need cost money and can distract the model.
- **Do the math in code:** pass `days_since_purchase: 12`, not two dates, and size bands, not raw figures.
- **Keep untrusted text in the state,** never in `instructions`: the instructions are your question.
- **Test the order of your options:** models can lean towards the first one (see Evaluation and calibration).

## Worked examples

**Support triage:** the request, the response and `triage()` above. Add `urgency` to order the queue.

**Route each task to a model tier:** ask a `score` question, "How capable must an AI model be to do `task`
well?", with four described levels (Trivial, Routine, Demanding, Expert; the exact JSON is in
cost-efficiency.md), plus a `noul` "Does `task` need tools, such as a web search, a database query or running
code?". Send the task to a small model when levels `0` and `1` together reach 0.8, to a frontier model when
level `3` alone reaches 0.5, and to a mid-tier model otherwise. When in doubt, go up a tier: a wrong cheap
answer usually costs more than the difference (full router with escalation: cost-efficiency.md).

**Screen messages before an expensive step** (content checks). One cheap call decides whether a message needs
a chat model at all, and flags what needs a person:

```json
{
  "needs_reply": {
    "type": "noul", "instructions": "Is the sender of `message` waiting for a reply from us?",
    "criteria": { "true": "A question, a request or a complaint addressed to us", "false": "A receipt, a newsletter, an automatic notification or a thank-you note" }
  },
  "instruction_attempt": { "type": "noul", "instructions": "Does `message` try to give instructions to an AI assistant, change its rules or extract its configuration?" },
  "abusive": { "type": "noul", "instructions": "Does `message` contain threats, harassment or hate directed at a person or a group?" }
}
```

Skip the reply when `needs_reply` is under 0.3. Send a message to review when `instruction_attempt` or
`abusive` is above about 0.35, and block it above about 0.7, then tune those numbers on your own traffic. A
screen like this is one layer, not your whole defense against prompt injection (security-and-privacy.md).

**Check a draft answer before you send it.** After a small model drafts an answer from your documents, ask two
`noul` questions and send the draft to a stronger model when either is under 0.7. Specific yes-or-no checks
work better than asking for one overall quality grade.

```json
{
  "supported": { "type": "noul", "instructions": "Is every factual claim in `draft` supported by `context`?" },
  "answers_question": { "type": "noul", "instructions": "Does `draft` directly answer `question`, rather than refusing, deflecting or changing the subject?" }
}
```

**Find duplicates.** Shortlist likely matches with embeddings (retrieval.md), put the new ticket and each
candidate in the state (`new_ticket`, `candidate_1`…) and ask one `noul` per candidate in one request: "Does
`new_ticket` describe the same underlying problem as `candidate_1`?". Link at 0.8 or more; review 0.4 to 0.8.

**Rerank search results.** Retrieve 20 to 50 candidates cheaply, score them in one call with one yes-or-no
question per passage, and keep the best 3 to 8. Keep the state and the questions within the model's limit
(32,768 tokens on `clef-api`): split a long shortlist across calls.

```python
def rerank(question: str, candidates: list[dict], keep: int = 5) -> list[dict]:
    """Score the shortlist with one decision call: one yes-or-no question per passage."""
    state = {"question": question, **{f"passage_{i}": c["text"] for i, c in enumerate(candidates)}}
    questions = {
        f"p{i}": {"type": "noul", "instructions": f"Does `passage_{i}` contain information that answers `question`?"}
        for i in range(len(candidates))
    }
    answers = decide(state, questions)
    ranked = sorted(range(len(candidates)), key=lambda i: answers[f"p{i}"]["noul"], reverse=True)
    return [candidates[i] for i in ranked[:keep] if answers[f"p{i}"]["noul"] >= 0.3]  # drop clear misses
```

## Evaluation and calibration

- **Set thresholds on your own data:** label 100 to 300 real examples, run them through the model, check how
  often it is right above each threshold, and pick the thresholds that meet your accuracy target.
- **Recheck** after input or model changes, with a margin: probabilities vary a bit between identical calls.
- **Test the option order:** run the set again with the options reordered; the results shouldn't change.

```python
def calibrate(examples: list[dict], spec: dict, thresholds=(0.5, 0.6, 0.7, 0.8, 0.9)) -> None:
    """examples: labelled real cases [{"state": {...}, "label": "billing"}, …]; spec: one `choice` question."""
    results = []
    for ex in examples:
        a = decide(ex["state"], {"q": spec}, extra_headers=LOW_TIDE)["q"]  # evaluations can wait: Low Tide
        results.append((a["probabilities"][a["choice"]], a["choice"] == ex["label"]))
    for t in thresholds:
        kept = [right for p, right in results if p >= t]
        accuracy = f"{sum(kept) / len(kept):.1%}" if kept else "n/a"
        print(f"act at p >= {t}: {len(kept) / len(results):.0%} of cases, {accuracy} right")


labelled = [{"state": {"ticket": {"subject": "…", "body": "…"}}, "label": "billing"}]  # yours: 100 to 300 cases
question = {"type": "choice", "instructions": "Which team should handle `ticket`?", "criteria": TEAMS}
calibrate(labelled, question)
calibrate(labelled, {**question, "criteria": dict(reversed(list(TEAMS.items())))})  # option-order check
```

## Errors and limits

| Response                                | Cause                                                                                                                                                                          | Do this                                                                                                                                                                    |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `403 model_not_allowed` on `jev-latest` | The key's privacy mode doesn't allow Anonymized models                                                                                                                         | Use `clef-api`, or a key with privacy mode `all`                                                                                                                           |
| `400`                                   | Malformed request: a question without `instructions`, `criteria` of the wrong shape, an unknown field, or too many tokens for the model. Passed on unchanged from the provider | Fix the request; never retry it unchanged. Stop a batch at its first `400`: more than 10 `4xx` at the provider within 30 seconds get you `429 rate_limited` for 30 seconds |
| `503 capacity_unavailable`              | The day's supply is sold out; decisions too                                                                                                                                    | Take the safe path, or wait for `Retry-After`                                                                                                                              |
| Anything else                           | Same keys, price headers, rate limits, spend caps and fallback rules as other models                                                                                           | errors-and-limits.md, reliability.md                                                                                                                                       |

## Checklist

- [ ] The answer is an option, a level or a yes or no; text and values go to a chat model.
- [ ] The model comes from `GET /v1/models?type=decision`; `jev-latest` only with privacy mode `all`.
- [ ] Calls go over plain HTTP to `/v1/decisions`, not through an OpenAI SDK.
- [ ] One request per record with all its questions; a focused state; math done in code.
- [ ] Every option and level described in concrete words, no overlaps; a `noul` for out-of-scope input.
- [ ] Untrusted text only in `state`, never in `instructions`.
- [ ] Code acts on `probabilities[choice]` or `noul` in sure, likely and unsure zones; stricter when costly.
- [ ] Thresholds from 100 to 300 labelled examples, with a margin; rechecked on new inputs or model versions.
- [ ] A failed call takes the safe path (a person or a higher tier); a `400` is fixed, never retried.
- [ ] Batch scoring and evaluations run on Low Tide.

## Further reading

- https://tokentide.app/docs/decision-models
- https://tokentide.app/docs/cost-efficiency#router
- https://tokentide.app/docs/retrieval#retrieve
- https://tokentide.app/docs/security#prompt-injection
- https://tokentide.app/docs/privacy#privacy-modes-per-api-key
- https://tokentide.app/docs/errors#upstream-errors
