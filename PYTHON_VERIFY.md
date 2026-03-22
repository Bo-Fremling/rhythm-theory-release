# Python verification entrypoints

A cross-platform Python path is available in parallel with the existing bash wrappers.

## Full verification

```bash
python verify/verify_all.py
```

## Core only

```bash
python verify/verify_core.py
```

## Compare only

```bash
python verify/verify_compare.py
```

## Why this exists

The original top-level entrypoints are bash wrappers:
- `verify_all.sh`
- `verify_core.sh`
- `verify_compare.sh`

Those work well on Ubuntu/Linux, but can be noisy on Windows.
The Python entrypoints are meant to reduce that shell friction without changing the verification logic.

## Recommended use

- **Ubuntu/Linux:** `bash verify_all.sh` is still fine.
- **Windows 11:** prefer `python verify/verify_all.py` after installing dependencies.

## Expected final line

```text
ALL_VERIFY: PASS
```
