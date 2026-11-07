# EU AI Act

> **Not legal advice.** This file is general information about the EU AI Act for teams that build on
> Tokentide. It is not legal advice, and Tokentide does not provide legal advice. Whether and how the Act
> applies depends on the facts of each case: the product, the role, the people affected and how the system is
> used. The law, its guidelines and its codes of practice are still evolving, and mistakes can carry large
> fines. Get advice from a qualified lawyer or AI compliance specialist before relying on any of it. It
> follows Tokentide's docs as published on 7 November 2026.

What the EU AI Act (Regulation (EU) 2024/1689, amended by Regulation (EU) 2026/1744) asks of a team building
AI features on the Tokentide API. Open it when the user's product serves people in the EU or its output is
used there, when they ask about AI disclosure or labelling, or before a feature touching hiring, education,
credit, insurance, biometrics or emotions. Model ids in examples are examples; the current catalog comes from
`GET /v1/models`.

**For you, the agent:** never present this file, or conclusions drawn from it, as legal advice or a compliance
verdict; say it is general information. When the user's situation is unclear or high-stakes (a possibly
prohibited or high-risk use, biometrics, minors, decisions about people), recommend a qualified lawyer or AI
compliance specialist before building. Use the file to build the technical measures and to prepare questions
for that specialist.

## Contents

- [Who it applies to, and the roles](#who-it-applies-to-and-the-roles)
- [Timeline as amended in 2026](#timeline-as-amended-in-2026)
- [Prohibited practices](#prohibited-practices)
- [High-risk uses](#high-risk-uses)
- [Transparency duties](#transparency-duties)
- [AI literacy](#ai-literacy)
- [Records, logging and human oversight](#records-logging-and-human-oversight)
- [General-purpose AI models](#general-purpose-ai-models)
- [Penalties](#penalties)
- [Checklist for a team on the Tokentide API](#checklist-for-a-team-on-the-tokentide-api)
- [Further reading](#further-reading)

## Who it applies to, and the roles

The Act covers AI systems offered in the EU, and AI systems anywhere whose output is used there. Most of what
teams build on Tokentide (chatbots, content generation, agents, search, classification) falls in the lighter
tiers, where the main duties are transparency: tell people when they deal with AI, and mark what AI generates.
A few uses, such as hiring, credit scoring and emotion recognition, are high-risk or prohibited. Text
classification, routing and moderation are usually minimal: document the use, since the risk follows the
decision it supports.

- **Provider:** develops an AI system, or has it developed, and offers it or puts it into service under its
  own name (usually the team, for a product it builds on Tokentide).
- **Deployer:** uses an AI system in a professional activity.

| What the team does with Tokentide                                                            | Role, in most cases                                                                             |
| -------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| Builds a product with an AI feature (a chatbot, an image generator, an agent) under its name | **Provider** of that AI system, even though the model comes from another company through an API |
| Builds an AI tool for its own staff                                                          | **Provider** (puts it into service) and **deployer** (uses it)                                  |
| Uses AI output in its work, for example AI images in its ads                                 | **Deployer**                                                                                    |
| Fine-tunes a model with more than a third of its original training compute                   | Possibly a **general-purpose AI model provider** for that modification                          |

**Tokentide's role, as its docs describe it:** the labs that make the models are providers of general-purpose
AI models, with duties of their own; Tokentide gives access to those models; the duties of the AI system the
team builds and uses are the team's. The API can support that work but can't make a project compliant.

Work feature by feature: record each AI feature's purpose, users and affected people, the team's role, its
models (fallback included), category, what it decides on its own, and its obligations with an owner. One API
key per AI system (the limited beta allows one key per account) makes usage per key
(https://tokentide.app/app/usage) show what each one actually uses.

## Timeline as amended in 2026

| Date                | What applies                                                                                                                                                                     |
| ------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 August 2024       | The AI Act entered into force                                                                                                                                                    |
| 2 February 2025     | Prohibited practices (Article 5) and AI literacy (Article 4)                                                                                                                     |
| 2 August 2025       | Obligations of general-purpose AI model providers, and the governance framework                                                                                                  |
| 27 July 2026        | The 2026 amendments (Regulation (EU) 2026/1744, the "Digital Omnibus on AI") entered into force                                                                                  |
| **2 August 2026**   | **Transparency obligations (Article 50) and most remaining rules apply; national authorities enforce prohibitions, literacy and transparency**                                   |
| **2 December 2026** | **Marking of generated content for generative systems placed on the market before 2 August 2026; two new bans (non-consensual intimate deepfakes, child sexual abuse material)** |
| 2 December 2027     | High-risk obligations for the uses listed in Annex III (employment, education, credit, essential services and others)                                                            |
| 2 August 2028       | High-risk obligations for AI in regulated products (Annex I)                                                                                                                     |

## Prohibited practices

Banned since 2 February 2025, with fines of up to €35 million or 7% of worldwide turnover:

| Banned practice                                                                                                                                                    | An example to avoid                                                       |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------- |
| Manipulative or deceptive techniques that distort people's behaviour and cause significant harm                                                                    | A sales chatbot that uses deceptive tactics to push people into purchases |
| Exploiting vulnerabilities due to age, disability or social or economic situation                                                                                  | Targeting people in financial distress with predatory offers              |
| Social scoring that leads to unjustified or unrelated detrimental treatment                                                                                        | Ranking customers' "trustworthiness" from their online behaviour          |
| Predicting crimes based solely on profiling or personality traits                                                                                                  | A "likely offender" score built from personal characteristics             |
| Untargeted scraping of facial images to build facial recognition databases                                                                                         | Collecting faces from the web to train a face search                      |
| Emotion recognition from biometric data at work or in education (except medical or safety reasons)                                                                 | Analysing employees' or job candidates' voices or faces for emotions      |
| Biometric categorisation to infer race, political opinions, trade-union membership, religion or sexual orientation                                                 | Inferring political views from photos                                     |
| Real-time remote biometric identification in public spaces for law enforcement                                                                                     | Live face matching in public spaces                                       |
| **From 2 December 2026:** generating realistic intimate or sexual content of an identifiable person without their explicit consent, or child sexual abuse material | An app that "undresses" photos of real people                             |

Sentiment analysis of **text** is not emotion recognition from biometric data, so it isn't banned. Analysing
the emotions of **customers** from their voice isn't banned either, but it is high-risk and needs a notice
(see Article 50(3) under [Transparency duties](#transparency-duties)).

- **Design it out.** Don't build these features, and say in the terms that users may not use the product for
  them. Deployers are responsible whatever a provider's terms say.
- **Keep generation safeguards on.** Tokentide always turns on image safe mode (`safe_mode`), which blurs
  images classified as adult content. Add your own safeguards for other media and for edits of photos of real
  people: the 2026 bans cover outcomes the product can foreseeably produce.
- **Screen open-ended products:** one cheap decision-model call can flag requests for uses you don't allow
  before a chat model acts. Send this body to `POST /v1/decisions` over plain HTTP (decision-models.md) and
  route any request whose `choice` isn't `none` to a person: a screen is a safeguard, not a guarantee.

```json
{
  "model": "clef-api",
  "state": { "request": "…the user’s request, as text…" },
  "questions": {
    "restricted_use": {
      "type": "choice",
      "instructions": "Does `request` ask the assistant to do any of these?",
      "criteria": {
        "emotions_at_work_or_school": "Infer the emotions of employees, job candidates or students from their face, voice or writing",
        "sensitive_traits_from_biometrics": "Infer race, political opinions, trade-union membership, religion or sexual orientation from photos, video or voice",
        "social_scoring": "Score or rank people’s trustworthiness from their social behaviour or personal characteristics",
        "intimate_deepfake": "Create sexual or intimate images, video or audio of a real, identifiable person",
        "none": "None of these"
      }
    }
  }
}
```

## High-risk uses

A system is high-risk when it is used in one of the areas of Annex III, among them:

| Area                                                                       | Examples of high-risk uses                                                                                    |
| -------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| Biometrics                                                                 | Emotion recognition (outside work and education), biometric categorisation, remote identification             |
| Education                                                                  | Admissions, grading exams, assessing a student's level, proctoring                                            |
| Employment                                                                 | Targeting job ads, filtering CVs, evaluating candidates, promotion and termination, monitoring performance    |
| Essential services                                                         | Credit scoring (except fraud detection), life and health insurance pricing, public benefits, emergency triage |
| Critical infrastructure, law enforcement, migration, justice and elections | Safety components, risk assessments, decisions affecting rights                                               |

- **Profiling people is always high-risk** in these areas.
- **A narrow exception** covers systems that pose no significant risk and only perform a narrow procedural
  task, improve the result of work a person already did, detect patterns without replacing a person's
  assessment, or prepare a task. The assessment must be documented and the system registered.
- **From 2 December 2027, providers** need risk management, data governance, technical documentation,
  automatic logs kept at least six months, instructions for deployers, human oversight, accuracy, robustness
  and cybersecurity, a quality management system, a conformity assessment, the CE marking, registration in the
  EU database, post-market monitoring and serious-incident reporting.
- **Deployers** must follow the instructions, assign trained people to oversee the system, keep its logs at
  least six months, inform workers and the people the system makes decisions about, and, for credit scoring
  and life or health insurance, assess the impact on fundamental rights. People affected by a decision have a
  right to an explanation.

**What it means for the team:** get specialist advice before building. The API can support a high-risk project
but can't make one compliant: decision-model probabilities for human oversight, an audit log linked to request
ids, privacy mode `private` with Private or E2EE models, pinned model ids and evaluations on every change.

## Transparency duties

### Tell people they are dealing with an AI (Article 50(1))

Since 2 August 2026, people must be told that they are interacting with an AI system, at the latest at their
first interaction, unless it is obvious to a reasonably well-informed person. This covers chatbots, voice
assistants, helpdesks, coding agents and other AI agents; an agent must also say on whose behalf it acts.
According to the Commission's guidelines:

- **Good ways to disclose:** a statement at the first turn ("You are interacting with an AI system"), a
  persistent label near the input field, a spoken statement at the start of a call with reminders after
  interruptions, and an "AI" label on emails an agent sends.
- **Not enough on their own:** a notice only in the terms, invisible metadata, a bare "assistant" label, a
  site-wide "we use AI" line, or "this system uses LLMs".
- **Always tell the truth when asked:** if a user asks whether they are talking to a person, the system must
  say it is an AI.
- **The "obvious" exception is narrow:** code assistants for professional developers or internal tools for
  trained staff may qualify; customer helpdesk chatbots don't.

Put the notice in the interface, not in the prompt, so it can't be skipped or talked away. For voice, say it
at the start of every call or message, in the same voice, and say on whose behalf the agent calls; never clone
a real person's voice without consent:

```python
import os

from openai import OpenAI

tokentide = OpenAI(base_url="https://api.tokentide.app/v1", api_key=os.environ["TOKENTIDE_API_KEY"])
SYSTEM_PROMPT = "You are the support assistant of Example Shop."  # illustrative
AI_NOTICE = "You’re chatting with an AI assistant. Type “agent” at any time to reach a person."


def reply(conversation: list[dict]) -> dict:
    completion = tokentide.chat.completions.create(
        model="zai-org-glm-5-2",
        max_completion_tokens=600,
        messages=[{"role": "system", "content": SYSTEM_PROMPT}, *conversation],
    )
    first_reply = not any(m["role"] == "assistant" for m in conversation)
    return {
        "text": completion.choices[0].message.content or "",
        "ai_generated": True,  # every client can label the message as AI-written
        "notice": AI_NOTICE if first_reply else None,  # shown by your interface: never left to the model
    }


def voice_message(message: str) -> None:
    speech = tokentide.audio.speech.create(
        model="tts-kokoro",
        voice="af_sky",
        # An audible disclosure at the start, in the same voice, before the message itself.
        input="This is an automated message with an AI-generated voice. " + message,
    )
    speech.write_to_file("reminder.mp3")
```

### Mark generated content (Article 50(2)) and label deepfakes (Article 50(4))

Two duties, on two different roles:

- **Marking (providers of generative systems):** images, video, audio and text the product generates must
  carry a machine-readable mark that lets them be detected as AI-generated, as far as technically feasible.
  The Code of Practice the Commission found adequate asks for at least two layers for images, video and audio
  (signed metadata and an imperceptible watermark), a watermark for longer text (over 200 tokens) and a way to
  detect the marks.
- **Labels (deployers):** a deepfake (content that resembles real people, places, objects or events and could
  falsely appear authentic, including in ads: realistic product images that differ from the real product)
  needs a label people can see or hear. So does AI-generated text published to inform the public on matters of
  public interest (politics, health, finance, science), unless a person substantively reviewed it, including
  fact-checking, and a named person or function holds editorial responsibility.

| Needs marking (Commission guidelines)               | Doesn't need marking                                                        |
| --------------------------------------------------- | --------------------------------------------------------------------------- |
| Generated images, video, audio and voices           | Source code, JSON, SQL and other machine-to-machine output                  |
| Generated text, including summaries and paraphrases | Very short text: single words, captions, alt text, interface labels         |
| Mixed human and AI content                          | Grammar fixes, translation, transcription, formatting and minor photo edits |

How to do it with Tokentide (generating the files: media.md):

- **Files arrive unchanged.** Tokentide passes generated images, video and audio through as the model provider
  returns them, without stripping metadata or watermarks. Some image models add a visible watermark by
  default: leave it on where it doesn't harm the use (`hide_watermark: false`).
- **Add the marks on your side** before storing or publishing a file: standard metadata that says it is
  AI-made (the IPTC "trained algorithmic media" source type) and, for the strongest result, signed C2PA
  content credentials and a watermark from a provider that offers one.
- **No personal data in the marks:** marking must not process information about the content's creator, so
  don't use `embed_exif_metadata`, which writes the generation details, including the prompt, into the image.
- **Label what could pass as real:** a visible "AI-generated" label (the EU icon is free to use), at the start
  of videos and at intervals, and a spoken disclaimer at the start of audio.

```bash
# Images: the IPTC digital source type that tools read as "generated by AI", and a description.
exiftool -overwrite_original \
  -XMP-iptcExt:DigitalSourceType=http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia \
  -XMP-dc:Description="AI-generated image" banner.png

# Video and audio: a metadata label, without re-encoding.
ffmpeg -i clip.mp4 -c copy -metadata comment="AI-generated video" clip-labelled.mp4
ffmpeg -i voice.mp3 -c copy -metadata comment="AI-generated voice" voice-labelled.mp3

# Video: a visible label as well, for content that could pass as real.
ffmpeg -i clip.mp4 -vf "drawtext=text='AI-generated':x=w-tw-24:y=h-th-24:fontsize=28:fontcolor=white:box=1:boxcolor=black@0.5" \
  -c:a copy clip-visible-label.mp4
```

- **Text is the open question.** Tokentide doesn't watermark text, and the guidance doesn't yet say how
  companies generating text through an API meet the marking duty: label longer AI-written text where it is
  published, and have the user ask their adviser how the duty applies.
- **Deadlines:** marking applies from 2 August 2026, and from 2 December 2026 for generative systems already
  on the market before 2 August 2026. Content created before 2 August 2026 doesn't need labels retroactively,
  but text generated earlier and published later does.

### Emotion recognition and biometric categorisation (Article 50(3))

Where emotion recognition or biometric categorisation is allowed at all (never at work or in education), the
people exposed to it must be told, and the system is high-risk. Voice or face analysis of customers' emotions
is an example; sentiment analysis of text is neither.

## AI literacy

Since 2 February 2025, providers and deployers must take measures to support the AI literacy of their staff
and of others who use AI systems on their behalf (Article 4). As amended in 2026, the duty doesn't require a
specific level, a certificate or an AI officer. In practice: train the people who build, buy and use the AI
features on what the systems can and can't do and on their risks (wrong answers, prompt injection, bias,
privacy); give people who oversee AI decisions deeper training than occasional users; keep a simple internal
record of what was done, and pair training with guidelines and review. security-and-privacy.md and
prompts-and-agents.md can serve as starting material for engineers.

## Records, logging and human oversight

Good records let the team show an authority, a customer or an auditor what its AI systems do: the feature
inventory, risk assessments, model ids and versions, prompt versions, evaluation results, oversight decisions,
incidents and the notices users saw. For high-risk systems, automatic logs must be kept at least six months.
Tokentide never stores prompts or outputs and keeps request metadata for 90 days, so keep your own audit log,
without content: each request's metadata with Tokentide's request id, the model that actually answered and the
privacy level. Add content only where an obligation requires it, under your data-protection rules (`tokentide`
is the client from the disclosure example).

```python
import json
import time
import uuid


def audited_call(system_id: str, prompt_version: str, **request) -> tuple:
    """Call Tokentide and append one audit record per request: metadata only, never content."""
    client_id = str(uuid.uuid4())
    raw = tokentide.chat.completions.with_raw_response.create(
        **request, extra_headers={"X-Client-Request-Id": client_id}
    )
    completion = raw.parse()
    record = {
        "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "ai_system": system_id,  # the entry in your AI inventory
        "prompt_version": prompt_version,
        "request_id": raw.headers.get("x-request-id"),  # quote it to Tokentide support
        "client_request_id": client_id,
        "model_requested": request["model"],
        "model_served": completion.model,  # differs if a backup model answered
        "backup_model_used": raw.headers.get("x-tokentide-model-fallback"),
        "privacy_level": raw.headers.get("x-tokentide-model-privacy"),
        "finish_reason": completion.choices[0].finish_reason,
        "charge_usd": raw.headers.get("x-tokentide-charge-usd"),
    }
    with open("ai-audit.jsonl", "a") as log:  # your own store, kept as long as your obligations require
        log.write(json.dumps(record) + "\n")
    return completion, record


completion, record = audited_call("support-bot", "v12", model="zai-org-glm-5-2", max_completion_tokens=600, messages=messages)
```

Export Tokentide's metadata at least monthly when it is needed for longer than 90 days (an API key sees its
own requests, so one key per AI system gives one export per system):

```bash
curl -s "https://api.tokentide.app/v1/account/usage?from=2026-10-01T00:00:00Z&to=2026-11-01T00:00:00Z&limit=1000&format=csv" \
  -H "Authorization: Bearer $TOKENTIDE_API_KEY" > tokentide-usage-2026-10.csv
# A page has at most 1,000 rows: repeat with before=<last request_id> until a page has fewer rows.
```

- **Model facts for the inventory:** `GET /v1/models?type=all` with the system's key lists each model it may
  call, with its `type` and `tokentide.privacy_tier`.
- **Keep records and code in step:** model ids in configuration, not scattered in code; alerts on Venice's
  deprecation headers (`x-venice-deprecated*`, `x-venice-model-deprecation-*`). A fallback provider is part of
  the system: list its models too, and log which provider served each request.
- **Human oversight:** decision models return probabilities, so code can route every uncertain case, or every
  case, to a trained person and log who decided (decision-models.md). Agents that act get step limits, budgets
  and a person's approval for what can't be undone (prompts-and-agents.md). Pin model ids and run an
  evaluation set on every change.

## General-purpose AI models

- **Model providers (the labs):** their obligations apply since 2 August 2025. They must give companies that
  build on their models technical documentation (Annex XII of the Act): intended uses, acceptable use
  policies, modalities, limits and licence.
- **Downstream builders (the team):** collect that documentation (model cards, the labs' documentation) for
  the models in use and keep it with the inventory. Open-weight models are exempt from some documentation
  duties unless they carry systemic risk: read their model cards. Fine-tuning a model with over a third of its
  original training compute can make the team a general-purpose AI model provider for that modification.

## Penalties

Maximum fines: €35 million or 7% of worldwide annual turnover for prohibited practices; €15 million or 3% for
most other obligations, including transparency (Article 50) and deployer duties; €7.5 million or 1% for
incorrect or misleading information to authorities. The higher amount applies, except for SMEs, which pay the
lower; small mid-caps also pay the lower for the last two categories. Member States set AI literacy penalties.

## Checklist for a team on the Tokentide API

- [ ] Every AI feature has a role (provider, deployer or both), an inventory entry, an owner and its own key.
- [ ] No prohibited practice (the terms forbid them too); open-ended products screen requests; safeguards on.
- [ ] Each feature checked against the high-risk areas; any match goes to a specialist before building.
- [ ] AI notice in the interface at the first interaction; the system admits it is an AI when asked.
- [ ] Agents say on whose behalf they act; voice messages start with a spoken disclosure.
- [ ] Generated files marked (IPTC metadata; C2PA, watermark where available); no `embed_exif_metadata`.
- [ ] Deepfakes, altered realistic product images and public-interest AI text labelled.
- [ ] Emotion recognition, biometric categorisation: never at work or school; elsewhere a notice, high-risk.
- [ ] AI literacy training done and recorded.
- [ ] Audit log with request ids, models and privacy levels; usage exported monthly if needed past 90 days.
- [ ] Human oversight for decisions about people; the labs' model documentation filed with the inventory.
- [ ] A qualified lawyer or AI compliance specialist has reviewed the plan.

## Further reading

- https://tokentide.app/docs/eu-ai-act: Tokentide's EU AI Act page, which this file follows.
- [The AI Act](https://eur-lex.europa.eu/eli/reg/2024/1689/oj/eng) and
  [the 2026 amendments](https://eur-lex.europa.eu/eli/reg/2026/1744/oj/eng) on EUR-Lex.
- [The AI Act Service Desk](https://ai-act-service-desk.ec.europa.eu/en), with the consolidated text and a
  [compliance checker](https://ai-act-service-desk.ec.europa.eu/en/eu-ai-act-compliance-checker).
- [The Code of Practice on AI-generated content](https://digital-strategy.ec.europa.eu/en/policies/code-practice-ai-generated-content)
- [The EU icons for labelling AI-generated content](https://digital-strategy.ec.europa.eu/en/policies/eu-icons-labelling-ai-generated-content)
- [Guidelines on prohibited AI practices](https://digital-strategy.ec.europa.eu/en/library/commission-publishes-guidelines-prohibited-artificial-intelligence-ai-practices-defined-ai-act)
- [AI literacy questions and answers](https://digital-strategy.ec.europa.eu/en/faqs/ai-literacy-questions-answers)
- [National market surveillance authorities](https://digital-strategy.ec.europa.eu/en/policies/market-surveillance-authorities-under-ai-act)

> **Once more: not legal advice.** Tokentide does not provide legal advice. This file simplifies a long and
> evolving regulation and can't account for the user's product, contracts or customers: confirm every
> obligation with a qualified lawyer or AI compliance specialist before relying on it.
