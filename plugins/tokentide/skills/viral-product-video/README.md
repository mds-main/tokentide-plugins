# viral-product-video — agent skill (Tokentide plugin)

Researches a product or brand in depth, builds a virality strategy, and produces finished vertical
videos for TikTok, Instagram Reels and X through the Tokentide API (a Venice-compatible API) + FFmpeg.
The agent (Claude, ChatGPT or Codex) reads `SKILL.md`; `agents/openai.yaml` holds its display name and
connector dependency for ChatGPT and Codex; this README is for humans.

## Install
This skill ships in the `tokentide` plugin, together with the Tokentide connector. Install the plugin
from the Tokentide marketplace (`mds-main/tokentide-plugins`); step-by-step instructions are at
https://tokentide.app/claude (Claude Code and the Claude apps) and https://tokentide.app/chatgpt
(ChatGPT and Codex).

## Sign in once
You sign in to Tokentide once, when the connector asks (pick privacy mode **`all`**, or `private_text`,
and a daily spending limit). That is the only step for you. The agent does the rest:
- It links the skill's scripts to your connection: the connector's `link_local_scripts` tool gives it a
  one-time code, and `scripts/auth.py exchange --code …` swaps it for the scripts' own key, stored in
  your config folder (`~/.config/tokentide/api_key`, Windows `%APPDATA%\tokentide\api_key`) readable by
  you only. You never create, copy or paste a key. The key shows up in your dashboard as "Local scripts
  (plugin)" under the connection, with the same privacy mode and caps; revoking the connection revokes it.
- Without the connector, `scripts/auth.py login` asks you to approve once on tokentide.app instead.
- `scripts/doctor.py --fix` checks everything and, if FFmpeg is missing or lacks a needed filter, installs
  a pinned, checksum-verified build (libass, freetype, fontconfig, libx264) for the plugin, without admin
  rights.

The default `private` privacy mode hides background removal, most premium edit and video models and all
music models; with it, the skill can only use Private models.

## Requirements
- For the full pipeline: a shell with Python 3.8+ and network access to `api.tokentide.app` (Claude Code
  and Codex on your computer, or a Claude/ChatGPT code environment that allows the domain; on
  Team/Enterprise plans owners control network access in the admin settings).
- Without a shell (ChatGPT, claude.ai), the connector's image, video and music tools cover model choice,
  quotes, keyframes, clips and music; editing, captions and the final mix need a shell.
- Host: production `https://api.tokentide.app/v1` (default) · any other (e.g. a preview
  deployment): `TOKENTIDE_BASE_URL`. `tt_test_` keys only work on preview/staging. An existing key in
  `TOKENTIDE_API_KEY` still works and takes precedence over the linked one.

## Quick start (what the agent runs)
```bash
python3 scripts/selftest.py                    # whole pipeline + sign-in flow against a mock: no key, no cost
python3 scripts/doctor.py --fix                # checks; installs FFmpeg for the plugin if needed
python3 scripts/auth.py exchange --code ttlink_…   # with the code from the connector's link_local_scripts
python3 scripts/init_project.py "My Product" --budget-usd 50
python3 scripts/models.py recommend --project projects/my-product   # live options with Tokentide prices
```
Then ask your agent, e.g. "Make our new insulated bottle go viral on TikTok, Reels and X — use Tokentide".

## Tokentide-specific behaviour
- Prices = Venice list × the tide multiplier (cheapest late in the UTC day); `--lane lowtide` for
  cheaper best-effort generation; exact charges are logged per request (`budget.py --live`).
- Inputs are shrunk to fit the 4.5 MB request limit; video inputs (upscale, video-to-video) need public URLs.
- Image requests are paced to the account limit (2/min on new accounts); ≤ 6 video jobs in flight.
- Video queue closes ~23:14 UTC until the 00:00 UTC reset (music ~23:39 UTC).
- Original music and sound effects via Tokentide's queued audio jobs (`audio.py music|sfx`).
- Not available through Tokentide: voice cloning.
- Full details and the gap list: `references/tokentide-api.md`.

## Notes
- Tokentide's terms (draft, 1 Nov 2026) grant output ownership subject to upstream terms; Venice's
  public terms limit their licence to personal, non-commercial use — get written commercial terms
  before publishing brand content.
- Label AI content, never present AI people as real customers, and substantiate every claim.
