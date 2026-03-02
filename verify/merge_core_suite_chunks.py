#!/usr/bin/env python3
"""Merge chunked Core suite runs into one canonical FULL report.

Why
- verify/verify_core.sh may run the core suite in multiple chunks.
- For reviewer clarity (and to keep verification quality), we merge the
  per-chunk summaries into one FULL summary with explicit coverage checks.

Stability / semhash
- Chunk summaries contain volatile fields (timestamps, audit paths, stdout tails).
- The FULL report includes a stable semhash computed over only:
    (script, status, exit_code, soft)
  for each entry, in coregen_order index order.

Outputs
- out/CORE_AUDIT/core_suite_run_v0_2_FULL_<label>_<STAMP>.json
- out/CORE_AUDIT/core_suite_run_v0_2_FULL_<label>_<STAMP>.md

Usage
  python3 -u verify/merge_core_suite_chunks.py --label baseline <chunk1.json> <chunk2.json> [...]
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def _sha256_json(obj: Any) -> str:
    blob = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _canon_result(r: Dict[str, Any]) -> Dict[str, Any]:
    out = {
        "script": r.get("script"),
        "status": r.get("status"),
        "exit_code": int(r.get("exit_code") or 0),
    }
    if r.get("soft") is True:
        out["soft"] = True
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True, help="run label (baseline / semhash_check / overlay_off)")
    ap.add_argument("chunks", nargs="+", help="paths to core_suite_run_v0_2_S*_N*_<STAMP>.json files")
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    out_dir = root / "out" / "CORE_AUDIT"
    out_dir.mkdir(parents=True, exist_ok=True)

    chunks: List[Dict[str, Any]] = []
    for p in args.chunks:
        pp = (Path(p) if Path(p).is_absolute() else (root / p)).resolve()
        if not pp.exists():
            raise SystemExit(f"FAIL: chunk file not found: {p}")
        obj = json.loads(pp.read_text(encoding="utf-8"))
        obj["_path"] = str(pp.relative_to(root)).replace("\\", "/")
        chunks.append(obj)

    # Validate coregen_order identity
    coregen_order: Optional[List[str]] = None
    for c in chunks:
        order = c.get("coregen_order")
        if not isinstance(order, list) or not order:
            raise SystemExit("FAIL: chunk missing coregen_order")
        if coregen_order is None:
            coregen_order = list(order)
        elif list(order) != coregen_order:
            raise SystemExit("FAIL: coregen_order mismatch across chunks")
    assert coregen_order is not None

    n_total = len(coregen_order)
    full: List[Optional[Dict[str, Any]]] = [None] * n_total

    # Place chunk results into the correct slots
    for c in chunks:
        ch = c.get("chunk") or {}
        start = int(ch.get("start") or 0)
        results = c.get("results") or []
        if not isinstance(results, list):
            raise SystemExit("FAIL: chunk results must be a list")
        for i, r in enumerate(results):
            idx = start + i
            if idx < 0 or idx >= n_total:
                raise SystemExit(f"FAIL: chunk result index out of range: {idx} (n_total={n_total})")
            if full[idx] is not None:
                raise SystemExit(f"FAIL: overlapping coverage at index {idx} ({coregen_order[idx]})")
            full[idx] = r

    missing = [coregen_order[i] for i, r in enumerate(full) if r is None]
    if missing:
        raise SystemExit(f"FAIL: missing coverage for {len(missing)} entries (first: {missing[0]})")

    # Canonical semhash basis (stable across environments)
    canon = [_canon_result(r or {}) for r in full]  # type: ignore[arg-type]
    semhash = _sha256_json({"coregen_order": coregen_order, "results": canon})

    # Counts
    counts: Dict[str, int] = {}
    for r in canon:
        s = r.get("status") or "UNKNOWN"
        counts[s] = counts.get(s, 0) + 1
    # Mirror the verify_core.sh expected keys
    for k in ("OK", "WARN", "MISSING", "FORBIDDEN", "TARGET_NONZERO", "WRAPPER_ERROR"):
        counts.setdefault(k, 0)

    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    payload = {
        "version": "v0.2.0-merged",
        "generated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "label": str(args.label),
        "coregen_order": coregen_order,
        "source_chunks": [c.get("_path") for c in chunks],
        "combined": {"semhash": semhash, "basis": "(script,status,exit_code,soft)"},
        "results": full,
        "results_canonical": canon,
        "counts": counts,
    }

    jp = out_dir / f"core_suite_run_v0_2_FULL_{args.label}_{stamp}.json"
    jp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # Markdown summary
    lines: List[str] = [
        "# Core suite run (NO-FACIT) — FULL (merged)",
        "",
        f"- label: `{args.label}`",
        f"- utc: `{stamp}`",
        f"- semhash: `{semhash}`",
        "",
        "## Coverage",
        f"- total: {n_total}",
        f"- OK: {counts.get('OK',0)}",
        f"- WARN: {counts.get('WARN',0)}",
        f"- MISSING: {counts.get('MISSING',0)}",
        f"- FORBIDDEN: {counts.get('FORBIDDEN',0)}",
        f"- TARGET_NONZERO: {counts.get('TARGET_NONZERO',0)}",
        f"- WRAPPER_ERROR: {counts.get('WRAPPER_ERROR',0)}",
        "",
        "## Results (canonical)",
        "",
        "| # | Script | Status | Exit |",
        "|---:|---|---|---:|",
    ]
    for i, r in enumerate(canon):
        lines.append(f"| {i} | {r.get('script')} | {r.get('status')} | {r.get('exit_code')} |")

    mp = jp.with_suffix(".md")
    mp.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"MERGED_WROTE: {jp}")
    print(f"MERGED_SEMHASH: {semhash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
