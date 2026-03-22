# Start here on Windows or with Python

This page is the shortest path if you are on **Windows 11** or if you want to avoid shell friction.

## Fastest recommended path

From the **Release root** (the directory that contains `00_TOP/`):

```bash
python -m pip install -r requirements.txt
python verify/verify_all.py
```

Expected final line:

```text
ALL_VERIFY: PASS
```

## When to use this page

Use this page if:
- you are on **Windows**
- `bash verify_all.sh` gives shell-related noise
- you want the cross-platform Python entrypoint directly

## Linux / Ubuntu users

If you are on Ubuntu/Linux, the original entrypoint is still fine:

```bash
bash verify_all.sh
```

## Windows recommendation

- **Best path:** WSL + Ubuntu
- **Good path:** native Windows + `python verify/verify_all.py`
- **Least clean path:** plain Windows shell + bash wrappers only

## Related files

- `START_HERE.md`
- `INSTALL.md`
- `WINDOWS.md`
- `PYTHON_VERIFY.md`
