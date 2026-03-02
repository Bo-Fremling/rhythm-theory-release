# RT (Release) — No‑Facit Threat Model (v1)

This document is written for external reviewers.

## What this release *does* guarantee (claim scope)

In **Core** runs, the release enforces (via the InfluenceAudit layer + verification scripts):

1) **No Overlay reads from Core**
   * Any path starting with `00_TOP/OVERLAY` is forbidden (prefix match).
   * Any `*reference*.json` file is forbidden (glob).

2) **No filesystem reads outside the repo**
   * Any attempted open outside the repo root hard‑fails, except a narrow **system allowlist** (Python stdlib / site‑packages and a few OS read‑only paths needed by Python).

3) **Overlay‑off negative control**
   * Verification moves `00_TOP/OVERLAY` out‑of‑tree (random temp dir) and runs a NEG test that must fail if Core tries to read a file from that moved overlay.

4) **Determinism lock**
   * Core suite runs twice and a canonical merged semhash must match.

Practical evidence is emitted in `out/CORE_AUDIT/core_suite_run_*.json` and checked by `Release/verify/check_audit_open_scopes.py`.

## What this release *does not* claim to prevent

These are real attack surfaces for a fully hostile execution wrapper. They are explicitly **out of scope** unless you add further sandboxing:

1) **Subprocess / C‑extension side‑channels**
   * A malicious Core could, in theory, invoke a subprocess or load a C extension that performs file I/O outside Python’s `open()` hooks.
   * The release includes a static check to detect obvious uses in `*_coregen.py` (see below), but it is not a formal proof against arbitrary native code.

2) **Pre‑opened file descriptors (FDs)**
   * If a hostile wrapper pre‑opens a sensitive file and hands the FD to the Python process, Core could read it via FD operations that are not caught by `open()` hooks.
   * The audit reports an `fd` scope counter; the verification requires `fd=0` for normal runs, but this is not a proof against all FD‑based tricks.

3) **Environment‑variable smuggling**
   * Core code can read `os.environ`. A hostile wrapper could smuggle “facit” as environment data.

4) **Hard‑coded values inside Core source**
   * No‑facit enforcement here is an I/O barrier. It does not prove the absence of hard‑coded targets inside allowed source files.

## Defense‑in‑depth included in this release

1) **Static safety grep (Core code hygiene)**
   * `Release/verify/static_core_safety_grep.py` fails verification if it finds obvious use of `subprocess`, `os.system`, `ctypes`, or `cffi` inside `Release/00_TOP/LOCKS/**/*_coregen.py`.

2) **Audit scope check**
   * `Release/verify/check_audit_open_scopes.py` requires that recorded opens are only in allowed scopes (repo/system/fd) and that “other” never occurs.

## If you want “hostile‑wrapper tight”

These are optional hardenings (not required for the release’s baseline claim):

* Close all file descriptors > 2 before starting Core.
* Run Core with a scrubbed environment (whitelist).
* Block `subprocess`, dynamic linking, and network modules at import time.
