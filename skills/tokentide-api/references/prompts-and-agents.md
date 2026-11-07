# Prompts, tools and agents

Prompts, sampling, structured output, tools, workflows, bounded agents, grounding, evals and operations for AI
features on Tokentide: open it to write a prompt, add tools or an agent loop, or set up evals. The practices
hold across model families, as one request may run on a router tier, a backup model or a fallback provider.
Model ids are examples: the current catalog and capabilities (`supportsFunctionCalling`,
`supportsResponseSchema`, `supportsReasoningEffort`) come from `GET /v1/models`.

## Contents

- Write prompts that work on every model
- Set sampling per model
- Ask for structured output
- Design tools
- Prefer a workflow to an agent
- Bound every agent
- Ground answers
- Evaluate every change
- Run it like software
- Checklist
- Further reading

## Write prompts that work on every model

- **Write a brief for a capable new colleague:** the goal and why, the context (who the users are, what the
  product does, what good looks like), the rules, the output. Test: would a smart newcomer, given only this
  prompt, know what to do? "Write replies customers can act on without writing back" beats "Write a reply":
  models follow rules more reliably when they know the reason.
- **Say what to do:** "Write in plain prose, in at most 150 words" beats "Don't be verbose".
- **Don't shout.** Capitals and "CRITICAL: you MUST" make current models over-apply a rule. Keep "always" and
  "never" for true invariants (safety rules, required fields); give judgment calls as plain guidance.
- **Specify the output:** format, length, language, audience, and what to return when the task can't be done.
- **Show examples when the format or tone is subtle:** three to five varied examples, marked as examples (the
  model copies details they share). Reasoning models often do best with none: try without first.
- **A role sets the tone, not the accuracy:** one sentence of role is enough; spend the words on context.
- **Give reasoning models goals, not steps:** the objective, the constraints and what a good result looks
  like; control their cost with `reasoning_effort`, not with instructions to think less.
- **Test on every model that may run it:** router tiers, backup models and your fallback provider's model.

Separate the parts with headings or tags, from most stable to most variable:

```text
# Role and goal
You write replies to customer support tickets for Acme, a project management app. The goal is a reply the
customer can act on without writing back.

# Context
- Customers are small businesses; many are not technical.
- The help center articles below are the only source of truth about how the product works.

# Rules
- Answer only from the help center articles. If they don't cover the question, say a person will follow up.
- Never promise refunds, discounts or dates: those are decided by the billing team.
- Write in the customer's language, in plain words, in at most 150 words.

# Output
Return JSON matching the schema: {"reply": string, "needs_human": boolean, "articles_used": [string]}.

# Help center articles
<articles>
…the long, stable reference text goes here, before anything that changes per request…
</articles>
```

- **Stable first:** role, rules, output format, examples, reference documents, identical on every request (no
  timestamps or ids near the top), so they are billed at the cheaper cached-input price.
- **Variable last:** the user's message and per-request data. With long documents, documents first and the
  question at the end: Anthropic measured up to 30% better answers that way.
- **One structure:** tags or Markdown headings, same names every time; wrap documents in plain tags, not JSON.
- **Short system prompt:** rules that apply only sometimes belong in retrieved context or a tool description.
- **Mark untrusted content as data** (tags, where it came from): it helps, but isn't a security boundary.

## Set sampling per model

- **Reasoning models ignore or reject sampling settings:** several reject `temperature` and `top_p` while they
  reason, or ignore custom values. Control them with `reasoning_effort` (`low`, or `minimal` or `none` where
  offered), or turn reasoning off where allowed: `extra_body={"reasoning": {"enabled": False}}` in Python.
- **Open-weight models have recommended settings:** their vendors publish a temperature and top-p per mode
  (lower for code and math, higher for creative writing). Use those, per model, not one value for all.
- **Temperature 0 isn't repeatable:** in one test, 1,000 identical requests at temperature 0 gave 80 different
  completions (servers batch requests). Rely on schemas, validation and caching; run test cases several times.
- **Keep a settings profile per model** in your code, and drop the fields a model doesn't accept before
  sending: a request that works on one model can fail on a router tier, a backup model or the fallback.
- **Leave room for reasoning in `max_completion_tokens`:** reasoning counts toward it and is billed as output;
  when the limit runs out mid-thought, the answer comes back short or empty.

## Ask for structured output

When code reads the answer, ask for JSON matching a schema, on models with `supportsResponseSchema`:

```python
import os

from openai import OpenAI
from pydantic import BaseModel

tokentide = OpenAI(base_url="https://api.tokentide.app/v1", api_key=os.environ["TOKENTIDE_API_KEY"])


class TicketReply(BaseModel):
    reply: str
    needs_human: bool
    articles_used: list[str]


schema = {
    "type": "object",
    "properties": {
        "reply": {"type": "string", "description": "The reply to send, at most 150 words"},
        "needs_human": {"type": "boolean", "description": "True when a person must follow up"},
        "articles_used": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["reply", "needs_human", "articles_used"],
    "additionalProperties": False,
}

completion = tokentide.chat.completions.create(  # SYSTEM_PROMPT (the template above) and ticket_text are yours
    model="zai-org-glm-5-2",  # a model with supportsResponseSchema in GET /v1/models
    max_completion_tokens=600,
    response_format={"type": "json_schema", "json_schema": {"name": "ticket_reply", "strict": True, "schema": schema}},
    messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": ticket_text}],
)
choice = completion.choices[0]
if choice.finish_reason == "length":
    raise RuntimeError("Cut off by max_completion_tokens: raise the limit")  # truncated JSON never validates
reply = TicketReply.model_validate_json(choice.message.content or "")  # validate anyway (zod in TypeScript)
```

- **Keep schemas simple and portable:** flat objects, every field `required` (a `null` type for optional
  values), `additionalProperties: false`, enums for categories, a short description per field. Avoid recursion
  and numeric or length constraints: some providers reject them, others ignore them.
- **It still fails two ways:** truncation (`finish_reason: "length"`) and refusals; both leave no valid JSON.
- **Validate anyway, values too:** a well-formed answer can still name a record the user may not touch. On a
  failure, retry once with the validation error in the prompt, then escalate to a stronger model or a person.
- **Let the model think before it formats:** a tight format on a hard judgment can lower its quality, so use a
  reasoning model or a free-form step first, then the schema. Ask for short "evidence" rather than "reasoning"
  in output fields: some reasoning models decline to write out their reasoning.
- **For a label, a score or a yes or no,** a decision model is cheaper and never answers in the wrong shape.

## Design tools

```json
{
  "type": "function",
  "function": {
    "name": "search_orders",
    "description": "Find the signed-in customer's orders. Use it when they ask about an order's status, items or delivery. Returns at most 5 orders, newest first. Does not return payment details. The customer is taken from the session, so never ask for an id.",
    "parameters": {
      "type": "object",
      "properties": {
        "status": { "type": "string", "enum": ["any", "processing", "shipped", "delivered", "returned"],
                    "description": "Filter by status; use any when the customer doesn't say" },
        "since_days": { "type": "integer", "minimum": 1, "maximum": 365, "description": "Only orders from the last N days" }
      },
      "required": ["status"],
      "additionalProperties": false
    }
  }
}
```

- **The description matters most:** what the tool does, when to use it, when not to, and what it returns, in a
  few clear sentences for someone who has never seen your system.
- **Few tools per request:** every definition is input billed on every call, and long lists make the model
  choose worse (OpenAI suggests fewer than 20 at a time; 58 tools can take about 55,000 tokens). Offer the
  tools the current step needs, and merge tools that are always called together.
- **Don't make the model fill in what you know:** the user's id, the tenant and the date come from your code.
- **Narrow parameters** (types, enums, ranges, `required`), validated in the tool: never trust them.
- **Small results:** ids and the fields that matter; large results are billed again on every later turn.
- **Actionable errors:** "No order C-1042 in the last 30 days; try a longer `since_days`", not a stack trace.
- **Idempotent side effects:** a repeated call must not charge, email or delete twice.
- **Results are data:** a tool result can carry injected instructions. Choose the allowed tools from the
  user's request before the model reads any tool output, and put consequential actions behind a person.
- **Send the model's turns back unchanged:** append the assistant message exactly as received, reasoning
  fields included; some reasoning models reject a conversation whose reasoning was removed.
- **Check each model:** `supportsFunctionCalling` in `GET /v1/models` (E2EE models take no function calling),
  and test `tool_choice` on every model a request may run on: forcing a tool works differently across models.

```python
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class SearchOrdersArgs(BaseModel):  # mirrors the tool's parameters
    model_config = ConfigDict(extra="forbid")  # unknown arguments are an error, not ignored
    status: Literal["any", "processing", "shipped", "delivered", "returned"]
    since_days: int = Field(default=30, ge=1, le=365)  # default illustrative


def search_orders(session, **raw) -> dict:  # bind it in your code: tools = {"search_orders": partial(search_orders, session)}
    try:
        args = SearchOrdersArgs.model_validate(raw)  # never trust the model's arguments
    except ValidationError as err:
        return {"error": "Invalid arguments: " + "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in err.errors())}
    orders = find_orders(session.customer_id, args.status, args.since_days, limit=5)  # customer from the session
    if not orders:
        return {"error": f"No {args.status} orders in the last {args.since_days} days; try a longer since_days."}
    return {"orders": [{"id": o.id, "status": o.status, "delivery_date": o.delivery_date} for o in orders]}
```

## Prefer a workflow to an agent

An agent lets the model pick its next step in a loop; a workflow runs steps you fixed in code. Workflows are
cheaper, faster and easier to test: start there, and add autonomy only where it pays off.

| Pattern               | How it works                                                               | Tokentide fit                                                  |
| --------------------- | -------------------------------------------------------------------------- | -------------------------------------------------------------- |
| **Chain**             | Fixed steps, each checked before the next (outline → draft → polish)       | A cheap model for easy steps, a stronger one only where needed |
| **Route**             | Classify the input, then send it to a specialized prompt or model          | A decision model as the classifier (`decision-models.md`)      |
| **Parallelize**       | Split independent parts, or ask several times and vote                     | Small models in parallel, within your rate limits              |
| **Plan and delegate** | A strong model breaks the job into steps; workers do the steps             | A frontier planner, small-model workers (`cost-efficiency.md`) |
| **Draft and check**   | One step drafts, another checks against criteria, and the draft is revised | Checks with tests, schemas or a decision model                 |

- **Parallel calls** count against your concurrent-request limit per account (16 new, 64 verified, 256
  trusted); a request over a limit gets `429 rate_limited` with `Retry-After` (`errors-and-limits.md`).
- **Use an agent only when the steps can't be known in advance** (open-ended research, debugging), and accept
  that it costs more and fails in more ways.
- **Start with one agent:** Anthropic measured multi-agent systems using about 15 times the tokens of a chat.
  They suit work that splits into independent parts, not tasks that share a lot of context.

## Bound every agent

```python
import json
import os
import time

import openai
from openai import OpenAI

tokentide = OpenAI(base_url="https://api.tokentide.app/v1", api_key=os.environ["TOKENTIDE_API_KEY"])

MAX_STEPS = 12  # an agent that hasn't finished in 12 steps is stuck, not thinking
BUDGET_USD = 0.50  # what one task may cost, across all its calls
DEADLINE_S = 300  # wall-clock limit per task (illustrative)
NEEDS_APPROVAL = {"send_email", "issue_refund"}  # tools whose effect can't be undone (illustrative names)
STOPPED = "Stopped: the step, cost or time limit was reached. A person should take over."
# AGENT_PROMPT, ask_a_person(name, args) -> bool and the tools are yours.


def run_agent(task: str, tools: dict, tool_specs: list) -> str:
    messages = [{"role": "system", "content": AGENT_PROMPT}, {"role": "user", "content": task}]
    spent, deadline = 0.0, time.monotonic() + DEADLINE_S
    for _ in range(MAX_STEPS):
        try:
            raw = tokentide.chat.completions.with_raw_response.create(
                model="zai-org-glm-5-2",
                max_completion_tokens=2_000,
                messages=messages,
                tools=tool_specs,
                extra_headers={"X-Tokentide-Max-Cost-USD": "0.10"},  # no single step may cost more
            )
        except openai.APIStatusError as err:  # e.g. 402 spend_limit_reached, 409 cost_above_limit: stop, don't loop
            return f"{STOPPED} ({err.status_code} {err.code})"
        spent += float(raw.headers.get("x-tokentide-charge-usd", "0"))
        message = raw.parse().choices[0].message
        if not message.tool_calls:
            return message.content or ""  # the agent is done
        messages.append(message)  # unchanged, reasoning fields included
        for call in message.tool_calls:
            name = call.function.name
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = None
            if name not in tools or not isinstance(args, dict):
                result = {"error": "Unknown tool, or arguments that aren't a JSON object. Use a listed tool."}
            elif name in NEEDS_APPROVAL and not ask_a_person(name, args):  # show the exact action, not a summary
                result = {"error": "A person declined this action. Choose another way or stop."}
            else:
                result = tools[name](**args)  # each tool validates its arguments and keeps its result small
            messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result)[:4_000]})
        if spent >= BUDGET_USD or time.monotonic() > deadline:
            break
    return STOPPED
```

In TypeScript, pass the header as request options (`{ headers: { 'X-Tokentide-Max-Cost-USD': '0.10' } }`) and
read the charge with `.withResponse()` (`response.headers.get('x-tokentide-charge-usd')`).

- **Per-call ceiling:** `X-Tokentide-Max-Cost-USD` refuses a call whose worst case (input plus
  `max_completion_tokens`) could cost more, with `409 cost_above_limit`, never charged. The worst case grows
  with the context: a long run that reaches the ceiling should stop, or trim its context.
- **A spend cap as the backstop:** give each agent its own API key with a small daily cap
  (https://tokentide.app/app/keys), so the most it can spend is known in advance. Over the cap, calls get
  `402 spend_limit_reached`, which the OpenAI SDKs don't retry: stop the run.
- **Timeouts:** check the clock between steps. An HTTP client timeout must be longer than your slowest request
  (up to 800 seconds): a request you stop waiting for can still run and be charged.
- **A person approves the exact irreversible action** (payment, message, deletion, permission change).
- **Least power:** few, narrow, read-only tools by default (no shell, no "fetch any URL"), with the user's
  permissions through short-lived credentials scoped to the task (`security-and-privacy.md`).
- **Keep the context lean:** trim old tool results, summarize long histories, hand subtasks to sub-agents.
- **Choose the model per step:** planning and hard judgments may need a frontier model; routine steps don't.
- **Log every step** (tool, arguments' shape, cost, outcome), never the content, to replay what went wrong.

## Ground answers

- **Give the facts** (passages, records, tool results: `retrieval.md`); ask for citations and check them.
- **Allow "I don't know"** and say so in the prompt: in OpenAI's published SimpleQA results, a model that
  declined 52% of the questions was wrong on 26%, one that almost never declined on 75%.
- **Check outside the model:** asking a model to double-check its own answer, with no new information, rarely
  fixes it. Tests, schemas, lookups, a second model or a decision-model check give real feedback.
- **People review what matters:** medical, legal, financial and other high-stakes outputs.

## Evaluate every change

- **Build a golden set before you tune:** 20 to 50 real cases per feature, taken from actual failures and edge
  cases, each with the expected answer or a clear pass-or-fail rule. Add every new failure. Pass or fail
  grades more consistently than a 1-to-5 score.
- **Grade with code where you can** (exact match, schema checks, tests), with a model where you must, and with
  people on a sample. A model judge needs a rubric, a different model family and calibration against human
  labels; judges favor longer answers and the first option shown: control for both.
- **Track quality, cost and latency together,** per prompt version and per model.
- **Run the set on every change** (prompt, model, parameters, retrieval) and on a schedule, since providers
  update models: pin versioned model ids where they exist. Run agents several times per case.
- **Run evals on Low Tide** (`X-Tokentide-Lane: lowtide`, non-streaming): no one is waiting for them.
- **Ship gradually:** try a change in shadow mode or on a small share of traffic, compare, then roll out.

## Run it like software

- **Model ids and prompt versions in config,** so a switch is one change; take ids from `GET /v1/models` and
  alert on Venice's deprecation headers (`x-venice-deprecated*`, `x-venice-model-deprecation-*`).
- **Trace metadata, not content:** ids (`X-Request-Id`, your `X-Client-Request-Id`), prompt version, model,
  tokens, cost, latency, outcome. With OpenTelemetry's generative AI conventions, leave content capture off.
- **Cost per run:** add up `X-Tokentide-Charge-USD` (via `with_raw_response`, as in the agent loop) over every
  call of a task, retries and fallbacks included; streams report cost in their final usage chunk.
- **Fallbacks:** `X-Tokentide-Fallback-Models` lists up to 3 Tokentide models (same privacy tier and features:
  tools, structured output, vision); the response's `model` and `X-Tokentide-Model-Fallback` show which ran. A
  fallback provider covers sold-out days (`reliability.md`). Test prompts and tools on all.
- **Watch:** user feedback, escalation and fallback rates, refusals, `finish_reason: "length"`, cost per task.
- **Feel fast:** stream answers, keep outputs short, run independent calls in parallel, cache stable prefixes.
- **Plan for failure:** timeouts, retries with idempotency keys, a fallback provider, a message if all fail.

## Checklist

- [ ] Prompt as a brief (goal and why, context, rules, exact output); stable parts first, variable last.
- [ ] No shouting; varied examples only where needed; tested on every model that may run it.
- [ ] A settings profile per model; `reasoning_effort` for reasoning models; room for reasoning in the limit.
- [ ] Simple schema on `supportsResponseSchema` models; `finish_reason: "length"` handled; output validated.
- [ ] Few tools with clear descriptions, validated parameters, small results, idempotent side effects.
- [ ] A workflow unless the steps can't be known in advance.
- [ ] Each agent: step limit, budget, `X-Tokentide-Max-Cost-USD`, timeout, own capped key, human approval.
- [ ] Answers grounded with citations, "I don't know" allowed, checks outside the model.
- [ ] Golden set on every change and on a schedule; agents run several times per case; judges calibrated.
- [ ] Model ids in config; metadata-only logs with cost per run; backup models and fallback provider tested.

## Further reading

- https://tokentide.app/docs/prompts-and-agents
- https://tokentide.app/docs/cost-efficiency#reasoning
- https://tokentide.app/docs/cost-efficiency#prompt-caching
- https://tokentide.app/docs/decision-models
- https://tokentide.app/docs/security#agents
- https://tokentide.app/docs/security#prompt-injection
- https://tokentide.app/docs/billing#per-request-limits
- https://tokentide.app/docs/best-practices#backup-models
- https://tokentide.app/docs/fallback
