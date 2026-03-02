# Explanation: RT and the current ontology (Release / V7)

**Recommended start:** read `00_TOP/RT_POSTULATES_VS_LOCKED_DISCOVERIES_v1_1.md` and `00_TOP/RT_ONTOLOGY_MAP_AND_GLOSSARY_v1.md` first.

This note explains RT in two layers:
- **A) Narrative** (human-readable but precise)
- **B) Technical core** (lemmas / definitions as used by the current verification suite)

Rule: the derivation is **Core-first**. SI/κ belong to **Overlay** and are used only for after-the-fact comparison.

---

## A) Narrative

### 1) Ontology: PP and RP/Σ
- **PP (Primal Plane)** is the primary arena. Objects are defined in PP and write traces as curves in PP; time is the z-axis.
- **RP/Σ** is a *measurement screen*: the full curve is not observed; a sampled projection is observed.
- The default sampling is **C30**: 30 discrete sample directions per turn.

### 2) What “objects” are in RT
- A **spiral/helix** is a track (a path), not a spinning rigid thing.
- A **TP** is a moving phase-coupled object that advances one tick at a time.
- Composite objects (like “tp-A”) are phase-coupled bundles.

### 3) Discrete labels that do the work
The current pipeline uses discrete structure as gates:
- **C30 / K=30** (strobe lattice)
- **A/B (Z2)** (two strands related by π)
- **Z3** (sector/ledger structure)
- **wrap** for phase differences (a strict branch-cut convention)

### 4) TickPulse as the driver
TickPulse is the discrete update rule. In Core, it is treated as:
- a deterministic step operator that advances state,
- a **globally synchronous** schedule (the entire PP state advances together tick-by-tick),
- with an internal mismatch measure (wrapped phase differences),
- and a preference for states that reduce mismatch.

### 5) δ, phase tension σ, and Φ (Core language)
When two phase-coupled structures are not aligned, this yields a wrapped mismatch δ.
From δ, the following are built:
- a nonnegative **tension** σ (a “compression cost”)
- a potential field **Φ** that summarizes σ in space

This is the Core mechanism that later, in Overlay, can be rendered as familiar “attraction/repulsion” effects.

### 6) Gates and NEG controls
A claim is considered “locked” only if it has:
- a discrete definition,
- an audit trail,
- **NEG controls** (known-fail variants: K=29/31, AB mismatch, etc).

---

## B) Technical core (as used by this Release)

### Lemma 1 — C30 strobe
Sampling points are fixed:
uₖ = 2πk/30, k ∈ {0,…,29}.

### Lemma 1b — Z3 sectors on the C30 lattice
Sector labels are s(k)=k mod 3. A Z3 phase offset ±2π/3 equals ±10 steps on the C30 lattice (exact identity, no approximation).
Details: `00_TOP/RT_Z3_Z6_RHO_LEMMAS_v1.md`.

### Lemma 2 — Wrapped phase difference
All phase differences are reduced by the normative wrap convention:
wrap(x) ∈ [-π, π), with wrap(π)=wrap(-π)=-π.

### Definition 3 — Core/Compare separation
- Core: `*_coregen.py` and anything that writes `out/CORE_*`.
- Compare: `*_compare.py` and anything that writes `out/COMPARE_*` and may read overlay refs.

### Definition 4 — “Derived” in SM29
A parameter is **DERIVED** when Core:
- generates a candidate set and a preferred choice by RT-internal rules,
- logs audits/NEG,
- and writes a stable entry into `out/CORE_SM29_INDEX/`.

(Compare can later validate; Compare validation does not change Core status.)

---

## How SM29 is produced in this Release
1) Core suite generates Core artifacts and the Core SM29 index.
2) Compare suite generates Compare artifacts and the Compare SM29 index.
3) Data-match produces an overlay triage summary.
4) Report/pages assemble the public reviewer packet:

- `00_TOP/LOCKS/SM_PARAM_INDEX/SM_29_REPORT.md`
- `out/SM29_PAGES.md`

Run it with:

```bash
bash verify_all.sh
```

---

## Status (short)
The current run status is always defined by the generated outputs:
- Core audit: `out/CORE_AUDIT/`
- Core index: `out/CORE_SM29_INDEX/`
- Compare audit/index: `out/COMPARE_AUDIT/`, `out/COMPARE_SM29_INDEX/`
- Executive summary: `00_TOP/LOCKS/SM_PARAM_INDEX/SM_29_REPORT.md`
