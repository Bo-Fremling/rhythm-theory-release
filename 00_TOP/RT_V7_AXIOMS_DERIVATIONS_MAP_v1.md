# RT — Axioms vs Policy vs LOCK (bookkeeping map) — v1 (Release)

Purpose: make it explicit **what is assumed/policy** and what is **derived/locked** in the current public pipeline.

Rule: anything that is Core-normative should be classifiable as one of:
- **Axiom / postulate** (taken as given)
- **Policy** (forbidden freedoms / method constraints)
- **LOCK / derivation** (discrete definition + evidence + NEG controls)

---

## 0) Minimal postulates (ontology)
1) **PP is ontologically primary** (time is z; objects are curves in PP).
2) **TickPulse exists** (the update is discrete; “front” is driven by a retarded/back-layer rule).
3) **TP objects exist** (tp-p, tp-e, tp-n, and composites such as tp-A).

In this Release, these are explained at a high level in:
- `00_TOP/RythmTheory_for_interested.md`
- `00_TOP/RT_ONTOLOGY_MAP_AND_GLOSSARY_v1.md`
- `00_TOP/RT_V7_EXPLAIN_RT_AND_ONTOLOGY_v1.md`

---

## 1) Mandatory policy (method constraints)
These are *not optional* in the current SM29 pipeline:

- **No SI numbers inside Core.** κ/SI mapping is Overlay only.
- **No facit influence:** Core must not read overlay/refs, and must not optimize/score against PDG/CODATA/targets.
- **Discreteness first:** any new freedom must be a discrete gate and come with NEG controls.
- **Determinism:** Core runs must be reproducible (semhash checks).

Where defined:
- `00_TOP/CORE_CONTRACT_NO_FACIT.md`
- `00_TOP/RT_GOVERNANCE_NO_SI_NEG_POLICY_v1.md`

---

## 2) Locked gates used by the current suite
These appear throughout the Core/lock code and are treated as “locked discoveries” for the public pipeline:

- **C30 / K=30** (strobe lattice). NEG: K=29/31 must fail.
- **Z2 (A/B)** (two strands; π-phase relation).
- **Z3 ledger** (sector structure used for controlled exceptions).
- **Z3/Z6/rho lemma pack** (structural consequences used by locks): `00_TOP/RT_Z3_Z6_RHO_LEMMAS_v1.md`.
- **wrap convention** for phase differences: `00_TOP/RT_WRAP_CONVENTION_v1_2026-02-06.md`.

Evidence for these gates is provided operationally by:
- the Core audit logs in `out/CORE_AUDIT/`
- the lock summaries in `out/CORE_*` (after running `bash verify_all.sh`)

---

## 3) What counts as a LOCK
A LOCK is a module that:
1) takes only Core-allowed inputs (no refs, no facit),
2) produces an observable candidate set / preferred value via explicit discrete rules,
3) logs audits and NEG controls,
4) writes its results under `out/CORE_<LOCK>/...`.

Compare modules (`*_compare.py`) may read overlay refs and write under `out/COMPARE_<LOCK>/...`, but must never feed back into Core.

---

## 4) SM29 bookkeeping
- Core produces `out/CORE_SM29_INDEX/sm29_core_index_*.{json,md}` with status per parameter (DERIVED / BLANK / etc).
- Compare produces `out/COMPARE_SM29_INDEX/sm29_compare_index_*.{json,md}` (overlay validation).
- The public “executive status” is generated as:
  - `00_TOP/LOCKS/SM_PARAM_INDEX/SM_29_REPORT.md`
  - `out/SM29_PAGES.md`
