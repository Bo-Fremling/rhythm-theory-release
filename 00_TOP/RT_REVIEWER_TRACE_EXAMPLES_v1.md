# RT (Release) — Reviewer Trace Examples (v1)

Purpose: show how to trace one derived quantity end‑to‑end *without* using external references.

## General method (works for any SM29 entry)

1) Run `bash verify_all.sh`.
2) Open the latest core index:
   * `out/CORE_SM29_INDEX/sm29_core_index_*.json` (pick the newest)
3) Find the entry you care about; note:
   * `derivation_status`
   * `preferred` (candidate id + expression)
   * `sources` / `promotion_rule` / any `depends_on`
4) Jump to the producing LOCK(s) under `00_TOP/LOCKS/<LOCK_NAME>/` and open:
   * `*_coregen.py` (how the candidate space is generated)
   * the latest `out/CORE_<LOCK_NAME>/*.json` (what was generated)
5) Only after Core is complete: compare using `out/COMPARE_SM29_INDEX/sm29_compare_index_*.json`.

## Example A — EM coupling (α)

This example is useful because it involves:
* a derived invariant,
* a candidate family,
* and a deterministic reduction step.

### Step A1 — the invariant (duty = 20/21)

LOCK:
* `00_TOP/LOCKS/EM_XI_INVARIANT_LOCK/em_xi_invariant_lock_coregen.py`

Core artifact:
* `out/CORE_EM_XI_INVARIANT_LOCK/em_xi_invariant_lock_core_*.json`

The invariant is derived purely from Core integers (cap/superpacket structure). In the index it is used as a *promotion trigger* for later reductions.

### Step A2 — candidate space for Ξ_RT / α

LOCK:
* `00_TOP/LOCKS/EM_LOCK/em_lock_coregen.py`

Core artifacts:
* `out/CORE_EM_LOCK/em_lock_core_*.json`

This LOCK generates a deterministic candidate list (families), with no scoring against PDG/CODATA.

### Step A3 — uniqueness (consistency reduction)

LOCK:
* `00_TOP/LOCKS/SM29_CONSISTENCY_LOCK/sm29_consistency_lock_coregen.py`

Core artifacts:
* `out/CORE_SM29_CONSISTENCY_LOCK/sm29_consistency_lock_core_*.json`

The reduction uses only internal gates (e.g. Z3/C30 consistency) plus the previously DERIVED duty‑invariant. The result is a single preferred α expression in the core index.

### Step A4 — where to point a reviewer

* Core index entry: `out/CORE_SM29_INDEX/sm29_core_index_*.json` (parameter “EM coupling (α)”).
* Compare entry (optional): `out/COMPARE_SM29_INDEX/sm29_compare_index_*.json`.

## Example B — weak coupling (g) as an inherited singleton

In this release, `g` is computed from the preferred α together with the electroweak mixing relation used in the SM29 chain.

Where to verify:
* Core index entry: `out/CORE_SM29_INDEX/sm29_core_index_*.json` (parameter “weak coupling (g)”).

What to check:
* `depends_on` includes the α entry.
* The preferred expression for `g` is a deterministic transform of the preferred α (no extra “fit” step).

## Why this matters

These traces show reviewers the difference between:
* **candidate generation** (Core‑internal, facit‑free),
* **deterministic reduction** (internal gates/tie‑break), and
* **comparison** (overlay only).
