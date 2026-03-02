# RytmTeorin — reproducibility notes (Release root)

**All run + read instructions live in `Release/START_HERE.md`.**

This page explains what the verification scripts *do* and what artifacts they produce.

## The three entry scripts

- `verify_core.sh`
  - Runs the **Core** suite in a *facit-free* mode.
  - Enforces InfluenceAudit rules (Core must not read overlay / reference data).
  - Produces Core artifacts under `out/CORE_*` and audit logs under `out/CORE_AUDIT/`.

- `verify_compare.sh`
  - Runs the **Compare** suite (overlay validation only).
  - Produces Compare artifacts under `out/COMPARE_*` and audit logs under `out/COMPARE_AUDIT/`.

- `verify_all.sh`
  - Runs **Core → Compare → SM29 report generation**.
  - Produces the two main reviewer artifacts:
    - `00_TOP/LOCKS/SM_PARAM_INDEX/SM_29_REPORT.md`
    - `out/SM29_PAGES.md`

## Where outputs go

Everything written by the verification flow ends up under `Release/out/`.

Key outputs:
- `out/SM29_PAGES.md` — generated navigation page for per-parameter result pages.
- `00_TOP/LOCKS/SM_PARAM_INDEX/SM_29_REPORT.md` — executive SM29 report.
- `out/CORE_AUDIT/` and `out/COMPARE_AUDIT/` — run logs and policy checks.

## Core/Compare separation (what is enforced)

- Core is not allowed to read `00_TOP/OVERLAY/**` or `*reference*.json`.
- Compare is allowed to read overlay references, but must never feed back into Core.

See also:
- `00_TOP/CORE_CONTRACT_NO_FACIT.md`
- `00_TOP/RT_GOVERNANCE_NO_SI_NEG_POLICY_v1.md`
