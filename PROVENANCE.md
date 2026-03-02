# Provenance

**Title:** RytmTeorin (RT) — Public Release (FULL)  
**Author:** Bo Fremling  
**Version:** v1.0  
**Release date:** 2026-03-01

## What this release is

This release is intended to be:

- a **reference implementation** (open standard),
- a **reproducible verification package** (deterministic runs + audit logs + negative controls),
- and a public disclosure record (see `PRIOR_ART.md`).

## How to reproduce the headline artifacts

From the `Release/` directory:

1. Run verification:
   - `bash verify_all.sh`

2. Read the generated outputs:
   - `out/SM29_PAGES.md`
   - `00_TOP/LOCKS/SM_PARAM_INDEX/SM_29_REPORT.md`

The verification pipeline is designed to be restart-safe and to avoid mutating the repo in-place.

## Core vs Compare (no-facit policy)

- **Core** must not read any external “answer key” material (facit), including:
  - `00_TOP/OVERLAY/**`
  - any `*reference*.json`

- **Compare/Overlay** may read facit only after Core artifacts exist, and only to report
  **AGREES / TENSION / UNTESTED**.

See `VERIFY.md` and `RELEASE_MANIFEST.json`.

## Included pre-generated outputs

This release includes some pre-generated outputs under `out/` for reviewers who want to browse
results without running code. A clean re-run should reproduce the same artifacts.
