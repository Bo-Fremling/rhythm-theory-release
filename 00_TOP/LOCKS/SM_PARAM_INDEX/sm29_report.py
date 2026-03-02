#!/usr/bin/env python3
"""SM+PPN(29) status report generator.

Creates a single markdown report that:
  - lists the 29 parameters and their current RT status (PASS/CANDIDATE/TODO/STRUCT)
  - pulls numeric frozen overlay values where available (κ)
  - points to the exact lock/spec files that justify PASS items

Usage (from repo root):
  python3 00_TOP/LOCKS/SM_PARAM_INDEX/sm29_report.py

Outputs:
  00_TOP/LOCKS/SM_PARAM_INDEX/SM_29_REPORT.md

Policy:
  - Core contains no SI anchors or numbers.
  - κ is Overlay-only and read from 00_TOP/OVERLAY/kappa_global.json.
"""

from __future__ import annotations

import json
import glob
import math
import cmath
import os
import re
import subprocess
import textwrap
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Optional: Overlay-only data-match triage (✅/❌/🟡)
try:
    from sm29_data_match import write_artifacts as _sm29_write_data_match_artifacts
except Exception:
    _sm29_write_data_match_artifacts = None


@dataclass(frozen=True)
class Row:
    param: str
    rt: str
    rt_ger: str
    kraver: str


def _rt_motsvarighet(param_name: str) -> str:
    """Heuristic tag: does RT have a *native* counterpart for this SM parameter *yet*?

    IMPORTANT: Conservative triage only. Never claims agreement with external data.
    """
    p = param_name.strip()

    if p.startswith("CKM") or p.startswith("PMNS"):
        return "Direct (Core)"
    if p.startswith("PPN"):
        return "Overlay comparison"
    if p.startswith("κ"):
        return "Overlay-only"
    if "EM‑koppling" in p or "(α" in p or p.endswith("(α)"):
        return "Indirect (Overlay)"
    if p.startswith("Svag koppling"):
        return "Indirect (LO)"
    if p.startswith("Stark koppling"):
        return "Scaffold (running/proxy)"
    if p.startswith("Stark CP"):
        return "Missing/Unclear"
    if p.startswith("Higgs"):
        return "Partial (structure)"
    if p.startswith("Neutrino"):
        return "Scaffold (ν-lock)"

    # Masses: RT currently produces ratios/modes; absolute scale is Overlay.
    # Quark masses in MSbar are scheme-dependent and treated as Overlay proxies.
    if "kvarkmassa" in p:
        return "Scheme parameter (Overlay proxy; not a Core target)"
    if p.endswith("massa"):
        return "Indirect (mode→anchor)"

    return "Unclear"



def _rt_krav(param_name: str, repo_root: Path) -> str:
    """Return a hard RT requirement pointer (lemma/object file + id) or 'Missing'.

    This is *not* a claim of data agreement; it is a reproducible pointer for what
    must exist/run to justify the row.
    """

    def rel(p: Path) -> str:
        return str(p.relative_to(repo_root)).replace("\\", "/")

    # Canonical pointers (keep stable across zips if possible)
    P_FLAVOR_UD = repo_root / "00_TOP/LOCKS/FLAVOR_LOCK/FLAVOR_LOCK_U_D_SPEC_v0_1.md"
    P_FLAVOR_ENU = repo_root / "00_TOP/LOCKS/FLAVOR_LOCK/FLAVOR_LOCK_E_NU_SPEC_v0_1.md"
    P_FLAVOR_VERIFY = repo_root / "00_TOP/LOCKS/FLAVOR_LOCK/FLAVOR_LOCK_VERIFY_SPEC_v0_2.md"
    P_PHASELIFT = repo_root / "00_TOP/LOCKS/FLAVOR_LOCK/FLAVOR_LOCK_PHASE_LIFT_UNITARY_RECON_SPEC_v0_1.md"
    P_EM_SPEC = repo_root / "00_TOP/LOCKS/EM_LOCK/EM_LOCK_SPEC_v0_2.md"
    P_EM_VERIFY = repo_root / "00_TOP/LOCKS/EM_LOCK/EM_LOCK_VERIFY_SPEC_v0_1.md"
    P_EW_SPEC = repo_root / "00_TOP/LOCKS/EW_COUPLING_LOCK/EW_COUPLING_LOCK_SPEC_v0_1.md"
    P_EW_LEM = repo_root / "00_TOP/LOCKS/EW_COUPLING_LOCK/EW_GEOMETRY_LEMMA_v0_1.md"
    P_GS_SPEC = repo_root / "00_TOP/LOCKS/GS_LOCK/GS_LOCK_SPEC_v0_1.md"
    P_NU_SPEC_1 = repo_root / "00_TOP/LOCKS/NU_MECHANISM_LOCK/NU_MECHANISM_LOCK_SPEC_v0_1.md"
    P_NU_SPEC_2 = repo_root / "00_TOP/LOCKS/NU_MECHANISM_LOCK/NU_MECHANISM_LOCK_SPEC_v0_2.md"
    P_NU_SPEC_3 = repo_root / "00_TOP/LOCKS/NU_MECHANISM_LOCK/NU_MECHANISM_LOCK_SPEC_v0_3.md"
    P_HIGGS_SPEC = repo_root / "00_TOP/LOCKS/HIGGS_VEV_LOCK/HIGGS_VEV_LOCK_SPEC_v0_2.md"
    P_EA_SPEC = repo_root / "00_TOP/LOCKS/ENERGY_ANCHOR_LOCK/ENERGY_ANCHOR_LOCK_SPEC_v0_1.md"
    P_EA_FREEZE = repo_root / "00_TOP/OVERLAY/ENERGY_ANCHOR_FREEZE_2026-02-14.json"
    P_LEP_SPEC = repo_root / "00_TOP/LOCKS/LEPTON_ENGAGEMENT_LOCK/LEPTON_ENGAGEMENT_LOCK_SPEC_v0_1.md"
    P_THETA_SPEC = repo_root / "00_TOP/LOCKS/THETA_QCD_LOCK/THETA_QCD_LOCK_SPEC_v0_1.md"
    P_PPN = repo_root / "00_TOP/OVERLAY/RT_OVERLAY_PPN_GAMMA_BETA_v1_2026-02-05.md"
    P_KAPPA = repo_root / "00_TOP/LOCKS/SM_PARAM_INDEX/KAPPA_FREEZE.md"
    P_MIS = repo_root / "00_TOP/LOCKS/SM_PARAM_INDEX/SM29_MISALIGNMENT_SPEC_v0_1.md"

    p = param_name.strip()

    # Masses (ratios in Core + 1 anchor in Overlay)
    if p in ("Elektronmassa", "Muonmassa", "Taumassa"):
        return f"{_fmt_code(rel(P_FLAVOR_ENU))} + {_fmt_code(rel(P_LEP_SPEC))} + {_fmt_code(rel(P_EA_SPEC))} + {_fmt_code(rel(P_EA_FREEZE))}"

    if "‑kvarkmassa" in p or p.endswith("kvarkmassa"):
        return f"{_fmt_code(rel(P_FLAVOR_UD))} + {_fmt_code(rel(P_EA_SPEC))} + {_fmt_code(rel(P_EA_FREEZE))}"

    # Neutrinos
    if p.startswith("Neutrino"):
        if P_NU_SPEC_3.exists():
            nu_spec = P_NU_SPEC_3
        elif P_NU_SPEC_2.exists():
            nu_spec = P_NU_SPEC_2
        else:
            nu_spec = P_NU_SPEC_1
        return f"{_fmt_code(rel(P_FLAVOR_ENU))} + {_fmt_code(rel(nu_spec))}"

    # Couplings
    if "EM‑koppling" in p or "(α" in p or "(α" in p:
        return f"{_fmt_code(rel(P_EM_SPEC))} + {_fmt_code(rel(P_EM_VERIFY))}"

    if p.startswith("Svag koppling"):
        return f"{_fmt_code(rel(P_EW_LEM))} + {_fmt_code(rel(P_EW_SPEC))} + {_fmt_code(rel(P_EM_SPEC))}"

    if p.startswith("Stark koppling"):
        return _fmt_code(rel(P_GS_SPEC))

    # Mixing
    if p.startswith("CKM"):
        return f"{_fmt_code(rel(P_MIS))} + {_fmt_code(rel(P_FLAVOR_UD))} + {_fmt_code(rel(P_FLAVOR_VERIFY))} + {_fmt_code(rel(P_PHASELIFT))}"

    if p.startswith("PMNS"):
        return f"{_fmt_code(rel(P_MIS))} + {_fmt_code(rel(P_FLAVOR_ENU))} + {_fmt_code(rel(P_FLAVOR_VERIFY))} + {_fmt_code(rel(P_PHASELIFT))}"

    # Higgs
    if p.startswith("Higgs"):
        return _fmt_code(rel(P_HIGGS_SPEC))

    # Strong CP
    if p.startswith("Stark CP") or "θ_QCD" in p:
        return _fmt_code(rel(P_THETA_SPEC))

    # PPN
    if p.startswith("PPN"):
        return _fmt_code(rel(P_PPN))

    # κ
    if p.startswith("κ"):
        return _fmt_code(rel(P_KAPPA))

    return "Missing"


def _mix_matrix_from_angles(theta12_rad: float, theta23_rad: float, theta13_rad: float, delta_rad: float):
    """PDG-style mixing matrix from angles+delta."""
    c12, s12 = math.cos(theta12_rad), math.sin(theta12_rad)
    c23, s23 = math.cos(theta23_rad), math.sin(theta23_rad)
    c13, s13 = math.cos(theta13_rad), math.sin(theta13_rad)

    em = cmath.exp(-1j * delta_rad)
    ep = cmath.exp( 1j * delta_rad)

    V11 = c12 * c13
    V12 = s12 * c13
    V13 = s13 * em

    V21 = -s12 * c23 - c12 * s23 * s13 * ep
    V22 =  c12 * c23 - s12 * s23 * s13 * ep
    V23 =  s23 * c13

    V31 =  s12 * s23 - c12 * c23 * s13 * ep
    V32 = -c12 * s23 - s12 * c23 * s13 * ep
    V33 =  c23 * c13

    return [[V11, V12, V13], [V21, V22, V23], [V31, V32, V33]]


def _misalignment_metrics(angles: dict):
    """Return (D_off, D_I) or None if angles are incomplete."""
    try:
        t12 = float(angles.get('theta12_rad'))
        t23 = float(angles.get('theta23_rad'))
        t13 = float(angles.get('theta13_rad'))
        dlt = float(angles.get('delta_rad_from_sin', 0.0))
    except Exception:
        return None

    V = _mix_matrix_from_angles(t12, t23, t13, dlt)

    # D_off = sqrt(sum_{i!=j} |V_ij|^2)
    off = 0.0
    di  = 0.0
    for i in range(3):
        for j in range(3):
            vij = V[i][j]
            a2 = (vij.real * vij.real + vij.imag * vij.imag)
            if i != j:
                off += a2
                di  += a2
            else:
                # (vij - 1)
                dr = vij.real - 1.0
                di += dr*dr + vij.imag*vij.imag

    return (math.sqrt(off), math.sqrt(di))


def _repo_root_from_here(here: Path) -> Path:
    # here = .../00_TOP/LOCKS/SM_PARAM_INDEX/sm29_report.py
    # root = .../
    return here.resolve().parents[3]


def _read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def _load_json(p: Path) -> dict:
    return json.loads(_read_text(p))


def _parse_md_table(md_text: str) -> List[Row]:
    """Parse the first markdown pipe-table in the file into Row objects."""
    lines = [ln.rstrip("\n") for ln in md_text.splitlines()]
    rows: List[Row] = []

    # Find header line containing "| Param |" then skip separator "|---".
    start = None
    for i, ln in enumerate(lines):
        if re.match(r"^\|\s*Param\s*\|", ln):
            start = i
            break
    if start is None:
        return rows

    for ln in lines[start + 2 :]:  # after header + separator
        if not ln.strip().startswith("|"):
            # end of table
            break
        parts = [p.strip() for p in ln.strip().strip("|").split("|")]
        if len(parts) < 4:
            continue
        rows.append(Row(param=parts[0], rt=parts[1], rt_ger=parts[2], kraver=parts[3]))

    return rows


def _status_counts(rows: List[Row]) -> Dict[str, int]:
    d: Dict[str, int] = {}
    for r in rows:
        key = r.rt.strip()
        d[key] = d.get(key, 0) + 1
    return dict(sorted(d.items(), key=lambda kv: (-kv[1], kv[0])))


def _scope_for_row(r: Row) -> str:
    """Coarse origin label to prevent Core/Overlay confusion in reviews."""
    p = (r.param or "").strip().lower()
    rt = (r.rt or "")
    rt_norm = rt.replace('‑', '-').replace('–', '-').replace('—', '-')
    up = rt_norm.upper()

    if p.startswith("ppn") or p.startswith("κ"):
        return "OVERLAY"

    m = re.search(r"\(([^)]+)\)", rt_norm)
    if m:
        tag = m.group(1).strip().upper().replace('‑', '-')
        if "OVERLAY" in tag or "FROZEN" in tag:
            return "OVERLAY"
        if "CORE" in tag:
            return "CORE"
        if "STRUCT" in tag:
            return "STRUCT"
        return tag

    if up.startswith("STRUCT"):
        return "STRUCT"

    return "UNKNOWN"


def _scope_counts(rows: List[Row]) -> Dict[str, int]:
    d: Dict[str, int] = {}
    for r in rows:
        s = _scope_for_row(r)
        d[s] = d.get(s, 0) + 1
    return dict(sorted(d.items(), key=lambda kv: (-kv[1], kv[0])))


def _run_overlay_guard(repo_root: Path) -> Tuple[str, List[str]]:
    """Return (status, tail_lines)."""
    guard = repo_root / "00_TOP/LOCKS/SM_PARAM_INDEX/guard_no_overlay_in_core.py"
    if not guard.exists():
        return "MISSING", []
    try:
        res = subprocess.run([sys.executable, str(guard)], cwd=str(repo_root), capture_output=True, text=True)
        out = (res.stdout or "") + (res.stderr or "")
        tail = [ln for ln in out.splitlines() if ln.strip()][-10:]
        return ("PASS" if res.returncode == 0 else f"FAIL({res.returncode})"), tail
    except Exception as e:
        return f"ERROR({type(e).__name__})", []




def _pick_latest(dirpath: Path, pattern: str) -> Optional[Path]:
    def _vk(p: Path) -> tuple[int, int]:
        m = re.search(r"_v(\d+)(?:_(\d+))?$", p.stem)
        if m:
            return (int(m.group(1)), int(m.group(2) or 0))
        return (0, 0)

    cands = list(dirpath.glob(pattern))
    return max(cands, key=_vk) if cands else None


def _load_latest_sm29_indexes(repo_root: Path) -> dict:
    """Load latest Core/Compare SM29 indexes (if present) and compute counts.

    Returns a dict with paths, counts, and lists of COMPARED/TENSION entries.
    """
    out = {
        "core_path": None,
        "compare_path": None,
        "core_counts": {},
        "compare_counts": {},
        "tension": [],
        "compared": [],
    }

    core_p = _pick_latest(repo_root / "out" / "CORE_SM29_INDEX", "sm29_core_index_v*.json")
    comp_p = _pick_latest(repo_root / "out" / "COMPARE_SM29_INDEX", "sm29_compare_index_v*.json")
    if core_p and core_p.exists():
        try:
            core = json.loads(core_p.read_text(encoding="utf-8"))
            out["core_path"] = str(core_p.relative_to(repo_root)).replace("\\", "/")
            cc = {}
            for e in (core.get("entries") or []):
                ds = str(e.get("derivation_status") or "")
                cc[ds] = cc.get(ds, 0) + 1
            out["core_counts"] = dict(sorted(cc.items(), key=lambda kv: (-kv[1], kv[0])))
        except Exception:
            pass

    if comp_p and comp_p.exists():
        try:
            comp = json.loads(comp_p.read_text(encoding="utf-8"))
            out["compare_path"] = str(comp_p.relative_to(repo_root)).replace("\\", "/")
            vc = {}
            for e in (comp.get("entries") or []):
                vs = str(e.get("validation_status") or "")
                vc[vs] = vc.get(vs, 0) + 1

                if vs == "TENSION":
                    out["tension"].append(str(e.get("parameter") or ""))
                if vs == "COMPARED":
                    out["compared"].append(str(e.get("parameter") or ""))

            out["compare_counts"] = dict(sorted(vc.items(), key=lambda kv: (-kv[1], kv[0])))
        except Exception:
            pass

    return out
def _extract_ppn_gamma_beta(ppn_md: str) -> Tuple[Optional[str], Optional[str]]:
    # Prefer explicit tokens "γ_PPN = 1" and "β_PPN = 1".
    g = None
    b = None

    mg = re.search(r"γ_PPN\s*=\s*([0-9.]+)", ppn_md)
    mb = re.search(r"β_PPN\s*=\s*([0-9.]+)", ppn_md)
    if mg:
        g = mg.group(1)
    if mb:
        b = mb.group(1)

    # Fallback: bold variants "**γ_PPN = 1**"
    if g is None:
        mg2 = re.search(r"\*\*\s*γ_PPN\s*=\s*([0-9.]+)\s*\*\*", ppn_md)
        if mg2:
            g = mg2.group(1)
    if b is None:
        mb2 = re.search(r"\*\*\s*β_PPN\s*=\s*([0-9.]+)\s*\*\*", ppn_md)
        if mb2:
            b = mb2.group(1)

    return g, b


def _fmt_code(p: str) -> str:
    return f"`{p}`"


def _param_to_datakey(param: str) -> Optional[str]:
    p = param.strip().lower()
    # normalize dash variants to '-' so table labels map deterministically
    p = p.replace('‑','-').replace('–','-').replace('—','-')
    if p.startswith("elektronmassa"):
        return "m_e"
    if p.startswith("muonmassa"):
        return "m_mu"
    if p.startswith("taumassa"):
        return "m_tau"
    if p.startswith("neutrino"):
        # Data-match via Δm² gate (Overlay-only triage)
        return "nu_dm2_gate"
    if p.startswith("em-koppling") or "(α" in p or "(\u03b1" in p:
        return "alpha"
    if p.startswith("ckm vinkel 1"):
        return "ckm_theta12_deg"
    if p.startswith("ckm vinkel 2"):
        return "ckm_theta23_deg"
    if p.startswith("ckm vinkel 3"):
        return "ckm_theta13_deg"
    if p.startswith("ckm cp-fas"):
        # phase δ (derived from sinδ/J in flavor artifacts)
        return "ckm_delta_deg"
    if p.startswith("pmns vinkel 1"):
        return "pmns_theta12_deg"
    if p.startswith("pmns vinkel 2"):
        return "pmns_theta23_deg"
    if p.startswith("pmns vinkel 3"):
        return "pmns_theta13_deg"
    if p.startswith("pmns cp-fas"):
        return "pmns_delta_deg"
    if p.startswith("svag koppling"):
        return "ew_g_tree_Q0"
    if "kvarkmassa" in p:
        # Scheme-dependent in SM; we mark via a strong-sector proxy gate for now.
        return "strong_proxy_gate"
    if p.startswith("stark koppling"):
        return "strong_proxy_gate"
    if p.startswith("higgs-massa"):
        return "higgs_struct_gate"
    if p.startswith("higgs-vev"):
        return "higgs_struct_gate"
    if p.startswith("stark cp") or "θ_qcd" in p:
        return "theta_qcd_deg"
    if p.startswith("κ"):
        return "kappa_L_m_per_RT"
    if p.startswith("ppn γ") or p.startswith("ppn gamma"):
        return "ppn_gamma"
    if p.startswith("ppn β") or p.startswith("ppn beta"):
        return "ppn_beta"
    return None


def _load_data_match(repo_root: Path) -> dict:
    """Return dict keyed by datakey -> {icon,status,note,...}. Creates artifacts if possible."""
    out_j = repo_root / "out/SM_PARAM_INDEX/sm29_data_match_v0_1.json"

    if _sm29_write_data_match_artifacts is not None:
        try:
            _sm29_write_data_match_artifacts(repo_root)
        except Exception:
            pass

    if out_j.exists():
        try:
            payload = json.loads(out_j.read_text(encoding="utf-8"))
            return payload.get("results", {})
        except Exception:
            return {}
    return {}


def _make_report(
    *,
    repo_root: Path,
    status_rows: List[Row],
    kappa: dict,
    ppn_gamma: Optional[str],
    ppn_beta: Optional[str],
) -> str:
    rel = lambda p: str(p.relative_to(repo_root)).replace("\\", "/")

    counts = _status_counts(status_rows)

    # Pull κ numbers (overlay)
    kappa_L_m = kappa.get("kappa_L_m_per_RT")
    kappa_L_fm = kappa.get("kappa_L_fm_per_RT")
    kappa_T_s = kappa.get("kappa_T_s_per_RT")
    freeze_date = kappa.get("freeze_date")
    freeze_source = kappa.get("freeze_source")

    lines: List[str] = []
    lines.append("# SM29 — Executive status (Core-first)")
    lines.append("")
    lines.append(f"Generated: {date.today().isoformat()}")
    lines.append("")
    lines.append("## Core/Compare contract (read first)")
    lines.append("")
    lines.append("- **Core** is facit-free: it must not read `00_TOP/OVERLAY/**`, `*reference*.json`, PDG/CODATA/targets files, nor score/optimize against external values.")
    lines.append("- **Compare** is the only place where external references appear, and Compare must not feed back into Core.")
    lines.append("- κ is **overlay-only** (an anchor) and is UNTESTED by policy.")
    lines.append("")
    lines.append("## How to regenerate")
    lines.append("")
    lines.append("Regenerate by running the verification chain described in `START_HERE.md` (Quick start).")
    lines.append("")
    lines.append("It regenerates the reviewer artifacts:")
    lines.append("")
    lines.append("- `00_TOP/LOCKS/SM_PARAM_INDEX/SM_29_REPORT.md`")
    lines.append("- `out/SM29_PAGES.md`")
    lines.append("- (Overlay-triage, does not affect Core): `out/SM_PARAM_INDEX/sm29_data_match_*`")
    lines.append("")
    lines.append("Note: `verify_core.sh` deletes `out/` at the start.")
    lines.append("")
    lines.append("## Where to read the derivation")
    lines.append("")
    lines.append(f"- Reviewer report (A4-first + sector pages): `{rel(repo_root / 'out/SM29_PAGES.md')}`")
    lines.append(f"- Core/Compare indices: `out/CORE_SM29_INDEX/` and `out/COMPARE_SM29_INDEX/`")
    lines.append("")
    lines.append("## Files in this package")
    lines.append("")
    # (legacy) SM_29_PARAMETERS_STATUS is intentionally not linked from the reviewer flow
    lines.append(f"- κ (overlay-only anchor): `{rel(repo_root / '00_TOP/OVERLAY/kappa_global.json')}`")
    lines.append("- Overlay-only reference files (never read by Core):")
    lines.append(f"  - `{rel(repo_root / '00_TOP/OVERLAY/alpha_reference.json')}`")
    lines.append(f"  - `{rel(repo_root / '00_TOP/OVERLAY/z0_reference.json')}`")
    lines.append(f"  - `{rel(repo_root / '00_TOP/OVERLAY/sm29_data_reference_v0_2.json')}`")
    lines.append(f"  - `{rel(repo_root / '00_TOP/OVERLAY/RT_OVERLAY_PPN_GAMMA_BETA_v1_2026-02-05.md')}`")
    lines.append("")

    lines.append("## Quick summary")
    lines.append("")
    lines.append("### Core/Compare index pipeline (facit-separation)")
    lines.append("")
    idx = _load_latest_sm29_indexes(repo_root)
    if idx.get("core_path"):
        lines.append(f"- core_index: {_fmt_code(idx['core_path'])}")
    if idx.get("compare_path"):
        lines.append(f"- compare_index: {_fmt_code(idx['compare_path'])}")
    lines.append("")

    core_counts = idx.get("core_counts") or {}
    comp_counts = idx.get("compare_counts") or {}

    if core_counts:
        lines.append("Core derivation-status:")
        lines.append("")
        for k, v in core_counts.items():
            lines.append(f"- {k}: {v}")
        lines.append("")

    if comp_counts:
        lines.append("Compare validation-status:")
        lines.append("")
        for k, v in comp_counts.items():
            lines.append(f"- {k}: {v}")
        lines.append("")

    tens = idx.get("tension") or []
    compd = idx.get("compared") or []

    if tens:
        lines.append("TENSION (mismatch trots DERIVED):")
        lines.append("")
        for p_ in tens:
            lines.append(f"- {p_}")
        lines.append("")
    else:
        lines.append("TENSION: none")
        lines.append("")

    if compd:
        lines.append("COMPARED (mismatch men ej DERIVED i Core):")
        lines.append("")
        for p_ in compd:
            lines.append(f"- {p_}")
        lines.append("")

    gstat, gtail = _run_overlay_guard(repo_root)
    lines.append("Overlay guard (Core must not read overlay refs):")
    lines.append("")
    lines.append(f"- Guard status: **{gstat}**")
    if gtail:
        lines.append("- tail:")
        lines.append("")
        for ln in gtail:
            lines.append(f"  - {ln}")
    lines.append("")

    lines.append("## Numerical freezes (overlay-only anchors)")
    lines.append("")
    lines.append("### κ (global SI morphism, Overlay-only)")
    lines.append("")
    if kappa_L_m is not None:
        lines.append(f"- κ_L = {kappa_L_m} m/RT  (={kappa_L_fm} fm/RT)")
    else:
        lines.append("- κ_L: MISSING")
    if kappa_T_s is not None:
        lines.append(f"- κ_T = {kappa_T_s} s/RT  (convention: κ_T = κ_L / c)")
    if freeze_date:
        lines.append(f"- freeze_date: {freeze_date}")
    if freeze_source:
        lines.append(f"- freeze_source: {_fmt_code(str(freeze_source))}")
    lines.append("")
    lines.append("Traceability:")
    lines.append(f"- {_fmt_code(rel(repo_root / '00_TOP/LOCKS/SM_PARAM_INDEX/KAPPA_FREEZE.md'))}")
    lines.append("")

    lines.append("### PPN (Core/Compare) — GR baseline check")
    lines.append("")
    lines.append(f"- γ_PPN = {ppn_gamma if ppn_gamma is not None else 'MISSING'}")
    lines.append(f"- β_PPN = {ppn_beta if ppn_beta is not None else 'MISSING'}")
    lines.append("")

    # LEPTON_MASS_LOCK (Core-derived hierarchy)
    lep_json = repo_root / "out/LEPTON_MASS_LOCK/lepton_mass_lock_v0_5.json"
    lep_sum  = repo_root / "out/LEPTON_MASS_LOCK/lepton_mass_lock_summary_v0_5.md"
    if lep_json.exists() or lep_sum.exists():
        lines.append("### LEPTON_MASS_LOCK (Core) — lepton-hierarki")
        lines.append("")
        if lep_sum.exists():
            lines.append(f"- summary: {_fmt_code(rel(lep_sum))}")
        if lep_json.exists():
            try:
                lep = _load_json(lep_json)
                best = (((lep.get('model') or {}).get('best') or {}))
                p12 = best.get('p12')
                p23 = best.get('p23')
                d = best.get('d') or {}
                N = best.get('N_act') or {}
                r = best.get('ratios_pred') or {}
                lines.append(f"- p12={p12}, p23={p23}")
                lines.append(f"- d: e={d.get('e')}, mu={d.get('mu')}, tau={d.get('tau')}")
                lines.append(f"- N_act: e={N.get('e')}, mu={N.get('mu')}, tau={N.get('tau')}")
                lines.append(f"- ratios_pred: mu/e={r.get('m_mu_over_m_e')}, tau/mu={r.get('m_tau_over_m_mu')}")
                tri = lep.get('overlay_triage') or {}
                er = tri.get('errors_rel') or {}
                if er:
                    lines.append(f"- overlay triage (info): rel_err(mu/e)={er.get('mu_over_e')}, rel_err(tau/mu)={er.get('tau_over_mu')}")
            except Exception:
                lines.append("- FAILED TO PARSE (see JSON)")
        lines.append("")

    # NU_MECHANISM_LOCK (Core-derived neutrino pattern)
    nu_json3 = repo_root / "out/NU_MECHANISM_LOCK/nu_mechanism_lock_v0_3.json"
    nu_json2 = repo_root / "out/NU_MECHANISM_LOCK/nu_mechanism_lock_v0_2.json"
    nu_json1 = repo_root / "out/NU_MECHANISM_LOCK/nu_mechanism_lock_v0_1.json"
    nu_sum3  = repo_root / "out/NU_MECHANISM_LOCK/nu_mechanism_lock_summary_v0_3.md"
    nu_sum2  = repo_root / "out/NU_MECHANISM_LOCK/nu_mechanism_lock_summary_v0_2.md"
    nu_sum1  = repo_root / "out/NU_MECHANISM_LOCK/nu_mechanism_lock_summary_v0_1.md"
    nu_tri   = repo_root / "out/NU_MECHANISM_LOCK/nu_mechanism_lock_overlay_triage_latest.json"

    nu_json = nu_json3 if nu_json3.exists() else (nu_json2 if nu_json2.exists() else nu_json1)
    nu_sum  = nu_sum3 if nu_sum3.exists() else (nu_sum2 if nu_sum2.exists() else nu_sum1)
    if nu_json.exists() or nu_sum.exists():
        lines.append("### NU_MECHANISM_LOCK (Core) — neutrino pattern")
        lines.append("")
        if nu_sum.exists():
            lines.append(f"- summary: {_fmt_code(rel(nu_sum))}")
        if nu_json.exists():
            try:
                nu = _load_json(nu_json)
                core = nu.get('core') or {}
                eps = core.get('epsilon')
                s_nu = core.get('s_nu')

                # exact ratio if present
                derived = core.get('derived') or {}
                rat = derived.get('pattern_A_delta_m2_ratio') or {}
                rat_str = None
                if isinstance(rat, dict) and 'num' in rat and 'den' in rat:
                    rat_str = f"{rat.get('num')}/{rat.get('den')}"

                lines.append(f"- epsilon=L_cap/L*={eps} ; s_nu=6*epsilon^4={s_nu}")
                if rat_str:
                    lines.append(f"- Pattern A (exakt): Δm²31/Δm²21 = {rat_str} ≈ {rat.get('value')}")

                # find Pattern A metrics (dimensionless)
                patt = (((nu.get('results') or {}).get('patterns')) or [])
                pA = None
                for p in patt:
                    if isinstance(p, dict) and p.get('id') == 'A':
                        pA = p
                        break

                if isinstance(pA, dict):
                    m0 = pA.get('m0_over_m_e')
                    dm = pA.get('delta_m2_over_m_e2') or {}
                    dm21 = dm.get('dm21')
                    dm31 = dm.get('dm31')
                    ratio = dm.get('dm31_over_dm21')
                    lines.append(f"- Pattern A (Core, dimensionless): m0/m_e={m0}; Δm²21/m_e²={dm21}; Δm²31/m_e²={dm31}; ratio={ratio}")

                # Overlay triage (optional) for eV comparison
                if nu_tri.exists():
                    try:
                        tri = _load_json(nu_tri)
                        if isinstance(tri, dict) and tri.get('available'):
                            dm = tri.get('delta_m2_eV2') or {}
                            lines.append(f"- Pattern {tri.get('pattern_id')} (Overlay triage): anchor={tri.get('anchor_source')}")
                            lines.append(f"  - Δm²21={dm.get('dm21')} eV² ; Δm²31={dm.get('dm31')} eV²")
                        elif isinstance(tri, dict):
                            lines.append(f"- Overlay triage: unavailable ({tri.get('reason')})")
                    except Exception:
                        lines.append("- Overlay triage: FAILED TO PARSE")
            except Exception:
                lines.append("- FAILED TO PARSE (see JSON)")
        lines.append("")

    # Optional: include EM_LOCK overlay numeric consistency if present.
    em_json = repo_root / "out/EM_LOCK/em_lock_v0_2.json"
    em_sum = repo_root / "out/EM_LOCK/em_lock_summary_v0_2.md"
    if em_json.exists() or em_sum.exists():
        lines.append("### EM_LOCK (Overlay) — α/Z0 konsistens")
        lines.append("")
        if em_sum.exists():
            lines.append(f"- summary: {_fmt_code(rel(em_sum))}")
        if em_json.exists():
            try:
                em = _load_json(em_json)
                inp = em.get("inputs", {})
                routes = em.get("routes", {})
                deltas = em.get("deltas", {})
                gate = em.get("gate", {})

                # Inputs
                if "alpha_ref" in inp:
                    lines.append(f"- alpha_ref: {inp.get('alpha_ref')}")
                if "z0_ref_ohm" in inp:
                    lines.append(f"- Z0_ref (Ohm): {inp.get('z0_ref_ohm')}")

                # Routes
                if "xi_from_z0_over_rk" in routes:
                    lines.append(f"- Xi = Z0/R_K: {routes.get('xi_from_z0_over_rk')}")
                if "xi_from_z0_times_g0" in routes:
                    lines.append(f"- Xi = Z0*(e^2/h): {routes.get('xi_from_z0_times_g0')}")
                if "alpha_from_z0_over_2rk" in routes:
                    lines.append(f"- alpha = Z0/(2 R_K): {routes.get('alpha_from_z0_over_2rk')}")
                if "z0_from_alpha_times_2rk" in routes and "alpha_ref" in inp:
                    lines.append(f"- Z0 = 2 alpha R_K (from alpha_ref): {routes.get('z0_from_alpha_times_2rk')}")

                # Consistency
                if "delta_ppb_alpha_from_z0_vs_alpha_ref" in deltas:
                    lines.append(
                        f"- delta(alpha_from_z0 vs alpha_ref): {deltas.get('delta_ppb_alpha_from_z0_vs_alpha_ref')} ppb"
                    )
                if "delta_ppb_z0_from_alpha_vs_z0_ref" in deltas:
                    lines.append(
                        f"- delta(Z0_from_alpha vs Z0_ref): {deltas.get('delta_ppb_z0_from_alpha_vs_z0_ref')} ppb"
                    )
                if "pass" in gate:
                    lines.append(
                        f"- gate: {'PASS' if gate.get('pass') else 'FAIL'} (|delta| <= {gate.get('gate_ppb')} ppb)"
                    )

                # Policy (do not elevate to Core)
                pol = em.get("policy", {})
                if pol:
                    scope = pol.get("scope")
                    core_claim = pol.get("core_claim")
                    if scope:
                        lines.append(f"- policy.scope: {scope}")
                    if core_claim:
                        lines.append(f"- policy.core_claim: {core_claim}")
            except Exception:
                lines.append("- FAILED TO PARSE (see JSON)")
        lines.append("")


    # Optional: include EW_COUPLING_LOCK (Overlay) — tree-level g from alpha + sin^2θW=1/4.
    ew_json = repo_root / "out/EW_COUPLING_LOCK/ew_coupling_lock_v0_1.json"
    ew_sum  = repo_root / "out/EW_COUPLING_LOCK/ew_coupling_lock_summary_v0_1.md"
    if ew_json.exists() or ew_sum.exists():
        lines.append("### EW_COUPLING_LOCK (Overlay) — g from α + sin²θ_W=1/4 (tree-level)")
        lines.append("")
        if ew_sum.exists():
            lines.append(f"- summary: {_fmt_code(rel(ew_sum))}")
        if ew_json.exists():
            try:
                ew = _load_json(ew_json)
                gate = ew.get('gate', {})
                res = ew.get('result', {})
                lines.append(f"- gate: {'PASS' if gate.get('pass') else 'FAIL'}")
                if isinstance(res, dict):
                    if 'g_tree' in res:
                        lines.append(f"- g_tree(Q→0): {res.get('g_tree')}")
                    if 'gprime_tree' in res:
                        lines.append(f"- g′_tree(Q→0): {res.get('gprime_tree')}")
                    if 'e' in res:
                        lines.append(f"- e = √(4π α): {res.get('e')}")
            except Exception:
                lines.append("- FAILED TO PARSE (see JSON)")
        lines.append("")




    # Optional: include FLAVOR_LOCK PP prediction (preferred; post-lifts) if present.
    # This is the object we data-match against (PMNS/CKM angles after deterministic lifts).
    pp_json = repo_root / "out/FLAVOR_LOCK/flavor_pp_pred_v0_1.json"
    pp_sum  = repo_root / "out/FLAVOR_LOCK/flavor_pp_pred_summary_v0_1.md"
    if pp_json.exists() or pp_sum.exists():
        lines.append("### FLAVOR_LOCK (PP pred; preferred)")
        lines.append("")
        if pp_sum.exists():
            lines.append(f"- summary: {_fmt_code(rel(pp_sum))}")
        if pp_json.exists():
            try:
                pp = _load_json(pp_json)
                for tag in ("CKM", "PMNS"):
                    sec = pp.get(tag, {}) or {}
                    a = sec.get("angles", {}) or {}
                    if a:
                        lines.append(
                            f"- {tag} (pred): θ12={float(a.get('theta12_deg', 0.0)):.6f}°, "
                            f"θ23={float(a.get('theta23_deg', 0.0)):.6f}°, "
                            f"θ13={float(a.get('theta13_deg', 0.0)):.6f}°, "
                            f"δ≈{float(a.get('delta_deg_from_sin', 0.0)):.6f}°, "
                            f"J={float(a.get('J', 0.0)):.6e}"
                        )
            except Exception:
                lines.append("- FAILED TO PARSE (see JSON)")
        lines.append("")
    # Optional: include FLAVOR_LOCK outputs (dimensionless, Core) if present.
    # Prefer newest runner output.
    for ver in ["v0_9", "v0_8", "v0_7", "v0_6", "v0_5", "v0_4", "v0_3", "v0_2", "v0_1"]:
        cand_ud = repo_root / f"out/FLAVOR_LOCK/flavor_ud_{ver}.json"
        cand_enu = repo_root / f"out/FLAVOR_LOCK/flavor_enu_{ver}.json"
        cand_sum = repo_root / f"out/FLAVOR_LOCK/flavor_lock_summary_{ver}.md"
        if cand_ud.exists() or cand_enu.exists() or cand_sum.exists():
            fl_ud, fl_enu, fl_sum = cand_ud, cand_enu, cand_sum
            break
    else:
        fl_ud = repo_root / "out/FLAVOR_LOCK/flavor_ud_v0_9.json"
        fl_enu = repo_root / "out/FLAVOR_LOCK/flavor_enu_v0_9.json"
        fl_sum = repo_root / "out/FLAVOR_LOCK/flavor_lock_summary_v0_9.md"
    if fl_ud.exists() or fl_enu.exists() or fl_sum.exists():
        lines.append("### FLAVOR_LOCK baseline artifacts (Core, dimensionless; pre-lifts)")
        lines.append("")
        lines.append("- note: these JSON/MD artifacts are *pre-lifts* (raw misalignment). For \"post-lifts\", use the PP-pred above.")
        if fl_sum.exists():
            lines.append(f"- summary: {_fmt_code(rel(fl_sum))}")
        if fl_ud.exists():
            try:
                ud = _load_json(fl_ud)
                u = ud.get("u", {})
                d = ud.get("d", {})
                ckm = ud.get("CKM", {})
                lines.append(
                    "- u ratios: m1/m2={:.6e}, m2/m3={:.6e}".format(
                        float(u.get("ratios", {}).get("m1_over_m2", 0.0)),
                        float(u.get("ratios", {}).get("m2_over_m3", 0.0)),
                    )
                )
                lines.append(
                    "- d ratios: m1/m2={:.6e}, m2/m3={:.6e}".format(
                        float(d.get("ratios", {}).get("m1_over_m2", 0.0)),
                        float(d.get("ratios", {}).get("m2_over_m3", 0.0)),
                    )
                )
                if "angles" in ckm:
                    a = ckm["angles"]
                    lines.append(
                        "- CKM: θ12={:.6f}°, θ23={:.6f}°, θ13={:.6f}°, δ={:.6f}°, J={:.6e}".format(
                            float(a.get("theta12_deg", 0.0)),
                            float(a.get("theta23_deg", 0.0)),
                            float(a.get("theta13_deg", 0.0)),
                            float(a.get("delta_deg_from_sin", 0.0)),
                            float(a.get("J", 0.0)),
                        )
                    )
                    m = _misalignment_metrics(a)
                    if m is not None:
                        lines.append(f"- CKM misalignment: D_off={m[0]:.6e}, D_I={m[1]:.6e}")
            except Exception:
                lines.append("- u/d: FAILED TO PARSE (see JSON)")
        if fl_enu.exists():
            try:
                enu = _load_json(fl_enu)
                e = enu.get("e", {})
                nu = enu.get("nu", {})
                pmns = enu.get("PMNS", {})
                lines.append(
                    "- e ratios: m1/m2={:.6e}, m2/m3={:.6e}".format(
                        float(e.get("ratios", {}).get("m1_over_m2", 0.0)),
                        float(e.get("ratios", {}).get("m2_over_m3", 0.0)),
                    )
                )
                lines.append(
                    "- ν ratios(proxy): m1/m2={:.6e}, m2/m3={:.6e}".format(
                        float(nu.get("ratios", {}).get("m1_over_m2", 0.0)),
                        float(nu.get("ratios", {}).get("m2_over_m3", 0.0)),
                    )
                )
                if "angles" in pmns:
                    a = pmns["angles"]
                    lines.append(
                        "- PMNS: θ12={:.6f}°, θ23={:.6f}°, θ13={:.6f}°, J={:.6e}".format(
                            float(a.get("theta12_deg", 0.0)),
                            float(a.get("theta23_deg", 0.0)),
                            float(a.get("theta13_deg", 0.0)),
                            float(a.get("J", 0.0)),
                        )
                    )
                    m = _misalignment_metrics(a)
                    if m is not None:
                        lines.append(f"- PMNS misalignment: D_off={m[0]:.6e}, D_I={m[1]:.6e}")
            except Exception:
                lines.append("- e/ν: FAILED TO PARSE (see JSON)")
        lines.append("")

    # Optional: include LEPTON_ENGAGEMENT_LOCK (Core scaffold) if present.
    lep_json = repo_root / "out/LEPTON_ENGAGEMENT_LOCK/lepton_engagement_lock_v0_1.json"
    lep_sum  = repo_root / "out/LEPTON_ENGAGEMENT_LOCK/lepton_engagement_lock_summary_v0_1.md"
    lep_vsum = repo_root / "out/LEPTON_ENGAGEMENT_LOCK/lepton_engagement_lock_verify_summary_v0_2.md"
    if lep_json.exists() or lep_sum.exists():
        lines.append("### LEPTON_ENGAGEMENT_LOCK (Core scaffold) — N_act (multiplar av 6, <=L_*)")
        lines.append("")
        if lep_sum.exists():
            lines.append(f"- summary: {_fmt_code(rel(lep_sum))}")
        if lep_vsum.exists():
            lines.append(f"- verify: {_fmt_code(rel(lep_vsum))}")
        if lep_json.exists():
            try:
                lep = _load_json(lep_json)
                best = lep.get("best", {})
                nact = best.get("N_act", {})
                lines.append(f"- N_act (e,μ,τ): e={nact.get('e')}, μ={nact.get('mu')}, τ={nact.get('tau')}")
                rp = best.get("ratios_pred", {})
                rr = best.get("residuals", {})
                lines.append(f"- ratios_pred: r12={rp.get('m1_over_m2')}, r23={rp.get('m2_over_m3')}")
                lines.append(f"- residuals: dr12={rr.get('dr12')}, dr23={rr.get('dr23')}")
            except Exception:
                lines.append("- FAILED TO PARSE (see JSON)")
        lines.append("")

    # Optional: include HIGGS/VEV lock scaffold if present (prefer newest).
    hv_json = None
    hv_sum = None
    for hv_ver in ["v0_3", "v0_2", "v0_1"]:
        cand_json = repo_root / f"out/HIGGS_VEV_LOCK/higgs_vev_lock_{hv_ver}.json"
        cand_sum = repo_root / f"out/HIGGS_VEV_LOCK/higgs_vev_lock_summary_{hv_ver}.md"
        if cand_json.exists() or cand_sum.exists():
            hv_json, hv_sum = cand_json, cand_sum
            break
    if hv_json is not None and (hv_json.exists() or (hv_sum is not None and hv_sum.exists())):
        lines.append("### HIGGS/VEV LOCK")
        lines.append("")
        if hv_sum is not None and hv_sum.exists():
            lines.append(f"- summary: {_fmt_code(rel(hv_sum))}")
        if hv_json.exists():
            try:
                hv = _load_json(hv_json)
                lines.append(f"- version: {hv.get('version', 'UNKNOWN')}")
                lines.append(f"- status: {hv.get('status', 'UNKNOWN')}")
                gates = hv.get('gates', {})
                if gates and 'prereq_presence' in gates:
                    lines.append(f"- gates.prereq_presence: {gates.get('prereq_presence')}")
                res = hv.get('result', {})
                ew = res.get('ew_struct') if isinstance(res, dict) else None
                if isinstance(ew, dict) and 'sin2_thetaW' in ew:
                    s2 = ew.get('sin2_thetaW', {})
                    mwmz = ew.get('mW_over_mZ', {})
                    lines.append(f"- EW: sin^2θW={s2.get('exact', s2)}, mW/mZ={mwmz.get('exact', mwmz)}")
            except Exception:
                lines.append("- FAILED TO PARSE (see JSON)")
        lines.append("")


    

    # Optional: include THETA_QCD_LOCK scaffold (Core).
    tq_json = repo_root / "out/THETA_QCD_LOCK/theta_qcd_lock_v0_1.json"
    tq_sum = repo_root / "out/THETA_QCD_LOCK/theta_qcd_lock_summary_v0_1.md"
    if tq_json.exists() or tq_sum.exists():
        lines.append("### THETA_QCD_LOCK (Core) — stark CP-vinkel")
        lines.append("")
        if tq_sum.exists():
            lines.append(f"- summary: {_fmt_code(rel(tq_sum))}")
        if tq_json.exists():
            try:
                tq = _load_json(tq_json)
                lines.append(f"- version: {tq.get('version','UNKNOWN')}")
                lines.append(f"- status: {tq.get('status','UNKNOWN')}")
                gate = tq.get('gate', {})
                if 'pass' in gate:
                    lines.append(f"- gate: {'PASS' if gate.get('pass') else 'FAIL'}")
                if 'reason' in gate:
                    lines.append(f"- reason: {gate.get('reason')}")
            except Exception:
                lines.append("- FAILED TO PARSE (see JSON)")
        lines.append("")

    # Optional: include ENERGY_ANCHOR_LOCK overlay (absolute mass scale via exactly one anchor).
    # Prefer newest
    ea_json = None
    ea_sum = None
    for ea_ver in ["v0_3", "v0_2", "v0_1"]:
        cand_json = repo_root / f"out/ENERGY_ANCHOR_LOCK/energy_anchor_lock_{ea_ver}.json"
        cand_sum  = repo_root / f"out/ENERGY_ANCHOR_LOCK/energy_anchor_lock_summary_{ea_ver}.md"
        if cand_json.exists() or cand_sum.exists():
            ea_json, ea_sum = cand_json, cand_sum
            break
    if ea_json is not None and (ea_json.exists() or (ea_sum is not None and ea_sum.exists())):
        lines.append("### ENERGY_ANCHOR_LOCK (Overlay) — exakt 1 energiankare")
        lines.append("")
        if ea_sum is not None and ea_sum.exists():
            lines.append(f"- summary: {_fmt_code(rel(ea_sum))}")
        if ea_json is not None and ea_json.exists():
            try:
                ea = _load_json(ea_json)
                gate = ea.get('gate', {})
                anc = ea.get('anchor', {})
                pol = ea.get('policy', {}) if isinstance(ea.get('policy', {}), dict) else {}
                scope = str(pol.get('scope', anc.get('scope', '')))
                lines.append(f"- gate: {'PASS' if gate.get('pass') else 'FAIL'}")
                lines.append(f"- anchor.enabled: {anc.get('enabled')}")
                if scope:
                    lines.append(f"- scope: {scope}")
                lines.append(f"- anchor.anchor_id: {anc.get('anchor_id')}")
                lines.append(f"- anchor.anchor_value: {anc.get('anchor_value')}")
                lines.append(f"- unit: {anc.get('unit')}")
                if gate.get('pass'):
                    masses_abs = ea.get('masses_absolute', ea.get('masses', {}))
                    sec = anc.get('anchor_sector')
                    labels = {'e': '(e,mu,tau)', 'u': '(u,c,t)', 'd': '(d,s,b)'}
                    if isinstance(masses_abs, dict):
                        if str(scope).strip().lower() == 'global':
                            for s in ['e','u','d']:
                                if s in masses_abs:
                                    m = masses_abs[s]
                                    lines.append(f"- {s} {labels.get(s,'')}: m1={m.get('m1')}, m2={m.get('m2')}, m3={m.get('m3')} {m.get('unit', anc.get('unit'))}")
                        else:
                            if sec in masses_abs:
                                m = masses_abs[sec]
                                lines.append(f"- {sec} {labels.get(sec,'')}: m1={m.get('m1')}, m2={m.get('m2')}, m3={m.get('m3')} {m.get('unit', anc.get('unit'))}")
            except Exception:
                lines.append("- FAILED TO PARSE (see JSON)")
        lines.append("")


# Optional: include verifier outputs (if present). These do not change status table; only evidence.
    flv_json = repo_root / "out/FLAVOR_LOCK/flavor_lock_verify_v0_1.json"
    flv_sum = repo_root / "out/FLAVOR_LOCK/flavor_lock_verify_summary_v0_1.md"
    emv_sum = repo_root / "out/EM_LOCK/em_lock_verify_summary_v0_1.md"
    mis_sum = repo_root / "out/SM29_MISALIGNMENT/sm29_misalignment_summary_v0_1.md"
    if emv_sum.exists() or flv_sum.exists() or mis_sum.exists():
        lines.append("## Verifier (evidence gates, no status promotion)")
        if mis_sum.exists():
            lines.append(f"- SM29 misalignment: {_fmt_code(rel(mis_sum))}")
        lines.append("")
        if emv_sum.exists():
            lines.append("### EM_LOCK verify (v0.1)")
            lines.append("")
            lines.append(f"- summary: {_fmt_code(rel(emv_sum))}")
            lines.append("")
        if flv_sum.exists():
            lines.append("### FLAVOR_LOCK verify (v0.1)")
            lines.append("")
            lines.append(f"- summary: {_fmt_code(rel(flv_sum))}")
            # If match-gates exist, summarize them (Overlay-only; informational)
            if flv_json.exists():
                try:
                    vj = _load_json(flv_json)
                    mg = ((vj.get('checks') or {}).get('match_gates') or {})
                    if mg.get('ref_present'):
                        ck = (mg.get('CKM') or {})
                        pm = (mg.get('PMNS') or {})
                        lines.append(f"- match(CKM, PDG): {ck.get('pass_all')}")
                        lines.append(f"- match(PMNS, PDG 3σ): {pm.get('pass_all')}")

                        ps = ((vj.get('checks') or {}).get('perm_scan_abs') or {})
                        if ps:
                            ckps = ps.get('CKM') or {}
                            pmps = ps.get('PMNS') or {}
                            if ckps:
                                lines.append(
                                    f"- CKM abs-only relabeling: best θ13={((ckps.get('best') or {}).get('angles_deg') or {}).get('theta13_deg')}, bound θ13≥{ckps.get('min_theta13_deg_bound')} (min|V|={ckps.get('min_abs')})"
                                )
                            if pmps:
                                lines.append(
                                    f"- PMNS abs-only relabeling: best θ13={((pmps.get('best') or {}).get('angles_deg') or {}).get('theta13_deg')}, bound θ13≥{pmps.get('min_theta13_deg_bound')} (min|U|={pmps.get('min_abs')})"
                                )

                        pls = ((vj.get('checks') or {}).get('phase_lift_scan') or {})
                        if pls:
                            def _pl_line(tag: str, name: str):
                                obj = pls.get(tag) or {}
                                best = obj.get('best') or {}
                                if not best:
                                    return
                                ang = best.get('angles') or {}
                                lines.append(
                                    f"- {name} phase-lift: best R={best.get('unitary_residual')}, ok={best.get('unitary_res_ok')}, J={ang.get('J')}, θ13={ang.get('theta13_deg')}"
                                )
                            _pl_line('CKM', 'CKM')
                            _pl_line('PMNS', 'PMNS')
                            
                            # abs-only feasibility + delta(C30) diagnostics
                            us = ((vj.get('checks') or {}).get('unistochastic') or {})
                            if us:
                                for tag, name in (('CKM','CKM'), ('PMNS','PMNS')):
                                    kk = (us.get(tag) or {})
                                    ds = ((kk.get('doubly_stochastic_sq') or {}).get('max_err'))
                                    tri = (((kk.get('triangle_checks') or {}).get('pass_all')))
                                    if (ds is not None) or (tri is not None):
                                        lines.append(f"- {name} unistochastic(abs): pass={tri}, max |sum(|M|^2)-1|={ds}")
                            dg = ((vj.get('checks') or {}).get('delta_grid_C30') or {})
                            if dg:
                                for tag, name in (('CKM','CKM'), ('PMNS','PMNS')):
                                    dd = (dg.get(tag) or {})
                                    if not dd:
                                        continue
                                    g = (dd.get('C30_grid') or {})
                                    lines.append(
                                        f"- {name} δ_best≈{dd.get('delta_best_deg')}°; nearest C30 k={g.get('k')}, Δ={g.get('delta_minus_grid_rad')} rad; abs_err@δ_grid(max)={dd.get('delta_grid_abs_max_err')}"
                                    )
                except Exception:
                    pass
            lines.append("")

    # -----------------------------
    # Computed table (authoritative): read directly from Core/Compare index artifacts
    # -----------------------------

    lines.append("## Computed SM29 status table (authoritative)")
    lines.append("")
    lines.append("This table is generated from the latest **Core** and **Compare** index artifacts.")
    lines.append("It is the most reliable snapshot for this zip because it is produced by the same pipeline that Compare executes.")
    if idx.get("core_path"):
        lines.append(f"- Core index: {_fmt_code(idx['core_path'])}")
    if idx.get("compare_path"):
        lines.append(f"- Compare index: {_fmt_code(idx['compare_path'])}")
    lines.append("")

    # Load entries (best-effort; report-only)
    core_entries = []
    compare_entries = []
    try:
        if idx.get("core_path"):
            core_entries = (_load_json(repo_root / idx["core_path"]).get("entries") or [])
    except Exception:
        core_entries = []
    try:
        if idx.get("compare_path"):
            compare_entries = (_load_json(repo_root / idx["compare_path"]).get("entries") or [])
    except Exception:
        compare_entries = []

    compare_map = {str(e.get("parameter") or ""): e for e in compare_entries if isinstance(e, dict)}

    def _cmp_checks_summary(entry: dict) -> str:
        det = entry.get("details") or []
        bits = []
        for d in det:
            ref = str(d.get("ref") or "").strip()
            ok = d.get("ok")
            if ok is True:
                bits.append(f"{ref}: OK")
            elif ok is False:
                bits.append(f"{ref}: FAIL")
            else:
                bits.append(f"{ref}: ?")
        return "; ".join(bits) if bits else "(no compare details)"

    lines.append("| Parameter | Core derivation | Core scope | Compare | Compare checks (summary) |")
    lines.append("|---|---:|---:|---:|---|")

    for ce in core_entries:
        if not isinstance(ce, dict):
            continue
        p = str(ce.get("parameter") or "")
        deriv = str(ce.get("derivation_status") or "")
        cscope = str(ce.get("core_scope") or "")
        cmp = compare_map.get(p)
        vstat = str((cmp.get("validation_status") if isinstance(cmp, dict) else "MISSING") or "MISSING")
        cs = _cmp_checks_summary(cmp) if isinstance(cmp, dict) else "(missing compare entry)"
        lines.append(f"| {p} | {deriv} | {cscope} | {vstat} | {cs} |")

    lines.append("")
    lines.append("Interpretation notes:")
    lines.append("")
    lines.append("- Many 'mass' parameters are represented in Core as **dimensionless ratio sets** plus exactly one Overlay energy anchor for absolute units.")
    lines.append("- For SM29 bookkeeping, the lepton ratio set (μ/e and τ/μ) is attached to all three lepton-mass entries, so they share the same compare checks.")
    lines.append("- Likewise, the neutrino rows represent the Δm² ratio pattern; absolute ν masses in eV remain anchor-dependent.")
    lines.append("- Quark masses m_q(μ) are treated as **scheme-dependent overlay proxies**, not RT primary targets. See `00_TOP/LOCKS/HADRON_PROXY_LOCK/`.")
    lines.append("- PPN entries are currently a **GR baseline sanity check** (γ=β=1) rather than an LLR-derived fit.")
    lines.append("- κ is an **overlay-only SI morphism** (policy: frozen for reproducibility; Core does not use it for selection).")
    lines.append("")

    # --- Core compare (any-hit vs preferred-hit)
    lines.append("## Core compare (any-hit vs preferred-hit)")
    lines.append("")
    cmp_dir = repo_root / "out" / "COMPARE_SM29_INDEX"
    cmp_json = None
    if cmp_dir.exists():
        # Always take newest compare index (do not pin to older versions).
        cands = sorted(cmp_dir.glob("sm29_compare_index_v*.json"))
        if cands:
            cmp_json = cands[-1]

    if cmp_json and cmp_json.exists():
        try:
            cmp = _load_json(cmp_json)
            ents = (cmp.get("entries") or [])

            def _agg(det_list: list[dict]) -> tuple[Optional[bool], Optional[bool]]:
                if not det_list:
                    return None, None
                any_list = []
                pref_list = []
                for d in det_list:
                    any_list.append(d.get("any_hit") if d.get("any_hit") is not None else d.get("ok"))
                    pref_list.append(d.get("preferred_hit"))
                any_all = all(x is True for x in any_list)
                pref_known = [x for x in pref_list if x is not None]
                pref_all = (all(x is True for x in pref_known) if pref_known else None)
                return any_all, pref_all

            c_any = 0
            c_pref = 0
            c_pref_known = 0
            any_only = []
            for e in ents:
                det = e.get("details") or []
                any_all, pref_all = _agg(det)
                if any_all is True:
                    c_any += 1
                if pref_all is not None:
                    c_pref_known += 1
                    if pref_all is True:
                        c_pref += 1
                if any_all is True and pref_all is False:
                    any_only.append(e.get("parameter"))

            lines.append(f"Source: {_fmt_code(rel(cmp_json))}")
            lines.append(f"- Any-hit (at least one candidate within tolerance): {c_any}/{len(ents)}")
            if c_pref_known:
                lines.append(f"- Preferred-hit (the marked 'preferred' within tolerance): {c_pref}/{c_pref_known} (unknown for the rest)")
            if any_only:
                lines.append("- Any-only (a candidate matches, but not the preferred one):")
                for p in any_only[:20]:
                    lines.append(f"  - {p}")
                if len(any_only) > 20:
                    lines.append(f"  - ... (+{len(any_only) - 20} more)")
        except Exception:
            lines.append(f"Compare index exists but could not be read: {_fmt_code(rel(cmp_json))}")
    else:
        lines.append("Missing: out/COMPARE_SM29_INDEX/sm29_compare_index_*.json")
    lines.append("")

    lines.append("## Next locks that unlock the remaining work")
    lines.append("")
    lines.append("1) FLAVOR_LOCK (u/d) PASS+NEG ⇒ CKM + quark-mass-ratios (runner v0.2 recommended)")
    lines.append(f"   - {_fmt_code(rel(repo_root / '00_TOP/LOCKS/FLAVOR_LOCK/FLAVOR_LOCK_U_D_SPEC_v0_1.md'))}")
    lines.append("2) FLAVOR_LOCK (e/ν) PASS+NEG ⇒ PMNS + lepton/ν-ratios")
    lines.append(f"   - {_fmt_code(rel(repo_root / '00_TOP/LOCKS/FLAVOR_LOCK/FLAVOR_LOCK_E_NU_SPEC_v0_1.md'))}")
    lines.append("3) EM-LOCK (α) ⇒ define Xi_RT in Core + (later) running/normalisation; overlay consistency can already be gated")
    lines.append("4) Exactly one energy anchor in Overlay (GeV scale) ⇒ make masses/couplings numeric")
    lines.append("")

    lines.append("## Regeneration")
    lines.append("")
    lines.append("See `START_HERE.md` (Quick start).")
    lines.append("")

    return "\n".join(lines)



# -----------------------------
# A4-friendly per-parameter pages (English)
# -----------------------------

_EN_PARAM = {
    "Elektronmassa": ("Electron mass", "m_e"),
    "Muonmassa": ("Muon mass", "m_μ"),
    "Taumassa": ("Tau mass", "m_τ"),
    "Up‑kvarkmassa": ("Up quark mass", "m_u"),
    "Down‑kvarkmassa": ("Down quark mass", "m_d"),
    "Charm‑kvarkmassa": ("Charm quark mass", "m_c"),
    "Strange‑kvarkmassa": ("Strange quark mass", "m_s"),
    "Top‑kvarkmassa": ("Top quark mass", "m_t"),
    "Bottom‑kvarkmassa": ("Bottom quark mass", "m_b"),
    "Neutrino‑massa 1": ("Neutrino mass 1", "m_ν1"),
    "Neutrino‑massa 2": ("Neutrino mass 2", "m_ν2"),
    "Neutrino‑massa 3": ("Neutrino mass 3", "m_ν3"),
    "EM‑koppling (α)": ("Electromagnetic coupling", "α"),
    "Svag koppling (g)": ("Weak coupling", "g"),
    "Stark koppling (g_s)": ("Strong coupling", "g_s"),
    "CKM vinkel 1": ("CKM angle 1", "θ12^q"),
    "CKM vinkel 2": ("CKM angle 2", "θ23^q"),
    "CKM vinkel 3": ("CKM angle 3", "θ13^q"),
    "CKM CP‑fas": ("CKM CP phase", "δ^q"),
    "PMNS vinkel 1": ("PMNS angle 1", "θ12^ℓ"),
    "PMNS vinkel 2": ("PMNS angle 2", "θ23^ℓ"),
    "PMNS vinkel 3": ("PMNS angle 3", "θ13^ℓ"),
    "PMNS CP‑fas": ("PMNS CP phase", "δ^ℓ"),
    "Higgs‑massa": ("Higgs mass", "m_H"),
    "Higgs‑VEV (v)": ("Higgs VEV", "v"),
    "Stark CP‑vinkel (θ_QCD)": ("Strong CP angle", "θ_QCD"),
    "PPN γ": ("PPN gamma", "γ"),
    "PPN β": ("PPN beta", "β"),
    "κ (SI‑ankare)": ("kappa (SI anchor)", "κ"),
}

# Stable P01..P29 ordering (matches core index order)
_P_ORDER = [
    "Elektronmassa","Muonmassa","Taumassa",
    "Up‑kvarkmassa","Down‑kvarkmassa","Charm‑kvarkmassa","Strange‑kvarkmassa","Top‑kvarkmassa","Bottom‑kvarkmassa",
    "Neutrino‑massa 1","Neutrino‑massa 2","Neutrino‑massa 3",
    "EM‑koppling (α)","Svag koppling (g)","Stark koppling (g_s)",
    "CKM vinkel 1","CKM vinkel 2","CKM vinkel 3","CKM CP‑fas",
    "PMNS vinkel 1","PMNS vinkel 2","PMNS vinkel 3","PMNS CP‑fas",
    "Higgs‑massa","Higgs‑VEV (v)","Stark CP‑vinkel (θ_QCD)",
    "PPN γ","PPN β","κ (SI‑ankare)",
]

def _find_latest_index(repo_root: Path, kind: str) -> Optional[Path]:
    # kind: "CORE" or "COMPARE"
    if kind == "CORE":
        pat = str(repo_root / "out/CORE_SM29_INDEX/sm29_core_index_v*.json")
    else:
        pat = str(repo_root / "out/COMPARE_SM29_INDEX/sm29_compare_index_v*.json")
    paths = sorted(glob.glob(pat))
    if not paths:
        return None
    def _ver(p: str) -> Tuple[int, ...]:
        m = re.search(r"_v([0-9]+(?:\.[0-9]+)*)\.json$", p)
        if not m:
            return (0,)
        return tuple(int(x) for x in m.group(1).split("."))
    paths.sort(key=_ver)
    return Path(paths[-1])

def _wrap_lines(s: str, width: int = 92) -> str:
    # Keep markdown bullets readable for A4.
    out_lines = []
    for ln in s.splitlines():
        if (len(ln) <= width or ln.lstrip().startswith("```") or ln.startswith("#")
                or ln.lstrip().startswith("|")  # markdown tables
                or ln.strip().startswith("\\")):  # latex commands like \newpage
            out_lines.append(ln)
            continue
        if ln.lstrip().startswith("- "):
            prefix = ln[: ln.find("- ")+2]
            body = ln[len(prefix):]
            wrapped = textwrap.fill(body, width=width, subsequent_indent="  ")
            out_lines.append(prefix + wrapped)
        else:
            out_lines.append(textwrap.fill(ln, width=width))
    return "\n".join(out_lines)

def _fmt_short_value(v: object, unit: Optional[str] = None) -> str:
    """Short, deterministic value formatting (A4-friendly).

    - Scalars: show a compact numeric/string form.
    - Ranges: show [lo, hi].
    - Multi-valued dict/list: avoid JSON dumps in-line; use a stable placeholder.
    """
    if v is None:
        return "N/A"

    # Ranges (common in Compare refs)
    if isinstance(v, list):
        if len(v) == 2 and all(isinstance(x, (int, float)) for x in v):
            lo, hi = float(v[0]), float(v[1])
            s = f"[{lo:.12g}, {hi:.12g}]"
            return s if not unit else f"{s} ({unit})"
        s = f"list(len={len(v)})"
        return s if not unit else f"{s} ({unit})"

    if isinstance(v, dict):
        keys = list(v.keys())
        kshow = ",".join(str(k) for k in keys[:5])
        tag = f"object(keys={kshow}" + (f",+{len(keys)-5}" if len(keys) > 5 else "") + ")"
        return tag if not unit else f"{tag} ({unit})"

    if isinstance(v, bool):
        s = "true" if v else "false"
        return s if not unit else f"{s} ({unit})"

    if isinstance(v, int):
        s = str(v)
        return s if not unit else f"{s} ({unit})"

    try:
        s = f"{float(v):.12g}"
    except Exception:
        s = str(v)
        if len(s) > 60:
            s = s[:57] + "..."

    return s if not unit else f"{s} ({unit})"


def _core_preferred_obj(core_value: dict):
    """Return the Core 'preferred' output in a robust way.

    Rules (report-only):
    - If preferred is a scalar wrapper (e.g. {'approx': 0.25}), return the scalar.
    - If preferred contains multiple semantic fields (e.g. {'approx': 66.1, 'J': 3e-5, ...}),
      keep it as a dict so the page can show all fields.
    - Never force-float; keep dict/list objects as-is for traceability.
    """
    pref = core_value.get("preferred")

    # Preferred may be a dict wrapper or a multi-output object.
    if isinstance(pref, dict):
        keys = set(pref.keys())
        scalar_keys = {"approx", "value", "scalar", "val"}
        # Pure scalar wrapper
        if keys and keys.issubset(scalar_keys):
            for k in ("approx", "value", "scalar", "val"):
                if k in pref:
                    return pref.get(k)
            return None
        # If it has an 'approx' but also other meaningful keys, keep the dict.
        return pref

    if pref is not None:
        return pref

    # Some locks use other fields instead of 'preferred'
    for k in ("hit", "best", "value", "approx"):
        if k in core_value:
            return core_value.get(k)

    # If no preferred wrapper exists but core_value itself carries the payload (common for
    # multi-output objects like mixing CP pages), return it as-is for traceability.
    if isinstance(core_value, dict) and core_value:
        return core_value

    return None


def _infer_candidate_type(core_entry: dict) -> str:
    """Inference from metadata only (never from external targets)."""
    cv = core_entry.get("core_value") or {}
    t = cv.get("type")
    if t and str(t).strip().lower() not in {"unknown", "n/a", "na", "?"}:
        return str(t)

    cand_full = cv.get("candidates_full_count")
    kept = cv.get("kept")
    reduction = cv.get("reduction_meta") or {}
    method = reduction.get("method") or reduction.get("method_id")

    if cand_full is not None and kept is not None:
        return "finite_candidate_set"
    if method:
        return f"reduction::{method}"

    sl = str(core_entry.get("source_lock") or "")
    if "FLAVOR" in sl:
        return "flavor lock (phase-lift / unitary reconstruction)"
    if "PPN" in sl:
        return "ppn lock (sigma→Phi→geodesic mapping)"
    if "QUARK_PROXY" in sl:
        return "proxy mass component"
    if "SM29_CONSISTENCY" in sl:
        return "finite candidate set (consistency lock)"
    if "HIGGS" in sl:
        return "structural lock (canonical denominators / gates)"
    if "THETA_QCD" in sl:
        return "finite candidate set (theta scan)"
    if "EM_" in sl or sl == "EM_LOCK":
        return "finite candidate set (EM family)"
    if "GS_" in sl:
        return "structural lock (canonical denominator)"
    return "metadata not recorded"



def _explain_core_value(core_entry: dict, rt_obj) -> str:
    status = str(core_entry.get("derivation_status") or "").upper()
    scope = str(core_entry.get("core_scope") or "")

    if status == "BLANK":
        return "Blank by policy (Overlay-only; no SI anchoring in Core)."

    if "OVERLAY_ANCHOR" in scope:
        if rt_obj is None:
            return "Core derives dimensionless ratios/patterns only; absolute scale is fixed only in Overlay/Compare."
        if isinstance(rt_obj, (dict, list)):
            return "Core output is multi-valued (a ratio/pattern set); this page is one member of that set."
        return "Core value is defined only up to an Overlay anchor."

    if rt_obj is None:
        return "No scalar value recorded in the Core index entry (likely a multi-valued output); see artifact pointer."
    if isinstance(rt_obj, (dict, list)):
        return "Multi-valued Core output (vector/range); see summary keys below."
    return ""


def _summarize_obj(rt_obj) -> List[str]:
    """Short, deterministic summary of multi-valued outputs (A4-safe)."""
    if rt_obj is None:
        return []
    if isinstance(rt_obj, dict):
        keys = list(rt_obj.keys())
        keys_s = ", ".join([str(k) for k in keys[:10]])
        out = [f"- Output keys: `{keys_s}`" + (f" ... (+{len(keys)-10} more)" if len(keys) > 10 else "")]

        # Helpful nested summaries for common multi-output shapes (keep short and deterministic).
        # Lepton mass lock often stores predicted ratios under ratios_pred.
        rpred = rt_obj.get('ratios_pred')
        if isinstance(rpred, dict):
            for kk in ('m_mu_over_m_e', 'm_tau_over_m_mu', 'm_tau_over_m_e'):
                if kk in rpred and isinstance(rpred.get(kk), (int, float, bool, str)):
                    out.append(f"- `ratios_pred.{kk}` = `{_fmt_short_value(rpred.get(kk), 'ratio')}`")

        shown = 0
        for k in keys:
            v = rt_obj.get(k)
            if isinstance(v, (int, float, bool, str)) and shown < 4:
                out.append(f"- `{k}` = `{_fmt_short_value(v)}`")
                shown += 1
        return out
    if isinstance(rt_obj, list):
        return [f"- Output is a list (len={len(rt_obj)}); see the Core index pointer below for full content."]
    return []


def _render_core_derivation_en(core_entry: dict) -> str:
    status = core_entry.get("derivation_status", "UNSPEC").upper()
    scope = core_entry.get("core_scope", "UNKNOWN")
    core_value = core_entry.get("core_value") or {}
    q = core_entry.get("_quantity_en") or core_value.get("quantity") or core_entry.get("parameter")
    t = _infer_candidate_type(core_entry)
    cand_full = core_value.get("candidates_full_count")
    kept = core_value.get("kept")
    promotion = core_value.get("promotion_rule")
    reduction = core_value.get("reduction_meta") or {}
    method = reduction.get("method") or reduction.get("method_id") or "n/a"
    rule = reduction.get("rule") or {}
    negs = reduction.get("neg_alternatives_same_k") or []

    lines = []
    lines.append("## 10-second claim")
    lines.append(f"In RT Core, **{q}** is **{status}** (scope: `{scope}`) by internal gates and deterministic selection. "
                 f"External reference values are used only in Compare.")
    lines.append("")
    lines.append("## Core derivation (1 minute)")
    lines.append("**What is being computed**")
    sym = core_value.get("symbol")
    rel = core_value.get("relation")
    if sym:
        lines.append(f"- Definition tag: `{sym}`")
    if rel:
        rel_s = rel if isinstance(rel, str) else json.dumps(rel, ensure_ascii=False)
        lines.append(f"- Relation: `{rel_s}`")
    lines.append(f"- Candidate construction type: `{t}`")
    if cand_full is not None and kept is not None:
        lines.append(f"- Reduction summary: start `{cand_full}` candidates → keep `{kept}` → report preferred value.")
    if method and method != "n/a":
        lines.append(f"- Reduction method: `{method}`")

    # Gates / forcing rules
    gates = []
    if isinstance(rule, dict):
        for k in ["z3_gate", "mode_gate", "tie_break", "prefer_family", "require_family_h_if_duty_lock"]:
            if k in rule and rule[k]:
                gates.append(f"{k}: {rule[k]}")
    inv = core_value.get("invariants") or {}
    if inv.get("expr"):
        gates.insert(0, f"invariant: {inv.get('expr')} = {inv.get('value')}")
    if gates:
        lines.append("")
        lines.append("**Why the value is forced**")
        for g in gates[:5]:
            lines.append(f"- {g}")

    # Uniqueness
    lines.append("")
    lines.append("**Uniqueness (why there is no tuning)**")
    _u0 = len(lines)
    pref = core_value.get("preferred")
    if isinstance(pref, dict) and pref.get("rule"):
        lines.append(f"- Preferred selection rule: `{pref.get('rule')}`")
    if promotion:
        # keep it short
        prom = promotion if len(str(promotion)) < 140 else (str(promotion)[:137] + "...")
        lines.append(f"- Promotion rule: `{prom}`")
    # If uniqueness summary is missing in metadata, say so explicitly.
    if len(lines) == _u0:
        lines.append("- Uniqueness summary not recorded in index metadata; see lock artifacts and index pointers below.")

    # Negative controls (compact)
    if negs:
        lines.append("")
        lines.append("**Negative controls (examples that are rejected)**")
        for n in negs[:3]:
            a_id = n.get("alpha_id") or n.get("id") or "alt"
            expect = n.get("expect") or "rejected by gates"
            fam = n.get("family")
            tag = f"{a_id}" + (f" (family {fam})" if fam else "")
            exp = expect if len(str(expect)) < 120 else (str(expect)[:117] + "...")
            lines.append(f"- {tag}: {exp}")

    return "\n".join(lines)

def _render_rt_short_formula_en(core_entry: dict) -> str:
    core_value = core_entry.get("core_value") or {}
    pref = core_value.get("preferred")
    if not isinstance(pref, dict):
        pref = {}
    sym = core_value.get("symbol")
    expr = pref.get("expr")
    pid = pref.get("id")
    lines = ["## RT short formula"]
    if sym:
        lines.append(f"- `{sym}`")
    if expr and isinstance(expr, str) and len(expr) <= 96:
        lines.append(f"- Preferred expression: `{expr}`")
    elif pid:
        lines.append(f"- Preferred expression id: `{pid}` (exact expression is recorded at the Core index pointer below)")
    else:
        if "value" in core_value and isinstance(core_value.get("value"), (int, float, str, bool)):
            lines.append("- Scalar is recorded as `core_value.value` in the Core index (see pointer below).")
        elif "delta_principal_deg" in core_value and isinstance(core_value.get("delta_principal_deg"), (int, float)):
            lines.append("- Scalar is recorded as `core_value.delta_principal_deg` (tie-broken branch) in the Core index (see pointer below).")
        else:
            lines.append("- Construction is recorded in the Core index entry (`core_value`) and in the lock artifact listed below (see pointers under “Values and traceability”).")
    return "\n".join(lines)

def _compare_preferred_obj(detail0: dict):
    """Return the object that Compare actually compares.

    Compare details may store the computed quantity in a few equivalent shapes:
      - details[0].core is already a scalar (float/int/str)
      - details[0].core.preferred is a scalar
      - details[0].core.preferred is a dict with one of {approx,value,scalar,val}

    This function is representational only (no external data usage).
    """
    core = detail0.get("core")

    # Sometimes Compare stores the computed value directly.
    if core is None:
        return None
    if isinstance(core, (int, float, str, bool)):
        return core

    # Sometimes it's a list/tuple (rare); prefer the first element if scalar.
    if isinstance(core, (list, tuple)) and core:
        if isinstance(core[0], (int, float, str, bool)):
            return core[0]
        # fall through to stringify the whole object
        return core

    # Normal case: dict with preferred
    if isinstance(core, dict):
        pref = core.get("preferred")
        if isinstance(pref, dict):
            for k in ("approx", "value", "scalar", "val"):
                if k in pref and isinstance(pref.get(k), (int, float, str, bool)):
                    return pref.get(k)
            return pref
        if isinstance(pref, (int, float, str, bool)):
            return pref

        # Fallback: if core itself has a value-like field
        for k in ("approx", "value", "scalar", "val"):
            if k in core and isinstance(core.get(k), (int, float, str, bool)):
                return core.get(k)

        return core

    # Unknown shape
    return core


def _describe_ref_key(ref_key, unit: Optional[str] = None) -> str:
    """Human-readable description for common Compare reference keys.

    This is only a label for readability; the raw key is always shown too.
    """
    if ref_key is None:
        return "n/a"
    r = str(ref_key)
    rl = r.lower()

    # Lepton ratios
    if ("m_mu" in rl and "m_e" in rl and ("over" in rl or "/" in rl)) or "mu_over_e" in rl:
        base = "lepton mass ratio mμ/me"
    elif ("m_tau" in rl and "m_mu" in rl and ("over" in rl or "/" in rl)) or "tau_over_mu" in rl:
        base = "lepton mass ratio mτ/mμ"
    elif ("m_tau" in rl and "m_e" in rl and ("over" in rl or "/" in rl)) or "tau_over_e" in rl:
        base = "lepton mass ratio mτ/me"
    # Quark ratios (scheme proxies) — order matters (numerator/denominator)
    elif "m_d_over_m_s" in rl or "md_over_ms" in rl:
        base = "quark mass ratio md/ms (scheme proxy)"
    elif "m_s_over_m_d" in rl or "ms_over_md" in rl:
        base = "quark mass ratio ms/md (scheme proxy)"
    elif "m_u_over_m_c" in rl or "mu_over_mc" in rl:
        base = "quark mass ratio mu/mc (scheme proxy)"
    elif "m_c_over_m_u" in rl or "mc_over_mu" in rl:
        base = "quark mass ratio mc/mu (scheme proxy)"
    elif "m_b_over_m_s" in rl or "mb_over_ms" in rl:
        base = "quark mass ratio mb/ms (scheme proxy)"
    elif "m_s_over_m_b" in rl or "ms_over_mb" in rl:
        base = "quark mass ratio ms/mb (scheme proxy)"
    elif "m_b_over_m_t" in rl or "mb_over_mt" in rl:
        base = "quark mass ratio mb/mt (scheme proxy)"
    elif "m_t_over_m_b" in rl or "mt_over_mb" in rl:
        base = "quark mass ratio mt/mb (scheme proxy)"

    # Angles / couplings
    elif "sin2" in rl and "theta" in rl and "w" in rl:
        base = "electroweak mixing angle sin²θ_W"
    elif "alpha" in rl:
        base = "fine-structure constant α (overlay mapping)"
    elif "g_s" in rl or "alpha_s" in rl:
        base = "strong coupling proxy (compare-only running/scheme)"
    elif "ckm" in rl or "pmns" in rl:
        base = "mixing parameter (angles/phase from unitary reconstruction)"
    else:
        base = r.replace("_", " ")

    if unit == "ratio":
        return base + " (dimensionless ratio)"
    return base

def _filter_compare_details_for_page(core_entry: dict, details: list) -> tuple:
    """Select/annotate Compare details for this page.

    Returns a list of (orig_index, detail_dict) so JSON pointers remain truthful even when we reorder.

    Reader-facing principle:
    - Each page should be understandable on its own.
    - Avoid duplicating the same lepton ratio checks on multiple pages (looks like a copy/paste bug).
    """
    p_key = str(core_entry.get('parameter') or '')
    indexed = list(enumerate(details))

    def _pick_first_by_substrings(want_subs):
        subs = [s.lower() for s in (want_subs if isinstance(want_subs, (list, tuple)) else [want_subs])]
        for j, d in indexed:
            ref = str(d.get('ref','')).lower()
            if any(s in ref for s in subs):
                return j, d
        return None

    # Lepton pages: show ONE primary ratio per page to avoid duplication across P01–P03.
    if p_key in ('Elektronmassa', 'Muonmassa', 'Taumassa'):
        note = (
            'Lepton absolute masses are not anchored in Core. '
            'Compare validates the lepton sector via ratios.'
        )

        d_mu_e = _pick_first_by_substrings(['m_mu_over_m_e', 'mu_over_e'])
        d_tau_mu = _pick_first_by_substrings(['m_tau_over_m_mu', 'tau_over_mu'])

        if p_key == 'Elektronmassa':
            if d_mu_e:
                return [d_mu_e], note
            return indexed, note

        if p_key == 'Muonmassa':
            if d_tau_mu:
                return [d_tau_mu], note
            return indexed, note

        # Tau page: show both ratios so implied mτ/me can be read as their product.
        sel = []
        if d_tau_mu:
            sel.append(d_tau_mu)
        if d_mu_e:
            sel.append(d_mu_e)
        if sel:
            return sel, (note + ' This page shows both ratios so the implied mτ/me can be read as their product.')
        return indexed, note

    # Neutrino mass pages share a single pattern validation (typically Δm² ratios); keep the pattern check first.
    if p_key in ('Neutrino‑massa 1', 'Neutrino‑massa 2', 'Neutrino‑massa 3'):
        note = (
            'Neutrino absolute masses are not anchored in Core. '
            'Compare validates the neutrino sector via Δm² ratios/patterns.'
        )

        def _score(item):
            _, d = item
            ref = str(d.get('ref','')).lower()
            return 0 if ('dm2' in ref or 'dmsq' in ref or 'delta_m2' in ref or 'dm^2' in ref) else 1

        ordered = sorted(indexed, key=_score)
        return ordered, note

    return indexed, None


def _render_values_traceability_en(
    core_entry: dict,
    compare_entry: Optional[dict],
    *,
    core_index_file: str,
    core_index_pos: Optional[int],
    compare_index_file: Optional[str],
    compare_index_pos: Optional[int],
    overlay_kappa_value: Optional[float],
) -> str:
    p_sv = core_entry.get("parameter")
    core_value = core_entry.get("core_value") or {}
    rt_obj = _core_preferred_obj(core_value)
    unit = core_value.get("unit")
    unit_disp = unit
    # Some Core entries carry multi-field unit metadata (e.g. {'delta':'deg','J':'dimensionless'}).
    # If the stored Core preferred value is scalar, prefer the unit used by the first Compare detail (if any).
    if isinstance(unit, dict) and not isinstance(rt_obj, (dict, list)):
        d0u = None
        try:
            d0u = (compare_entry.get("details") or [])[0].get("unit") if compare_entry else None
        except Exception:
            d0u = None
        if isinstance(d0u, str):
            unit_disp = d0u
        else:
            unit_disp = unit.get('delta') or unit.get('value') or next(iter(unit.values()), None)
    source_lock = core_entry.get("source_lock")
    artifact = core_entry.get("artifact")

    lines = ["## Values and traceability", "**RT value (Core)**"]

    explain = _explain_core_value(core_entry, rt_obj)
    # Keep the main value line clean: do not inline JSON for dict/list.
    if isinstance(rt_obj, dict):
        val_str = 'multi-valued object (dict)'
    elif isinstance(rt_obj, list):
        val_str = f'multi-valued object (list,len={len(rt_obj)})'
    else:
        val_str = _fmt_short_value(rt_obj, unit_disp)
    lines.append(f"- Value: **{val_str}**" + (f" — {explain}" if explain else ""))
    if val_str == 'N/A' and compare_entry and (compare_entry.get('details') or []):
        lines.append('- Note: Core index does not store a scalar here; Compare extracts the scalar from the Core multi-output object (see Compare section below).')
    # Reader-facing notes for common scope/validation patterns.
    scope_s = str(core_entry.get('core_scope') or '')
    if 'PROXY_RATIO_ONLY_OVERLAY_ANCHOR' in scope_s:
        lines.append('- Note: This Core value is a proxy component. Compare maps the proxy set to one or more *ratios* (e.g. m_u/m_c) for validation.')
    # Important: do not match substrings ("PROXY_RATIO_ONLY_OVERLAY_ANCHOR" contains the token),
    # otherwise this lepton/neutrino note leaks onto quark proxy pages.
    if scope_s.strip() == 'RATIO_ONLY_OVERLAY_ANCHOR':
        lines.append('- Note: Core does not set an absolute SI mass scale. Lepton/neutrino checks are therefore shown as ratios/patterns in Compare.')

    # Lepton pages: make the page-specific ratio explicit (so "Electron mass" does not look unrelated to ratios).
    if p_sv in ('Elektronmassa', 'Muonmassa', 'Taumassa') and isinstance(rt_obj, dict):
        rpred = rt_obj.get('ratios_pred')
        if isinstance(rpred, dict):
            mu_e = rpred.get('m_mu_over_m_e')
            tau_mu = rpred.get('m_tau_over_m_mu')
            if p_sv == 'Elektronmassa' and isinstance(mu_e, (int, float)):
                lines.append(f"- Selected ratio for this page: **mμ/me = {_fmt_short_value(mu_e, 'ratio')}**")
            elif p_sv == 'Muonmassa' and isinstance(tau_mu, (int, float)):
                lines.append(f"- Selected ratio for this page: **mτ/mμ = {_fmt_short_value(tau_mu, 'ratio')}**")
            elif p_sv == 'Taumassa':
                # Prefer explicit tau/e if recorded; otherwise show the product when available.
                tau_e = rpred.get('m_tau_over_m_e')
                if isinstance(tau_e, (int, float)):
                    lines.append(f"- Selected ratio for this page: **mτ/me = {_fmt_short_value(tau_e, 'ratio')}**")
                elif isinstance(mu_e, (int, float)) and isinstance(tau_mu, (int, float)):
                    lines.append(f"- Derived ratio for this page: **mτ/me = (mτ/mμ)·(mμ/me) = {_fmt_short_value(tau_mu*mu_e, 'ratio')}**")


    # If Core is BLANK but we know the overlay κ freeze, show it explicitly for clarity.
    if str(core_entry.get("derivation_status") or "").upper() == "BLANK" and overlay_kappa_value is not None:
        lines.append(
            f"- Note: κ is BLANK in Core by policy; Overlay freeze (Compare-only anchor) is **{_fmt_short_value(overlay_kappa_value)}**."
        )

    for ln in _summarize_obj(rt_obj):
        lines.append(ln)

    lines.append(f"- Core status: `{core_entry.get('derivation_status')}`")
    lines.append(f"- Scope: `{core_entry.get('core_scope')}`")
    if source_lock:
        lines.append(f"- Source-lock: `{source_lock}`")

    if artifact:
        parts = [a.strip() for a in str(artifact).split(",") if a.strip()]
        if parts:
            lines.append("- Core artifacts (files):")
            for a in parts[:6]:
                lines.append(f"  - `{a}`")
            if len(parts) > 6:
                lines.append(f"  - ... (+{len(parts)-6} more)")

    # Deterministic, concrete index pointers
    lines.append(f"- Core index file: `{core_index_file}`")
    has_preferred = isinstance(core_value, dict) and ('preferred' in core_value)
    has_value = isinstance(core_value, dict) and ('value' in core_value)
    if core_index_pos is not None:
        if has_preferred:
            lines.append(
                f"- Core JSON pointer: `entries[{core_index_pos}].core_value.preferred` (use `.approx`/`.value` if present)"
            )
        elif has_value:
            lines.append(
                f"- Core JSON pointer: `entries[{core_index_pos}].core_value.value`"
            )
        else:
            lines.append(
                f"- Core JSON pointer: `entries[{core_index_pos}].core_value` (no `preferred` wrapper recorded for this entry)"
            )
    else:
        if has_preferred:
            lines.append(
                f"- Core JSON pointer: find entry where `parameter == '{p_sv}'`; then read `core_value.preferred`"
            )
        elif has_value:
            lines.append(
                f"- Core JSON pointer: find entry where `parameter == '{p_sv}'`; then read `core_value.value`"
            )
        else:
            lines.append(
                f"- Core JSON pointer: find entry where `parameter == '{p_sv}'`; then read `core_value`"
            )

    lines.append("")
    lines.append("**SM value (Compare only)**")
    if not compare_entry:
        lines.append("- Compare not run (no compare index found).")
        return "\n".join(lines)

    lines.append(f"- Compare summary status: `{compare_entry.get('validation_status')}`")

    details_all = (compare_entry.get("details") or [])
    details, details_note = _filter_compare_details_for_page(core_entry, list(details_all))
    if details_note:
        lines.append(f"- Note: {details_note}")
    if details:
        # Show up to 4 compare details (A4-safe); each detail is what Compare actually validated.
        for j, item in enumerate(details[:4]):
            orig_j, d0 = item
            ref = d0.get("ref")
            ref_value = d0.get("ref_value")
            unit2 = d0.get("unit")
            tol = d0.get("tol")
            compared_obj = _compare_preferred_obj(d0)

            # Some compares encode ranges via tol='range[lo,hi]' even when ref_value is a scalar center.
            range_from_tol = None
            if isinstance(tol, str) and tol.startswith('range[') and ',' in tol and ']' in tol:
                try:
                    inside = tol[tol.find('[')+1:tol.rfind(']')]
                    a,b = inside.split(',', 1)
                    range_from_tol = (float(a.strip()), float(b.strip()))
                except Exception:
                    range_from_tol = None

            # Separate multiple checks on the same page.
            if j > 0:
                lines.append("")

            # Classify the compare check so 'AGREES' is interpretable.
            is_bool = (unit2 == "bool") or (tol == "bool") or isinstance(ref_value, bool)
            is_range = (isinstance(ref_value, list) and len(ref_value) == 2 and all(isinstance(x, (int, float)) for x in ref_value)) or (range_from_tol is not None)
            if is_bool:
                cclass = "STRUCTURAL CHECK (gate)"
            elif is_range:
                cclass = "RANGE CHECK"
            else:
                cclass = "SCALAR CHECK"

            lines.append(f"- Compare class: {cclass}")
            lines.append(f"- Compared quantity: `{ref}` — {_describe_ref_key(ref, unit2)}")
            if unit2:
                lines.append(f"- Unit: `{unit2}`")

            if is_bool:
                try:
                    gate_pass = bool(compared_obj)
                except Exception:
                    gate_pass = False
                lines.append(f"- Overlay calculation results in: **{'PASS' if gate_pass else 'FAIL'}**")
                lines.append(f"- Raw result: `{_fmt_short_value(compared_obj, unit2)}`")
            else:
                lines.append(f"- Overlay calculation results in: **{_fmt_short_value(compared_obj, unit2)}**")

            for ln in _summarize_obj(compared_obj):
                lines.append(ln)

            # Reference value formatting differs by class
            if is_bool:
                # Gate checks are PASS/FAIL, not numeric fits.
                try:
                    gate_pass = bool(compared_obj)
                except Exception:
                    gate_pass = False
                lines.append(f"- Gate result: **{'PASS' if gate_pass else 'FAIL'}**")
                lines.append(f"- Expected (gate): **{_fmt_short_value(ref_value, unit2)}**")
                lines.append("- Note: This is a structural gate in Compare (PASS/FAIL), not a PDG/CODATA numeric fit.")
            elif is_range:
                # Prefer explicit reference ranges; otherwise use the tol range if present.
                lo = hi = None
                if isinstance(ref_value, list) and len(ref_value) == 2:
                    try:
                        lo, hi = float(ref_value[0]), float(ref_value[1])
                    except Exception:
                        lo = hi = None
                elif range_from_tol is not None:
                    lo, hi = range_from_tol
                    # Keep the scalar ref_value visible as the range center when available.
                    if ref_value is not None and not isinstance(ref_value, bool):
                        lines.append(f"- SM/reference value (center): **{_fmt_short_value(ref_value, unit2)}**")
                if lo is not None and hi is not None:
                    lines.append(f"- SM/reference range: **{_fmt_short_value([lo, hi], unit2)}**")
                    try:
                        x = float(compared_obj)
                        in_rng = (lo <= x <= hi)
                        lines.append(f"- In range: `{in_rng}`")
                    except Exception:
                        pass
                else:
                    lines.append(f"- SM/reference range: **{_fmt_short_value(ref_value, unit2)}**")
            else:
                lines.append(f"- SM/reference value: **{_fmt_short_value(ref_value, unit2)}**")
                # Error reporting: respect tol_abs / tol_rel when present.
                tol_abs = d0.get('tol_abs')
                tol_rel = d0.get('tol_rel')
                try:
                    x = float(compared_obj)
                    y = float(ref_value)
                    abs_err = abs(x - y)
                    rel_err = abs_err / abs(y) if y != 0 else None
                    if tol_abs is not None:
                        lines.append(f"- Absolute error: `{abs_err:.3g}` (tol_abs={tol_abs})")
                    elif tol_rel is not None:
                        if rel_err is not None:
                            lines.append(f"- Relative error: `{rel_err:.3g}` (tol_rel={tol_rel})")
                        else:
                            lines.append(f"- Absolute error: `{abs_err:.3g}` (reference is zero)")
                    else:
                        # If no explicit tol fields, show both in a compact way.
                        if rel_err is not None:
                            lines.append(f"- Error: abs=`{abs_err:.3g}`, rel=`{rel_err:.3g}`")
                        else:
                            lines.append(f"- Error: abs=`{abs_err:.3g}`")
                except Exception:
                    pass

            if tol:
                lines.append(f"- Tolerance: `{tol}`")

            if compare_index_file:
                lines.append(f"- Compare index file: `{compare_index_file}`")
            if compare_index_pos is not None:
                if orig_j is None:
                    lines.append("- Compare JSON pointer: derived from multiple details on this page (see the two pointers above).")
                else:
                    lines.append(f"- Compare JSON pointer: `entries[{compare_index_pos}].details[{orig_j}]` (uses `.ref_value` and `.core.preferred`)")
            else:
                lines.append("- Compare JSON pointer: find entry where `parameter == ...`; use `details[*].ref_value` and `details[*].core.preferred`.")
    else:
        if details_note:
            lines.append("- Compare details are intentionally reported on the referenced page(s) and are not duplicated here.")
        elif p_sv == 'κ (SI‑ankare)':
            lines.append("- Compare does not record a κ value in this repo (Overlay-only policy), therefore UNTESTED.")
        else:
            lines.append("- Compare has no per-parameter detail records for this entry in the current compare index.")

    return "\n".join(lines)


def _write_sm29_pages_en(*, repo_root: Path, core_index_path: Path, compare_index_path: Optional[Path], out_path: Path) -> None:
    """Generate `out/SM29_PAGES.md`.

    Reviewer goals:
    - A4-first overview (print-friendly), then sector pages.
    - Form before numbers: Core fixes structure/ratios by gates+NEG+tiebreak; Compare maps to comparable quantities.
    - Never leak absolute local paths (use repo-relative paths in the report).
    """

    core_idx = _load_json(core_index_path)
    core_list = list(core_idx.get("entries", []) or [])
    core_entries = {e.get("parameter"): e for e in core_list if e.get("parameter") is not None}

    compare_entries = {}
    compare_list = []
    if compare_index_path and compare_index_path.exists():
        cmp_idx = _load_json(compare_index_path)
        compare_list = list(cmp_idx.get("entries", []) or [])
        compare_entries = {e.get("parameter"): e for e in compare_list if e.get("parameter") is not None}

    # Repo-relative pointers
    core_rel = core_index_path.relative_to(repo_root).as_posix() if core_index_path.is_absolute() else core_index_path.as_posix()
    cmp_rel = None
    if compare_index_path:
        cmp_rel = compare_index_path.relative_to(repo_root).as_posix() if compare_index_path.is_absolute() else compare_index_path.as_posix()

    # κ (overlay-only anchor) for transparency on the κ page
    overlay_kappa_value = None
    kappa_rel = "00_TOP/OVERLAY/kappa_global.json"
    kappa_path = repo_root / kappa_rel
    if kappa_path.exists():
        try:
            kobj = _load_json(kappa_path)
            if isinstance(kobj, dict):
                for kk in ("kappa_L_m_per_RT", "kappa_L_fm_per_RT", "kappa", "value", "kappa_value", "kappa_global"):
                    vv = kobj.get(kk)
                    if isinstance(vv, (int, float)):
                        overlay_kappa_value = float(vv)
                        break
        except Exception:
            overlay_kappa_value = None

    # Counts (Core / Compare)
    d_stat = [str(e.get("derivation_status") or "") for e in core_list]
    v_stat = [str(compare_entries.get(e.get("parameter"), {}).get("validation_status") or "") for e in core_list]
    core_derived = sum(1 for s in d_stat if s == "DERIVED")
    core_blank = sum(1 for s in d_stat if s == "BLANK")
    cmp_agrees = sum(1 for s in v_stat if s == "AGREES")
    cmp_untested = sum(1 for s in v_stat if s == "UNTESTED")

    # Determinism (hash lock)
    hash_lock_match = None
    hash_lock_rel = None
    try:
        hl_dir = repo_root / "out/CORE_CORE_ARTIFACT_HASH_LOCK"
        cands = sorted(hl_dir.glob("core_artifact_hash_lock_core_*.md"), key=lambda p: p.stat().st_mtime)
        if cands:
            hl = cands[-1]
            hash_lock_rel = hl.relative_to(repo_root).as_posix()
            t = _read_text(hl)
            m = re.search(r"\bmatch:\s*\*\*(True|False)\*\*", t)
            if m:
                hash_lock_match = (m.group(1) == "True")
    except Exception:
        pass

    # Influence audit summary (approx): count forbidden opens by contract patterns.
    forbidden_total = None
    core_audit_rel = None
    try:
        aud_dir = repo_root / "out/CORE_AUDIT"
        # pick the latest core_suite_run file as the run reference
        suite = sorted(aud_dir.glob("core_suite_run_*.md"), key=lambda p: p.stat().st_mtime)
        if suite:
            core_audit_rel = suite[-1].relative_to(repo_root).as_posix()

        def is_forbidden_path(p: str) -> bool:
            ps = p.replace('\\\\','/').lower()
            if '/00_top/overlay/' in ps:
                return True
            # reference jsons are forbidden in Core
            base = ps.rsplit('/', 1)[-1]
            if base.endswith('.json') and 'reference' in base:
                return True
            if 'codata' in ps or 'pdg' in ps or 'targets' in ps:
                return True
            return False

        fcount = 0
        for aj in aud_dir.glob("*_audit_*.json"):
            try:
                obj = _load_json(aj)
                opened = obj.get('opened') or []
                for item in opened:
                    p = item.get('path') if isinstance(item, dict) else None
                    if isinstance(p, str) and is_forbidden_path(p):
                        fcount += 1
            except Exception:
                continue
        forbidden_total = fcount
    except Exception:
        forbidden_total = None

    # -------------------------
    # A4-first preamble
    # -------------------------
    pre: List[str] = []
    pre.append("# SM29 — Reviewer report (A4-first)")
    pre.append("")
    pre.append(f"Generated: {date.today().isoformat()}")
    pre.append("Generated by: `00_TOP/LOCKS/SM_PARAM_INDEX/sm29_report.py`")
    pre.append("")
    pre.append("Inputs:")
    pre.append(f"- Core index: `{core_rel}`")
    if cmp_rel:
        pre.append(f"- Compare index: `{cmp_rel}`")
    else:
        pre.append("- Compare index: (missing)")
    pre.append("")
    pre.append("**Form before numbers:** Core fixes the *form* (ratios, discrete patterns, structural gates) by RT-internal rules only: gates (C30, Z3, A/B, RCC, audits) + NEG + deterministic tie-break. Compare is a separate pipeline that maps Core artifacts into comparable quantities and checks them against references.")
    pre.append("")
    pre.append("**Core/Compare separation:** Core never reads external targets (no PDG/CODATA in Core). Compare uses references only after Core artifacts exist.")
    pre.append("")

    pre.append("## A4 overview")
    pre.append("")
    pre.append("**Snapshot (this repo run):**")
    pre.append(f"- Core: DERIVED **{core_derived}/29**, BLANK **{core_blank}/29** (policy BLANK: κ overlay-only).")
    pre.append(f"- Compare: AGREES **{cmp_agrees}/29**, UNTESTED **{cmp_untested}/29** (policy UNTESTED: κ).")
    if forbidden_total is not None:
        pre.append(f"- Influence audit (Core): FORBIDDEN opens **{forbidden_total}** (contract patterns: OVERLAY/, *reference*.json, PDG/CODATA/targets).")
    if core_audit_rel:
        pre.append(f"- Latest Core suite run log: `{core_audit_rel}`")
    if hash_lock_match is not None:
        pre.append(f"- Determinism (Core artifact hash lock): match = **{hash_lock_match}**" + (f" (`{hash_lock_rel}`)" if hash_lock_rel else ""))
    pre.append("")
    pre.append(f"**Inputs:** Core index `{core_rel}`" + (f", Compare index `{cmp_rel}`" if cmp_rel else ", Compare index: (not found)"))
    pre.append("")

    pre.append("### How to reproduce")
    pre.append("Run these from repo root:")
    pre.append("- `python3 00_TOP/TOOLS/run_core_no_facit_suite.py`")
    pre.append("- `python3 00_TOP/TOOLS/run_compare_suite.py`")
    pre.append("- `python3 00_TOP/LOCKS/SM_PARAM_INDEX/sm29_report.py` (regenerates this report)")
    pre.append("")

    pre.append("### Trust checks (anti-facit)")
    if forbidden_total is not None:
        pre.append(f"- Influence audit summary (Core): FORBIDDEN opens = **{forbidden_total}**")
    if core_audit_rel:
        pre.append(f"- Evidence log: `{core_audit_rel}`")
    if hash_lock_match is not None:
        pre.append(f"- Determinism: Core artifact hash lock match = **{hash_lock_match}**" + (f" (`{hash_lock_rel}`)" if hash_lock_rel else ""))
    # Optional marker: overlay-off test
    overlay_off_rel = None
    overlay_off_pass = None
    try:
        aud_dir = repo_root / "out/CORE_AUDIT"
        off = sorted(aud_dir.glob("overlay_off_test_*.md"), key=lambda p: p.stat().st_mtime)
        if off:
            overlay_off_rel = off[-1].relative_to(repo_root).as_posix()
            t = _read_text(off[-1])
            m = re.search(r"\bPASS\b", t)
            overlay_off_pass = bool(m)
    except Exception:
        pass
    if overlay_off_rel:
        pre.append(f"- Overlay folder disabled (rename OVERLAY→OVERLAY__OFF) test: **{'PASS' if overlay_off_pass else 'FAIL'}** (`{overlay_off_rel}`)")
    else:
        pre.append("- Overlay folder disabled test: (not recorded in this build; recommended reviewer step)")
    pre.append("")

    pre.append("### Legend")
    pre.append("- **Core DERIVED**: produced by RT-internal rules only (no external targets).")
    pre.append("- **Core BLANK**: intentionally not produced in Core (policy).")
    pre.append("- **Compare AGREES**: Compare computed a comparable value and it passed its check.")
    pre.append("- **Compare UNTESTED**: Compare does not check this (policy anchor) or lacks data.")
    pre.append("- **SCALAR CHECK**: compare a scalar value to a reference (with tolerance).")
    pre.append("- **RANGE CHECK**: compare a scalar to a reference interval (scheme-dependent quantities use ranges).")
    pre.append("- **STRUCTURAL CHECK**: boolean/identity gate (PASS/FAIL, not a numeric match).")
    pre.append("")

    pre.append("### What a reviewer should look for")
    pre.append("- **Core page:** where the candidate set comes from, and the deterministic rule selecting `preferred` (no scores vs facit).")
    pre.append("- **Compare page:** always contains the line `Overlay calculation results in: ...` showing the computed comparable quantity.")
    pre.append("- **Structural checks** are shown as PASS/FAIL (not a numeric match).")
    pre.append("- **Range checks** are shown with `In range: True/False`.")
    pre.append("")

    # ---------------------------------
    # SM29 summary table (A4-friendly)
    # ---------------------------------
    def _core_output_kind(e: dict) -> str:
        cv = e.get('core_value')
        if cv is None:
            return 'BLANK'
        if isinstance(cv, dict):
            if 'gate' in cv or (isinstance(cv.get('unit'), str) and cv.get('unit') == 'bool'):
                return 'STRUCT_GATE'
            if 'compare_proxy' in cv:
                return 'PROXY→RATIO'
            pref = cv.get('preferred')
            if isinstance(pref, dict) and isinstance(pref.get('ratios_pred'), dict):
                return 'RATIO_SET'
            if isinstance(pref, dict) and isinstance(pref.get('expr'), str):
                return 'EXPR→SCALAR'
            if 'value' in cv:
                return 'SCALAR'
            if any(k.startswith('delta_') for k in cv.keys()):
                return 'DICT (multi)'
        return 'VALUE'

    def _compare_check_kind(details: list[dict]) -> str:
        if not details:
            return 'UNTESTED'
        kinds = []
        for d in details:
            unit = d.get('unit')
            tol = d.get('tol')
            rv = d.get('ref_value')
            is_bool = (unit == 'bool') or (tol == 'bool') or isinstance(rv, bool)
            is_range = isinstance(rv, list) and len(rv) == 2
            if is_bool:
                kinds.append('STRUCT')
            elif is_range:
                kinds.append('RANGE')
            else:
                kinds.append('SCALAR')
        # compact
        out = []
        for k in ('SCALAR','RANGE','STRUCT'):
            n = sum(1 for x in kinds if x == k)
            if n:
                out.append(f"{k}×{n}" if n > 1 else k)
        return "+".join(out) if out else 'UNTESTED'

    pre.append("### SM29 summary table")
    pre.append("(One line per parameter; use sector pages below for full trace.)")
    pre.append("")
    pre.append("| ID | Parameter | Core status | Core output | Compare status | Compare check | Source lock |")
    pre.append("|---:|---|---|---|---|---|---|")

    # Fixed, reviewer-friendly ordering (matches the Pxx pages)
    ordered = [
        'Elektronmassa','Muonmassa','Taumassa',
        'Up‑kvarkmassa','Down‑kvarkmassa','Charm‑kvarkmassa','Strange‑kvarkmassa','Top‑kvarkmassa','Bottom‑kvarkmassa',
        'Neutrino‑massa 1','Neutrino‑massa 2','Neutrino‑massa 3',
        'EM‑koppling (α)','Svag koppling (g)','Stark koppling (g_s)',
        'CKM vinkel 1','CKM vinkel 2','CKM vinkel 3','CKM CP‑fas',
        'PMNS vinkel 1','PMNS vinkel 2','PMNS vinkel 3','PMNS CP‑fas',
        'Higgs‑massa','Higgs‑VEV (v)',
        'Stark CP‑vinkel (θ_QCD)',
        'PPN γ','PPN β',
        'κ (SI‑ankare)',
    ]

    def _pid(i: int) -> str:
        return f"P{i:02d}"

    for i, p in enumerate(ordered, start=1):
        ce = core_entries.get(p) or {}
        cmp_e = compare_entries.get(p) or {}
        core_status = str(ce.get('derivation_status') or '')
        core_kind = _core_output_kind(ce)
        cmp_status = str(cmp_e.get('validation_status') or '')
        check_kind = _compare_check_kind(list(cmp_e.get('details') or []))
        source_lock = str(ce.get('source_lock') or '')
        pre.append(f"| {_pid(i)} | {p} | {core_status} | {core_kind} | {cmp_status} | {check_kind} | {source_lock} |")

    pre.append("")

    # Short sector bullets (A4-friendly)
    def _cmp_detail_value(d: dict) -> tuple[str,str,str,str]:
        unit = d.get('unit')
        tol = d.get('tol')
        ref = d.get('ref')
        ref_value = d.get('ref_value')
        core_pref = _compare_preferred_obj(d)
        # classify
        is_bool = (unit == 'bool') or (tol == 'bool') or isinstance(ref_value, bool)
        if is_bool:
            return (str(ref), 'STRUCTURAL', 'PASS' if bool(core_pref) else 'FAIL', '')
        is_range = (isinstance(ref_value, list) and len(ref_value) == 2)
        if is_range:
            lo, hi = ref_value
            in_range = (isinstance(core_pref, (int,float)) and lo <= core_pref <= hi)
            return (str(ref), 'RANGE', f"{_fmt_short_value(core_pref, unit)} (in-range: {in_range})", f"[{_fmt_short_value(lo, unit)}, {_fmt_short_value(hi, unit)}]")
        return (str(ref), 'SCALAR', _fmt_short_value(core_pref, unit), _fmt_short_value(ref_value, unit))

    pre.append("### Sectors at a glance")
    pre.append("")

    # Leptons (use Elektronmassa compare entry as carrier)
    lep_cmp = compare_entries.get('Elektronmassa', {})
    lep_details = list(lep_cmp.get('details') or [])
    if lep_details:
        pre.append("**Leptons (m_e, m_μ, m_τ):** ratios (no SI scale in Core)")
        for d in lep_details:
            ref, kind, got, refv = _cmp_detail_value(d)
            if kind == 'SCALAR':
                pre.append(f"- {ref}: {got} (ref {refv})")
            else:
                pre.append(f"- {ref}: {got}")
        pre.append("")

    # Quarks (each entry has one range check)
    pre.append("**Quarks (u,d,c,s,t,b):** proxy → compared as ratios/ranges")
    for p in ['Up‑kvarkmassa','Down‑kvarkmassa','Charm‑kvarkmassa','Strange‑kvarkmassa','Top‑kvarkmassa','Bottom‑kvarkmassa']:
        ce = compare_entries.get(p, {})
        ds = list(ce.get('details') or [])
        if not ds:
            continue
        d = ds[0]
        ref, kind, got, refv = _cmp_detail_value(d)
        if kind == 'RANGE':
            pre.append(f"- {ref}: {got} vs {refv}")
        else:
            pre.append(f"- {ref}: {got} (ref {refv})")
    pre.append("")

    # Neutrinos
    nu_cmp = compare_entries.get('Neutrino‑massa 1', {})
    nu_details = list(nu_cmp.get('details') or [])
    if nu_details:
        pre.append("**Neutrinos (ν1,ν2,ν3):** pattern via Δm² ratios")
        d = nu_details[0]
        ref, kind, got, refv = _cmp_detail_value(d)
        pre.append(f"- {ref}: {got} vs {refv}")
        pre.append("")

    # Couplings
    pre.append("**Couplings:**")
    for p in ['EM‑koppling (α)','Svag koppling (g)','Stark koppling (g_s)']:
        ce = compare_entries.get(p, {})
        ds = list(ce.get('details') or [])
        if not ds:
            continue
        d = ds[0]
        ref, kind, got, refv = _cmp_detail_value(d)
        if kind == 'STRUCTURAL':
            pre.append(f"- {p}: {got}")
        else:
            pre.append(f"- {p}: {got} (ref {refv})")
    pre.append("")

    # Mixing
    pre.append("**Mixing:**")
    for p in ['CKM vinkel 1','CKM vinkel 2','CKM vinkel 3','CKM CP‑fas','PMNS vinkel 1','PMNS vinkel 2','PMNS vinkel 3','PMNS CP‑fas']:
        ce = compare_entries.get(p, {})
        ds = list(ce.get('details') or [])
        if not ds:
            continue
        d0 = ds[0]
        ref, kind, got, refv = _cmp_detail_value(d0)
        if kind == 'SCALAR':
            pre.append(f"- {ref}: {got} (ref {refv})")
        else:
            pre.append(f"- {ref}: {got}")
    pre.append("")

    # Higgs + θ_QCD + PPN + κ
    pre.append("**Structural / GR / Anchors:**")
    for p in ['Higgs‑massa','Higgs‑VEV (v)','Stark CP‑vinkel (θ_QCD)','PPN γ','PPN β','κ (SI‑ankare)']:
        ce = compare_entries.get(p, {})
        ds = list(ce.get('details') or [])
        if ds:
            d0 = ds[0]
            ref, kind, got, refv = _cmp_detail_value(d0)
            if kind == 'STRUCTURAL':
                pre.append(f"- {p}: {got}")
            elif kind == 'RANGE':
                pre.append(f"- {p}: {got} vs {refv}")
            else:
                pre.append(f"- {p}: {got} (ref {refv})")
        else:
            if p.startswith('κ') and overlay_kappa_value is not None:
                pre.append(f"- κ: frozen overlay-only anchor = {overlay_kappa_value} (not compared)")
            else:
                pre.append(f"- {p}: (no compare details)")

    parts: List[str] = ["\n".join(pre)]

    def add_page(md: str) -> None:
        if md.strip():
            parts.append("\\newpage")
            parts.append(md.strip())

    # -------------------------
    # Sector pages
    # -------------------------

    def render_core_header_for_entries(title: str, ids: str, parameters: list[str]) -> list[str]:
        lines = [f"# {title}", "", f"**Covers:** {ids}", ""]
        lines.append("## What this page contains")
        lines.append("- **Core:** what is produced, and where it lives (artifact file + JSON pointer in the Core index).")
        lines.append("- **Determinism:** if multiple candidates exist, the RT-internal tie-break rule selecting `preferred`.")
        lines.append("- **Compare:** the computed comparable quantity (the line `Overlay calculation results in: ...`) and the check type.")
        lines.append("")
        lines.append("**Parameters in this page:** " + ", ".join(parameters))
        return lines

    def render_compare_block_for_details(details: list[dict]) -> list[str]:
        out = ["## Compare (overlay-only validation)", ""]
        if not details:
            out.append("No Compare details recorded for this sector.")
            return out
        for d in details:
            ref = str(d.get('ref') or '')
            unit = d.get('unit')
            tol = d.get('tol')
            ref_value = d.get('ref_value')
            # Compare records both `hit` and `preferred` to make "any-hit vs preferred-hit" auditable.
            core_rec = d.get('core') if isinstance(d.get('core'), dict) else {}
            got_hit = core_rec.get('hit') if isinstance(core_rec.get('hit'), (int,float,bool)) else _compare_preferred_obj(d)
            got_pref = _compare_preferred_obj(d)
            out.append(f"### {ref}")
            if d.get('note'):
                out.append(f"- Note: {d.get('note')}")
            if 'any_hit' in d or 'preferred_hit' in d:
                out.append(f"- any_hit: `{d.get('any_hit')}`, preferred_hit: `{d.get('preferred_hit')}`")
            # classification
            is_bool = (unit == 'bool') or (tol == 'bool') or isinstance(ref_value, bool)
            is_range = (isinstance(ref_value, list) and len(ref_value) == 2)
            if is_bool:
                out.append(f"- STRUCTURAL CHECK: **{'PASS' if bool(got_hit) else 'FAIL'}**")
                out.append(f"- Overlay calculation results in: **{'PASS' if bool(got_hit) else 'FAIL'}**")
                if got_pref is not None and got_pref != got_hit:
                    out.append(f"- Preferred candidate: **{'PASS' if bool(got_pref) else 'FAIL'}**")
            elif is_range:
                lo, hi = ref_value
                in_range = (isinstance(got_hit, (int,float)) and float(lo) <= float(got_hit) <= float(hi))
                out.append(f"- RANGE CHECK: [{_fmt_short_value(lo, unit)}, {_fmt_short_value(hi, unit)}]")
                out.append(f"- In range: **{in_range}**")
                out.append(f"- Overlay calculation results in: **{_fmt_short_value(got_hit, unit)}**")
                if got_pref is not None and got_pref != got_hit:
                    out.append(f"- Preferred candidate: **{_fmt_short_value(got_pref, unit)}**")
            else:
                out.append(f"- SCALAR CHECK")
                out.append(f"- Overlay calculation results in: **{_fmt_short_value(got_hit, unit)}**")
                out.append(f"- Reference: **{_fmt_short_value(ref_value, unit)}**")
                if got_pref is not None and got_pref != got_hit:
                    out.append(f"- Preferred candidate: **{_fmt_short_value(got_pref, unit)}**")
            if tol:
                out.append(f"- Tolerance: `{tol}`")

            # Show compact Core candidate context (first few values only)
            cands = core_rec.get('candidates')
            if isinstance(cands, list) and cands:
                head = cands[:6]
                tail = " …" if len(cands) > 6 else ""
                out.append(f"- Core candidates (n={len(cands)}): {head}{tail}")
            out.append("")
        return out

    # Lepton sector page (P01–P03)
    lep_core = core_entries.get('Elektronmassa')
    lep_cmp = compare_entries.get('Elektronmassa', {})
    if lep_core:
        lines = render_core_header_for_entries(
            "[P01–P03] Lepton masses (m_e, m_μ, m_τ)",
            "P01 Electron mass, P02 Muon mass, P03 Tau mass",
            ["m_e", "m_μ", "m_τ"],
        )
        lines.append("")
        lines.append("## Core (ratio set)")
        cv = (lep_core.get('core_value') or {})
        pref = _core_preferred_obj(cv)
        if isinstance(pref, dict) and isinstance(pref.get('ratios_pred'), dict):
            r = pref['ratios_pred']
            mu_e = r.get('m_mu_over_m_e')
            tau_mu = r.get('m_tau_over_m_mu')
            lines.append("Core does **not** set an absolute SI mass scale. It outputs a ratio set:")
            if isinstance(mu_e, (int,float)):
                lines.append(f"- mμ/me = **{_fmt_short_value(mu_e, 'ratio')}**")
            if isinstance(tau_mu, (int,float)):
                lines.append(f"- mτ/mμ = **{_fmt_short_value(tau_mu, 'ratio')}**")
            if isinstance(mu_e, (int,float)) and isinstance(tau_mu, (int,float)):
                lines.append(f"- implied mτ/me = **{_fmt_short_value(mu_e*tau_mu, 'ratio')}** (product)")
        # provenance
        lines.append("")
        lines.append("**Core provenance:**")
        lines.append(f"- Core status: `{lep_core.get('derivation_status')}`")
        lines.append(f"- Scope: `{lep_core.get('core_scope')}`")
        lines.append(f"- Source-lock: `{lep_core.get('source_lock')}`")
        if lep_core.get('artifact'):
            lines.append(f"- Core artifact: `{lep_core.get('artifact')}`")
        lines.append(f"- Core index pointer: find entry where `parameter == 'Elektronmassa'` in `{core_rel}`")
        lines.append("")
        lines.extend(render_compare_block_for_details(list(lep_cmp.get('details') or [])))
        add_page("\n".join(lines))

    # Quark sector page (P04–P09)
    q_params = ['Up‑kvarkmassa','Down‑kvarkmassa','Charm‑kvarkmassa','Strange‑kvarkmassa','Top‑kvarkmassa','Bottom‑kvarkmassa']
    if all(p in core_entries for p in q_params):
        lines = render_core_header_for_entries(
            "[P04–P09] Quark masses (u,d,c,s,t,b)",
            "P04–P09 quark masses",
            ["m_u","m_d","m_c","m_s","m_t","m_b"],
        )
        lines.append("")
        lines.append("## Core (proxy components) and Compare mapping")
        lines.append("Core outputs **dimensionless proxy components** and a **proxy→ratio mapping** object. Compare validates the mapped ratio against a reference range. This avoids pretending scheme-dependent MSbar masses are Core-native.")
        lines.append("")
        lines.append("| Quark | Core proxy component | Compare ratio (computed) | Reference range | In range |")
        lines.append("|---|---:|---:|---:|---:|")
        # Also collect compare details for full trace below
        q_compare_details = []
        for p in q_params:
            ce = core_entries[p]
            cmp_e = compare_entries.get(p, {})
            ds = list(cmp_e.get('details') or [])
            if ds:
                q_compare_details.extend(ds)
            cv = ce.get('core_value') or {}
            choice = (cv.get('choice') or {}) if isinstance(cv, dict) else {}
            core_proxy = cv.get('value')
            unit = cv.get('unit') or 'dimensionless_proxy'
            # Compare ratio is stored in core_value.compare_proxy.preferred.approx (for transparency)
            comp_ratio = None
            try:
                cp = cv.get('compare_proxy') or {}
                pref = cp.get('preferred') or {}
                comp_ratio = pref.get('approx')
            except Exception:
                comp_ratio = None
            # Reference range from compare details
            ref_range = None
            got = None
            in_range = None
            if ds:
                d0 = ds[0]
                got = _compare_preferred_obj(d0)
                rv = d0.get('ref_value')
                if isinstance(rv, list) and len(rv) == 2:
                    ref_range = rv
                    if isinstance(got, (int,float)):
                        in_range = (float(rv[0]) <= float(got) <= float(rv[1]))
            qname = _EN_PARAM.get(p, (p,''))[1] or p
            lines.append(
                f"| {qname} | {_fmt_short_value(core_proxy, unit)} | {_fmt_short_value(got if got is not None else comp_ratio, 'ratio')} | "
                f"{('['+_fmt_short_value(ref_range[0],'ratio')+', '+_fmt_short_value(ref_range[1],'ratio')+']') if ref_range else 'N/A'} | "
                f"{str(in_range) if in_range is not None else 'N/A'} |"
            )
        lines.append("")
        lines.append("**Core provenance (shared):**")
        lines.append(f"- Source-locks: QUARK_PROXY_REDUCE_LOCK / QUARK_PROXY_* (see each Core entry in `{core_rel}`)")
        lines.append("")
        lines.extend(render_compare_block_for_details(q_compare_details))
        add_page("\n".join(lines))

    # Neutrino sector page (P10–P12)
    nu_core = core_entries.get('Neutrino‑massa 1')
    nu_cmp = compare_entries.get('Neutrino‑massa 1', {})
    if nu_core:
        lines = render_core_header_for_entries(
            "[P10–P12] Neutrino masses (ν1, ν2, ν3)",
            "P10 Neutrino mass 1, P11 Neutrino mass 2, P12 Neutrino mass 3",
            ["m_ν1", "m_ν2", "m_ν3"],
        )
        lines.append("")
        lines.append("## Core (pattern)")
        cv = nu_core.get('core_value') or {}
        pref = _core_preferred_obj(cv)
        if isinstance(pref, dict):
            dm = pref.get('delta_m2_ratio_exact')
            if isinstance(dm, dict) and isinstance(dm.get('value'), (int,float)):
                lines.append(f"- Δm²31/Δm²21 = **{_fmt_short_value(dm.get('value'), 'ratio')}** (exact {dm.get('num')}/{dm.get('den')})")
            if isinstance(pref.get('m_over_m_e'), list):
                m = pref.get('m_over_m_e')
                lines.append(f"- mν/m_e pattern (Core, unanchored): {m}")
        lines.append("")
        lines.append("**Core provenance:**")
        lines.append(f"- Core status: `{nu_core.get('derivation_status')}`")
        lines.append(f"- Scope: `{nu_core.get('core_scope')}`")
        lines.append(f"- Source-lock: `{nu_core.get('source_lock')}`")
        if nu_core.get('artifact'):
            lines.append(f"- Core artifact: `{nu_core.get('artifact')}`")
        lines.append("")
        lines.extend(render_compare_block_for_details(list(nu_cmp.get('details') or [])))
        add_page("\n".join(lines))

    # Couplings page (P13–P15)
    coup_params = ['EM‑koppling (α)','Svag koppling (g)','Stark koppling (g_s)']
    if any(p in core_entries for p in coup_params):
        lines = render_core_header_for_entries(
            "[P13–P15] Couplings (α, g, g_s)",
            "P13–P15 couplings",
            ["α", "g", "g_s"],
        )
        lines.append("")
        lines.append("## Core (what is produced)")
        lines.append("Core emits explicit expressions or scalars for α, g and a strong-coupling proxy. For transparency we show the **preferred** candidate and its expression string when available.")
        lines.append("")

        def _core_expr_block(param_sv: str, label: str):
            ce = core_entries.get(param_sv) or {}
            cv = ce.get('core_value') or {}
            pref = _core_preferred_obj(cv)
            lines.append(f"### {label}")
            lines.append(f"- Core status: `{ce.get('derivation_status')}`")
            if ce.get('source_lock'):
                lines.append(f"- Source-lock: `{ce.get('source_lock')}`")
            if ce.get('artifact'):
                arts = [a.strip() for a in str(ce.get('artifact')).split(',') if a.strip()]
                if len(arts) == 1:
                    lines.append(f"- Core artifact: `{arts[0]}`")
                else:
                    lines.append("- Core artifacts:")
                    for a in arts:
                        lines.append(f"  - `{a}`")
            if isinstance(pref, dict):
                if isinstance(pref.get('approx'), (int,float)):
                    lines.append(f"- Preferred value: **{_fmt_short_value(pref.get('approx'), cv.get('unit') or 'dimensionless')}**")
                if isinstance(pref.get('expr'), str):
                    lines.append(f"- Preferred expression: `{pref.get('expr')}`")
                if isinstance(pref.get('rule'), str):
                    lines.append(f"- Tie-break / rule: `{pref.get('rule')}`")
            elif isinstance(cv, dict) and isinstance(cv.get('value'), (int,float)):
                lines.append(f"- Value: **{_fmt_short_value(cv.get('value'), cv.get('unit'))}**")
            lines.append("")

        _core_expr_block('EM‑koppling (α)', 'α (electromagnetic coupling)')
        _core_expr_block('Svag koppling (g)', 'g (weak SU(2) coupling)')
        _core_expr_block('Stark koppling (g_s)', 'g_s proxy (strong coupling)')
        lines.append("**Why Compare may be structural here:** strong coupling and quark masses are scheme-dependent in the usual SM conventions; this repo therefore uses **STRUCTURAL** or **RANGE** checks instead of claiming a unique numeric match.")
        lines.append("")
        dets = []
        for p in coup_params:
            cmp_e = compare_entries.get(p, {})
            dets.extend(list(cmp_e.get('details') or []))
        lines.extend(render_compare_block_for_details(dets))
        add_page("\n".join(lines))

    # CKM page (P16–P19)
    ckm_params = ['CKM vinkel 1','CKM vinkel 2','CKM vinkel 3','CKM CP‑fas']
    if all(p in core_entries for p in ckm_params):
        lines = render_core_header_for_entries(
            "[P16–P19] CKM mixing",
            "P16–P19 CKM",
            ["θ12^q","θ23^q","θ13^q","δ^q"],
        )
        lines.append("")
        lines.append("## Core (angles + deterministic branch choice)")
        lines.append("Core provides the three mixing angles directly. The CP phase δ is represented by multiple sin-consistent branches; Core selects a **principal** branch by an RT-internal tie-break (no facit).")
        lines.append("")
        for p in ['CKM vinkel 1','CKM vinkel 2','CKM vinkel 3']:
            ce = core_entries.get(p) or {}
            cv = ce.get('core_value') or {}
            if isinstance(cv, dict) and isinstance(cv.get('value'), (int,float)):
                lines.append(f"- {p}: **{_fmt_short_value(cv.get('value'), cv.get('unit'))}**")
        # CP phase
        cp = core_entries.get('CKM CP‑fas') or {}
        cv = cp.get('core_value') or {}
        if isinstance(cv, dict):
            if isinstance(cv.get('delta_principal_deg'), (int,float)):
                lines.append(f"- CKM δ (principal): **{_fmt_short_value(cv.get('delta_principal_deg'), 'deg')}**")
            if isinstance(cv.get('delta_other_branches_deg'), list):
                lines.append(f"- CKM δ (other branches): {cv.get('delta_other_branches_deg')}")
            if cv.get('note'):
                lines.append(f"- Tie-break note: {cv.get('note')}")
        if cp.get('artifact'):
            lines.append(f"- Core artifact: `{cp.get('artifact')}`")
        lines.append("")
        dets = []
        for p in ckm_params:
            dets.extend(list(compare_entries.get(p, {}).get('details') or []))
        lines.extend(render_compare_block_for_details(dets))
        add_page("\n".join(lines))

    # PMNS page (P20–P23)
    pmns_params = ['PMNS vinkel 1','PMNS vinkel 2','PMNS vinkel 3','PMNS CP‑fas']
    if all(p in core_entries for p in pmns_params):
        lines = render_core_header_for_entries(
            "[P20–P23] PMNS mixing",
            "P20–P23 PMNS",
            ["θ12^ℓ","θ23^ℓ","θ13^ℓ","δ^ℓ"],
        )
        lines.append("")
        lines.append("## Core (angles + deterministic branch choice)")
        lines.append("As with CKM, Core provides three angles directly. The leptonic CP phase δ has multiple branches; Core selects a principal branch by an internal tie-break (documented in the Core value note).")
        lines.append("")
        for p in ['PMNS vinkel 1','PMNS vinkel 2','PMNS vinkel 3']:
            ce = core_entries.get(p) or {}
            cv = ce.get('core_value') or {}
            if isinstance(cv, dict) and isinstance(cv.get('value'), (int,float)):
                lines.append(f"- {p}: **{_fmt_short_value(cv.get('value'), cv.get('unit'))}**")
        cp = core_entries.get('PMNS CP‑fas') or {}
        cv = cp.get('core_value') or {}
        if isinstance(cv, dict):
            if isinstance(cv.get('delta_principal_deg'), (int,float)):
                lines.append(f"- PMNS δ (principal): **{_fmt_short_value(cv.get('delta_principal_deg'), 'deg')}**")
            if isinstance(cv.get('delta_other_branches_deg'), list):
                lines.append(f"- PMNS δ (other branches): {cv.get('delta_other_branches_deg')}")
            if isinstance(cv.get('J'), (int,float)):
                lines.append(f"- J (aux): {cv.get('J')} (dimensionless)")
            if cv.get('note'):
                lines.append(f"- Tie-break note: {cv.get('note')}")
        if cp.get('artifact'):
            lines.append(f"- Core artifact: `{cp.get('artifact')}`")
        lines.append("")
        dets = []
        for p in pmns_params:
            dets.extend(list(compare_entries.get(p, {}).get('details') or []))
        lines.extend(render_compare_block_for_details(dets))
        add_page("\n".join(lines))

    # Higgs page (P24–P25)
    higgs_params = ['Higgs‑massa','Higgs‑VEV (v)']
    if all(p in core_entries for p in higgs_params):
        lines = render_core_header_for_entries(
            "[P24–P25] Higgs sector",
            "P24 Higgs mass, P25 Higgs VEV",
            ["m_H", "v"],
        )
        lines.append("")
        lines.append("## Core (structural lock)")
        hm = core_entries.get('Higgs‑massa') or {}
        hv = core_entries.get('Higgs‑VEV (v)') or {}
        for p, e in [('Higgs‑massa', hm), ('Higgs‑VEV (v)', hv)]:
            cv = e.get('core_value') or {}
            lines.append(f"### {p}")
            if e.get('source_lock'):
                lines.append(f"- Source-lock: `{e.get('source_lock')}`")
            if e.get('artifact'):
                lines.append(f"- Core artifact: `{e.get('artifact')}`")
            if isinstance(cv, dict):
                if cv.get('proxy'):
                    lines.append(f"- Proxy definition: `{cv.get('proxy')}`")
                pref = cv.get('preferred')
                if isinstance(pref, dict) and isinstance(pref.get('expr'), str):
                    lines.append(f"- Preferred expression: `{pref.get('expr')}`")
                if cv.get('gate'):
                    lines.append(f"- Gate: `{cv.get('gate')}`")
            lines.append("")

        # Compare: both Higgs parameters share the same structural gate key.
        det_hm = list(compare_entries.get('Higgs‑massa', {}).get('details') or [])
        det_hv = list(compare_entries.get('Higgs‑VEV (v)', {}).get('details') or [])
        dets = []
        if det_hm:
            dets.append(det_hm[0])
        elif det_hv:
            dets.append(det_hv[0])
        lines.append("## Compare (overlay-only validation)")
        lines.append("")
        if dets:
            d = dets[0]
            core_rec = d.get('core') if isinstance(d.get('core'), dict) else {}
            got = core_rec.get('hit') if isinstance(core_rec.get('hit'), (bool,int,float)) else _compare_preferred_obj(d)
            ok = bool(got)
            lines.append("### higgs_struct_gate")
            lines.append(f"- STRUCTURAL CHECK: **{'PASS' if ok else 'FAIL'}**")
            lines.append(f"- Overlay calculation results in: **{'PASS' if ok else 'FAIL'}**")
            lines.append("- Applies to: **Higgs‑massa** and **Higgs‑VEV (v)**")
            if d.get('tol'):
                lines.append(f"- Tolerance: `{d.get('tol')}`")
        else:
            lines.append("No Compare details recorded for this sector.")
        add_page("\n".join(lines))

    # Strong CP page (P26)
    th = core_entries.get('Stark CP‑vinkel (θ_QCD)')
    th_cmp = compare_entries.get('Stark CP‑vinkel (θ_QCD)', {})
    if th:
        lines = render_core_header_for_entries(
            "[P26] Strong CP angle",
            "P26 θ_QCD",
            ["θ_QCD"],
        )
        lines.append("")
        lines.append("## Core")
        cv = th.get('core_value') or {}
        if isinstance(cv, dict) and isinstance(cv.get('value'), (int,float)):
            lines.append(f"- Core value: **{_fmt_short_value(cv.get('value'), cv.get('unit'))}**")
        if th.get('source_lock'):
            lines.append(f"- Source-lock: `{th.get('source_lock')}`")
        if th.get('artifact'):
            lines.append(f"- Core artifact: `{th.get('artifact')}`")
        lines.append("- Interpretation: this repo treats θ_QCD as an exact structural identity in the current lock (Compare uses a strict scalar check).")
        lines.append("")
        lines.extend(render_compare_block_for_details(list(th_cmp.get('details') or [])))
        add_page("\n".join(lines))

    # PPN page (P27–P28)
    if 'PPN γ' in core_entries and 'PPN β' in core_entries:
        lines = render_core_header_for_entries(
            "[P27–P28] PPN (GR cross-check)",
            "P27 γ, P28 β",
            ["γ", "β"],
        )
        lines.append("")
        lines.append("## Core")
        for p in ['PPN γ','PPN β']:
            ce = core_entries.get(p) or {}
            cv = ce.get('core_value') or {}
            if isinstance(cv, dict) and isinstance(cv.get('value'), (int,float)):
                lines.append(f"- {p}: **{_fmt_short_value(cv.get('value'), cv.get('unit'))}** (exact identity in current PPN lock)")
        # shared provenance
        ppn_lock = core_entries.get('PPN γ', {}).get('source_lock')
        ppn_art = core_entries.get('PPN γ', {}).get('artifact')
        if ppn_lock:
            lines.append(f"- Source-lock: `{ppn_lock}`")
        if ppn_art:
            lines.append(f"- Core artifact: `{ppn_art}`")
        lines.append("")
        dets = []
        for p in ['PPN γ','PPN β']:
            dets.extend(list(compare_entries.get(p, {}).get('details') or []))
        lines.extend(render_compare_block_for_details(dets))
        add_page("\n".join(lines))

    # κ page (P29)
    if 'κ (SI‑ankare)' in core_entries:
        lines = ["# [P29] κ (SI anchor)", "", "## Policy", "κ is intentionally **Overlay-only**. Core never reads κ and never uses SI anchoring.", ""]
        if overlay_kappa_value is None:
            lines.append(f"- κ value: (not found in `{kappa_rel}`)")
        else:
            lines.append(f"- Frozen κ (overlay-only): **{overlay_kappa_value}** (from `{kappa_rel}`)")
        lines.append("")
        lines.append("## Compare")
        lines.append("- Validation status: **UNTESTED** (policy; κ is an anchor, not a fitted/compared parameter).")
        add_page("\n".join(lines))

    out_text = _wrap_lines("\n\n".join(parts))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(out_text, encoding="utf-8")


def main() -> int:
    here = Path(__file__).resolve()
    repo_root = _repo_root_from_here(here)

    status_md_path = repo_root / "00_TOP/LOCKS/SM_PARAM_INDEX/SM_29_PARAMETERS_STATUS.md"
    if not status_md_path.exists():
        print("ERROR: missing required file:")
        print(f"  - {status_md_path}")
        return 2

    # Legacy report: Overlay inputs are OPTIONAL (report will mark N/A if absent)
    kappa_json_path = repo_root / "00_TOP/OVERLAY/kappa_global.json"
    ppn_md_path = repo_root / "00_TOP/OVERLAY/RT_OVERLAY_PPN_GAMMA_BETA_v1_2026-02-05.md"

    status_rows = _parse_md_table(_read_text(status_md_path))

    kappa = {}
    if kappa_json_path.exists():
        kappa = _load_json(kappa_json_path)

    ppn_gamma = None
    ppn_beta = None
    if ppn_md_path.exists():
        ppn_md = _read_text(ppn_md_path)
        ppn_gamma, ppn_beta = _extract_ppn_gamma_beta(ppn_md)

    report_text = _make_report(
        repo_root=repo_root,
        status_rows=status_rows,
        kappa=kappa,
        ppn_gamma=ppn_gamma,
        ppn_beta=ppn_beta,
    )

    out_path = repo_root / "00_TOP/LOCKS/SM_PARAM_INDEX/SM_29_REPORT.md"
    out_path.write_text(report_text, encoding="utf-8")
    print(f"WROTE: {out_path}")

    # New: A4-friendly one-page-per-parameter report (English), derived from *index artifacts*.
    core_index = _find_latest_index(repo_root, "CORE")
    if core_index is None:
        print("NOTE: no Core index found under out/CORE_SM29_INDEX; skipping SM29_PAGES.md")
        return 0

    compare_index = _find_latest_index(repo_root, "COMPARE")
    pages_out = repo_root / "out/SM29_PAGES.md"
    _write_sm29_pages_en(
        repo_root=repo_root,
        core_index_path=core_index,
        compare_index_path=compare_index,
        out_path=pages_out,
    )
    print(f"WROTE: {pages_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
