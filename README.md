# Tokentide plugins for Claude, ChatGPT and Codex

The official plugin marketplace of [Tokentide](https://tokentide.app): Venice AI models below list
price, with a published intraday tide table, an opt-in Low Tide lane and zero data retention at
Tokentide, on every model. The same marketplace serves Claude (`.claude-plugin/marketplace.json`) and
ChatGPT and Codex (`.agents/plugins/marketplace.json`).

| Plugin                           | What it adds                                                                                                                                                |
| -------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`tokentide`](plugins/tokentide) | The Tokentide connector (live prices, Low Tide, quotes, estimates, models, balance, usage and paid calls under your caps) and the viral product video skill |

## Install

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

This repository is published from the Tokentide monorepo, where the connector and the plugin are kept
aligned with the API on every change, so changes made here directly are overwritten. Please report problems and
suggestions as issues.

## License

Proprietary: the plugin may be installed and used only with the Tokentide service, under the Tokentide Terms. The
bundled fonts keep their SIL Open Font License 1.1, and the Tokentide name and logo are not licensed. See
[LICENSE](LICENSE).
