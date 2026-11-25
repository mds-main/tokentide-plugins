#!/usr/bin/env python3
"""Project spend vs. cap. Tokentide reports the real charge of every non-streaming request
(X-Tokentide-Charge-USD), so the ledger is exact; --live also reads the account balance.

  budget.py --project P            # ledger summary (charges, Venice list price, savings)
  budget.py --project P --live     # + live balance and today's spend from GET /account
  budget.py --project P --set-cap 120   (only with the user's OK)
"""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import apiclient as api
import common


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True)
    ap.add_argument("--set-cap", type=float)
    ap.add_argument("--live", action="store_true")
    a = ap.parse_args()
    root = Path(a.project)
    meta = common.project_meta(root)
    if not meta:
        common.die(f"No project.json in {root}")
    if a.set_cap is not None:
        meta["budget_usd"] = a.set_cap
        common.save_json(root / "project.json", meta)
        print(f"cap set to ${a.set_cap:.2f}")
    entries = common.ledger_entries(root)
    spent = common.spent_usd(root)
    listed = sum(float(e.get("list_usd") or 0) for e in entries)
    charged_exact = sum(float(e.get("usd") or 0) for e in entries if e.get("list_usd") is not None)
    cap = meta.get("budget_usd")
    calls = Counter(e.get("kind") for e in entries)
    print(f"Project: {meta.get('name')}  cap: ${cap}  spent: ${spent:.2f}"
          + (f"  remaining: ${float(cap) - spent:.2f}" if cap is not None else ""))
    if listed:
        print(f"Venice list price of charged calls: ${listed:.2f} → you paid ${charged_exact:.2f} "
              f"(saved ${listed - charged_exact:.2f} via tide pricing)")
    print("Calls: " + ", ".join(f"{k}={v}" for k, v in sorted(calls.items())))
    if a.live:
        api.use_project(root)
        acct = api.account(refresh=True)
        bal = acct.get("balance") or {}
        today = acct.get("spend_today") or {}
        print(f"Account: spendable ${bal.get('spendable_usd')} (paid ${bal.get('available_usd')}, promo ${bal.get('promo_usd')}) · "
              f"today charged ${today.get('charged_usd')} vs list ${today.get('list_usd')}")


if __name__ == "__main__":
    main()
