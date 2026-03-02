#!/usr/bin/env python3
"""Generate a lock contamination report.

- legacy runner contaminated if it references overlay/refs/PDG/CODATA/targets
- core clean if *_coregen.py exists and does not reference forbidden strings

Outputs:
  out/CORE_AUDIT/lock_contamination_report_v0_1.json
  out/CORE_AUDIT/lock_contamination_report_v0_1.md
"""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LOCKS = REPO / "00_TOP" / "LOCKS"

FORBIDDEN = [
    "00_TOP/OVERLAY",
    "sm29_data_reference",
    "alpha_reference",
    "z0_reference",
    "reference.json",
    "CODATA",
    "PDG",
    "targets",
]


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _hits(text: str):
    return [k for k in FORBIDDEN if k in text]


def main() -> int:
    rows = []

    for lock_dir in sorted([p for p in LOCKS.iterdir() if p.is_dir()]):
        lock = lock_dir.name

        # legacy runners: anything ending with _run.py or containing "run" in name
        legacy_files = sorted(set(lock_dir.glob("*run*.py")) | set(lock_dir.glob("*_lock*.py")))
        legacy_hits = []
        for f in legacy_files:
            if f.name.endswith("_coregen.py") or f.name.endswith("_compare.py"):
                continue
            h = _hits(_read(f))
            if h:
                legacy_hits.append({"file": str(f.relative_to(REPO)).replace("\\", "/"), "found": h})

        legacy_contaminated = len(legacy_hits) > 0

        # coregen presence + scan
        coregen_files = sorted(lock_dir.glob("*_coregen.py"))
        coregen_hits = []
        for f in coregen_files:
            h = _hits(_read(f))
            if h:
                coregen_hits.append({"file": str(f.relative_to(REPO)).replace("\\", "/"), "found": h})

        core_clean_available = (len(coregen_files) > 0) and (len(coregen_hits) == 0)

        rows.append(
            {
                "lock": lock,
                "legacy_contaminated": legacy_contaminated,
                "legacy_hits": legacy_hits,
                "coregen_files": [str(f.relative_to(REPO)).replace("\\", "/") for f in coregen_files],
                "coregen_contaminated": len(coregen_hits) > 0,
                "coregen_hits": coregen_hits,
                "core_clean_available": core_clean_available,
            }
        )

    out_dir = REPO / "out" / "CORE_AUDIT"
    out_dir.mkdir(parents=True, exist_ok=True)

    j = out_dir / "lock_contamination_report_v0_1.json"
    j.write_text(json.dumps({"version": "v0.1", "rows": rows}, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # markdown
    clean = [r for r in rows if (not r["legacy_contaminated"]) and r["core_clean_available"]]
    contaminated = [r for r in rows if r["legacy_contaminated"]]

    lines = [
        "# LOCK contamination report (v0.1)",
        "",
        "## Summary",
        f"- Total LOCKS: {len(rows)}",
        f"- Legacy contaminated: {len(contaminated)}",
        f"- Legacy clean + coregen available: {len(clean)}",
        "",
        "## Legacy contaminated LOCKS",
        "| LOCK | Legacy hits | Coregen available |",
        "|---|---|---|",
    ]
    for r in contaminated:
        hits = ", ".join(sorted({h for x in r["legacy_hits"] for h in x["found"]}))
        lines.append(f"| {r['lock']} | {hits} | {'YES' if r['core_clean_available'] else 'NO'} |")

    lines += [
        "",
        "## Core-clean LOCKS (legacy runner clean + coregen present)",
        "| LOCK | Coregen files |",
        "|---|---|",
    ]
    for r in clean:
        lines.append(f"| {r['lock']} | {'; '.join(r['coregen_files'])} |")

    (out_dir / "lock_contamination_report_v0_1.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"WROTE: {j}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
