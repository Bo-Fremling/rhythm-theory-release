## Governance: No-SI-in-Core + NEG Policy (v1, 2026-01-03)

### Why this exists
RT is built to avoid “hidden knobs”. The governance layer is part of the scientific claim: what is allowed to be postulated, what must be derived, and how decisions are locked.

### Hard rule: no SI in Core
- Core derivations must not take SI constants (c, h, G, CODATA) as inputs, tuning, or anchors.
- SI is allowed only in **Overlay** for reporting and comparison (a posteriori kappa mapping).

### NEG first (negative controls)
A claim is not considered “locked” unless it survives negative controls.
Examples used in this package:
- K=29/31 fail while K=30 passes (C30 gate).
- wrong sign or AB mismatch should collapse the effect (e.g. tension goes to zero).

### Locks, not vibes
Each LOCK must specify:
- definitions (objects, cost functionals),
- invariances / gauge conventions,
- negative controls,
- explicit PASS/FAIL criteria,
- evidence file paths.

### Valpunkts ledger (decision bookkeeping)
If a choice is not derived, it must be logged as either:
- a *locked discovery/gate* (survived NEG), or
- a *policy choice* (governance), never a silent default.

### Scope discipline
- V6 is the core theory archive.
- V7 atom module is a consequence/demonstrator: any new ingredient that cannot be traced back to V6 + gates must be reclassified as a new gate until derived.

### Canonical references (within this Release)

- Contract (NO-FACIT): `00_TOP/CORE_CONTRACT_NO_FACIT.md`
- Postulates vs locks: `00_TOP/RT_POSTULATES_VS_LOCKED_DISCOVERIES_v1_1.md`
- Ontology map + glossary: `00_TOP/RT_ONTOLOGY_MAP_AND_GLOSSARY_v1.md`
- Verification flow: `00_TOP/RT_V7_COMPUTE_MAP_v1_2026-02-05.md`
