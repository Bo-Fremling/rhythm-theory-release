# Rhythm Theory (RT) — public repository

This repository hosts the public RT release by **Bo Fremling**.

For the release snapshot and official release asset, see:
- **Releases**: `v1.0.1`

For the in-repo entry point, see:
- **START_HERE.md**
- **VERIFY.md**
- **INSTALL.md**

## What this repository is

RT is an ontology-first attempt to derive physics from discrete rhythm (**TickPulse**), geometry (**PP**), and a readout boundary (**RP**), rather than from fitted parameters.

The release is set up to be reviewable without authority:
- deterministic runs,
- audit logs,
- negative controls,
- a hard separation between facit-free derivation (**Core**) and comparison (**Compare/Overlay**).

## Quick start

From the **Release root** (the directory that contains `00_TOP/`):

### Ubuntu / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
bash verify_all.sh
```

Expected final line:

```text
ALL_VERIFY: PASS
```

### Windows 11

**Recommended:** use **WSL (Ubuntu)** and run the same commands as above.

If you prefer a native Windows shell, install Python 3 and the packages from `requirements.txt` first, then read:
- `INSTALL.md`
- `verify_all.ps1`

## Important note about Windows

The current top-level verification entrypoints are **bash wrappers**:
- `verify_all.sh`
- `verify_core.sh`
- `verify_compare.sh`

That means Linux/WSL is the cleanest path today.

## What to read after running

Open:
- `out/SM29_PAGES.md`
- `00_TOP/LOCKS/SM_PARAM_INDEX/SM_29_REPORT.md`

## Scope note

The attached **release zip** under GitHub Releases is the exact release snapshot.
This repository branch may contain small post-release documentation or usability improvements.
