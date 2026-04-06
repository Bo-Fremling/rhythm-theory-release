# Internal changelog

## 2026-04-06

- FLAVOR canonical policy changed from implicit small-scan / full-forbidden behavior to full-scan default with `--no-full` opt-out.
- `FLAVOR_SEED_STABILITY_LOCK`, `FLAVOR_MULTI_SEED_STABILITY_LOCK`, and `FLAVOR_TOP_STABILITY_LOCK` were updated to follow the same canonical full-scan policy and metadata checks.
- `QUARK_PROXY_NEG_LOCK` now records degenerate NEG cases as non-fatal soft issues instead of hard failures.
- `QUARK_PROXY_LOCK` preferred selection was updated for the full-scan FLAVOR canonical while remaining Core-internal and facit-free.
- Local verification after these changes reported `CORE_VERIFY: PASS`, `COMPARE_VERIFY: PASS`, `ALL_VERIFY: PASS`, core counts `DERIVED=28, BLANK=1`, and compare counts `AGREES=28, UNTESTED=1`.
