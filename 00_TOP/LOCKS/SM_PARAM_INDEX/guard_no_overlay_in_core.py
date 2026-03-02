#!/usr/bin/env python3
"""Guard: prevent Overlay refs from being used by Core locks.

Policy intent:
- Core locks should not read 00_TOP/OVERLAY/*.
- Overlay-only locks (EM_LOCK, EW_COUPLING_LOCK, ENERGY_ANCHOR_LOCK) may read Overlay.
- Reporting (SM_PARAM_INDEX) may read Overlay.

This guard is a static scan using tokenization: it ignores comments/docstrings, but catches overlay path literals used in executable code. It is not a full import tracer.
"""

from __future__ import annotations

import sys
from pathlib import Path

ALLOW_DIRS = {
    Path("00_TOP/LOCKS/EM_LOCK"),
    Path("00_TOP/LOCKS/EW_COUPLING_LOCK"),
    Path("00_TOP/LOCKS/ENERGY_ANCHOR_LOCK"),
    Path("00_TOP/LOCKS/SM_PARAM_INDEX"),  # report + overlay triage
    Path("00_TOP/LOCKS/HADRON_PROXY_LOCK"),
}

PATTERNS = ["00_TOP/OVERLAY", "overlay/", "OVERLAY/"]


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def is_allowed(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    for a in ALLOW_DIRS:
        try:
            rel.relative_to(a)
            return True
        except ValueError:
            pass
    # allow verify scripts anywhere (they may compare against overlay refs)
    if rel.name.endswith("_verify.py"):
        return True
    # allow compare scripts anywhere (they are explicitly overlay-facing)
    if rel.name.endswith("_compare.py"):
        return True
    return False


def main() -> int:
    root = repo_root()
    locks = root / "00_TOP/LOCKS"
    bad = []

    for p in locks.rglob("*.py"):
        if is_allowed(p, root):
            continue

        # Token-based scan: ignore comments and docstrings, but keep string literals
        # used in executable code (e.g., Path("00_TOP/OVERLAY/..."))
        try:
            import io
            import tokenize

            src = p.read_text(encoding="utf-8", errors="replace")
            readline = io.StringIO(src).readline
            tokens = tokenize.generate_tokens(readline)

            # Detect docstrings: first STRING in module or in an indented suite.
            # Track when we are at the start of a new suite.
            suite_start = [True]  # module level
            filtered = []

            for tok in tokens:
                ttype, tstr, *_ = tok

                if ttype == tokenize.INDENT:
                    suite_start.append(True)
                    continue
                if ttype == tokenize.DEDENT:
                    if len(suite_start) > 1:
                        suite_start.pop()
                    continue
                if ttype in (tokenize.NL, tokenize.NEWLINE):
                    continue
                if ttype == tokenize.COMMENT:
                    continue

                if ttype == tokenize.STRING and suite_start[-1]:
                    # docstring — ignore
                    suite_start[-1] = False
                    continue

                # any other significant token ends suite-start state
                if suite_start[-1]:
                    suite_start[-1] = False

                # keep other tokens (including non-docstring STRING)
                filtered.append(tstr)

            code_txt = " ".join(filtered)
            if any(s in code_txt for s in PATTERNS):
                bad.append(p.relative_to(root))

        except Exception:
            # fallback: conservative (old) behavior on parse errors
            txt = p.read_text(encoding="utf-8", errors="replace")
            if any(s in txt for s in PATTERNS):
                bad.append(p.relative_to(root))

    if bad:
        print("FAIL: Overlay refs appear in non-allowed lock code:")
        for b in bad:
            print(f"- {b}")
        print("\nAllowed dirs:")
        for a in sorted(ALLOW_DIRS):
            print(f"- {a}")
        return 2

    print("PASS: No overlay-ref usage detected in Core locks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
