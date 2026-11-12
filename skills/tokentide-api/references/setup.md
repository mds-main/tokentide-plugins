# Set up Tokentide: account, API key and credit

The one-time setup a person does in a browser (account, API key, credit), what each setting means, how to store the
key so code can use it, and how to verify everything works. Open this file when the user has no key yet, when a
setup check fails, or before taking an integration to production.

## Contents

- [Who does what](#who-does-what)
- [1. Create an account](#1-create-an-account)
- [2. Create an API key](#2-create-an-api-key)
- [3. Add credit](#3-add-credit)
- [4. Store the key where your code can read it](#4-store-the-key-where-your-code-can-read-it)
- [5. Verify the setup](#5-verify-the-setup)
- [6. Make the account production-ready](#6-make-the-account-production-ready)
- [Troubleshooting](#troubleshooting)
- [Using this skill with the Tokentide plugin](#using-this-skill-with-the-tokentide-plugin)

## Who does what

| Step                              | Who        | Why                                                                         |
| --------------------------------- | ---------- | --------------------------------------------------------------------------- |
| Create the account, verify email  | The user   | Needs their email inbox and acceptance of the Terms                         |
| Create the API key                | The user   | The key is shown once, in the dashboard                                     |
| Add credit                        | The user   | Payment happens on Stripe's page (or from the user's own wallet)            |
| Store the key in the environment  | The user   | Keys must never pass through the chat                                       |
| Write the code, verify, optimize  | You        | Everything after the key exists                                             |

Guide the user through the steps with the links below, in their language, one step at a time. **Never ask the user to
paste their key into the conversation**, never print it, never write it into a file you show or commit. Ask them to
set `TOKENTIDE_API_KEY` themselves, then check it with `scripts/tokentide.py check` (it never prints the key).

## 1. Create an account

1. Open https://tokentide.app/sign-up.
2. Sign up with an email address and a password (at least 12 characters; it is checked against known data breaches),
   or choose **Sign up without a password** to get an email sign-up link. If the page offers it, a crypto wallet works
   too (Sign-In-With-X).
3. Accept the Terms of Service and the Privacy Policy, then select **Create account**.
4. Open the verification email and follow the link (it expires after a short while; check the spam or promotions
   folder, or ask for a new link). The link should be opened in the same browser.
5. Recommended: add a **passkey** (Face ID, Touch ID, Windows Hello, a phone or a security key) when the dashboard
   offers it. A passkey or two-factor authentication is required later to save a card and turn on auto top-up, and
   when trial credit is offered, claiming it needs a verified email and an established GitHub account.

Or sign up with **GitHub** where the sign-up page offers it (accept the Terms first): GitHub's verified email address
is used, and the account signs in with GitHub from then on. An existing account connects GitHub under Settings →
Security, never by a matching email address.

Sign-ups are checked automatically before the account is created. If the page says the account could not be created,
nothing was saved: the user can select **Request a review** on that page, and a person answers by email. Retrying with
other addresses does not help and is not a workaround to suggest. Disposable (throwaway) mailboxes are not accepted,
and a sign-up whose email is not confirmed within 24 hours is deleted (the user simply signs up again).

Notes:

- **Limited beta.** While Tokentide is in its limited beta, sign-ups can be paused (only pre-approved addresses can
  sign up then), each account can hold one API key, and spend is limited per UTC day. The sign-up page and the
  dashboard show the current limits.
- **Trust tiers.** New accounts start in tier `new`; limits (top-up size, rate limits) grow with the tier. See
  https://tokentide.app/docs/rate-limits#limits-by-trust-tier.

## 2. Create an API key

Fastest path: the dashboard's **Get started** page, https://tokentide.app/app/onboarding, walks through creating a
key, copying a ready-made snippet, making a first request (the page shows it the moment it arrives) and adding credit.
Before the account has credit, model calls answer `402 insufficient_balance`; the free `GET /v1/account` checks the
key and the base URL in the meantime.

Or create a key under **API keys**, https://tokentide.app/app/keys:

1. Create a key and name it after the app and environment that will use it, for example `support-bot-prod`.
2. **Copy it immediately.** The full key (`tt_live_…`) is shown **once**; afterwards the dashboard shows only its
   prefix and last four characters. Lost it? Rotate or create a new key.
3. Review its settings under **Edit settings** (all can be changed later):

| Setting             | Default    | What to choose                                                                                                     |
| ------------------- | ---------- | ------------------------------------------------------------------------------------------------------------------ |
| Privacy mode        | `private`  | `private`: Private, TEE and E2EE models only. `private_text`: text, embedding and decision models stay Private, TEE or E2EE; image, video and audio models may be Anonymized. `all`: every model, including Anonymized ones (Claude, GPT, Gemini…). Choose the narrowest mode the app needs |
| Default lane        | `standard` | `lowtide` for a key used only by batch jobs that can wait (non-streaming)                                         |
| Max multiplier      | none       | The highest fraction of the Venice list price this key will pay                                                    |
| Spend caps          | none       | Daily, weekly and monthly caps for this key; `0` pauses the key without revoking it                                |
| IP allowlist        | none       | Addresses or CIDR ranges the key works from (others get `403 ip_not_allowed`), for servers with fixed addresses   |
| Requests per minute | account's  | A lower limit for keys that need little                                                                             |
| Expiry              | none       | A date the key stops working (up to 3 years ahead), for contractors, demos and short projects                     |

Key kinds: `tt_live_…` keys work on production (`https://api.tokentide.app`). `tt_test_…` keys work only on preview
and staging deployments, which answer from a deterministic mock instead of real models. Keys from Venice or other
providers are never accepted.

## 3. Add credit

Tokentide is prepaid: credit in US dollars, and each request is paid from it at the price locked when it starts. No
subscription, no monthly bill. Paid credit never expires, and unused paid credit can be refunded within 30 days of a
top-up (EU consumers can also withdraw within 14 days).

Open **Billing**, https://tokentide.app/app/billing:

| Method           | Amount                                                                                       | Notes                                                                                                                              |
| ---------------- | -------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| Card (Stripe)    | Packs of $10, $25, $50, $100, $250 or a custom amount; at least $10                          | Stripe Checkout: cards, Link, Apple Pay, Google Pay, 3-D Secure when the bank asks. Credit arrives within seconds; tax is added for where you live; Stripe emails the receipt and invoice |
| USDC, if offered | $5 to $10,000, plus 2% in promotional credit                                                 | On Base, through the x402 protocol: from Billing with a wallet, or `POST /v1/x402/top-up` from code. See https://tokentide.app/docs/x402 |

Limits for new accounts: at most $1,000 per card top-up (more in higher tiers), at most $50 by card in any 24 hours,
from at most 2 cards, and no saved card or auto top-up until the account is at least 7 days old **and** has added $100
by card. Businesses can add a tax ID at checkout (reverse charge where the law provides for it).

When offered, trial credit is claimed on the Get started page. An automatic check runs first, so the credit appears
in the balance a minute or two later; one trial per person or organization. Only an established GitHub account (old
enough, a personal account, used for no other trial) earns it: sign up with GitHub, or connect it on the Get started
page; a passkey alone earns none. Accounts on free use (`free_use: true`
in `GET /v1/account`) are not charged and need no credit.

### Keep the balance topped up (once eligible)

**Auto top-up** charges a saved card when the spendable balance drops below a threshold: Billing → **Card and auto
top-up**. Threshold $1 to $1,000, amount $10 to $1,000 (at least the threshold), optional monthly maximum, at most 10
automatic top-ups per UTC day. It needs a passkey or two-factor authentication, an account past the new-account
period and a recent confirmation. Details: https://tokentide.app/docs/billing#auto-top-up.

### Limits and alerts

- **Account caps:** Billing → **Budgets and alerts** (daily, weekly, monthly; all keys together), with a cap warning
  at 50, 75, 80 (default) or 90%.
- **Key caps:** API keys → **Edit settings** → **Spending limits**.
- **Notifications:** Settings → Notifications (https://tokentide.app/app/settings): low-balance alert ($5 by default),
  a price alert when the Standard multiplier reaches a level, and a weekly report.

Alerts only inform; caps and the balance block requests (`402 spend_limit_reached`, `402 insufficient_balance`).

## 4. Store the key where your code can read it

Every example in this skill reads the key from the environment variable `TOKENTIDE_API_KEY`.

| Where the code runs                     | How the user stores the key                                                                       |
| --------------------------------------- | ------------------------------------------------------------------------------------------------- |
| Local development                       | A `.env` file listed in `.gitignore` (loaded by the framework or `python-dotenv`), or the OS keychain |
| macOS / Linux terminal                  | `export TOKENTIDE_API_KEY="tt_live_…"` in the current shell or the shell profile                 |
| Windows PowerShell                      | `$env:TOKENTIDE_API_KEY = "tt_live_…"` (or `setx TOKENTIDE_API_KEY "tt_live_…"` for new shells)  |
| Servers, CI, serverless, containers     | The platform's secret store (environment secrets, a secrets manager, Kubernetes or Docker secrets) |

Rules:

- Use the key only from server-side code, only in the `Authorization: Bearer` header. Never in browser or mobile app
  code, URLs, query strings, logs, error messages, analytics or screenshots.
- Never commit it. Add `.env` to `.gitignore` before creating the file; enable secret scanning where available.
- To check that the key is set without revealing it: `python3 scripts/tokentide.py check`, or
  `test -n "$TOKENTIDE_API_KEY" && echo set`. Never `echo` the variable, `cat` a `.env` file, or print it in code.
- Give each app and environment its own key (one key during the limited beta), so one can be revoked alone.

## 5. Verify the setup

Run the bundled helper (Python 3.8+, no dependencies, only free read-only calls):

```sh
python3 scripts/tokentide.py check
```

| Exit code | Meaning                                       | What to tell the user                                                         |
| --------- | --------------------------------------------- | ----------------------------------------------------------------------------- |
| 0         | Key valid, credit available                   | Ready                                                                         |
| 2         | `TOKENTIDE_API_KEY` is not set                | Steps 2 and 4                                                                 |
| 3         | Key rejected (revoked, mistyped, wrong kind, IP not allowed) | Check the key in the dashboard, or create a new one             |
| 4         | No credit to spend, or a cap of 0             | Step 3, or raise the cap                                                       |
| 5         | Network or API error                          | Check network access to `api.tokentide.app` and https://tokentide.app/status |

The same check with curl, then a first paid request (a fraction of a cent):

```sh
curl -s https://api.tokentide.app/v1/account -H "Authorization: Bearer $TOKENTIDE_API_KEY"

curl -s https://api.tokentide.app/v1/chat/completions \
  -H "Authorization: Bearer $TOKENTIDE_API_KEY" -H "Content-Type: application/json" \
  -d '{"model": "zai-org-glm-5-2", "max_completion_tokens": 50,
       "messages": [{"role": "user", "content": "Say hello in five words."}]}'
```

The model id is an example: list the models the key may call with `python3 scripts/tokentide.py models` (or
`GET /v1/models`). A successful response carries `X-Tokentide-Charge-USD`, what the request cost.

## 6. Make the account production-ready

- [ ] Passkey or two-factor authentication on the account.
- [ ] One key per app and environment, each with the narrowest privacy mode, an IP allowlist where addresses are
      fixed, and a daily cap.
- [ ] An account-wide monthly cap as the budget, plus a cap warning.
- [ ] Auto top-up with a monthly maximum (once eligible), and the low-balance alert.
- [ ] A rotation plan: Rotate creates a new key with the same settings, and the old one keeps working for the overlap
      you choose (none, 1 hour, 24 hours or 7 days). Suspect a leak? Rotate with no overlap.
- [ ] A fallback provider for sold-out days (see `reliability.md`).

## Troubleshooting

| Symptom                                           | Cause                                                                | Fix                                                                                          |
| ------------------------------------------------- | -------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| "Sign-ups are paused"                             | Limited beta                                                         | Try again later, or use a pre-approved address                                               |
| No verification email                             | Spam folder, typo, expired link                                      | Check spam, or send a new link from the sign-up page                                         |
| `401 invalid_api_key`                             | Mistyped, revoked or expired key; `tt_test_` key on production; a Venice key | Copy the key again or create a new one                                               |
| `403 ip_not_allowed`                              | The key's IP allowlist doesn't include this machine                  | Add the address in the key settings, or use another key                                     |
| `403 model_not_allowed`                           | The key's privacy mode doesn't allow that model                      | Pick a model from `GET /v1/models`, or change the privacy mode deliberately                  |
| `403 account_restricted`                          | The account is restricted                                            | Check the dashboard, contact support                                                         |
| `402 insufficient_balance`                        | Not enough spendable credit for the request's worst case             | Add credit; lower `max_completion_tokens`                                                    |
| `402 spend_limit_reached`                         | A key or account cap is reached                                      | Wait for the reset in `Retry-After`, or raise the cap                                        |
| `503 capacity_unavailable`                        | Today's discounted supply is sold out (or too little is left for this request) | Wait for `Retry-After` (the 00:00 UTC reset when sold out), or use a fallback provider |
| Card top-up refused above $50                     | New-account card limit                                               | Wait 24 hours, or use USDC where offered                                                    |
| Can't turn on auto top-up                         | Account too new, no passkey or two-factor, no recent confirmation    | Billing shows what is missing                                                               |
| Connection errors from a sandbox                  | The sandbox blocks `api.tokentide.app`                               | Allow the host in the sandbox's network settings                                            |

## Using this skill with the Tokentide plugin

Tokentide also offers a plugin for Claude, ChatGPT and Codex (marketplace `mds-main/tokentide-plugins`) with a
connector and a video skill. They work side by side with this skill:

- The connector signs in once with OAuth and creates its own key for its tools; it doesn't use
  `TOKENTIDE_API_KEY`. When its tools are available (`get_market`, `estimate_cost`, `get_account`, `explain_pricing`
  and others), they are a quick way to answer pricing and account questions in the conversation.
- The plugin's video skill links its own key for its scripts, but if `TOKENTIDE_API_KEY` is set in the same
  environment, its scripts use that key first. The video, music and edit models are mostly Anonymized, so that key
  then needs privacy mode `private_text` or `all`.
- This skill covers building with the API in code; the video skill covers short-form social videos end to end.

## Further reading

- Quickstart: https://tokentide.app/docs/quickstart
- Billing, auto top-up, limits and alerts: https://tokentide.app/docs/billing
- Privacy modes and zero data retention: https://tokentide.app/docs/privacy
- Keys and least privilege: https://tokentide.app/docs/security
- USDC top-ups and wallets: https://tokentide.app/docs/x402
- Connector and plugin: https://tokentide.app/docs/mcp
