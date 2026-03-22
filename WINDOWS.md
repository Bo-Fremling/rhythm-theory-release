# Windows notes

## Recommended path

The cleanest way to run the RT release on **Windows 11** is:

1. install **WSL** with Ubuntu
2. open the repository inside WSL
3. run:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
bash verify_all.sh
```

## Why this is recommended

The current top-level verification entrypoints are **bash wrappers**:

- `verify_all.sh`
- `verify_core.sh`
- `verify_compare.sh`

That is why Linux/WSL is the least noisy environment.

## Native Windows option

Native Windows can still work, but it is more sensitive to shell setup.

### Step 1
Install **Python 3.8+**.

### Step 2
Install dependencies:

```powershell
py -m pip install -r requirements.txt
```

### Step 3
If `bash` is available in PATH, run:

```powershell
bash verify_all.sh
```

This is commonly available through **Git Bash**.

## If Windows prints many shell errors

That usually means the shell layer is the problem, not the RT code itself.

Typical cause:
- Python is installed
- packages are installed
- but `bash` is missing, or PATH/shell behavior is inconsistent

## Bottom line

- **Best path:** WSL + Ubuntu
- **Possible path:** native Windows + Git Bash
- **Least recommended:** plain Windows shell without bash

See also:
- `INSTALL.md`
- `START_HERE.md`
- `VERIFY.md`
