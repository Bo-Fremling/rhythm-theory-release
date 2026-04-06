# Python verification

A cross-platform Python verifier is available directly in the **Release root**.

## Full verification

### Windows

```bash
python verify_all.py
```

### Linux / Ubuntu / WSL

```bash
python3 verify_all.py
```

## Core only

### Windows

```bash
python verify_all.py --core-only
```

### Linux / Ubuntu / WSL

```bash
python3 verify_all.py --core-only
```

## Compare only

### Windows

```bash
python verify_all.py --compare-only
```

### Linux / Ubuntu / WSL

```bash
python3 verify_all.py --compare-only
```

## Why this exists

`verify_all.py` runs the same verification pipeline as the release bash entrypoint, but without requiring a bash-first workflow.
This is especially useful on Windows or on systems where shell setup adds unnecessary friction.

## Related entrypoints

- Linux / WSL alternative: `bash verify_all.sh`
- Linux / WSL optional split wrappers: `bash verify_core.sh`, `bash verify_compare.sh`

## Expected final line

```text
ALL_VERIFY: PASS
```
