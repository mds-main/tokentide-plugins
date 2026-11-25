# Universal storycraft, hooks, pacing & format library

## Contents
1. Universal directing principles (what makes ANY video spectacular)
2. Opening strong: the first 2–3 seconds
3. Universal format & genre blueprints
4. Retention editing & visual rhythm
5. Hook formulas (for social, growth & commercial videos)
6. Endings & CTAs by destination
7. Shareability (STEPPS & send test) for growth campaigns
8. High craft vs. "AI slop"
9. Series & recurring visual signatures

## 1. Universal directing principles (what makes ANY video spectacular)
No matter what the user asks for — a cinematic trailer, a technical tutorial, a documentary mini-film, a
product commercial, a personal celebration, a music video, a real estate showcase, or a social growth reel —
six craft decisions turn raw clips into studio-grade work:
1. **Truthful visual grounding:** real faces stay recognizable, real interfaces stay pixel-sharp, real
   products and places stay faithful, and imagined worlds stay stylistically unified (`visual-grounding.md`).
2. **One unmistakable narrative spine:** hook/premise (why care?) → purposeful progression (escalation,
   discovery, or step-by-step clarity) → emotional or practical climax (~70–80%) → clean, resonant landing.
3. **Visual hierarchy & shot choreography:** alternate scale (wide establishing → medium action → close-up
   emotion/focus → macro detail) so every cut feels intentional and kinetic.
4. **Coherent look bible:** unified lighting, color palette, lens texture and typography across every shot
   (mixing real captures, real clips and generated visuals seamlessly).
5. **Cinema-grade sound design:** deliberate voice pacing (or intentional music-only storytelling), an
   original score matching the emotional energy curve, subtle foley/UI/transition SFX, and clean −14 LUFS
   mastering with zero speech artifacts.
6. **Destination-native framing:** compose cleanly for `16:9`, `9:16`, or `1:1` safe zones, choosing
   burned captions when feeds start muted and clean caption-free framing (+ `.srt`) when cinematic elegance
   wins.

## 2. Opening strong: the first 2–3 seconds
Never waste second 0 on a black fade-in, a static logo card, or generic throat-clearing ("Hey everyone...").
- **Immediate visual interest:** motion in frame 1, a striking reveal, a payoff preview (then rewind to
  Step 1), or a compelling human/visual moment.
- **Audio anchor:** downbeat of the score, tactile sound effect, or crisp opening line within 0.3 s.
- **Typography (only when it serves the genre):** concise ≤8-word hook/title clear of UI safe zones.

## 3. Universal format & genre blueprints
Adapt structure, canvas, audio and caption choices to the exact genre — never force one template onto all:

| Genre / Video kind | Typical canvas & length | Narrative & visual blueprint | Grounding & post-production signature |
|---|---|---|---|
| **Cinematic brand film / launch trailer** | `16:9` (+ `9:16` cutdown), 30–90 s | World-building visual hook → tension/contrast → dramatic hero reveal → escalating proof montage → iconic closing lockup & end card | Style Master + real product/brand anchors; custom orchestral/electronic build; crisp title cards; clean mix |
| **Software / workflow video guide & tutorial** | `16:9` (2–6 min) or `9:16` (20–55 s) | Payoff preview (0–8s) → starting screen → click-by-click cause-and-effect steps → completed output + tight zoomed detail crops → next-step CTA | 100% real crisp captures (`shots[].image` + targeted focal `edit.zoom` + `smoothleft`/cuts + subtle UI click/chime SFX); calm 2.3–2.6 w/s narration; optional 1–2 non-UI hook shots |
| **Personal, family, event, travel or tribute film** | `16:9` or `9:16`, 30–120 s | Signature opening frame → rising chapters of shared moments & atmosphere → golden emotional climax → warm closing hold & subtle title/date | Real multi-angle photos/clips (`fidelity: "person"`, Kling/Veo/`@r2v` + authentic photos with smooth Ken Burns / `fit: "blur"`); emotional custom score; often cleanest with `captions.enabled: false` |
| **Explainer, educational lesson or science/data story** | `16:9` or `9:16`, 45–240 s | Counterintuitive hook/question → visual metaphor + crisp data/diagram progression → "aha" synthesis → practical takeaway | Approved Style Master + crisp programmatic charts/diagrams (`shots[].image`) + verified `claims[]`; clear 2.4–2.6 w/s VO |
| **Documentary mini-film / founder or origin story** | `16:9` or `9:16`, 60–180 s | In-medias-res moment → context & obstacle → turning point → real proof/impact → reflective closing | Real photos/footage (`fit: "blur"` / Ken Burns) blended with atmospheric establishing cinema; warm understated score |
| **Physical product commercial / viral short** | `9:16` (10–35 s) or `16:9` (15–45 s) | 0–2s payoff flash / PAS hook / myth-bust / torture test → tactile demo (macro sound `@i2v_audio`) → undeniable result → platform CTA or seamless loop | Multi-angle product cutouts (`bg-remove` + `multi-edit` `fidelity: "product"`), hands off labels, real proof clips, punchy burned `highlight` captions |
| **Music video / visual poem / stylized art / animation** | `16:9` or `9:16`, 30–180 s | Beat-synced visual motif → thematic escalation across distinct visual chapters → visual crescendo → lingering final image | Locked Style Master + Character Sheets across all shots; cuts timed to musical bars; zero unwanted captions |
| **Real estate, hospitality, venue, automotive or portfolio showcase** | `16:9` or `9:16`, 30–90 s | Hero establishing shot → smooth spatial walkthrough (exterior → key spaces → tactile details → lifestyle atmosphere) → clean contact/brand end card | Real photos/clips + lighting-enhanced `edit` (`fidelity: "subject"`) + slow stabilized sweeps; refined ambient score |

## 4. Retention editing & visual rhythm
- **Short-form (`9:16`):** visual change every **1.5–3 s** (angle cut, focal `punch`, smooth `push`,
  caption highlight, SFX accent).
- **Long-form / cinema / guides (`16:9`):** visual change every **3–6 s** (new capture, targeted zoom
  onto a button/chart/face, shot-size progression, or smooth chapter transition).
- **Open loop early** and pay it off around 70–80% of runtime.
- **One unified focus per video** — if it tries to cover three unrelated stories, split it into a series.
- **Seamless loops** (`loop: true` + `end_image` = frame 1) boost replays on short-form feeds.

## 5. Hook formulas (when optimizing for social reach & ads)
Fill with authentic audience language:
- **Curiosity / payoff:** "Watch what happens at step 3…" · "This is what [N] [unit] actually looks like."
- **Identity / callout:** "If you [specific situation], watch this." · "POV: you finally [outcome]."
- **Contrarian / myth-bust:** "Stop [common habit]. Do this instead." · "You've been doing [X] the hard way."
- **Problem → solution:** "[Pain in their exact words]? Fix it in 30 seconds."
- **Proof / comparison:** "[Approach] vs. the old way." · "Before and after [time]."
- **Behind the scenes:** "How we built [X] from scratch."

## 6. Endings & CTAs by destination
- **Personal / artistic / brand cinema:** lingering hero frame + clean minimal title/date/logo card.
- **YouTube Long-Form:** recap the outcome + direct viewers to the description link and next video.
- **Instagram Reels:** explicit send/save prompt (*"Send this to someone who needs this"*).
- **TikTok / YouTube Shorts:** comment question or episodic Part 2 tease.
- **X / LinkedIn:** sharp takeaway or thoughtful discussion prompt.

## 7. Shareability (STEPPS & send test — for social growth campaigns)
Score concepts 0–2 on Jonah Berger's **STEPPS**: Social currency · Triggers · High-arousal Emotion
(awe, amusement, surprise) · Public · Practical value · Stories. Greenlight at ≥7/12 + a concrete
**send test**: *"[persona] sends this to [person] because [reason]."*

## 8. High craft vs. "AI slop"
- **Studio craft:** visually grounded subjects (zero hallucinated faces/UIs/logos), unified visual bible,
  purposeful camera and shot progression, clean pacing synced to custom score & SFX, honest AI labels.
- **AI slop (never ship):** mutating faces or characters, garbled AI-generated buttons/text, disconnected
  stock visuals with no arc, robotic ad-copy TTS, morphing logos, undisclosed fake testimonials.

## 9. Series & recurring visual signatures
Channels and brands compound fastest through **series**: consistent visual signature (palette, title
format, character/host, sound motif) and a clear promise that makes viewers follow for the next episode.
