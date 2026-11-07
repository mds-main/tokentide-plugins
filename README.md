# Tokentide plugins and agent skills

The official plugin marketplace and agent skills of [Tokentide](https://tokentide.app): Venice AI models below list
price, with a published intraday tide table, an opt-in Low Tide lane and zero data retention at Tokentide, on every
model. The same marketplace serves Claude (`.claude-plugin/marketplace.json`) and ChatGPT and Codex
(`.agents/plugins/marketplace.json`); the agent skill installs into any coding agent.

| Package                                       | What it adds                                                                                                                                                                           | Install                                                           |
| --------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| [`tokentide`](plugins/tokentide) plugin       | The Tokentide connector (live prices, Low Tide, quotes, estimates, models, balance, usage and paid calls under your caps) and the viral product video skill                            | [Claude, ChatGPT and Codex](#install-the-plugin)                  |
| [`tokentide-api`](skills/tokentide-api) skill | Everything a coding agent needs to set up, build on and optimize the Tokentide API: account and key setup, model choice, cost control, reliability, errors, security and the EU AI Act | `npx skills add mds-main/tokentide-plugins --skill tokentide-api` |

## Agent skill for any coding agent

The `tokentide-api` skill teaches Claude Code, Codex, Cursor, GitHub Copilot, Gemini CLI and other agents that read
[Agent Skills](https://agentskills.io) how to use the Tokentide API well:

- **Setup:** walks you through creating an account, an API key and adding credit, then checks it. You store the key
  in `TOKENTIDE_API_KEY` yourself; the agent never asks you to paste it.
- **Building:** the first call with the OpenAI SDKs, every endpoint and header, streaming, images, audio, video and
  music, embeddings and decision models.
- **Optimizing:** the right model for each task, an automatic task router, output limits, caching, Low Tide and the
  tide table, price and spend caps, and cost per task.
- **Running in production:** a fallback provider for sold-out days, retries, idempotency, every error code, security,
  privacy levels and EU AI Act transparency (general information, not legal advice).

Install it with the [skills CLI](https://skills.sh):

```text
npx skills add mds-main/tokentide-plugins --skill tokentide-api
```

Add `-g` to install it for your user instead of the current project, and `-a claude-code` (or `codex`, `cursor`,
`github-copilot`, `gemini-cli`, …) to choose the agent. Its helper script, `scripts/tokentide.py`, only makes free,
read-only calls to the Tokentide API and never prints your key.

Already using the plugin? Keep it: the plugin brings the connector and the video skill, and the agent skill adds what
you need to build on the API in your own code. They work side by side.

## Install the plugin

Claude Code:

```text
/plugin marketplace add mds-main/tokentide-plugins
/plugin install tokentide@tokentide
```

Claude apps (claude.ai, desktop, Cowork): **Customize > Plugins > Add marketplace**, enter
`mds-main/tokentide-plugins`, then install **Tokentide**.

Codex CLI:

```text
codex plugin marketplace add mds-main/tokentide-plugins
codex plugin add tokentide@tokentide
codex mcp login tokentide
```

ChatGPT desktop app and Codex: once the marketplace is added, open **Plugins** (or `/plugins` in Codex
CLI), choose the `tokentide` marketplace and install **Tokentide**.

Only want the connector? Add `https://api.tokentide.app/mcp` as a custom connector (Claude:
**Customize > Connectors**; ChatGPT: **Plugins > Add custom MCP server**). The plugin itself connects to
`https://api.tokentide.app/mcp/studio`, which adds image, video and music tools.

After installing, you sign in to Tokentide once. The video skill links its scripts to that connection
and sets up FFmpeg on its own; there is no second key to create or paste.

Step-by-step instructions: https://tokentide.app/claude (Claude) and https://tokentide.app/chatgpt
(ChatGPT and Codex).

## Updates

This repository is published from the Tokentide monorepo, where the connector, the plugin and the agent
skill are kept aligned with the API on every change, so changes made here directly are overwritten. Please report problems and
suggestions as issues.

## License

Proprietary: the plugin may be installed and used only with the Tokentide service, under the Tokentide Terms. The
bundled fonts keep their SIL Open Font License 1.1, and the Tokentide name and logo are not licensed. See
[LICENSE](LICENSE).
