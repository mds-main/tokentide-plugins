# professional-video — agent skill (Tokentide plugin)

Universal studio-grade video production skill for any kind of video (`16:9`, `9:16` or `1:1`) — films,
personal stories, app and website video guides, tutorials, commercials, explainers, trailers and social
campaigns for YouTube, TikTok, Instagram Reels, X, LinkedIn or direct delivery — through the Tokentide
API (a Venice-compatible API) + FFmpeg. Grounds every visual anchor first (gathering real reference
photos, capturing live workflows via browser/computer use with login handoff on gated apps, or locking
style sheets) so finished videos stay faithful and non-hallucinated. The agent (Claude, ChatGPT, Codex
or Antigravity) reads `SKILL.md`; `agents/openai.yaml` holds its display name and connector dependency
for ChatGPT and Codex; this README is for humans.

## Install
This skill ships in the `tokentide` plugin, together with the Tokentide connector. Install the plugin
from the Tokentide marketplace (`mds-main/tokentide-plugins`); step-by-step instructions are at
https://tokentide.app/claude (Claude Code and the Claude apps) and https://tokentide.app/chatgpt
(ChatGPT and Codex).

## Sign in once
You sign in to Tokentide once, when the connector asks (keep privacy mode **`all`**, preselected, or pick
`private_text`, and set a daily spending limit). That is the only step for you. The agent does the rest:
- It links the skill's scripts to your connection: the connector's `link_local_scripts` tool gives it a
  one-time code, and `scripts/auth.py exchange --code …` swaps it for the scripts' own key, stored in
  your config folder (`~/.config/tokentide/api_key`, Windows `%APPDATA%\tokentide\api_key`) readable by
  you only. You never create, copy or paste a key. The key shows up in your dashboard as "Local scripts
  (plugin)" under the connection, with the same privacy mode and caps; revoking the connection revokes it.
- Without the connector, `scripts/auth.py login` asks you to approve once on tokentide.app instead.
- `scripts/doctor.py --fix` checks everything and, if FFmpeg is missing or lacks a needed filter, installs
  a pinned, checksum-verified build (libass, freetype, fontconfig, libx264) for the plugin, without admin
  rights.

A key in privacy mode `private` hides background removal, most premium edit and video models and all
music models; with it, the skill can only use Private models. New keys default to `all`.

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
python3 scripts/models.py match "Kling 3 Pro" "nano banana 2.1" --project projects/my-product  # your own models
python3 scripts/models.py tiers --project projects/my-product --videos 3   # or levels
python3 scripts/models.py choose --project projects/my-product --tier pro
python3 scripts/models.py cost --project projects/my-product --videos 3   # the total: a quote or an estimate
```
Then ask your agent, e.g. "Create a 90-second 16:9 walkthrough video for my app with real screenshots, natural voice-over and original music — use Tokentide".

## Choosing models & up-front quote
By default, every new request proposes the **Pro** tier — **Seedance 2.5 Flash**
(`seedance-2-5-flash-image-to-video-basic`) for video and **ElevenLabs TTS v4 Turbo**
(`elevenlabs-tts-v4-turbo`) for voice-overs, paired with live Pro-level image and music models from
Tokentide — unless you explicitly specify different models or pick another level from the **Essential /
Pro / Max** tiers (`models.py tiers`, Arena leaderboard ratings for video/images under CC BY 4.0 and skill
estimates for voice/music). Before any paid generation starts, `models.py cost` always presents the full
itemized estimated quote for the whole video (video clips, images/keyframes, voice-over, music and SFX).
Details: `references/models.md`.

## Tokentide-specific behaviour
- Prices = Venice list × the tide multiplier (cheapest late in the UTC day); `--lane lowtide` for
  cheaper best-effort generation; exact charges are logged per request (`budget.py --live`).
- Inputs are shrunk to fit the 4.5 MB request limit; video inputs (upscale, video-to-video) need public URLs.
- Image requests are paced to the account limit (4/min on new accounts); ≤ 6 video jobs in flight.
- Video queue closes ~23:14 UTC until the 00:00 UTC reset (music ~23:39 UTC).
- Original music and sound effects via Tokentide's queued audio jobs (`audio.py music|sfx`).
- Voice models on the queued audio route (e.g. ElevenLabs TTS v4 Turbo) are supported by `audio.py tts`. The skill
  never picks ElevenLabs TTS v4 by default; it uses v4 Turbo instead.
- Not available through Tokentide: voice cloning.
- Full details and the gap list: `references/tokentide-api.md`.

## Notes
- Tokentide's terms (draft, 1 Nov 2026) grant output ownership subject to upstream terms; Venice's
  public terms limit their licence to personal, non-commercial use — get written commercial terms
  before publishing brand content.
- Label AI content, never present AI people as real customers, and substantiate every claim.
