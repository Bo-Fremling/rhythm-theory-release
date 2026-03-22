# Install and run

This page is for **environment setup** and **platform notes**.
For the release entry flow, see `START_HERE.md`.
For verification scope, see `VERIFY.md`.

## Tested baseline

- **Ubuntu 20.04**: known-good path
- **Windows 11**: can work, but the cleanest route is **WSL (Ubuntu)**

## Python

Use **Python 3.8+**.

Install minimal runtime dependencies:

```bash
pip install -r requirements.txt
```

Current minimal dependencies:
- `numpy>=1.20`
- `matplotlib>=3.3`

## Ubuntu 20.04 / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
bash verify_all.sh
```

Alternative:

```bash
bash verify_core.sh
bash verify_compare.sh
```

## Windows 11

### Recommended path: WSL

1. Install **WSL** with Ubuntu.
2. Open the repo inside WSL.
3. Run the same commands as on Ubuntu/Linux.

This is the recommended path because the current top-level verification entrypoints are bash wrappers.

### Native Windows path

Native Windows can work, but may produce extra shell-related noise if `bash` is not available.

Suggested setup:

1. Install **Python 3.8+**
2. Install dependencies:

```powershell
py -m pip install -r requirements.txt
```

3. If `bash` is available (for example through Git Bash), run:

```powershell
bash verify_all.sh
```

4. If `bash` is **not** available, use:

```powershell
powershell -ExecutionPolicy Bypass -File .\verify_all.ps1
```

## Notes

- `verify_all.sh`, `verify_core.sh`, and `verify_compare.sh` are bash entrypoints.
- On Windows, **WSL is preferred** for the cleanest verification experience.
- The release zip under GitHub Releases is still the exact published release snapshot. These repo docs are there to make setup clearer.
