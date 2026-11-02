# Hooks, retention and formats that sell without feeling like ads

## Contents
1. The first 2 seconds
2. Hook templates (fill with VOC language)
3. Retention editing
4. Endings and CTAs per platform
5. Format library with beat sheets
6. Why people share (STEPPS, arousal) and the send test
7. AI content that works vs. "AI slop"
8. Series, recurring characters and mascots

## 1. The first 2 seconds
A viewer decides in about a second. Stack three hooks that say the same thing:
- **Visual hook (frame 1):** motion or the payoff itself — never a logo, never a slow fade-in. Start
  mid-action. If the best moment is at 7 s, flash it first ("payoff-first") and rewind.
- **Text hook:** ≤8 words, high-contrast, inside the safe area, on screen from frame 1 to ~2.5 s.
- **Spoken hook:** ≤12 words, starts within 0.3 s. Matches the text but isn't identical.
- **Sound:** a sharp transient (click, pour, snap, whoosh) at 0 s beats silence.
Kill anything in the first 2 s that is context, greeting or branding.

## 2. Hook templates (fill with VOC language)
Curiosity & payoff
1. "I didn't expect this to work on [thing]…"
2. "Watch what happens at [second/step]."
3. "[N] hours later…" / "Day [N] of [test]."
4. "This is what [N] [unit] of [thing] looks like."
5. "Nobody tells you this about [category]."
Callout / identity
6. "If you [specific situation], watch this."
7. "POV: you finally [dream outcome]."
8. "For the people who [quirky behaviour from VOC]."
9. "[Persona] be like:" (relatable skit)
Contrarian / myth
10. "Stop [common habit]. Do this instead."
11. "[Common belief] is a lie. Here's proof."
12. "You've been [doing X] wrong."
13. "Unpopular opinion: [take you can back]."
Problem → solution
14. "[Pain in their words]? Same. Until this."
15. "The reason your [thing] keeps [failing]."
16. "I was today years old when I learned [fact]."
Test / proof
17. "Can [product] survive [extreme test]?"
18. "[Product] vs [the old way] — [test]."
19. "I tested [N] [category] so you don't have to." (only if you really did)
20. "Before / after [time]." (split screen from frame 1)
Lists & value
21. "3 ways to use [product] you didn't know."
22. "[N] [category] mistakes that cost you [outcome]."
23. "Save this for your next [situation]."
Story & behind the scenes
24. "We almost didn't launch this because…"
25. "How we make [product] (it's weirder than you think)."
26. "The customer email that made us change [thing]."
Humour / absurd
27. "Things that just make sense: [product moment]."
28. "Rating [category] by how [absurd criterion]."
29. Overly dramatic narration of a mundane use.
Offer (most-aware only)
30. "If you've been waiting for [product] to drop, this is it."
Write variants per angle; keep the strongest 3 per video for A/B tests.

## 3. Retention editing
- Visual change every **1.5–3 s**: cut, angle change, punch-in (`zoom: punch`), slow push (`push`),
  caption colour pop, sound effect.
- **Open loop early** ("…the last one surprised us") and close it at the end.
- Deliver the payoff by ~70% of the runtime; the remaining 30% is reaction + CTA.
- One idea per video. If you need "and also", it's two videos.
- Captions in 2–4 word chunks with the active word highlighted (captions.py `highlight`).
- Remove breaths and pauses in VO (TTS speed 1.05–1.15 for energetic content).
- Endings that loop back to the opening frame drive rewatches (`loop: true` + `end_image`).

## 4. Endings and CTAs per platform
| Platform | Best CTA | Example |
|---|---|---|
| Instagram | Send / save | "Send this to the friend who…" |
| TikTok | Comment → video reply, follow for part 2 | "Which one should we test next?" |
| X | Reply / quote | "Would yours survive this? Wrong answers only." |
Organic: soft CTAs (follow for the series, send, comment). Hard sell ("buy now", price) belongs in
paid versions and most-aware audiences.

## 5. Format library with beat sheets (times for a ~13 s cut)
| Format | Beats | Best for |
|---|---|---|
| Satisfying demo / ASMR | 0–1 payoff flash · 1–8 the action in macro, real sound · 8–11 result · 11–13 CTA/loop | physical products with texture, sound, motion |
| Problem → solution (PAS) | 0–2 pain in VOC words · 2–5 agitate (fail clip) · 5–10 product solves it · 10–13 proof + CTA | problem-aware |
| Before / after | 0–1 split screen · 1–9 transformation · 9–13 reveal + CTA | visible outcomes (cleaning, beauty, home, design) |
| Torture / durability test | 0–2 "can it survive…?" · 2–9 escalating test · 9–11 result · 11–13 "send to…" | durable goods |
| Myth-bust | 0–2 myth on screen · 2–9 demo disproving it · 9–13 takeaway | sophisticated markets |
| 3 ways / hacks | 0–1 hook · 3 × ~3 s uses · end with the most surprising use | versatile products |
| POV / skit | 0–2 POV text · 2–10 relatable situation · 10–13 product punchline | identity & humour |
| Unboxing / first look | 0–1 the best detail · 1–9 open + details · 9–13 verdict | launches, premium packaging |
| Behind the scenes | 0–2 surprising process detail · 2–11 steps · 11–13 "now you know" | brand story, craft |
| Comparison vs. old way | 0–2 side-by-side · 2–10 race/test · 10–13 result | solution-aware (never fake a competitor) |
| Educational mini-lesson | 0–2 counterintuitive fact · 2–11 explain + show · 11–13 save CTA | SaaS, health-adjacent (no unproven claims) |
| Trend-jack | follow the trend's structure with an original twist; use licensed/original audio | timely reach |
| Episodic series | recurring title card · same structure each episode · cliffhanger | follower growth |

## 6. Why people share
**STEPPS (Jonah Berger):** Social currency (makes the sharer look good/in-the-know) · Triggers
(everyday cues remind them) · Emotion · Public (visible use) · Practical value · Stories.
**Arousal matters:** Berger & Milkman (2012, NYT articles) found high-arousal emotions — awe,
amusement/surprise, anger, anxiety — drive sharing; low-arousal sadness reduces it.
**Send test:** "[persona] sends this to [person] because [reason]". If it's not completable, rework
the concept — on Instagram sends per reach is a top signal, and on X DM shares rank like replies.

## 7. AI content that works vs. "AI slop"
Works: AI as the production tool, a real idea and a real product; impossible-but-honest product
moments (macro worlds, physics-defying demos clearly stylised); consistent mascots/characters
disclosed as AI; real product photos animated faithfully; native lo-fi framing; specific customer
language; honest labels.
Fails: generic glossy scenes with no idea; uncanny humans presented as real customers; AI voice
reading ad copy; morphing products and garbled labels; templated repetitive posts; anything that
feels like it hides being AI. Audiences and platforms are increasingly sensitive to undisclosed AI —
treat disclosure as part of the creative, not a footnote.

## 8. Series, recurring characters and mascots
- A series needs a name, a fixed structure, a recurring visual signature (title card, colour, sound,
  character) and a reason to come back (next test, next episode, ranking).
- Mascots/virtual presenters: build a character sheet (front/side/3-4 views, outfit, palette) and
  reuse it as reference (Kling O3 `elements`, Seedance R2V for non-human characters). Disclose them as
  AI; never present them as real customers or employees.
- Keep 2 series running and rotate formats around them; series episodes convert viewers to followers.
