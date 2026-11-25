# Compliance: honest, labelled, lawful content

The goal is maximum engagement without deception. Deceptive tactics (fake customers, fake reviews,
unprovable claims, hidden AI) trade short-term reach for takedowns, fines and lost trust — and
platforms increasingly detect and demote them. This is a working checklist, not legal advice; for
regulated categories or big paid campaigns, suggest the user involve counsel.

## 1. AI labelling (every platform)
| Platform | Rule (Nov 2026) | How |
|---|---|---|
| TikTok | Realistic AI content must be labelled; unlabelled realistic AIGC can be removed (Community Guidelines "Edited Media and AI-Generated Content", updated 24 Sep 2026). TikTok reads C2PA credentials and auto-labels. | Turn on the AI-generated content setting; optional on-screen "AI-generated" label |
| Instagram / Meta | AI label for realistic AI imagery; "AI-generated profile" label for fully virtual personas (from 31 Aug 2026) | AI label toggle; profile label for virtual influencers |
| X | No dedicated toggle relied on here | Say it in the text or on screen |
Keep C2PA/Content Credentials metadata when a tool provides it; don't strip it.

## 2. EU AI Act Article 50 (applies from 2 Aug 2026)
- Deployers must disclose deepfakes (realistic AI images/video/audio of people, objects, places or
  events that could appear authentic) — lighter treatment for evidently artistic, satirical or
  fictional work. The Digital Omnibus (Reg. (EU) 2026/1744, in force 27 Jul 2026) delayed high-risk
  obligations but **did not delay Article 50**; only providers' machine-readable marking for systems
  already on the market got a grace period to 2 Dec 2026. Commission guidelines adopted 20 Jul 2026.
- Practical: for EU audiences, realistic AI scenes and voices get a visible disclosure.

## 3. Endorsements, reviews and testimonials
- **FTC Rule on Consumer Reviews and Testimonials (16 CFR Part 465, effective 21 Oct 2024):** bans
  fake or AI-generated reviews/testimonials presented as real, undisclosed insider reviews, buying
  positive/negative-conditioned reviews, review suppression, fake "independent" review sites and
  fake social indicators (bought followers/views). Civil penalties up to $53,088 per violation
  (Jan 2025 inflation adjustment). AI avatars aren't banned — an avatar presented as a real customer
  giving a testimonial is.
- Never script "I've used this for 3 months and…" for an AI person. Use real reviews only with
  permission and exact wording, attributed honestly ("from a verified buyer review").
- Paid creators/partners: #ad or the platform's paid-partnership / branded-content tool, clearly visible.
- No bought engagement, no fake comment threads, no engagement pods presented as organic.

## 4. Claims
- Every factual claim in VO, captions, on-screen text or post copy needs evidence in `claims[]`
  (`status: "substantiated"`). package.py blocks risky wording without it ("cures", "guaranteed",
  "clinically proven", "#1", "risk-free", weight-loss numbers…).
- Comparative claims against a named competitor need solid substantiation — default to "vs. the old
  way" instead of naming competitors. Never show or fake competitors' products.
- Regulated categories (health, supplements, cosmetics, finance, alcohol, gambling, kids, weight loss,
  medical devices) have extra rules per market and per platform ad policy — flag them in the risk
  register and keep claims to approved wording.

## 5. People, likeness, voice, IP
- No real person's face, name or voice (celebrities, influencers, employees) without written consent.
  Avoid prompts that resemble a specific real person.
- Voice cloning only with the speaker's written consent (`audio.py clone --i-have-consent`).
- Virtual influencers/mascots: disclose as AI; don't claim lived experiences.
- Trademarks: only the client's own marks; no third-party logos, characters or branded products in
  scenes (also a common 422 trigger).
- Music: generate original tracks (`audio.py music`), use licensed tracks, or platform commercial
  libraries; trending commercial sounds are often not cleared for business accounts. Check the music
  model provider's terms for commercial use (they flow down through Tokentide).

## 6. Tokentide and Venice terms, and data
- Tokentide's Terms (draft dated 1 Nov 2026, "pending review by counsel", Spanish law) say you own your
  outputs *subject to the upstream terms* (Venice's and each model provider's, the stricter rule
  applying), that outputs may not be protected by IP rights and may resemble other users', that you
  need rights to your inputs, and that you must follow EU AI Act disclosure rules.
- Venice's public Terms (8 Jun 2026) grant the service licence "solely for your personal,
  non-commercial use" (§7.1) while contemplating API customers who build for end users (§7.3). Because
  those terms flow down, brand use stays ambiguous: tell the user once to get written commercial terms
  (from Tokentide, and Venice if needed) before publishing.
- Tokentide stores no prompts or outputs (metadata and ledger in AWS US East; a DPA is available).
  Anonymized models send prompts/media to third-party providers who may retain them; use Private
  models (or get the client's OK) for unreleased products.
- Keep the provenance log: every generated file has a `.json` sidecar (model, prompt, date, request id)
  and `logs/ledger.jsonl` records calls and spend.

## 7. Disclosure copy that doesn't kill the vibe
- On screen (small label, top-left, whole video): "AI-generated visuals" / "Made with AI".
- Caption end: "Visuals created with AI. Product and results are real." (only if true)
- Mascot series: "[Name] is our AI mascot 🤖".
- Paid partnership: platform tool + "#ad" at the start of the caption.
