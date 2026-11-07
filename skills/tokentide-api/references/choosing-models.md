# Choosing models

How to pick a model on Tokentide: the ten model types with their endpoints and price drivers, privacy levels
and key privacy modes (including what `403 model_not_allowed` means), reading `GET /v1/models`, example picks
per task, a procedure for choosing a model for a new feature, and keeping model ids in configuration. Open it
before you hard-code a model id, when a feature needs a new kind of model, or when a model is refused,
retiring or too expensive.

## Contents

- How to choose
- Model types
- Privacy levels and key privacy modes
- Reading the catalog
- Picking a model per task
- Procedure: choose a model for a new feature
- Model ids in configuration
- Further reading

## How to choose

- **Use the cheapest model that does the task well.** Within each type, prices differ by 10 to 100 times, and
  a frontier model on a task that a small model handles well costs 20 to 100 times more for the same result.
- **Start with the smallest model that might work**, test it on your own examples, and move up only for what
  fails. Keep frontier models for hard, ambiguous, novel or high-stakes work: spend on difficulty, not volume.
- **Lower the reasoning effort before you change models:** on many tasks that is the cheaper fix.
- **Use the right type, not a chat model for everything:** a decision model for labels, scores and yes-or-no
  checks, an embedding model for search and similarity, plain code where a rule is enough.
- **Let a strong model plan and a cheap one do the steps** when a job splits into small, clear steps.
- **Compare cost per task, not price per token:** models split text into different numbers of tokens, write
  answers of different lengths and need different numbers of retries (cost-efficiency.md).
- **Test again when new models arrive:** small models catch up fast.
- **Model ids in this file are examples** taken from the docs. Take current ids from `GET /v1/models`, called
  with the key that will run the feature.

## Model types

| `type`      | Use it for                                             | Endpoint                                                   | Priced by                                       | Privacy levels                 |
| ----------- | ------------------------------------------------------ | ---------------------------------------------------------- | ----------------------------------------------- | ------------------------------ |
| `text`      | Chat, reasoning, code, vision, tools, structured output | `POST /v1/chat/completions`, `POST /v1/responses`          | Tokens in and out; repeated input costs less    | Private, TEE, E2EE, Anonymized |
| `decision`  | A label, a score or a yes or no, with probabilities    | `POST /v1/decisions` (alias `/v1/systemone`)               | Tokens in (the output is a few tokens)          | Private, Anonymized            |
| `embedding` | Search, similarity, clustering, deduplication          | `POST /v1/embeddings`                                      | Tokens in                                       | Private, Anonymized            |
| `image`     | Images from a prompt                                   | `POST /v1/image/generate`, `POST /v1/images/generations`   | Per image, by resolution and quality            | Private, Anonymized            |
| `inpaint`   | Edit an image, or edit it with reference images        | `POST /v1/image/edit`, `POST /v1/image/multi-edit`         | Per edit, sometimes plus each extra input image | Private, Anonymized            |
| `upscale`   | Enlarge an image 2× or 4×                              | `POST /v1/image/upscale`                                   | Per image, by scale                             | Private                        |
| `video`     | Video from text or a start image (queued job)          | `POST /v1/video/quote`, `/queue`, `/retrieve`, `/complete` | Per job, from its parameters (quote first)      | Private, Anonymized            |
| `music`     | Music and sound effects (queued job)                   | `POST /v1/audio/quote`, `/queue`, `/retrieve`, `/complete` | Per track, per length band or per second        | Anonymized                     |
| `tts`       | Text to speech                                         | `POST /v1/audio/speech`                                    | Per character                                   | Private, Anonymized            |
| `asr`       | Speech to text                                         | `POST /v1/audio/transcriptions`                            | Per second of audio                             | Private, Anonymized            |

Background removal (`POST /v1/image/background-remove`) always runs on `bria-bg-remover`, an Anonymized model,
so it needs a key with privacy mode `all` or `private_text`. How to call each media endpoint: media.md.

### Text and reasoning models

- **Reasoning.** Models with `supportsReasoning` think before they answer, which helps multi-step logic, math,
  planning and code; the thinking is billed as output tokens. For extraction, formatting and short answers,
  set `reasoning_effort` to `low` (or `minimal` or `none` where offered), or send
  `"reasoning": {"enabled": false}` on models that allow it. `supportsReasoningEffort` says which models take
  the setting; some models always reason.
- **Code.** A code-specialized model (the `default_code` trait points to one) is often better and cheaper for
  code than a general frontier model.
- **Vision.** Models with `supportsVision` read `image_url` parts (base64 images need the
  `data:image/…;base64,` prefix). Image tokens grow with pixel area: halving the width and the height cuts the
  cost about four times. Crop to what matters, downscale to the smallest legible size, and check
  `supportsMultipleImages` before sending several.
- **Long context.** Many models accept a million tokens, but every token is billed on every request and
  reliability drops as input grows: retrieve the passages you need instead (retrieval.md).
- **Tools and structured output.** Check `supportsFunctionCalling` and `supportsResponseSchema`, and test them
  on every model a request may run on, backup models included (prompts-and-agents.md).
- **Privacy.** Private models (open-weight models run by Venice) suit most work; E2EE models keep prompts
  encrypted until they reach an attested enclave; Claude, GPT and Gemini models are Anonymized and need
  privacy mode `all`.

### Decision, embedding and media models

- **Decision models** return a typed answer with probabilities for a fraction of a chat model's price:
  `clef-api` (Private) and `jev-latest` (Anonymized, needs privacy mode `all`). See decision-models.md.
- **Embedding models** start at $0.0125 per million tokens for Private ones (list price): embedding a thousand
  pages costs about a cent. Choose by accuracy on your own data, vector size and privacy, and keep one model
  per index.
- **Media models** (list prices): images from $0.01 to about $1 each, and the same model can cost 13 times
  more at high quality than at low; speech from about $3.50 per million characters (`tts-kokoro`, Private) to
  more than $100; transcription from about $0.11 per hour of audio (`stt-xai-v1`, Private) to about $0.60;
  video priced per job and music per track, both quoted for free before you queue.

## Privacy levels and key privacy modes

Every model has a privacy level, and every API key has a privacy mode that decides which levels it may call.
At every level Tokentide stores no prompts, files or outputs, and nobody past Tokentide receives your identity
(Venice gets Tokentide's key and a pseudonymous per-account hash, never your IP address, email or account id).

| Level      | Who runs the model                                                    | Who can read your content                                                                                                        | `X-Tokentide-Model-Privacy` | Choose it for                                                                     |
| ---------- | --------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- | --------------------------- | --------------------------------------------------------------------------------- |
| Private    | Venice                                                                | Tokentide (in memory only) and Venice while it runs the model. Venice's privacy policy says it keeps no prompts or outputs (Venice's commitment, not checkable from outside) | `private`                   | Everyday work, confidential content included, when a published policy is enough |
| TEE        | Venice, inside a hardware enclave (ids usually start with `tee-`)     | Tokentide (in memory only), Venice's API on the way in, and the enclave; not the machine's operator. Venice publishes attestation and a signature per response | `tee`                       | Content where you want hardware evidence of where it is processed                 |
| E2EE       | Venice, inside an attested enclave (`e2ee-*` ids)                     | Nobody in between, Tokentide included: you encrypt, the enclave decrypts                                                         | `e2ee`                      | Content nobody in between may ever read                                           |
| Anonymized | A third-party provider through Venice's account (Claude, GPT, Gemini…) | Tokentide (in memory only), Venice and the provider, which sees and may keep your content under its own policy but never learns who you are | `anonymized`                | Tasks that need one of these models, with content you may share with its provider |

- **E2EE has limits:** `/v1/chat/completions` only, `stream: true`, no file inputs, function calling or web
  search, and the Standard lane only. Without the E2EE headers the same models run as TEE (and still report
  `e2ee`). Setup and verification: security-and-privacy.md.
- **Anonymized content can still identify people:** leave out what you would not share with that provider.

| Privacy mode                     | The key may call                                                                                                              | Use it for                                                        |
| -------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| `private` (default for new keys) | Private, TEE and E2EE models only                                                                                             | Anything sensitive                                                |
| `private_text`                   | Text, embedding and decision models: Private, TEE or E2EE only. Image, video and audio models (prompts included) may be Anonymized | Apps that need Anonymized media models but must keep text private |
| `all`                            | Every model, Anonymized ones included                                                                                         | Claude, GPT and Gemini models, `jev-latest`, Anonymized media     |

- **The user owns the key's privacy mode.** It is set per key in the dashboard
  (https://tokentide.app/app/keys). Never widen it on your own: tell the user which model needs which mode and
  that its provider will see the content.
- **Give each workload a key with the narrowest mode that works.** During the limited beta an account has one
  API key: choose the narrowest mode the whole app needs.
- **What needs which mode:** an Anonymized decision model needs `all`; background removal, all music models
  and most video models need `all` or `private_text`; Private video models (the `grok-imagine-*-private`
  family) work with any key.
- **Pick backup models of the same privacy level**, and keep requests that must stay private off a fallback
  provider outside Tokentide, which has its own terms (reliability.md).

### `403 model_not_allowed`

The answer is final: never retry the request unchanged.

| Cause                                                                                    | Fix                                                                                                                                                                    |
| ---------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| The key's privacy mode does not allow the model's privacy level                          | Pick a model from `GET /v1/models` called with that key, or ask the user to switch the key to `all` (`private_text` is enough for Anonymized media) if the content may go to that provider |
| The model is not offered on Tokentide                                                    | Choose another model from the catalog                                                                                                                                  |
| A Low Tide request names a model excluded from Low Tide (`tokentide.lowtide.eligible: false`) | Send it on Standard, or add `X-Tokentide-Lowtide-Fallback: standard`                                                                                             |

## Reading the catalog

`GET /v1/models?type=<type>` lists the models of one type (`text`, `decision`, `embedding`, `image`,
`inpaint`, `upscale`, `video`, `music`, `tts`, `asr`, or `all`). Always pass `type`, and call it with the key
that will run the feature: it then lists only the models that key may call, with your current prices.

| Field                                             | What it holds                                                                                                                                                                                                                                                         |
| ------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `id`, `type`                                      | The id to send as `model`, and the model's type                                                                                                                                                                                                                       |
| `model_spec`                                      | Venice's spec: `name`, `privacy`, list `pricing`, `capabilities` (`supportsReasoning`, `supportsReasoningEffort`, `supportsVision`, `supportsMultipleImages`, `supportsFunctionCalling`, `supportsResponseSchema`…), context length (`availableContextTokens`), output limit (`maxCompletionTokens`), the options of media models (resolutions, aspect ratios, durations, voices, formats) and `deprecation` (retirement date and replacement) |
| `tokentide.privacy_tier`                          | `private`, `tee`, `e2ee` or `anonymized`                                                                                                                                                                                                                              |
| `tokentide.standard`                              | Your Standard price now, rounded up: `multiplier`, `input_per_1m` and `output_per_1m` (USD per million tokens), or `per_unit` and `unit` (which names the unit) for models priced per image, second of audio or characters                                            |
| `tokentide.lowtide`                               | `open`, `eligible`, `multiplier` and the same prices on Low Tide                                                                                                                                                                                                       |
| `tokentide.price_locked_until`, `tokentide.epoch` | A price lock (`null` when none) and the UTC day the prices belong to                                                                                                                                                                                                 |

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

The values are illustrative: prices move through the UTC day. List candidates that have the features you need,
cheapest first:

```python
import os

import httpx

API = "https://api.tokentide.app/v1"
HEADERS = {"Authorization": f"Bearer {os.environ['TOKENTIDE_API_KEY']}"}  # lists only what this key may call


def candidates(model_type: str = "text", need: tuple = (), min_context: int = 0) -> list:
    """Models with every capability in `need` and enough context, cheapest Standard output price first."""
    res = httpx.get(f"{API}/models", params={"type": model_type}, headers=HEADERS, timeout=30)
    res.raise_for_status()
    rows = []
    for m in res.json()["data"]:
        spec, tt = m.get("model_spec", {}), m["tokentide"]
        if not all((spec.get("capabilities") or {}).get(flag) for flag in need):
            continue
        if (spec.get("availableContextTokens") or 0) < min_context:
            continue
        rows.append({
            "id": m["id"],
            "privacy": tt["privacy_tier"],
            "input_per_1m": float(tt["standard"]["input_per_1m"] or 0),
            "output_per_1m": float(tt["standard"]["output_per_1m"] or 0),
            "lowtide_eligible": tt["lowtide"]["eligible"],
            "retires": (spec.get("deprecation") or {}).get("date"),
        })
    return sorted(rows, key=lambda r: (r["output_per_1m"], r["input_per_1m"]))


for row in candidates("text", need=("supportsFunctionCalling", "supportsResponseSchema"), min_context=128_000)[:10]:
    print(row)
```

- **Price a concrete request** with `GET /v1/market/estimate?model=…&input_tokens=…&output_tokens=…` (or
  `units=…` for models priced per unit). It is public, needs no key, and answers for now, every remaining UTC
  hour and tomorrow's opening (pricing-and-timing.md).
- **Traits:** `GET /v1/models/traits` suggests a model per role, such as `most_intelligent`,
  `default_reasoning`, `default_code`, `default_vision` and `fastest`. Use it to explore, then pin explicit
  ids: a trait can move to another model when the catalog changes.
- **Compatibility mapping:** `GET /v1/models/compatibility_mapping` maps model names that other APIs use to
  catalog models. Send explicit Tokentide ids in production anyway.
- **Retirement:** models due for retirement show their date and replacement on the models page
  (https://tokentide.app/models) and in `GET /v1/models`, and responses carry Venice's deprecation headers
  (`x-venice-deprecated*`, `x-venice-model-deprecation-*`). Alert on them, test the replacement, switch before
  the date.

## Picking a model per task

| Task                                                                                                  | Start with                     | Example ids                                                                                  | Notes                                                |
| ----------------------------------------------------------------------------------------------------- | ------------------------------ | -------------------------------------------------------------------------------------------- | ---------------------------------------------------- |
| Yes-or-no checks, classification, routing, scoring, moderation pre-checks                             | Decision model                 | `clef-api` (Private), `jev-latest` (Anonymized)                                              | Act on the probabilities (decision-models.md)        |
| Search, similarity, deduplication, clustering, retrieval for RAG                                      | Embedding model                | `text-embedding-qwen3-0-6b`, `text-embedding-qwen3-8b`                                       | One model per index (retrieval.md)                   |
| Extraction to JSON, tagging, formatting, short summaries, simple translation and rewriting            | Small, fast text model         | `z-ai-glm-5-3-flash`, `deepseek-v4-1-flash`                                                  | Little or no reasoning                               |
| Long summaries, answers from your documents, drafting, routine coding, tool use with clear steps      | Mid-tier text model            | `zai-org-glm-5-2`, `deepseek-v4-pro`                                                         | Low to medium reasoning                              |
| Hard reasoning, novel problems, complex coding and debugging, system design, long agent work, high stakes | Frontier text model        | `grok-4-7`, `kimi-k3` (Private); `claude-opus-5-5`, `openai-gpt-55` (privacy mode `all`)     | Compare `medium` and `high` effort before the maximum |
| Code                                                                                                  | Code-specialized text model    | The model the `default_code` trait names                                                     | Often beats a general frontier model on code         |
| Screenshots, photos, scanned pages                                                                    | Text model with `supportsVision` | The model the `default_vision` trait names                                                 | Crop and downscale first                             |
| Images                                                                                                | A fast model, then the premium one | `z-image-turbo` to draft, `flux-3-image` to finish                                       | Fixed `seed` while drafting (media.md)               |
| Speech; transcription                                                                                 | `tts`; `asr`                   | `tts-kokoro`; `stt-xai-v1`, `openai/whisper-large-v3` (all Private)                          | Test on your own voices and recordings               |
| Video with a `private` key; music and sound effects                                                   | Private `video`; `music`       | `grok-imagine-text-to-video-private`; `elevenlabs-music` (Anonymized)                        | Music needs `all` or `private_text`                  |

## Procedure: choose a model for a new feature

1. **Write down the requirements:** the task (which type and endpoint), how sensitive the data is (which
   privacy level, so which key mode), the features it needs (tools, JSON schema, vision, reasoning, context
   and output length), latency (interactive and streamed, or batch work that can wait for Low Tide), volume,
   and the budget per task.
2. **List candidates from the catalog** with the key that will run the feature (`candidates()` above): filter
   by capabilities and limits, drop retiring models, and keep three to five across tiers, cheapest first. A
   trait is a hint, not a choice.
3. **Run a small eval:** 50 to 200 real examples with the right answer or a scoring rubric, the production
   prompt, settings and `max_completion_tokens`. Grade automatically where you can (exact match for labels,
   schema checks and tests for structured output and code, a decision model or a strong model with a rubric
   for open text), and read a sample by hand.
4. **Measure cost per task,** retries and escalations included: record `X-Tokentide-List-Cost-USD` and
   `X-Tokentide-Charge-USD` per example (on streams, the final usage chunk). Compare models on list cost,
   since the multiplier moves through the day, and budget with the charge. Put a price on mistakes too: a
   cheaper model that is wrong more often can cost more overall.
5. **Pick the cheapest model that meets the bar, and a backup:** another model on Tokentide with the same
   privacy level and the features you use, sent in `X-Tokentide-Fallback-Models` (up to 3, tried in order when
   the model is offline or overloaded). Run the eval on it too. A fallback provider for sold-out days:
   reliability.md.
6. **Ship and watch:** ids in configuration (below), the model that answered logged per request, and the eval
   run again whenever models, prompts or the catalog change.

```python
import os

from openai import OpenAI

client = OpenAI(base_url="https://api.tokentide.app/v1", api_key=os.environ["TOKENTIDE_API_KEY"])
CASES = [{"prompt": "Extract the invoice number from this email: …", "expected": "INV-2041"}]  # 50-200 real ones


def grade(answer: str, expected: str) -> bool:
    return answer.strip() == expected  # your check: exact match, a schema, tests or a rubric


def evaluate(model: str, max_tokens: int = 500) -> dict:
    passed, list_usd, charge_usd = 0, 0.0, 0.0
    for case in CASES:
        raw = client.chat.completions.with_raw_response.create(
            model=model,
            max_completion_tokens=max_tokens,
            messages=[{"role": "user", "content": case["prompt"]}],
        )
        passed += grade(raw.parse().choices[0].message.content or "", case["expected"])
        list_usd += float(raw.headers.get("x-tokentide-list-cost-usd") or 0)
        charge_usd += float(raw.headers.get("x-tokentide-charge-usd") or 0)
    n = len(CASES)
    return {"model": model, "pass_rate": passed / n, "list_usd": list_usd / n, "charge_usd": charge_usd / n}


for model in ["z-ai-glm-5-3-flash", "deepseek-v4-1-flash", "zai-org-glm-5-2"]:  # cheapest first
    print(evaluate(model))
```

## Model ids in configuration

- **Keep ids in configuration, not scattered through code:** one place, named by role (`small`, `mid`,
  `frontier`, `backup`), so a switch is one change.
- **Pin explicit ids,** never traits or compatibility names, so a catalog change cannot switch your model
  silently.
- **Check them at startup or deploy** against `GET /v1/models` with the production key: each id exists, the
  key may call it, and none is retiring.
- **Log the model that answered** (the response's `model`, which differs when a backup model ran, as
  `X-Tokentide-Model-Fallback` reports) and `X-Tokentide-Model-Privacy`, next to `X-Request-Id`.

```python
import logging
import os

import httpx

MODELS = {  # one place, by role; override per environment
    "small": os.environ.get("MODEL_SMALL", "z-ai-glm-5-3-flash"),
    "mid": os.environ.get("MODEL_MID", "zai-org-glm-5-2"),
    "frontier": os.environ.get("MODEL_FRONTIER", "grok-4-7"),
}


def check_models() -> None:
    res = httpx.get("https://api.tokentide.app/v1/models", params={"type": "all"}, timeout=30,
                    headers={"Authorization": f"Bearer {os.environ['TOKENTIDE_API_KEY']}"})
    res.raise_for_status()
    catalog = {m["id"]: m for m in res.json()["data"]}  # only the models this key may call
    for role, model_id in MODELS.items():
        if model_id not in catalog:
            raise RuntimeError(f"{role}: {model_id} is not callable with this key (privacy mode, or retired)")
        retires = (catalog[model_id]["model_spec"].get("deprecation") or {}).get("date")
        if retires:
            logging.warning("%s: %s retires on %s; test its replacement", role, model_id, retires)
```

## Further reading

- https://tokentide.app/docs/choosing-models
- https://tokentide.app/docs/cost-efficiency#match-the-model
- https://tokentide.app/docs/privacy
- https://tokentide.app/docs/security#privacy-tiers
- https://tokentide.app/docs/e2ee
- https://tokentide.app/docs/best-practices#model-ids
- https://tokentide.app/docs/best-practices#backup-models
- https://tokentide.app/docs/decision-models
- https://tokentide.app/docs/retrieval#embedding-models
- https://tokentide.app/docs/timing#price-it-first
- https://tokentide.app/models
