#!/usr/bin/env python3
"""Check InfluenceAudit 'opened' scopes for hostile-reviewer tightness.

Policy
- Every open event must include a scope.
- Allowed scopes: repo, system, fd
- Any scope outside that set is a FAIL (including missing/unknown).

This is defense-in-depth: InfluenceAudit should already hard-fail on "other",
but this check makes the guarantee explicit in public verification artifacts.
"""

from __future__ import annotations

import json
from pathlib import Path


ALLOWED = {"repo", "system", "fd"}


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    aud = root / "out" / "CORE_AUDIT"
    if not aud.exists():
        print("[core] audit scope check: (no out/CORE_AUDIT yet)")
        return 0

    files = sorted(aud.glob("*_audit_*.json"))
    if not files:
        print("[core] audit scope check: (no per-script audit files found)")
        return 0

    bad = []
    counts = {"repo": 0, "system": 0, "fd": 0, "bad": 0}

    for p in files:
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        opened = obj.get("opened") or []
        for ev in opened:
            scope = ev.get("scope")
            if scope in ALLOWED:
                counts[scope] += 1
            else:
                counts["bad"] += 1
                bad.append((p.name, ev.get("path"), ev.get("op"), ev.get("mode"), scope))

    if bad:
        first = bad[0]
        print("FAIL: audit recorded open(s) outside repo/system allowlist OR missing scope")
        print(
            f"- first: file={first[0]} scope={first[4]} op={first[2]} mode={first[3]} path={first[1]}"
        )
        print(f"- total_bad: {len(bad)}")
        return 2

    print(
        "[core] audit scope check: PASS "
        f"(repo={counts['repo']}, system={counts['system']}, fd={counts['fd']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
