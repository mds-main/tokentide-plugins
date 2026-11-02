# Tokentide plugins for Claude

The official Claude plugin marketplace of [Tokentide](https://tokentide.app): Venice AI models
below list price, with a published intraday tide table, an opt-in Low Tide lane and zero data retention
on Private models.

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

Only want the connector? Add `https://api.tokentide.app/mcp` as a custom connector under
**Customize > Connectors**.

Step-by-step instructions: https://tokentide.app/claude

## Updates

This repository is published from the Tokentide monorepo, where the connector and the plugin are kept
aligned with the API on every change, so changes made here directly are overwritten. Please report problems and
suggestions as issues.

## License

Proprietary: the plugin may be installed and used only with the Tokentide service, under the Tokentide Terms. The
bundled fonts keep their SIL Open Font License 1.1, and the Tokentide name and logo are not licensed. See
[LICENSE](LICENSE).
