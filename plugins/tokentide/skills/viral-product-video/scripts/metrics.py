#!/usr/bin/env python3
"""Turn post performance into decisions: SCALE / ITERATE (hook, body or payoff) / KILL.

  metrics.py template --out logs/performance.csv     # header + one example row
  metrics.py analyze  --csv logs/performance.csv [--out qa/performance_report.md] [--min-age-h 48]

Rates are per reach (views if reach is missing). Posts are compared with the median of the same
platform, so judge only posts older than 48-72 h. Columns not available on a platform can stay empty.
"""
from __future__ import annotations

import argparse
import csv
import statistics
from collections import defaultdict
from pathlib import Path

import common

COLUMNS = ["post_id", "video_id", "platform", "posted_at", "age_hours", "duration_s", "views", "reach",
           "avg_watch_s", "completion_rate", "hold_3s_rate", "likes", "comments", "shares", "sends", "saves",
           "follows", "profile_visits", "link_clicks", "hook_variant", "format", "pillar", "notes"]


def f(x):
    try:
        return float(str(x).replace(",", "").replace("%", "")) if str(x).strip() != "" else None
    except ValueError:
        return None


def pct(x):
    if x is None:
        return None
    return x / 100 if x > 1.0 else x  # accept 45 or 0.45


def derive(r):
    reach = f(r.get("reach")) or f(r.get("views"))
    dur = f(r.get("duration_s"))
    d = {"reach": reach}
    sends = f(r.get("sends"))
    shares = f(r.get("shares"))
    for k, v in (("sends_pr", sends if sends is not None else shares), ("likes_pr", f(r.get("likes"))),
                 ("comments_pr", f(r.get("comments"))), ("saves_pr", f(r.get("saves")))):
        d[k] = (v / reach) if (v is not None and reach) else None
    fol = f(r.get("follows"))
    d["follows_per_1k"] = (fol / reach * 1000) if (fol is not None and reach) else None
    aw = f(r.get("avg_watch_s"))
    d["watch_pct"] = (aw / dur) if (aw is not None and dur) else None
    d["hold"] = pct(f(r.get("hold_3s_rate")))
    d["completion"] = pct(f(r.get("completion_rate")))
    return d


BASELINE = {"hold": 0.60, "watch_pct": 0.50, "sends_pr": 0.010, "follows_per_1k": 3.0}  # heuristics when < 3 posts


def ratio(v, ref):
    return None if v is None or not ref else v / ref


def decide(r):
    """r = ratios to the platform median (1.0 = median). Order matters: strongest signal first."""
    hold = r.get("hold") if r.get("hold") is not None else r.get("watch_pct")
    ret, share, fol = r.get("watch_pct"), r.get("sends_pr"), r.get("follows_per_1k")
    if share is not None and share >= 1.5 and (ret is None or ret >= 0.9):
        return "SCALE", "Winner: make 3 variants (new hooks on the same body), turn it into a series, consider Spark Ads / boosting."
    if hold is not None and hold < 0.7 and (share is None or share < 0.5):
        return "KILL", "Far below median on hook and shares: drop the angle or re-concept it."
    if hold is not None and hold < 0.85 and ret is not None and ret >= 0.9:
        return "ITERATE-HOOK", "Body works but the opening loses people: test 3 new hooks (visual-first, payoff-first, callout)."
    if hold is not None and hold >= 0.9 and ret is not None and ret < 0.85:
        return "ITERATE-BODY", "Hook works, middle sags: cut 20-30%, add a pattern interrupt every ~2 s, reveal the payoff earlier."
    if ret is not None and ret >= 0.9 and share is not None and share < 0.8:
        return "ITERATE-PAYOFF", "Watched but not shared: sharper payoff, social-currency/identity angle, explicit 'send this to…' CTA."
    if share is not None and share >= 1.0 and fol is not None and fol < 0.6:
        return "ITERATE-FOLLOW", "Shared but few follows: make it episodic ('part 2'), add series branding and a reason to follow."
    return "HOLD", "Around the median: keep the format, change one variable next time."


def cmd_template(a):
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(COLUMNS)
        w.writerow(["tt_001", "v01", "tiktok", "2026-11-03 19:00", "72", "13", "5400", "5100", "6.1", "21", "58",
                    "310", "24", "41", "", "37", "29", "120", "", "A-payoff-first", "satisfying-demo", "demo", ""])
    print(out)


def cmd_analyze(a):
    rows = list(csv.DictReader(open(a.csv, encoding="utf-8-sig")))
    if not rows:
        common.die("CSV has no rows")
    rows = [r for r in rows if not (f(r.get("age_hours")) is not None and f(r.get("age_hours")) < a.min_age_h)]
    by_plat = defaultdict(list)
    for r in rows:
        r["_d"] = derive(r)
        by_plat[(r.get("platform") or "?").lower()].append(r)
    lines = ["# Performance report", "", f"Posts analysed: {len(rows)} (older than {a.min_age_h} h). Each post is compared with its platform median "
             "(fixed heuristics when a platform has fewer than 3 posts).", ""]
    keys = ("hold", "watch_pct", "completion", "sends_pr", "likes_pr", "comments_pr", "saves_pr", "follows_per_1k")
    groups = defaultdict(list)
    for plat, rs in by_plat.items():
        cols = {k: [r["_d"][k] for r in rs] for k in keys}
        med = {k: statistics.median([x for x in v if x is not None]) if any(x is not None for x in v) else None
               for k, v in cols.items()}
        lines += [f"## {plat} ({len(rs)} posts)", "",
                  "| post | video | hook | hold3s | watch% | sends/reach | follows/1k | decision | next step |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for r in sorted(rs, key=lambda x: -(x["_d"]["sends_pr"] or 0)):
            d = r["_d"]
            ref = med if len(rs) >= 3 else {k: BASELINE.get(k) for k in keys}
            dec, step = decide({k: ratio(d[k], ref.get(k)) for k in keys})
            r["_dec"] = dec
            fmt = lambda x, p=True: "-" if x is None else (f"{x * 100:.1f}%" if p else f"{x:.1f}")
            lines.append(f"| {r.get('post_id')} | {r.get('video_id')} | {r.get('hook_variant', '')} | {fmt(d['hold'])} | "
                         f"{fmt(d['watch_pct'])} | {fmt(d['sends_pr'])} | {fmt(d['follows_per_1k'], False)} | **{dec}** | {step} |")
            for g in ("format", "pillar", "hook_variant"):
                if r.get(g):
                    groups[(g, r[g])].append(d)
        lines += ["", "Medians: " + ", ".join(f"{k}={'-' if v is None else round(v, 4)}" for k, v in med.items()), ""]
    lines += ["## What is working (mean across platforms)", "", "| dimension | value | posts | sends/reach | watch% |",
              "|---|---|---|---|---|"]
    for (g, val), ds in sorted(groups.items(), key=lambda kv: -statistics.mean([d["sends_pr"] or 0 for d in kv[1]])):
        sp = statistics.mean([d["sends_pr"] or 0 for d in ds])
        wp = [d["watch_pct"] for d in ds if d["watch_pct"] is not None]
        lines.append(f"| {g} | {val} | {len(ds)} | {sp * 100:.2f}% | {(statistics.mean(wp) * 100) if wp else 0:.0f}% |")
    lines += ["", "Rules: change one variable per test; judge after 48-72 h; promote SCALE posts to the hook bank;"
                  " retire angles that are KILL twice."]
    report = "\n".join(lines) + "\n"
    out = Path(a.out) if a.out else Path(a.csv).with_name("performance_report.md")
    out.write_text(report, encoding="utf-8")
    print(report)
    print(f"saved {out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("template")
    t.add_argument("--out", required=True)
    z = sub.add_parser("analyze")
    z.add_argument("--csv", required=True)
    z.add_argument("--out")
    z.add_argument("--min-age-h", type=float, default=48)
    a = ap.parse_args()
    {"template": cmd_template, "analyze": cmd_analyze}[a.cmd](a)


if __name__ == "__main__":
    main()
