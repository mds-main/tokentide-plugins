# Visual grounding: reference gathering, autonomous capture & zero-hallucination craft

The biggest difference between a breathtaking, credible video and generic "AI slop" is **visual
grounding**. Generative models excel at lighting, camera motion, atmosphere and imagination, but they
cannot read minds or fabricate real people, real interfaces, real products, real places or exact data
without hallucinating them.

**Golden rule: complete a Reality Inventory and ground every visual anchor BEFORE writing a shot spec
or generating a single frame.** Combine **(a) autonomous capture with whatever browser, computer-use or
local tools exist in your environment** and **(b) targeted, low-friction requests to the user for
references only they have** — always doing everything you can yourself first.

## Contents
1. The Universal Reality Inventory (how to ground ANY video)
2. Acquisition intelligence: capture autonomously vs. ask the user
3. Interactive browser / computer-use capture & authenticated login handoff
4. Real beings (people, groups, presenters, pets) — max identity consistency
5. Readable interfaces, documents, data & digital media (zero text distortion)
6. Real objects, products, brands, places & events
7. Invented worlds, stylized animation & recurring characters (Visual Bible)
8. Hybrid directing: picking the highest-craft modality per shot
9. Reference layout & Grounding Readiness Gate

---

## 1. The Universal Reality Inventory (how to ground ANY video)

Before designing shots for **any** video — film, documentary, tutorial, commercial, explainer, music
video, real estate tour, event recap, personal story, trailer, course lesson or social series — list
every recurring or real-world visual element the video will show and classify its anchor type:

| Visual anchor class | Examples (illustrative, non-exhaustive) | Why it must be grounded | Storage (`P/assets/`) |
|---|---|---|---|
| **Identifiable real beings** | People, founders, presenters, families, couples, performers, pets | Models hallucinate faces, proportions and markings if prompted from text alone | `people/<slug>/` |
| **Readable interfaces, text & data** | Web/desktop/mobile apps, terminals, code, dashboards, charts, slides, maps, documents, games | Video models warp small text, buttons, menus and numbers | `captures/` |
| **Real objects, products & brands** | Hardware, packaging, fashion, vehicles, instruments, logos, brand typography | Viewers instantly spot wrong silhouettes, colors, logos or label text | `product/`, `brand/`, `fonts/` |
| **Real places, architecture & events** | Buildings, interiors, venues, cities, landscapes, live events, artwork | Models invent generic stock places that don't match reality | `references/`, `footage/` |
| **Invented worlds & recurring cast** | Original characters, mascots, sci-fi/fantasy settings, stylized 2D/3D/anime/claymation, abstract visual metaphors | Without visual anchors, style, lighting and character appearance mutate every cut | `references/`, `scenes/` |

Most high-craft videos contain a mix of these anchor classes. Ground EVERY class present before Phase 5.

---

## 2. Acquisition intelligence: capture autonomously vs. ask the user

For each item in the Reality Inventory, choose the fastest, highest-fidelity acquisition path:

1. **Gather autonomously whenever you have access (do the work yourself!):**
   - **Live web resource** (website, web app, SaaS dashboard, docs, property listing, portfolio, public
     dataset, map, press kit, storefront): use your environment's **agentic browser, browser subagent,
     Playwright, Puppeteer, Chrome DevTools MCP, or web fetch** to inspect and capture high-resolution
     screens, facts and official assets directly. Never ask the user to manually screenshot 20 pages you
     can open yourself.
   - **Local desktop app, simulator, terminal, or codebase:** use **Computer Use / desktop automation /
     local scripts** to drive the real workflow or render razor-sharp data charts, diagrams, code blocks
     and graphics programmatically (HTML/SVG → PNG at exact canvas dimensions).
   - **Local files already in the workspace:** discover and inspect existing photos, clips, logos, fonts,
     docs and data in the user's folder before asking for duplicates.
2. **Ask the user once, cleanly and specifically, ONLY for what you cannot reach yourself:**
   - Personal photos or private footage (people, pets, venues, events, memories).
   - Unreleased products, high-res original photography, transparent logos, licensed brand fonts, raw
     screen recordings or internal brand guidelines.
   - Clarifications that affect visual truth (exact workflow to show, wardrobe/era, must-include moments).
   - Bundle all requests into **one concise message** explaining *why* each asset makes the final video
     dramatically better (e.g. "2–4 clear, well-lit photos per person from front and 3/4 angles keep faces
     consistent across every shot").
3. **Generate & lock Style Anchors for invented worlds:**
   - When no real-world photo exists (original stories, trailers, explainers, stylized art), generate
     1–2 **Style Master** frames and any **Character/Asset Sheets** first, review them visually (and with
     the user at the approval gate), and pass them as anchors to every downstream shot.

---

## 3. Interactive browser / computer-use capture & authenticated login handoff

Whenever the video needs real screens, workflows, layouts or visual proof from a web app, website,
desktop app, or online platform:

### 3.1 Authenticated / gated resource protocol (Login Handoff)
If the target URL or workflow sits behind **login, OAuth, SSO, passkey, 2FA, CAPTCHA, or a paywall**:
1. Open the agent's **interactive / visible browser** (browser subagent, headful browser, or desktop
   browser via Computer Use) and navigate directly to the sign-in screen.
2. **Pause and hand control to the user in one clear message:**
   > *"I've opened the sign-in page for [Site/App] in the browser. Please log in there (and complete any
   > SSO, 2FA or verification — never paste passwords, passkeys or tokens in chat). Tell me once you're
   > signed in and I'll resume automatically and capture everything needed."*
3. **Hard security rules:** never request passwords, cookies, tokens or 2FA codes in chat; never attempt
   to bypass auth walls, access controls or CAPTCHAs. Suggest clean demo/staging data when showing a live
   account so no sensitive personal or customer data is exposed.
4. **Resume in the exact same authenticated session** once the user confirms — do not open a fresh
   logged-out browser — and navigate through the full workflow to capture every needed visual and fact.
5. If your environment has **no** interactive browser or computer-use tool at all, send the user a concise
   numbered capture shot list (exact views, recommended window size, clean demo data checklist) instead.

### 3.2 Dense visual capture standards (for interfaces, workflows & web resources)
Capture the full **cause-and-effect chain** rather than jumping across disconnected states:
- **Coverage:** opening payoff/result preview → starting state → every meaningful click, hover, input,
  modal, feedback/progress state → completed output → tight zoomed detail crops on small numbers, labels,
  charts or code → 1–2 uncluttered hero frames for thumbnails/covers.
- **Density:** ~10–18 distinct captures for a 20–55 s short; ~18–40+ captures for a 2–6 min walkthrough.
- **Legible retina viewports matching the target canvas:**
  - `16:9` (`1920×1080`): **`1280×720 @ 1.5x`** (boosts UI typography 1.5× for phone readability while
    exporting razor-sharp `1920×1080` PNGs!) or `1920×1080 @ 1x` for spacious layouts.
  - `9:16` (`1080×1920`): **`540×960 @ 2x`** or **`360×640 @ 3x`** (true responsive mobile layout).
  - `1:1` (`1080×1080`): **`540×540 @ 2x`** or **`720×720 @ 1.5x`**.
- **Viewport & privacy hygiene:** dismiss cookie popups, chat bubbles and dev overlays; wait for fonts,
  images, charts and spinners to settle; use realistic fictional demo data (never `"test123"`, and ZERO
  real PII, private emails, API keys, `.env` values, billing numbers or personal bookmarks).
- **Catalog & inspect:** save numbered PNGs in `P/assets/captures/` (`01_*.png`, `02_*.png`…) with an
  `INDEX.md` noting what each frame shows and the normalized focal `(x, y)` coordinates of key elements
  (for targeted Ken Burns zooms in `assemble.py`). Open and inspect EVERY PNG visually before writing specs.

---

## 4. Real beings (people, groups, presenters, pets) — max identity consistency

When ANY identifiable real person, group, presenter, or pet appears:
1. **Gather clean multi-angle references:**
   - **Per individual:** **2–4 sharp, well-lit, unobstructed photos** (front-facing + 3/4 angle +
     optional medium/full-body for build/posture; avoid heavy sunglasses, motion blur or harsh filters).
   - **Multiple beings together:** **1–2 photos together** to ground relative height, scale, skin-tone
     balance and natural rapport.
   - **Optional context:** wardrobe photos, venue/location photos, or authentic existing clips/photos.
   - **Consent:** confirm identifiable people consent to appearing (`references/compliance.md` §5).
   - Write a brief `P/assets/people/IDENTITY.md` noting factual traits (hair, eyes, approximate age,
     distinctive details, relative heights, wardrobe per scene) so every prompt stays consistent.
2. **Lock identity in still keyframes FIRST (`multi-edit` / `edit` with `fidelity: "person"` or `"subject"`):**
   - Generate empty scenes separately (`@scene`), then composite the real subject(s) in with `multi-edit`
     (2–8 inputs depending on model `maxInputImages`, e.g. `[scene, subject_1, subject_2]`) mapping image
     numbers explicitly in the prompt — OR restyle a real photo of them together (`[together_photo, scene_ref]`)
     to preserve natural posture and proportions effortlessly.
   - `image.py` auto-enables `fidelity: "person"` for inputs inside `assets/people/` (or set
     `keyframe.fidelity: "person"` explicitly; use `"subject"` for pets/non-human subjects).
   - Produce 3–4 candidates at `2K` and **inspect side-by-side against the originals** (`qa.py vision
     --mode people`). Reject likeness scores `< 4/5` BEFORE spending on video animation!
3. **Animate with identity-preserving models & camera discipline:**
   - **Person-safe models ONLY:** use **Kling (V3 / O3)**, **Veo (3.x)** or other Arena-proven human-safe
     models. **NEVER use Seedance `-basic` models on shots containing people** (`409` rejection).
   - **Reference-to-Video (`@r2v`) + Start/End anchoring:** pass reference photos via `video.reference_images`
     or Kling O3 `video.elements` (`video.py` auto-encodes local files within 4.5 MB!) AND/OR lock both
     start (`image`) and closing (`end_image`) keyframes from the same references.
   - Keep clips **4–6 s** with well-lit front/3-4 angles and natural, unhurried motion (avoid fast 180°
     spins or objects crossing faces). Keep wardrobe and lighting coherent across cuts.
   - Blend in authentic original photos (`shots[].image` + smooth Ken Burns centered on faces) or real
     clips (`shots[].clip`) whenever authenticity amplifies emotional impact.

---

## 5. Readable interfaces, documents, data & digital media (zero text distortion)

- **NEVER pass readable UI screens, terminals, spreadsheets, slides, charts or document pages into
  image-to-video (`@i2v`)** — generative video models garble small letters, icons and numbers.
- Instead, animate verified crisp PNGs directly in `assemble.py` (`shots[].image` or `keyframe.mode:
  "file"`/`"frame"`, **no** `video` block) at **`$0` generation cost**:
  - Use **targeted focal Ken Burns zooms** (`edit.zoom: {"type": "push", "amount": 0.24, "x": 0.78, "y": 0.30}`)
    to draw the viewer's eye directly onto the exact button, chart peak, code line or headline.
  - Use directional pans (`pan-down`, `pan-right`) for tall pages or wide tables, and `edit.fit: "contain"`
    or `"blur"` whenever source dimensions differ from the canvas so zero characters get clipped.
  - Pair crisp screen cuts (`cut`, `smoothleft`, `fade`) with subtle sound design (soft UI clicks, clean
    whooshes, payoff chimes) and optionally 1–2 generative non-UI conceptual/atmospheric bookend shots.
- For custom data visualizations, diagrams, timelines, formulas or title graphics, render them crisply as
  exact-resolution PNGs (HTML/SVG/Pillow/browser render) rather than asking an image model to spell text.

---

## 6. Real objects, products, brands, places & events

- **Products & brands:** obtain multi-angle high-res photos on plain backgrounds, transparent PNG/SVG
  logos (`assets/brand/`), and licensed fonts (`assets/fonts/`). Cut out cleanly (`image.py bg-remove`),
  composite into custom scenes (`multi-edit` with `fidelity: "product"`), inspect side-by-side, animate
  with steady camera moves and hands off labels, and apply logos/text strictly in post.
- **Real places, interiors, vehicles, artwork & events:** gather real photos/clips from the user or
  public online listings/sites (`assets/references/`, `assets/footage/`). Use directly with subtle Ken
  Burns / `fit: "blur"` for documentary truth, OR use `edit`/`multi-edit` (`fidelity: "subject"`) +
  `@i2v` for cinematic lighting/time-of-day shifts and gentle camera sweeps while keeping geometry true.

---

## 7. Invented worlds, stylized animation & recurring characters (Visual Bible)

Even when nothing in the video exists in real life (original fiction, trailers, animated explainers,
music videos, stylized brand films, visual essays), **unguided per-shot generation creates a disjointed
patchwork**. Ground the aesthetic before generating the full storyboard:
1. Write `P/assets/references/STYLE_BIBLE.md`: art direction (e.g. 35mm cinema, neo-noir, painterly 2D,
   clean 3D tactile motion, editorial documentary, stop-motion), 4–5 hex color palette, lighting rule,
   lens language, texture/grain, and recurring character/world descriptors.
2. Generate 2–4 candidates for **1–2 Style Master frames** (`@scene`) at the target aspect ratio and lock
   the winning look.
3. For any recurring character, creature, mascot, vehicle or hero prop, generate a clean **Character /
   Asset Sheet** (front, 3/4, side, consistent outfit/palette) in `P/assets/references/`.
4. Reuse the Style Master and Character Sheet as input anchors on every shot (`multi-edit` with
   `fidelity: "subject"`, `--style-ref`, or `@r2v` `reference_images`/`elements`) so every cut belongs to
   one unmistakably unified film.

---

## 8. Hybrid directing: picking the highest-craft modality per shot

Never trap an entire video in a single visual technique when blending produces a stronger result. On
every beat of the storyboard, choose deliberately among four visual modalities:
1. **Authentic live video / screen recording** (`shots[].clip`) — unmatched motion truth.
2. **Crisp real image / capture / diagram + focal 2D camera motion** (`shots[].image` + `edit.zoom` /
   `edit.fit`) — 100% legible UI, data, photography or custom vector graphics at `$0` gen cost.
3. **Reference-grounded generative cinema** (`multi-edit`/`edit` keyframe → QA → `@i2v`/`@r2v` + optional
   `end_image`) — dramatic camera motion, lighting shifts, impossible perspectives, imagined scenes.
4. **Editorial typography & audio glue** — unified font hierarchy, intentional color palette, custom
   original music score, clean voice narration (or deliberate music-only space) and tactile SFX.

---

## 9. Reference layout & Grounding Readiness Gate

```text
P/assets/
  people/<slug>/     real multi-angle photos of identifiable people/pets + together/ + IDENTITY.md
  captures/          sequential crisp UI/web/document captures (01_*.png…) + INDEX.md (with focal x,y)
  product/           high-res multi-angle product photos + *_cutout.png
  brand/             transparent logos, end cards, brand tokens
  fonts/             licensed .ttf / .otf fonts
  references/        real places/objects/wardrobe, Style Master frames, Character Sheets, STYLE_BIBLE.md
  footage/           user-provided video clips or screen recordings
  scenes/            generated subject-free environments and B-roll stills
  music/  sfx/       licensed or generated audio tracks
```

**Grounding Readiness Gate (confirm BEFORE Phase 5 spec writing):**
- [ ] Every identifiable real person/pet has clean multi-angle references in `P/assets/people/` (+ consent).
- [ ] Every real interface, app workflow, webpage, chart or document is captured crisply in
      `P/assets/captures/` (via autonomous browser/computer use, with login handoff if gated) and visually
      verified for legibility, zero spinners and zero PII/secrets.
- [ ] Every real product, brand mark, place or custom object has real references in `product/`, `brand/`,
      or `references/`.
- [ ] Every invented/stylized world or recurring character has an approved Style Master / Character Sheet.
- [ ] Zero real-world subjects are left to ungrounded text-only hallucination.
