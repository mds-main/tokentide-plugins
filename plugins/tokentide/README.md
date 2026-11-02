# Tokentide for Claude, ChatGPT and Codex

Tokentide sells access to Venice AI models below list price, with prices that fall through the day (the
tide table) and an opt-in Low Tide lane that is cheaper still. This plugin connects Claude, ChatGPT or
Codex to your Tokentide account and adds a skill that turns a product into short-form videos.

## What's inside

- **Tokentide connector** (`https://api.tokentide.app/mcp`). Your agent can explain how Tokentide
  pricing works (tide prices, Low Tide, quotes, the daily reset, job cutoffs), read the live market,
  estimate and quote costs before you spend, browse the model catalog, show your balance, caps and
  usage, and run chat, embeddings and decision requests under your own price caps.
- **Viral product video skill** (`skills/viral-product-video`). Your agent researches a product, writes
  a virality strategy, then plans, generates, edits, checks and packages vertical videos for TikTok,
  Instagram Reels and X with Tokentide's image, video, voice and music models and FFmpeg.

One package serves every host: `.claude-plugin/plugin.json` and `.mcp.json` describe it to Claude;
`plugin.json` and `mcp.json` (the portable Agent Plugins format, with OpenAI's listing and sign-in
settings) describe it to ChatGPT and Codex. The skill is shared.

## Use it

1. Install the plugin from the Tokentide marketplace, `mds-main/tokentide-plugins`.

   Claude Code:

   ```text
   /plugin marketplace add mds-main/tokentide-plugins
   /plugin install tokentide@tokentide
   ```

   In the Claude apps, open **Customize > Plugins**, add the marketplace and install **Tokentide**.
   Full instructions: https://tokentide.app/claude

   Codex CLI:

   ```text
   codex plugin marketplace add mds-main/tokentide-plugins
   codex plugin add tokentide@tokentide
   ```

   Or open `/plugins` in Codex, or **Plugins** in the ChatGPT desktop app, and install **Tokentide** from
   the `tokentide` marketplace. Full instructions: https://tokentide.app/chatgpt

2. Connect the connector. Your app opens a Tokentide sign-in page (in Codex CLI, run
   `codex mcp login tokentide`); you choose a daily spending cap and a privacy mode, and Tokentide
   creates an API key just for this connection. Revoke it any time under **Dashboard > API keys**.
3. Ask, for example: "How does Tokentide pricing work?", "When is the cheapest time today to run 2
   million tokens on the best coding model?", "What did I spend this week?", or "Make our new water
   bottle go viral on TikTok, Reels and X".

The video skill runs Python scripts in your agent's code environment, so it needs code execution,
network access to `api.tokentide.app`, FFmpeg, and an API key in `TOKENTIDE_API_KEY` that you set
yourself (privacy mode `all` or `private_text`, for the anonymized edit, video and music models). The
skill never asks you to paste the key into the chat. Its README lists every requirement.

## What data it sends

- **Connector:** each tool call sends its arguments (for example a prompt you ask your agent to run, or
  the filters of a usage report) to Tokentide's API over HTTPS, authenticated with the connection's key.
  Model requests go on to Venice and, for anonymized models, to the model's provider.
- **Video skill:** the scripts send prompts, product photos, keyframes, voice-over text and audio to
  Tokentide's API with your key, and your agent's web search gathers public information about the
  product. Generated files stay in your project folder.
- Tokentide never stores prompts, inputs or outputs; it keeps account data, request metadata and the
  billing ledger. On Private models, Venice retains nothing either. Anonymized models' providers may
  retain content under their own policies, without your identity. See
  https://tokentide.app/docs/privacy and https://tokentide.app/legal/privacy

## License

Proprietary: install and use the plugin only with the Tokentide service, under the Tokentide Terms. The bundled
fonts keep their SIL Open Font License 1.1, and the Tokentide name and logo are not licensed. See [LICENSE](LICENSE).

## Support

Email support@tokentide.app or open an issue in https://github.com/mds-main/tokentide-plugins.
Tokentide is an independent service, not affiliated with Venice.ai, Anthropic or OpenAI.
