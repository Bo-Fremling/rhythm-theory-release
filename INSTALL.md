# Install and run

This page is for **environment setup** and **platform notes**.
For the release entry flow, see `START_HERE.md`.
For verification scope, see `VERIFY.md`.

## Tested baseline

- **Ubuntu 20.04**: known-good path
- **Windows 11**: supported; **WSL (Ubuntu)** is still the cleanest route

## Python

Use **Python 3.8+**.

Install minimal runtime dependencies:

```bash
python -m pip install -r requirements.txt
```

Current minimal dependencies:
- `numpy>=1.20`
- `matplotlib>=3.3`

## Ubuntu 20.04 / Linux / WSL

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python3 verify_all.py
```

Alternative:

```bash
bash verify_all.sh
```

Optional split wrappers:

```bash
bash verify_core.sh
bash verify_compare.sh
```

## Windows 11

### Recommended path: WSL

1. Install **WSL** with Ubuntu.
2. Open the repo inside WSL.
3. Run the same commands as on Ubuntu/Linux.

This is still the cleanest route if you want the least shell and path noise.

### Native Windows path

1. Install **Python 3.8+**.
2. Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

3. Run verification:

```powershell
python verify_all.py
```

## Notes

- `verify_all.py` is the cross-platform verifier in the Release root.
- `verify_all.sh`, `verify_core.sh`, and `verify_compare.sh` remain available as bash entrypoints on Linux / WSL.
- The release zip under GitHub Releases is still the exact published release snapshot. These repo docs are there to make setup clearer.
