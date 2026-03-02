# RT Core Contract — NO-FACIT (canonical)

version: 1.1  
as_of: 2026-02-19  
scope: **Core** = all `*_coregen.py` and anything that writes `out/CORE_*`.

## HARD FAIL (Core must not do this)

forbidden_roots (prefix-based):
- `00_TOP/OVERLAY*`   # blocks OVERLAY, OVERLAY__OFF, OVERLAY__STUBBED__, etc.

forbidden_file_globs:
- `*reference*.json`   # e.g. alpha/z0/sm29_data_reference

forbidden_data_sources:
- PDG/CODATA/targets (any format/filename)

forbidden_behaviors:
- selection/optimization/scoring/cost that uses PDG/CODATA/overlay numbers (directly or indirectly)
- numerical use of legacy/approx Bf inside Core

sandbox rule:
- Core must not open arbitrary files **outside the repo tree**.
  Only runtime/system reads (Python stdlib + site-packages + a small OS allowlist for certificates/locales) are permitted.

## Core / Overlay separation (mandatory)

required_split:
- **coregen** scripts write only `out/CORE_*` artifacts and must pass the forbidden-access audit.
- **compare** scripts write only `out/COMPARE_*` artifacts and may read overlay refs.

## Audit (must exist)

Core runs must log:
- `FORBIDDEN=0` (no forbidden reads)
- **no outside-repo opens** (audit scopes must not contain `other`)
- determinism/semhash check (two runs must match)
- NEG controls where applicable

The public entry point for the full chain in this Release is:

```bash
bash verify_all.sh
```
