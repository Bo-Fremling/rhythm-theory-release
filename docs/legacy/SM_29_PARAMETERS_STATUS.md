# SM+PPN (29) — RT status (ärligt läge)

> **OBS (2026‑02‑19):** Den här tabellen är **handredigerad/legacy** och kan släpa efter.
> För maskin‑genererad, spårbar status använd:
> - `out/CORE_SM29_INDEX/sm29_core_index_v0_2.md` (Core: DERIVED/CANDIDATE‑SET/HYP/BLANK)
> - `out/COMPARE_SM29_INDEX/sm29_compare_index_v0_1.md` (Overlay: AGREES/TENSION/UNTESTED)
> 
> Dessa byggs av `sm29_index_coregen.py` och `sm29_index_compare.py`.

**RT:** PASS (låst) · CANDIDATE (spec/gated, ej beviskörd) · TODO (saknas) · STRUCT (struktur/rel, ej absolut tal)

| Param | RT | RT ger | Kräver |
|---|---:|---|---|
| Elektronmassa | PASS (OVERLAY) | SPEKTRUM‑ratio (e,μ,τ) | Kör FLAVOR_LOCK (e/ν) + 1 ankare |
| Muonmassa | PASS (CORE‑RATIO) | SPEKTRUM‑ratio (μ/e) | LEPTON_MASS_LOCK v0.5 + 1 ankare |
| Taumassa | PASS (CORE‑RATIO) | SPEKTRUM‑ratio (τ/μ) | LEPTON_MASS_LOCK v0.5 + 1 ankare |
| Up‑kvarkmassa | CANDIDATE (OVERLAY) | SPEKTRUM‑ratio (u,c,t) | Kör FLAVOR_LOCK (u/d) + 1 ankare |
| Down‑kvarkmassa | CANDIDATE (OVERLAY) | SPEKTRUM‑ratio (d,s,b) | FLAVOR_LOCK (u/d) + ankare |
| Charm‑kvarkmassa | CANDIDATE (OVERLAY) | SPEKTRUM‑ratio | FLAVOR_LOCK (u/d) + ankare |
| Strange‑kvarkmassa | CANDIDATE (OVERLAY) | SPEKTRUM‑ratio | FLAVOR_LOCK (u/d) + ankare |
| Top‑kvarkmassa | CANDIDATE (OVERLAY) | SPEKTRUM‑ratio | FLAVOR_LOCK (u/d) + ankare |
| Bottom‑kvarkmassa | CANDIDATE (OVERLAY) | SPEKTRUM‑ratio | FLAVOR_LOCK (u/d) + ankare |
| Neutrino‑massa 1 | CANDIDATE | ν‑mönster + ratios (eV efter ankare) | ν‑mekanism‑LOCK + FLAVOR_LOCK (e/ν) |
| Neutrino‑massa 2 | CANDIDATE | ν‑mönster + ratios | ν‑mekanism‑LOCK + FLAVOR_LOCK (e/ν) |
| Neutrino‑massa 3 | CANDIDATE | ν‑mönster + ratios | ν‑mekanism‑LOCK + FLAVOR_LOCK (e/ν) |
| EM‑koppling (α) | PASS (OVERLAY) | Overlay‑numerik (refs) med gate PASS; Core‑Xi_RT saknas | EM‑LOCK körd (se `out/EM_LOCK/em_lock_summary_v0_2.md`); definiera Xi_RT i Core + ev. running/korrelator |
| Svag koppling (g) | CANDIDATE (OVERLAY) | g_tree(Q→0) från α + sin²θ_W=1/4 (LO) | EW_COUPLING_LOCK (tree-level); running/normalisering till g(μ=m_Z) = TODO |
| Stark koppling (g_s) | STRUCT | SU(3) struktur/klass | g_s(μ): RT‑skala + running + confinement‑proxy |
| CKM vinkel 1 | PASS (CORE) | CKM från U_u†U_d | FLAVOR_LOCK v0.34 (CKM PASS) + NEG |
| CKM vinkel 2 | PASS (CORE) | CKM | FLAVOR_LOCK v0.34 (CKM PASS) + NEG |
| CKM vinkel 3 | PASS (CORE) | CKM | FLAVOR_LOCK v0.34 (CKM PASS) + NEG |
| CKM CP‑fas | PASS (CORE) | CKM CP‑fas, J | FLAVOR_LOCK v0.34 (CKM PASS) + CP‑NEG |
| PMNS vinkel 1 | PASS (CORE) | PMNS från U_e†U_ν | Kör FLAVOR_LOCK (e/ν) (PASS+NEG) |
| PMNS vinkel 2 | PASS (CORE) | PMNS | FLAVOR_LOCK (e/ν) |
| PMNS vinkel 3 | PASS (CORE) | PMNS | FLAVOR_LOCK v0.34 + NEG |
| PMNS CP‑fas | PASS (CORE) | PMNS CP‑fas | FLAVOR_LOCK (e/ν) + CP‑NEG |
| Higgs‑massa | STRUCT | Minimal Higgs-innehåll låst | Higgs‑potential/kvantisering ⇒ m_H; + ankare för GeV |
| Higgs‑VEV (v) | STRUCT | SSB‑ram/normalisering | VEV‑LOCK ⇒ v; + ankare för GeV |
| Stark CP‑vinkel (θ_QCD) | CANDIDATE | Förväntas låsas nära 0 | θ‑LOCK (diskret/symmetri) + NEG |
| PPN γ | PASS | γ_PPN=1 (LOCK) | — |
| PPN β | PASS | β_PPN=1 (LOCK) | — |
| κ (SI‑ankare) | PASS (FROZEN) | κ_L global längd‑morfism (Overlay) | Fryst via r_E^p‑ankare; se `00_TOP/LOCKS/SM_PARAM_INDEX/KAPPA_FREEZE.md` |
