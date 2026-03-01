# What is Rhythm Theory (RT)?
*Who wrote the numbers into the world? Rhythm Theory asks where the constants come from — and whether geometry can explain them.*

Rhythm Theory (RT) is a deterministic, geometric framework built around a strict separation between:

* CORE: generates candidates without any “target/facit” influence (no PDG/CODATA/known values).
* COMPARE/OVERLAY: only used afterwards to compare CORE results against references.

RT uses a two-plane viewpoint:

* PP (Primal Plane): the internal geometric/dynamic state space.
* RP (Real Plane): the measurement screen/projection (a stroboscopic readout).

In RT terms, many “quantum-like” phenomena are treated as PP→RP projection effects (limited readout + phase/tension structure), not as extra axioms.

## What RT claims (high level)

* Deterministic CORE rules can generate a constrained candidate set for physical parameters using internal gates/symmetries/lexicographic tie-breaks.
* A strict “no-facit” boundary can be enforced and audited (CORE is not allowed to read overlay/reference files).
* A reproducible verification pipeline can be run by outsiders to obtain PASS/FAIL and inspect audit artifacts.

## What you can test right now

External verification is the point of this release. You can:

1. Run the verification pipeline.
2. Inspect generated audit JSON files.
3. Confirm that CORE never reads overlay/reference data (negative controls must PASS).
4. Read the resulting SM29 report and navigation pages.

## How to verify (the official package)

Download the attached release zip asset (not GitHub’s auto-generated “Source code” archives).

Steps:

1. Unzip the archive.
2. cd Release/
3. Run: bash verify_all.sh

Expected:

* ALL_VERIFY: PASS
* Generates: 00_TOP/LOCKS/SM_PARAM_INDEX/SM_29_REPORT.md
* Generates: out/SM29_PAGES.md

Optional strict check (slower):

* CORE_OVERLAY_OFF=1 bash verify_all.sh

## What “PASS” means here

PASS means:

* The pipeline ran end-to-end reproducibly.
* CORE audit guards and negative controls succeeded.
* COMPARE/OVERLAY was only used after CORE and only for comparison.
* Outputs and audit logs were generated for review.

PASS does NOT mean “physics is proven true” — it means the package is verifiable and the claimed separation and reproducibility hold.

## Status snapshot (release-level)

* SM29 status is reported in SM_29_REPORT.md with categories such as DERIVED / BLANK and COMPARE statuses (AGREES / TENSION / UNTESTED).
* κ is policy-classed as overlay-only (UNTESTED by design).

## Roadmap (short)

* Strengthen “Core-only” derivations and shrink remaining blanks.
* Expand falsifiable predictions and external datasets.
* Improve pedagogical docs while keeping CORE/COMPARE separation strict.

## Attribution / citation

Author: Bo Fremling
See CITATION.cff inside the release archive for a standard citation entry.
