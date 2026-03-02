#!/usr/bin/env python3
"""HADRON_PROXY_LOCK runner (v0.1)

Goal (scaffold): Provide a minimal, deterministic "hadron proxy" artifact consisting of
selected PDG mass ratios (dimensionless) plus a NEG toggle.

This is *overlay/reference* only in v0.1. RT-derivation is tracked in SM29_WORKPLAN.

Usage:
  python3 00_TOP/LOCKS/HADRON_PROXY_LOCK/hadron_proxy_lock_run.py
  python3 00_TOP/LOCKS/HADRON_PROXY_LOCK/hadron_proxy_lock_run.py --neg_corrupt --tag neg

Outputs (tag=main):
  out/HADRON_PROXY_LOCK/hadron_proxy_lock_v0_1.json
  out/HADRON_PROXY_LOCK/hadron_proxy_lock_summary_v0_1.md

Outputs (tag!=main):
  out/HADRON_PROXY_LOCK/hadron_proxy_lock_v0_1_<tag>.json
  out/HADRON_PROXY_LOCK/hadron_proxy_lock_summary_v0_1_<tag>.md

Exit codes:
  0 OK, 2 MISSING input
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_json(p: Path) -> Dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))


def _out_paths(out_dir: Path, tag: str) -> tuple[Path, Path]:
    if tag == "main":
        return (out_dir / "hadron_proxy_lock_v0_1.json", out_dir / "hadron_proxy_lock_summary_v0_1.md")
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in tag)
    return (
        out_dir / f"hadron_proxy_lock_v0_1_{safe}.json",
        out_dir / f"hadron_proxy_lock_summary_v0_1_{safe}.md",
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--neg_corrupt", action="store_true", help="NEG: corrupt one ratio value")
    ap.add_argument("--tag", default="main", help="output tag (default: main)")
    args = ap.parse_args()

    ref = REPO_ROOT / "00_TOP/OVERLAY/hadron_mass_reference_v0_1.json"
    out_dir = REPO_ROOT / "out/HADRON_PROXY_LOCK"
    out_dir.mkdir(parents=True, exist_ok=True)

    out_json, out_md = _out_paths(out_dir, args.tag)

    if not ref.exists():
        out_md.write_text(
            "# HADRON_PROXY_LOCK (v0.1)\n\nMISSING input:\n- " + str(ref.relative_to(REPO_ROOT)) + "\n",
            encoding="utf-8",
        )
        return 2

    d = _load_json(ref)
    ratios = dict(d.get("ratios_to_mp", {}))

    # NEG: corrupt one ratio deterministically (small but nonzero drift)
    neg = {"neg_corrupt": bool(args.neg_corrupt)}
    if args.neg_corrupt and "m_n_over_m_p" in ratios:
        ratios["m_n_over_m_p"] = float(ratios["m_n_over_m_p"]) * 1.0001
        neg["corrupt_target"] = "m_n_over_m_p"
        neg["corrupt_factor"] = 1.0001

    out = {
        "version": "v0.1",
        "inputs": {
            "hadron_mass_reference": str(ref.relative_to(REPO_ROOT)),
        },
        "tag": args.tag,
        "neg": neg,
        "ratios_to_mp": ratios,
        "notes": [
            "Overlay-only reference artifact in v0.1 (not an RT-derivation).",
            "Used to build hadron-proxy gates later without adding continuous parameters.",
        ],
    }

    out_json.write_text(json.dumps(out, indent=2, sort_keys=True), encoding="utf-8")

    md = []
    md.append("# HADRON_PROXY_LOCK (v0.1)\n")
    md.append("\nOverlay/reference-only.\n")
    md.append("\n## Ratios to mp\n")
    for k in sorted(ratios):
        md.append(f"- {k}: {ratios[k]:.12g}\n")
    if args.neg_corrupt:
        md.append("\nNEG: --neg_corrupt enabled (intentional drift)\n")
    out_md.write_text("".join(md), encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
