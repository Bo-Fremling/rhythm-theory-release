#!/usr/bin/env python3
"""Static safety grep for Core code.

Purpose:
  Defense-in-depth: catch obvious attempts to bypass InfluenceAudit via
  subprocesses or native/dynamic I/O from within *_coregen.py.

Scope:
  This is intentionally conservative and only scans Release/00_TOP/LOCKS
  *_coregen.py files.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


FORBIDDEN_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("subprocess", re.compile(r"\bsubprocess\b")),
    ("os.system", re.compile(r"\bos\s*\.\s*system\b")),
    ("Popen", re.compile(r"\bPopen\b")),
    ("ctypes", re.compile(r"\bctypes\b")),
    ("cffi", re.compile(r"\bcffi\b")),
    ("ffi.dlopen", re.compile(r"\bffi\s*\.\s*dlopen\b")),
]


def main() -> int:
    root = Path(__file__).resolve().parents[1]  # Release/
    locks = root / "00_TOP" / "LOCKS"
    if not locks.exists():
        print("[core] static safety grep: SKIP (LOCKS not found)")
        return 0

    hits: list[str] = []
    for p in sorted(locks.rglob("*_coregen.py")):
        try:
            txt = p.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            hits.append(f"READ_ERROR: {p.as_posix()} :: {e!r}")
            continue

        for label, rx in FORBIDDEN_PATTERNS:
            m = rx.search(txt)
            if m:
                # show the first match line for reviewer clarity
                line_no = txt[: m.start()].count("\n") + 1
                hits.append(f"{label}: {p.as_posix()}:{line_no}")

    if hits:
        print("FAIL: static safety grep found forbidden patterns in Core code:")
        for h in hits:
            print("-", h)
        print("\nIf this is a false positive, rewrite the code to avoid these modules/commands.")
        return 2

    print("[core] static safety grep: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
