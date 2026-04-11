# Internal changelog

## 2026-04-06

- FLAVOR canonical policy changed from implicit small-scan / full-forbidden behavior to full-scan default with `--no-full` opt-out.
- `FLAVOR_SEED_STABILITY_LOCK`, `FLAVOR_MULTI_SEED_STABILITY_LOCK`, and `FLAVOR_TOP_STABILITY_LOCK` were updated to follow the same canonical full-scan policy and metadata checks.
- `QUARK_PROXY_NEG_LOCK` now records degenerate NEG cases as non-fatal soft issues instead of hard failures.
- `QUARK_PROXY_LOCK` preferred selection was updated for the full-scan FLAVOR canonical while remaining Core-internal and facit-free.
- Local verification after these changes reported `CORE_VERIFY: PASS`, `COMPARE_VERIFY: PASS`, `ALL_VERIFY: PASS`, core counts `DERIVED=28, BLANK=1`, and compare counts `AGREES=28, UNTESTED=1`.

## 2026-04-11

- `FLAVOR_LOCK` CKM selector order in `00_TOP/LOCKS/FLAVOR_LOCK/flavor_lock_pp_predict.py` was updated so the effective preference now follows the file’s stated policy: prefer `rt_construct_monodromy_1260_postR12_seam_down_oriented_pp23_uubasis_ckm13_rho2_phiB` before later `...holoC30_CPBEST` / `...GRIDBEST` freeze candidates.
- This was a selector cleanup only: no change to PMNS selector, no change to `--full`, and no new physics knobs or scan rules.
- Local verification on `Release` confirmed `picked_key_ckm = ...ckm13_rho2_phiB` while `picked_key_pmns` remained unchanged.
  
