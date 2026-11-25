#!/usr/bin/env python3
"""Create a project workspace with templates and the universal visual-grounding folder layout.

  init_project.py "My Video" [--type general|campaign|guide|personal|commercial|explainer|story]
                  [--canvas 16:9|9:16|1:1] [--root projects] [--budget-usd 50]
                  [--platforms youtube,tiktok,instagram,x] [--languages en] [--markets US] [--url https://...]

Layout: research/ strategy/ briefs/
        assets/{people,captures,product,brand,fonts,references,footage,scenes,music,sfx}/
        keyframes/ clips/ audio/ captions/ renders/ qa/ post/ logs/ + project.json
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import common

DIRS = [
    "research", "strategy", "briefs",
    "assets/people", "assets/captures", "assets/product", "assets/brand", "assets/fonts",
    "assets/references", "assets/footage", "assets/scenes", "assets/music", "assets/sfx",
    "keyframes", "clips", "audio", "captions", "renders", "qa", "post", "logs",
]
PROJECT_TYPES = ["general", "campaign", "guide", "personal", "commercial", "explainer", "story"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name")
    ap.add_argument("--type", default="general", choices=PROJECT_TYPES,
                    help="video project type (guides workflow depth)")
    ap.add_argument("--root", default="projects")
    ap.add_argument("--budget-usd", type=float, default=50.0, help="hard cap for Tokentide spend in this project")
    ap.add_argument("--platforms", default="tiktok,instagram,x")
    ap.add_argument("--languages", default="en")
    ap.add_argument("--markets", default="")
    ap.add_argument("--url", default="")
    ap.add_argument("--canvas", default="9:16", choices=["9:16", "16:9", "1:1"],
                    help="default video canvas aspect ratio (9:16 vertical, 16:9 landscape, 1:1 square)")
    ap.add_argument("--force", action="store_true", help="re-copy templates into an existing project")
    a = ap.parse_args()

    slug = common.slugify(a.name)
    root = Path(a.root) / slug
    exists = (root / "project.json").exists()
    for d in DIRS:
        (root / d).mkdir(parents=True, exist_ok=True)
    copied = []
    for src in sorted(common.TEMPLATES_DIR.rglob("*")):
        if src.is_dir():
            continue
        rel = src.relative_to(common.TEMPLATES_DIR)
        if rel.parts[0] in ("research", "strategy"):
            dst = root / rel
        elif src.name == "video_spec.example.json":
            dst = root / "briefs" / "_example_spec.json"
        elif src.name == "performance.csv":
            dst = root / "logs" / "performance.csv"
        else:
            continue
        if not dst.exists() or a.force:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, dst)
            copied.append(str(dst.relative_to(root)))
    if not exists:
        common.save_json(root / "project.json", {
            "name": a.name, "slug": slug, "type": a.type, "created": common.now_iso(), "product_url": a.url,
            "platforms": [p.strip() for p in a.platforms.split(",") if p.strip()],
            "languages": [x.strip() for x in a.languages.split(",") if x.strip()],
            "markets": [x.strip() for x in a.markets.split(",") if x.strip()],
            "budget_usd": a.budget_usd,
            "canvas": a.canvas,
            "notes": "budget_usd is a hard cap enforced by video.py run; raise it only with the user's OK."})
    print(f"{'Updated' if exists else 'Created'} project: {root}")
    for c in copied:
        print(f"  + {c}")
    print("Next: store visual anchors under assets/ (people/, captures/, product/, references/, footage/, brand/, fonts/), "
          "then pick models from the live catalog:\n"
          f"  python3 {Path(__file__).resolve().parent}/models.py tiers --project {root}")


if __name__ == "__main__":
    main()
