# RT V7 — how the computation is wired (one-page map, v1, 2026-02-05)

This is a **one-page map** from “state” → locks → observables, with pointers to what is normative in this Release bundle.

## 0) Policy (hard constraints)
- **No SI numbers in Core.** (see `00_TOP/RT_GOVERNANCE_NO_SI_NEG_POLICY_v1.md`)
- Any SI mapping (κ, Hz, meters) is **Overlay** only.
- **No facit influence:** Core must never read `00_TOP/OVERLAY/**` or `*reference*.json`. (see `00_TOP/CORE_CONTRACT_NO_FACIT.md`)

## 1) State (PP) and sampling (RP/Σ)
- PP: curves/spirals in xy with time as z.
- Sampling: **C30 strobe** at uₖ = 2πk/30.
- Symmetry gates: A/B (Z2), Z3 ledger, RCC centering.
These are treated as **locked gates** in the current pipeline.

## 2) Gates / audits (negative controls)
Locks are required to expose **NEG controls** (known-fail variants), e.g.
- K=29 / K=31 (C30 broken) → FAIL
- AB mismatch → FAIL
- sign flips that remove tension → FAIL

Audits are logged by the Core suite in `out/CORE_AUDIT/`.

## 3) Locks (Core generation)
Core runs a suite of `*_coregen.py` scripts and writes:
- `out/CORE_*` summaries
- `out/CORE_SM29_INDEX/sm29_core_index_*.{json,md}`

Entry points (scripts):
- Core suite runner: `00_TOP/TOOLS/run_core_no_facit_suite.py`
- Individual locks: `00_TOP/LOCKS/**`

## 4) Compare (Overlay validation)
Compare runs `*_compare.py` scripts that may read:
- `00_TOP/OVERLAY/**` and `*reference*.json`

Compare writes:
- `out/COMPARE_*` summaries
- `out/COMPARE_SM29_INDEX/sm29_compare_index_*.{json,md}`

Entry point:
- Compare suite runner: `00_TOP/TOOLS/run_compare_suite.py`

## 5) SM29 triage + report
After Core+Compare:
- `00_TOP/LOCKS/SM_PARAM_INDEX/sm29_data_match.py` produces overlay triage under `out/SM_PARAM_INDEX/`
- `00_TOP/LOCKS/SM_PARAM_INDEX/sm29_report.py` generates:
  - `00_TOP/LOCKS/SM_PARAM_INDEX/SM_29_REPORT.md`
  - `out/SM29_PAGES.md`

## 6) The one command
From the Release root:

```bash
bash verify_all.sh
```

It runs the full chain (Core → Compare → data-match → report/pages).
