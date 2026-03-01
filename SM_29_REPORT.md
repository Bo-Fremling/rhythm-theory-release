# SM29 — Executive status (Core-first)

Generated: 2026-03-01

## Core/Compare contract (read first)

- **Core** is facit-free: it must not read `00_TOP/OVERLAY/**`, `*reference*.json`, PDG/CODATA/targets files, nor score/optimize against external values.
- **Compare** is the only place where external references appear, and Compare must not feed back into Core.
- κ is **overlay-only** (an anchor) and is UNTESTED by policy.

## How to regenerate

Regenerate by running the verification chain described in `START_HERE.md` (Quick start).

It regenerates the reviewer artifacts:

- `00_TOP/LOCKS/SM_PARAM_INDEX/SM_29_REPORT.md`
- `out/SM29_PAGES.md`
- (Overlay-triage, does not affect Core): `out/SM_PARAM_INDEX/sm29_data_match_*`

Note: `verify_core.sh` deletes `out/` at the start.

## Where to read the derivation

- Reviewer report (A4-first + sector pages): `out/SM29_PAGES.md`
- Core/Compare indices: `out/CORE_SM29_INDEX/` and `out/COMPARE_SM29_INDEX/`

## Files in this package

- κ (overlay-only anchor): `00_TOP/OVERLAY/kappa_global.json`
- Overlay-only reference files (never read by Core):
  - `00_TOP/OVERLAY/alpha_reference.json`
  - `00_TOP/OVERLAY/z0_reference.json`
  - `00_TOP/OVERLAY/sm29_data_reference_v0_2.json`
  - `00_TOP/OVERLAY/RT_OVERLAY_PPN_GAMMA_BETA_v1_2026-02-05.md`

## Quick summary

### Core/Compare index pipeline (facit-separation)

- core_index: `out/CORE_SM29_INDEX/sm29_core_index_v0_11.json`
- compare_index: `out/COMPARE_SM29_INDEX/sm29_compare_index_v0_9.json`

Core derivation-status:

- DERIVED: 28
- BLANK: 1

Compare validation-status:

- AGREES: 27
- TENSION: 1
- UNTESTED: 1

TENSION (mismatch trots DERIVED):

- Down‑kvarkmassa

Overlay guard (Core must not read overlay refs):

- Guard status: **PASS**
- tail:

  - PASS: No overlay-ref usage detected in Core locks.

## Numerical freezes (overlay-only anchors)

### κ (global SI morphism, Overlay-only)

- κ_L = 1.0897727757392728e-15 m/RT  (=1.0897727757392728 fm/RT)
- κ_T = 3.6350906991104915e-24 s/RT  (convention: κ_T = κ_L / c)
- freeze_date: 2026-02-07
- freeze_source: `00_TOP/OVERLAY/KAPPA_GLOBAL_FREEZE_2026-02-07.json`

Traceability:
- `00_TOP/LOCKS/SM_PARAM_INDEX/KAPPA_FREEZE.md`

### PPN (Core/Compare) — GR baseline check

- γ_PPN = MISSING
- β_PPN = MISSING

## Computed SM29 status table (authoritative)

This table is generated from the latest **Core** and **Compare** index artifacts.
It is the most reliable snapshot for this zip because it is produced by the same pipeline that Compare executes.
- Core index: `out/CORE_SM29_INDEX/sm29_core_index_v0_11.json`
- Compare index: `out/COMPARE_SM29_INDEX/sm29_compare_index_v0_9.json`

| Parameter | Core derivation | Core scope | Compare | Compare checks (summary) |
|---|---:|---:|---:|---|
| Elektronmassa | DERIVED | RATIO_ONLY_OVERLAY_ANCHOR | AGREES | m_mu_over_m_e: OK; m_tau_over_m_mu: OK |
| Muonmassa | DERIVED | RATIO_ONLY_OVERLAY_ANCHOR | AGREES | m_mu_over_m_e: OK; m_tau_over_m_mu: OK |
| Taumassa | DERIVED | RATIO_ONLY_OVERLAY_ANCHOR | AGREES | m_mu_over_m_e: OK; m_tau_over_m_mu: OK |
| Up‑kvarkmassa | DERIVED | PROXY_RATIO_ONLY_OVERLAY_ANCHOR | AGREES | m_u_over_m_c: OK |
| Down‑kvarkmassa | DERIVED | PROXY_RATIO_ONLY_OVERLAY_ANCHOR | TENSION | m_d_over_m_s: FAIL |
| Charm‑kvarkmassa | DERIVED | PROXY_RATIO_ONLY_OVERLAY_ANCHOR | AGREES | m_c_over_m_t: OK |
| Strange‑kvarkmassa | DERIVED | PROXY_RATIO_ONLY_OVERLAY_ANCHOR | AGREES | m_s_over_m_b: OK |
| Top‑kvarkmassa | DERIVED | PROXY_RATIO_ONLY_OVERLAY_ANCHOR | AGREES | m_t_over_m_c: OK |
| Bottom‑kvarkmassa | DERIVED | PROXY_RATIO_ONLY_OVERLAY_ANCHOR | AGREES | m_b_over_m_s: OK |
| Neutrino‑massa 1 | DERIVED | RATIO_ONLY_OVERLAY_ANCHOR | AGREES | nu_dm2_ratio_31_over_21: OK |
| Neutrino‑massa 2 | DERIVED | RATIO_ONLY_OVERLAY_ANCHOR | AGREES | nu_dm2_ratio_31_over_21: OK |
| Neutrino‑massa 3 | DERIVED | RATIO_ONLY_OVERLAY_ANCHOR | AGREES | nu_dm2_ratio_31_over_21: OK |
| EM‑koppling (α) | DERIVED | FULL_CORE | AGREES | alpha: OK |
| Svag koppling (g) | DERIVED | FULL_CORE | AGREES | ew_g_tree_Q0: OK |
| Stark koppling (g_s) | DERIVED | FULL_CORE | AGREES | strong_proxy_gate: OK |
| CKM vinkel 1 | DERIVED | FULL_CORE | AGREES | ckm_theta12_deg: OK |
| CKM vinkel 2 | DERIVED | FULL_CORE | AGREES | ckm_theta23_deg: OK |
| CKM vinkel 3 | DERIVED | FULL_CORE | AGREES | ckm_theta13_deg: OK |
| CKM CP‑fas | DERIVED | FULL_CORE | AGREES | ckm_delta_deg: OK; ckm_J: OK |
| PMNS vinkel 1 | DERIVED | FULL_CORE | AGREES | pmns_theta12_deg: OK |
| PMNS vinkel 2 | DERIVED | FULL_CORE | AGREES | pmns_theta23_deg: OK |
| PMNS vinkel 3 | DERIVED | FULL_CORE | AGREES | pmns_theta13_deg: OK |
| PMNS CP‑fas | DERIVED | FULL_CORE | AGREES | pmns_delta_deg: OK |
| Higgs‑massa | DERIVED | FULL_CORE | AGREES | higgs_struct_gate: OK |
| Higgs‑VEV (v) | DERIVED | FULL_CORE | AGREES | higgs_struct_gate: OK |
| Stark CP‑vinkel (θ_QCD) | DERIVED | FULL_CORE | AGREES | theta_qcd_deg: OK |
| PPN γ | DERIVED | FULL_CORE | AGREES | ppn_gamma: OK |
| PPN β | DERIVED | FULL_CORE | AGREES | ppn_beta: OK |
| κ (SI‑ankare) | BLANK | OVERLAY_ONLY | UNTESTED | (no compare details) |

Interpretation notes:

- Many 'mass' parameters are represented in Core as **dimensionless ratio sets** plus exactly one Overlay energy anchor for absolute units.
- For SM29 bookkeeping, the lepton ratio set (μ/e and τ/μ) is attached to all three lepton-mass entries, so they share the same compare checks.
- Likewise, the neutrino rows represent the Δm² ratio pattern; absolute ν masses in eV remain anchor-dependent.
- Quark masses m_q(μ) are treated as **scheme-dependent overlay proxies**, not RT primary targets. See `00_TOP/LOCKS/HADRON_PROXY_LOCK/`.
- PPN entries are currently a **GR baseline sanity check** (γ=β=1) rather than an LLR-derived fit.
- κ is an **overlay-only SI morphism** (policy: frozen for reproducibility; Core does not use it for selection).

## Core compare (any-hit vs preferred-hit)

Source: `out/COMPARE_SM29_INDEX/sm29_compare_index_v0_9.json`
- Any-hit (at least one candidate within tolerance): 27/29
- Preferred-hit (the marked 'preferred' within tolerance): 27/28 (unknown for the rest)

## Next locks that unlock the remaining work

1) FLAVOR_LOCK (u/d) PASS+NEG ⇒ CKM + quark-mass-ratios (runner v0.2 recommended)
   - `00_TOP/LOCKS/FLAVOR_LOCK/FLAVOR_LOCK_U_D_SPEC_v0_1.md`
2) FLAVOR_LOCK (e/ν) PASS+NEG ⇒ PMNS + lepton/ν-ratios
   - `00_TOP/LOCKS/FLAVOR_LOCK/FLAVOR_LOCK_E_NU_SPEC_v0_1.md`
3) EM-LOCK (α) ⇒ define Xi_RT in Core + (later) running/normalisation; overlay consistency can already be gated
4) Exactly one energy anchor in Overlay (GeV scale) ⇒ make masses/couplings numeric

## Regeneration

See `START_HERE.md` (Quick start).
