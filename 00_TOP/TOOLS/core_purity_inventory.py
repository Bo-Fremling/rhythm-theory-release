#!/usr/bin/env python3
"""Core purity inventory.

Two complementary signals:

1) Runtime (authoritative): parse latest InfluenceAudit reports for each *_coregen.py.
   - PASS means: script ran with overlay stubbed and did NOT open forbidden paths.

2) Static (heuristic): string scan of python sources.
   - Only used as a hotspot finder (may false-positive on comments/docstrings).

Outputs:
  out/CORE_AUDIT/core_purity_inventory_v0_1.json   (static scan; legacy behavior)
  out/CORE_AUDIT/core_purity_inventory_v0_2.json   (runtime + static, lock summary)
  out/CORE_AUDIT/core_purity_inventory_v0_2.md
"""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LOCKS = REPO / "00_TOP" / "LOCKS"
AUDIT_DIR = REPO / "out" / "CORE_AUDIT"

FORBIDDEN_SNIPPETS = [
    "00_TOP/OVERLAY",
    "reference.json",
    "sm29_data_reference",
    "CODATA",
    "PDG",
]


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _scan_file(p: Path):
    s = _read(p)
    found = [sn for sn in FORBIDDEN_SNIPPETS if sn in s]
    return found


def _latest_audit_for(stem: str):
    # InfluenceAudit writes: out/CORE_AUDIT/<stem>_audit_<STAMP>.json
    if not AUDIT_DIR.exists():
        return None
    cands = sorted(AUDIT_DIR.glob(f"{stem}_audit_*.json"))
    if not cands:
        return None
    return cands[-1]


def _load_json(p: Path):
    try:
        return json.loads(_read(p))
    except Exception:
        return None


def main() -> int:
    rows_static = []
    rows = []

    for lock_dir in sorted([p for p in LOCKS.iterdir() if p.is_dir()]):
        lock = lock_dir.name

        py_files = sorted(lock_dir.glob("*.py"))
        # --- static legacy output (v0.1): any forbidden snippet anywhere under lock
        hits = []
        for f in py_files:
            found = _scan_file(f)
            if found:
                hits.append({"file": str(f.relative_to(REPO)).replace("\\", "/"), "found": found})
        rows_static.append({"lock": lock, "hits": hits, "clean": (len(hits) == 0)})

        # --- runtime-aware summary (v0.2)
        coregen_files = sorted(lock_dir.glob("*_coregen.py"))
        compare_files = sorted(lock_dir.glob("*_compare.py"))
        legacy_files = sorted([p for p in py_files if p not in set(coregen_files + compare_files)])

        coregen = []
        for f in coregen_files:
            stem = f.stem
            audit_path = _latest_audit_for(stem)
            audit = _load_json(audit_path) if audit_path else None
            coregen.append(
                {
                    "file": str(f.relative_to(REPO)).replace("\\", "/"),
                    "audit": {
                        "present": bool(audit_path),
                        "path": str(audit_path.relative_to(REPO)).replace("\\", "/") if audit_path else None,
                        "result": (audit or {}).get("result") if isinstance(audit, dict) else None,
                        "exit_code": (audit or {}).get("exit_code") if isinstance(audit, dict) else None,
                        "forbidden": (audit or {}).get("forbidden") if isinstance(audit, dict) else None,
                    },
                    "static_mentions": _scan_file(f),
                }
            )

        legacy_hits = []
        for f in legacy_files:
            found = _scan_file(f)
            if found:
                legacy_hits.append({"file": str(f.relative_to(REPO)).replace("\\", "/"), "found": found})

        compare_hits = []
        for f in compare_files:
            found = _scan_file(f)
            if found:
                compare_hits.append({"file": str(f.relative_to(REPO)).replace("\\", "/"), "found": found})

        # Core runtime status
        audited = [c for c in coregen if c["audit"]["present"]]
        any_forbidden = any((c["audit"]["result"] == "FORBIDDEN") for c in audited)
        any_wrapper_err = any((c["audit"]["result"] in ("WRAPPER_ERROR", "TARGET_NONZERO")) for c in audited)
        all_ok = (len(audited) == len(coregen)) and (len(coregen) > 0) and (not any_forbidden) and (not any_wrapper_err)

        core_runtime_status = (
            "NO_COREGEN" if not coregen else (
                "UNAUDITED" if len(audited) == 0 else (
                    "FORBIDDEN" if any_forbidden else (
                        "ERROR" if any_wrapper_err else (
                            "PASS" if all_ok else "PARTIAL"
                        )
                    )
                )
            )
        )

        rows.append(
            {
                "lock": lock,
                "coregen": coregen,
                "core_runtime_status": core_runtime_status,
                "legacy_static_hits": legacy_hits,
                "compare_static_hits": compare_hits,
            }
        )

    out = REPO / "out" / "CORE_AUDIT"
    out.mkdir(parents=True, exist_ok=True)

    # v0.1: keep legacy static output for compatibility
    out_path1 = out / "core_purity_inventory_v0_1.json"
    out_path1.write_text(json.dumps({"version": "v0.1", "rows": rows_static}, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # v0.2: runtime-aware output
    out_path2 = out / "core_purity_inventory_v0_2.json"
    out_path2.write_text(json.dumps({"version": "v0.2", "rows": rows}, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # markdown summary
    pass_locks = [r["lock"] for r in rows if r["core_runtime_status"] == "PASS"]
    partial = [r["lock"] for r in rows if r["core_runtime_status"] in ("PARTIAL", "UNAUDITED")]
    forbidden = [r["lock"] for r in rows if r["core_runtime_status"] == "FORBIDDEN"]

    lines = [
        "# Core purity inventory (v0.2)",
        "",
        "Runtime-status (InfluenceAudit) är det som räknas för NO‑FACIT.",
        "",
        f"- PASS (alla coregen auditerade OK): {len(pass_locks)}",
        f"- PARTIAL/UNAUDITED: {len(partial)}",
        f"- FORBIDDEN: {len(forbidden)}",
        "",
        "## PASS (runtime)",
    ]
    for l in sorted(pass_locks):
        lines.append(f"- {l}")

    lines += ["", "## PARTIAL/UNAUDITED (runtime)"]
    for l in sorted(partial):
        lines.append(f"- {l}")

    if forbidden:
        lines += ["", "## FORBIDDEN (runtime)"]
        for l in sorted(forbidden):
            lines.append(f"- {l}")

    (out / "core_purity_inventory_v0_2.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"WROTE: {out_path1}")
    print(f"WROTE: {out_path2}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
