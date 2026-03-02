# RT Foundation: Ontology, Core, Theory (public release)

This document is the **single map** of what RT means in this release: **what exists (Ontology)**, **how it evolves without facit (Core)**, and **what is claimed/derived (Theory)**.

## 1) Ontology — what exists (minimal)

**Entities and primitives (no numbers, no fitting):**

- **PP (Primal Plane):** the primary arena in Core: an **infinite xy-plane** with **time as the z-axis** (z=time, not depth). Geometry is defined in PP.
- **Σ / RP (measurement screen):** a projection/sampling surface used for observation, reporting, and overlay comparisons. Σ is not the Core arena.
- **TickPulse:** discrete, **globally synchronous** update step. Each tick advances the **entire PP state** (one universe-step per tick). “Synchronous” describes the shared update schedule, not instantaneous long-range influence.
- **C30 strobing:** observation/sampling uses **30 discrete slots** per cycle.
- **A/B (Z₂):** two-strand counterpart rule (π-phase pair) in the state.
- **Z₃ sectors:** a 3-sector label used with C30 (mod-3 structure). In this release, Z₃ is treated as a sector label + phase structure, not as an extra geometric dimension.

**Ontology is intentionally small.** Anything that can be expressed as a lemma/lock lives in **Theory**, not here.

## 2) Core — facit-free evolution (machine rules)

Core is the **facit-free generator**. It produces candidates and “preferred” choices using only RT-internal rules.

### 2.1 State (discrete, with A/B)
A Core state is sampled on C30 slots and carries position/phase per strand:

- slots: \(k \in \mathbb{Z}_{30}\)
- strands: \(h \in \{A,B\}\)
- content: \((r_{i,h,k}, \psi_{i,h,k})\)

A/B rule constrains B as the counterpart of A (π-shifted phase and matched geometry), as implemented by the Core.

### 2.2 Mismatch → tension → potential
Core avoids “force-language”. Interaction is expressed as:

- **mismatch** \(\delta\) (phase/closure mismatch under gates)
- **tension** \(\sigma = \langle \mathrm{wrap}(\delta)^2 \rangle \ge 0\)
- **potential/compression field** \(\Phi\) in PP derived from \(\sigma\)

Update steps are chosen to reduce \(\sigma\) subject to constraints (no-overlap, gates, closure windows, etc.).

### 2.3 Determinism and tie-breaks
Core selection is deterministic:

1) minimize objective(s) derived from \(\sigma\)
2) apply fixed lexical tie-break order
3) use fixed, documented tie-breakers if still ambiguous

### 2.4 Gates, NEG controls, audits
Every lock/step has:

- **PASS gates** (what must hold)
- **NEG controls** (what must fail under known-bad perturbations)
- **audits** (recorded checks: A/B consistency, C30 closure, RCC constraints, etc.)

### 2.5 Core vs Compare separation (“no-facit”)
Core must not use experimental targets or overlay references.

In this release this is enforced by:

- a **runtime influence audit** that forbids reading:
  - `00_TOP/OVERLAY*`
  - any `*reference*.json`
  - any non-system path outside the repo (sandbox rule)
- determinism locks via **semantic hashes** of generated artifacts

See: `00_TOP/CORE_CONTRACT_NO_FACIT.md`.

For reviewer threat model (what is and is not covered):
- `00_TOP/RT_NO_FACIT_THREAT_MODEL_v1.md`

For concrete “trace one constant” examples:
- `00_TOP/RT_REVIEWER_TRACE_EXAMPLES_v1.md`

## 3) Theory — what is claimed/derived (lemmas + locks)

Theory is where RT becomes specific and testable.

### 3.1 Lemmas (structure that follows from Core + ontology)
Examples included in this release:

- Z₃ real-mode weight \((2,-1,-1)\) (unique up to scale/permutation)
- Z₂×Z₃ closure ⇒ Z₆ (π/3 quantisation)
- compatibility statements linking C30, Z₃, and \(\rho\)

See: `00_TOP/RT_Z3_Z6_RHO_LEMMAS_v1.md`.

### 3.2 Locks (derivation pipelines)
Locks are the executable theory chain that produces **DERIVED / CANDIDATE / HYP / BLANK** states toward SM29.

- Implementation: `00_TOP/LOCKS/**`
- Generated indexes and pages: `out/SM_PARAM_INDEX/*` and `out/SM29_PAGES.md`

### 3.3 Compare/Overlay (validation only)
Compare is allowed to read overlay references to produce **AGREES / TENSION** classifications.

- Overlay lives in: `00_TOP/OVERLAY/**`
- Compare runner: `00_TOP/TOOLS/run_compare_suite.py`

**κ (kappa)** is treated as an **overlay-only anchor** in this release.

## 4) Where each layer lives (files)

**Ontology:**
- `00_TOP/RT_ONTOLOGY_MAP_AND_GLOSSARY_v1.md`
- `00_TOP/RT_V7_EXPLAIN_RT_AND_ONTOLOGY_v1.md`

**Core (policy + machinery):**
- `00_TOP/CORE_CONTRACT_NO_FACIT.md`
- `00_TOP/TOOLS/run_core_no_facit_suite.py`
- `00_TOP/TOOLS/influence_audit.py`

**Theory (lemmas + locks + reports):**
- `00_TOP/RT_Z3_Z6_RHO_LEMMAS_v1.md`
- `00_TOP/RT_POSTULATES_VS_LOCKED_DISCOVERIES_v1_1.md`
- `00_TOP/LOCKS/**`
- `out/SM29_PAGES.md`

## 5) Reader path (minimal)

1) `START_HERE.md`
2) this file (foundation)
3) `00_TOP/RythmTheory_for_interested.md`
4) `00_TOP/RT_POSTULATES_VS_LOCKED_DISCOVERIES_v1_1.md`
5) `00_TOP/RT_Z3_Z6_RHO_LEMMAS_v1.md`
6) run `bash verify_all.sh` and open `out/SM29_PAGES.md`

Optional reviewer helpers:
- `00_TOP/RT_NO_FACIT_THREAT_MODEL_v1.md`
- `00_TOP/RT_REVIEWER_TRACE_EXAMPLES_v1.md`
