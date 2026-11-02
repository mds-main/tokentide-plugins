# viral-product-video — Claude skill (Tokentide plugin)

Researches a product or brand in depth, builds a virality strategy, and produces finished vertical
videos for TikTok, Instagram Reels and X through the Tokentide API (a discounted, Venice-compatible
proxy) + FFmpeg. Claude reads `SKILL.md`; this README is for humans.

## Install
This skill ships in the `tokentide` plugin, together with the Tokentide connector. Install the plugin
from the Tokentide marketplace (`mds-main/tokentide-plugins`); step-by-step instructions for Claude Code
and the Claude apps are at https://tokentide.app/claude. Skills need code execution enabled.

## Requirements
- A Tokentide key (`tt_live_…`) created with **privacy mode `all`** (or `private_text`) — the default
  `private` mode hides background removal, most premium edit and video models (needed for
  product-accurate keyframes and clips) and all music models. Set `TOKENTIDE_API_KEY` (or
  `TOKENTIDE_API_KEY_FILE`). Never commit or share the key.
- Host: production `https://api.tokentide.app/v1` (default) · any other (e.g. a preview
  deployment): `TOKENTIDE_BASE_URL`. `tt_test_` keys only work on preview/staging.
- Network access to that host from the code sandbox (in the Claude apps, allow the domain; on
  Team/Enterprise plans owners control network access in Admin settings → Capabilities).
- Python 3.8+ and ffmpeg with libass (`python3 scripts/doctor.py` checks everything, incl. account limits).

## Quick start
```bash
python3 scripts/selftest.py                    # whole pipeline against a Tokentide-shaped mock: no key, no cost
python3 scripts/init_project.py "My Product" --budget-usd 50
python3 scripts/doctor.py --project projects/my-product
python3 scripts/models.py recommend --project projects/my-product   # live options with Tokentide prices
```
Then ask Claude, e.g. "Make our new insulated bottle go viral on TikTok, Reels and X — use Tokentide".

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
