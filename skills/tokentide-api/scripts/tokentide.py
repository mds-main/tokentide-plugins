#!/usr/bin/env python3
"""Read-only helper for the Tokentide API (https://tokentide.app/docs).

Checks a setup and reads prices, models, cost estimates and usage. It only sends GET requests, so it never
spends credit, and it only talks to the Tokentide API. It reads the API key from the TOKENTIDE_API_KEY
environment variable and never prints it. Python 3.8+, standard library only.

  python3 tokentide.py check                        is the key set and valid, is there credit, what are the limits
  python3 tokentide.py market                       today's prices, Low Tide, sold-out state, cheapest times left
  python3 tokentide.py models [--type text]         models this key may call, with their prices
  python3 tokentide.py estimate --model ID --input-tokens N --output-tokens N
                                                    what a request costs now, through the day and tomorrow
  python3 tokentide.py usage [--days 7]             what this key spent, by model (request metadata only)

Add --json to any command for machine-readable output. Exit codes: 0 ready, 2 no key, 3 key rejected,
4 no credit to spend, 5 network or API error, 64 bad arguments.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

VERSION = "1.0.11"
DEFAULT_BASE = "https://api.tokentide.app/v1"
USER_AGENT = "tokentide-skill/" + VERSION + " (+https://tokentide.app)"
KEY_PREFIXES = ("tt_live_", "tt_test_")
MODEL_TYPES = ("text", "image", "video", "music", "tts", "asr", "embedding", "upscale", "inpaint", "decision",
               "all", "code")
SETUP_HINT = ("Create an account at https://tokentide.app/sign-up, create a key under API keys "
              "(https://tokentide.app/app/keys), then set it in the environment as TOKENTIDE_API_KEY. "
              "See references/setup.md.")

EXIT_OK, EXIT_NO_KEY, EXIT_KEY_REJECTED, EXIT_NO_CREDIT, EXIT_API, EXIT_USAGE = 0, 2, 3, 4, 5, 64


class ApiError(Exception):
    def __init__(self, status, code, message, retry_after=None):
        Exception.__init__(self, message)
        self.status, self.code, self.message, self.retry_after = status, code, message, retry_after


def base_url():
    """The API base URL. Overrides must stay on a Tokentide host (or this machine, for tests), so the key
    can never be sent anywhere else."""
    base = (os.environ.get("TOKENTIDE_BASE_URL") or DEFAULT_BASE).rstrip("/")
    parsed = urllib.parse.urlparse(base)
    host = (parsed.hostname or "").lower()
    tokentide = parsed.scheme == "https" and (host == "tokentide.app" or host.endswith(".tokentide.app"))
    local = parsed.scheme in ("http", "https") and host in ("localhost", "127.0.0.1", "::1")
    if not (tokentide or local):
        raise SystemExit("TOKENTIDE_BASE_URL must be an https://*.tokentide.app URL (or localhost for tests).")
    return base


def api_key():
    key = (os.environ.get("TOKENTIDE_API_KEY") or "").strip()
    return key or None


def masked(key):
    prefix = next((p for p in KEY_PREFIXES if key.startswith(p)), key[:3])
    return prefix + "..." + key[-4:] if len(key) > len(prefix) + 4 else prefix + "..."


class _KeepKeyOnSameOrigin(urllib.request.HTTPRedirectHandler):
    """Follows redirects, but the key goes only to the same scheme and host: urllib would otherwise
    copy the Authorization header to wherever a redirect points."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is None:
            return None
        old, nxt = urllib.parse.urlsplit(req.full_url), urllib.parse.urlsplit(new.full_url)
        if (nxt.scheme, nxt.netloc.lower()) != (old.scheme, old.netloc.lower()):
            for name in [h for h in new.headers if h.lower() == "authorization"]:
                del new.headers[name]
        return new


def _opener():
    return urllib.request.build_opener(_KeepKeyOnSameOrigin())


def get(path, params=None, key=None, accept="application/json"):
    query = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})
    url = base_url() + path + ("?" + query if query else "")
    headers = {"Accept": accept, "User-Agent": USER_AGENT}
    if key:
        headers["Authorization"] = "Bearer " + key
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with _opener().open(request, timeout=30) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if "json" in response.headers.get("Content-Type", "") else body
    except urllib.error.HTTPError as e:
        code, message = None, e.reason
        try:
            err = json.loads(e.read().decode("utf-8")).get("error") or {}
            code, message = err.get("code"), err.get("message") or message
        except (ValueError, AttributeError):
            pass
        raise ApiError(e.code, code, str(message), e.headers.get("Retry-After"))
    except (urllib.error.URLError, OSError) as e:
        raise ApiError(None, "network_error", "Could not reach " + base_url() + ": " + str(e))


def dec(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal(0)


def usd(value):
    if value is None:
        return "none"
    return "$" + format(dec(value).quantize(Decimal("0.0001")), "f")


def pct_below_list(multiplier):
    return str(int(((1 - dec(multiplier)) * 100).quantize(Decimal("1")))) + "% below list"


def hhmm(iso):
    return iso[11:16] + " UTC" if isinstance(iso, str) and len(iso) >= 16 else str(iso)


def emit(args, data, lines):
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        print("\n".join(lines))


def fail(args, error, code=EXIT_API):
    data = {"ok": False, "status": error.status, "code": error.code, "message": error.message}
    if error.retry_after:
        data["retry_after_seconds"] = error.retry_after
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        status = "HTTP " + str(error.status) if error.status else "network"
        print("Error (" + status + ", " + str(error.code) + "): " + error.message, file=sys.stderr)
        if error.retry_after:
            print("Retry after " + str(error.retry_after) + " s.", file=sys.stderr)
    return code


def cmd_check(args):
    key = api_key()
    if not key:
        message = "TOKENTIDE_API_KEY is not set. " + SETUP_HINT
        emit(args, {"ok": False, "code": "no_key", "message": message}, [message])
        return EXIT_NO_KEY
    if not key.startswith(KEY_PREFIXES):
        message = ("TOKENTIDE_API_KEY does not look like a Tokentide key (tt_live_... or tt_test_...). "
                   "Venice keys and other providers' keys are not accepted. " + SETUP_HINT)
        emit(args, {"ok": False, "code": "invalid_api_key", "message": message}, [message])
        return EXIT_KEY_REJECTED
    try:
        account = get("/account", key=key)
    except ApiError as e:
        if e.status in (401, 403):
            hint = {
                "invalid_api_key": "The key was rejected: revoked, expired, mistyped, or a tt_test_ key used on "
                                   "production. Create a new key at https://tokentide.app/app/keys.",
                "ip_not_allowed": "This key has an IP allowlist that does not include this machine's address.",
                "account_restricted": "The account is restricted. Check the dashboard or contact support.",
            }.get(e.code or "", "")
            if hint:
                e.message = e.message + " " + hint
            return fail(args, e, EXIT_KEY_REJECTED)
        return fail(args, e)
    try:
        models = get("/models", {"type": "all"}, key=key).get("data", [])
    except (ApiError, AttributeError):
        models = []
    try:
        market = get("/market")
    except ApiError:
        market = {}

    balance, limits, lowtide = account.get("balance") or {}, account.get("limits") or {}, account.get("lowtide") or {}
    free_use = bool(account.get("free_use"))
    spendable = dec(balance.get("spendable_usd"))
    caps = {name: limits.get(name) for name in ("daily_cap_usd", "weekly_cap_usd", "monthly_cap_usd",
                                                 "account_daily_cap_usd", "account_weekly_cap_usd",
                                                 "account_monthly_cap_usd")}
    blocked = [name for name, value in caps.items() if value is not None and dec(value) == 0]
    ready = (free_use or spendable > 0) and not blocked
    types = sorted({m.get("type") for m in models if m.get("type")})
    privacy = sorted({(m.get("tokentide") or {}).get("privacy_tier") for m in models} - {None})
    data = {
        "ok": ready,
        "key": masked(key),
        "tier": account.get("tier"),
        "free_use": free_use,
        "balance": balance,
        "spend_today": account.get("spend_today"),
        "caps": caps,
        "rate_limits": {k: limits.get(k) for k in ("requests_per_minute_per_key", "concurrency",
                                                    "image_requests_per_minute", "running_requests_usd")},
        "lowtide": lowtide,
        "models_callable": len(models),
        "model_types": types,
        "privacy_tiers_allowed": privacy,
        "market": {k: market.get(k) for k in ("sold_out", "reopens_at", "sales_paused")},
    }
    lines = [
        "Key " + masked(key) + " is valid. Trust tier: " + str(account.get("tier")) + ".",
        "Spendable balance: " + usd(balance.get("spendable_usd")) + " (paid " + usd(balance.get("available_usd"))
        + ", promotional " + usd(balance.get("promo_usd")) + ")." + (" Free use: requests are not charged."
                                                                      if free_use else ""),
        "Spend caps (key day/week/month): " + ", ".join(usd(caps[n]) for n in ("daily_cap_usd", "weekly_cap_usd",
                                                                                "monthly_cap_usd"))
        + "; account: " + ", ".join(usd(caps[n]) for n in ("account_daily_cap_usd", "account_weekly_cap_usd",
                                                            "account_monthly_cap_usd")) + ".",
        "Models this key may call: " + str(len(models)) + (" (" + ", ".join(types) + ")" if types else "")
        + (". Privacy tiers: " + ", ".join(privacy) if privacy else "") + ".",
    ]
    if privacy and "anonymized" not in privacy:
        lines.append("Anonymized models (for example Claude, GPT and Gemini) need a key with privacy mode `all`.")
    if market.get("sold_out"):
        lines.append("Today's supply is sold out until " + hhmm(market.get("reopens_at")) + ": use a fallback "
                     "provider or wait for the reset.")
    if blocked:
        lines.append("A spend cap of 0 blocks all spend: " + ", ".join(blocked) + ". Change it in the dashboard.")
    if not free_use and spendable <= 0:
        lines.append("No credit to spend. Add credit at https://tokentide.app/app/billing (card from $10).")
        emit(args, data, lines)
        return EXIT_NO_CREDIT
    lines.append("Ready." if ready else "Not ready: see above.")
    emit(args, data, lines)
    return EXIT_OK if ready else EXIT_NO_CREDIT


def cheapest_slots(curve, now, count=3):
    """The lowest-priced 15-minute points of a tide table curve that are still ahead."""
    ahead = [p for p in curve or [] if isinstance(p, dict) and str(p.get("t", "")) >= now]
    return sorted(ahead, key=lambda p: (p.get("m_ppm", 10 ** 9), p.get("t")))[:count]


def cmd_market(args):
    try:
        market = get("/market")
    except ApiError as e:
        return fail(args, e)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    standard, lowtide = market.get("standard") or {}, market.get("lowtide") or {}
    epoch, tables = market.get("epoch") or {}, market.get("tide_table") or {}
    today = cheapest_slots((tables.get("today") or {}).get("curve"), now)
    tomorrow_table = tables.get("tomorrow") or {}
    tomorrow = cheapest_slots(tomorrow_table.get("curve"), now)
    data = {"market": market, "cheapest_today": today, "cheapest_tomorrow": tomorrow}
    lines = [
        "Day " + str(epoch.get("id")) + " (" + str(epoch.get("state")) + "), "
        + str(int(epoch.get("seconds_to_reset") or 0) // 60) + " min to the 00:00 UTC reset.",
        "Standard: multiplier " + str(standard.get("multiplier")) + " (" + pct_below_list(standard.get("multiplier"))
        + ").",
        "Low Tide: " + ("open" if lowtide.get("open") else "closed") + ", multiplier " + str(lowtide.get("multiplier"))
        + " (" + pct_below_list(lowtide.get("multiplier")) + ")"
        + ("" if lowtide.get("open") else ", reason " + str(lowtide.get("reason"))
           + (", forecast to open at " + hhmm(lowtide.get("opens_at")) if lowtide.get("opens_at") else ""))
        + ".",
    ]
    if market.get("sold_out"):
        lines.append("Sold out until " + hhmm(market.get("reopens_at")) + ".")
    if market.get("sales_paused"):
        lines.append("Sales are paused.")
    if today:
        lines.append("Cheapest Standard times left today: " + ", ".join(
            hhmm(p.get("t")) + " (" + str(Decimal(p.get("m_ppm", 0)) / Decimal(10 ** 6)) + ")" for p in today) + ".")
    next_epoch = market.get("next_epoch") or {}
    lines.append("Tomorrow opens at multiplier " + str(next_epoch.get("open_multiplier")) + "."
                 + (" Tomorrow's table is published." if tomorrow_table else
                    " Tomorrow's table is published at 12:00 UTC."))
    emit(args, data, lines)
    return EXIT_OK


def price_line(lane):
    if not lane:
        return "n/a"
    if lane.get("per_unit") is not None:
        return usd(lane.get("per_unit")) + "/" + str(lane.get("unit") or "unit")
    return usd(lane.get("input_per_1m")) + " in, " + usd(lane.get("output_per_1m")) + " out per 1M tokens"


def cmd_models(args):
    key = api_key()
    try:
        models = get("/models", {"type": args.type}, key=key).get("data", [])
    except ApiError as e:
        return fail(args, e)
    rows = []
    for m in models:
        tt = m.get("tokentide") or {}
        low = tt.get("lowtide") or {}
        rows.append({
            "id": m.get("id"),
            "type": m.get("type"),
            "privacy": tt.get("privacy_tier"),
            "standard": price_line(tt.get("standard")),
            "lowtide": price_line(low) if low.get("eligible") else "not eligible",
            "lowtide_open": bool(low.get("open")),
        })
    lines = ["" if key else "No TOKENTIDE_API_KEY: showing the public catalog, not filtered to a key."]
    lines += [r["id"] + "  [" + str(r["type"]) + ", " + str(r["privacy"]) + "]  Standard " + r["standard"]
              + "  |  Low Tide " + r["lowtide"] for r in rows]
    lines.append(str(len(rows)) + " model(s) of type " + args.type + ". Prices are the current ones and change "
                 "through the day.")
    emit(args, {"models": rows, "filtered_to_key": bool(key)}, [line for line in lines if line])
    return EXIT_OK


def cmd_estimate(args):
    if args.input_tokens is None and args.output_tokens is None and args.units is None:
        print("Give --input-tokens and/or --output-tokens (token-priced models) or --units.", file=sys.stderr)
        return EXIT_USAGE
    params = {"model": args.model, "input_tokens": args.input_tokens, "output_tokens": args.output_tokens,
              "units": args.units, "at": args.at}
    try:
        est = get("/market/estimate", params)
    except ApiError as e:
        return fail(args, e)
    now = est.get("now") or {}
    standard, lowtide = now.get("standard") or {}, now.get("lowtide") or {}
    schedule = [s for s in est.get("schedule") or [] if isinstance(s, dict)]
    best = min(schedule, key=lambda s: dec(s.get("standard_charge_usd"))) if schedule else None
    tomorrow = est.get("tomorrow_open") or {}
    lines = [
        "Model " + str((est.get("model") or {}).get("id")) + ": list price " + usd(est.get("list_cost_usd")) + ".",
        "Now on Standard: " + usd(standard.get("charge_usd")) + " (multiplier " + str(standard.get("multiplier"))
        + ").",
        "Now on Low Tide: " + (usd(lowtide.get("charge_usd")) + " (multiplier " + str(lowtide.get("multiplier"))
                               + ")" if lowtide.get("open") else "closed"
                               + (", forecast to open at " + hhmm(lowtide.get("opens_at"))
                                  if lowtide.get("opens_at") else "")) + ".",
    ]
    if best:
        lines.append("Cheapest Standard hour left today: " + hhmm(best.get("at")) + " at "
                     + usd(best.get("standard_charge_usd")) + ".")
    last = est.get("last_same_day") or {}
    if last.get("standard"):
        lines.append("Last moment still priced as today (the day's lowest table price): " + hhmm(last.get("at"))
                     + " at " + usd(last["standard"].get("charge_usd")) + ".")
    if tomorrow:
        lines.append("At tomorrow's opening: " + usd((tomorrow.get("standard") or tomorrow).get("charge_usd")) + ".")
    for note in est.get("notes") or []:
        lines.append("Note: " + str(note))
    emit(args, est, lines)
    return EXIT_OK


def cmd_usage(args):
    key = api_key()
    if not key:
        message = "TOKENTIDE_API_KEY is not set. " + SETUP_HINT
        emit(args, {"ok": False, "code": "no_key", "message": message}, [message])
        return EXIT_NO_KEY
    since = (datetime.now(timezone.utc) - timedelta(days=args.days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    totals, before, pages, rows = {}, None, 0, 0
    try:
        while pages < args.max_pages:
            page = get("/account/usage", {"limit": 1000, "from": since, "before": before, "model": args.model},
                       key=key)
            for r in page.get("data") or []:
                t = totals.setdefault(r.get("model_id") or "unknown", {"requests": 0, "errors": 0, "charge_micros": 0,
                                                                       "list_cost_micros": 0})
                t["requests"] += 1
                t["errors"] += 1 if int(r.get("status_code") or 200) >= 400 else 0
                t["charge_micros"] += int(r.get("charge_micros") or 0)
                t["list_cost_micros"] += int(r.get("list_cost_micros") or 0)
                rows += 1
            pages += 1
            if not page.get("has_more"):
                break
            before = page.get("next_before")
    except ApiError as e:
        return fail(args, e, EXIT_KEY_REJECTED if e.status == 401 else EXIT_API)
    paid = sum(t["charge_micros"] for t in totals.values())
    listed = sum(t["list_cost_micros"] for t in totals.values())
    lines = ["Last " + str(args.days) + " day(s), this key: " + str(rows) + " request(s), paid "
             + usd(Decimal(paid) / 10 ** 6) + ", list price " + usd(Decimal(listed) / 10 ** 6) + "."]
    for model, t in sorted(totals.items(), key=lambda kv: -kv[1]["charge_micros"]):
        lines.append("  " + model + ": " + str(t["requests"]) + " requests (" + str(t["errors"]) + " errors), paid "
                     + usd(Decimal(t["charge_micros"]) / 10 ** 6))
    if pages >= args.max_pages:
        lines.append("Stopped after " + str(pages) + " page(s); raise --max-pages for more.")
    emit(args, {"since": since, "requests": rows, "paid_micros": paid, "list_cost_micros": listed,
                "by_model": totals}, lines)
    return EXIT_OK


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only helper for the Tokentide API (never spends credit).")
    parser.add_argument("--version", action="version", version="%(prog)s " + VERSION)
    sub = parser.add_subparsers(dest="command")
    for name, help_text in (("check", "check the key, credit and limits"), ("market", "today's prices and Low Tide"),
                            ("models", "models this key may call, with prices"),
                            ("estimate", "what a request costs now and later today"),
                            ("usage", "what this key spent, by model")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--json", action="store_true", help="machine-readable output")
        if name == "models":
            p.add_argument("--type", default="text", choices=MODEL_TYPES, help="model type (default: text)")
        if name == "estimate":
            p.add_argument("--model", required=True, help="model id from GET /v1/models")
            p.add_argument("--input-tokens", type=int, help="prompt tokens (token-priced models)")
            p.add_argument("--output-tokens", type=int, help="completion tokens, reasoning included")
            p.add_argument("--units", type=float, help="quantity in the model's pricing unit (images, seconds...)")
            p.add_argument("--at", help="also price at this ISO 8601 time from the published tide table")
        if name == "usage":
            p.add_argument("--days", type=int, default=7, help="how many days back (default 7, at most 90)")
            p.add_argument("--model", help="only this model id")
            p.add_argument("--max-pages", type=int, default=10, help="pages of 1,000 requests to read (default 10)")
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return EXIT_USAGE
    if args.command == "usage" and not 1 <= args.days <= 90:
        print("--days must be between 1 and 90 (request metadata is kept for 90 days).", file=sys.stderr)
        return EXIT_USAGE
    handlers = {"check": cmd_check, "market": cmd_market, "models": cmd_models, "estimate": cmd_estimate,
                "usage": cmd_usage}
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
