# -*- coding: utf-8 -*-
"""
h2o_rt_rcc_harm_qav4f.py
------------------------
RT-intern H₂O-modell (RCC) med harmoniserad A/B-geometri, utökad QA och snabb/stabil solver.

NYTT i v4f (för hybrid-strategi 1-2-3):
• --skip_peaks och --qa_speed {fast,normal,max}: kan hoppa över "peaks"-estimatorn (dyr) i QA
  – solver-läge använder per default fast = skip_peaks
• --peaks_stride: sampelsteg i peaks-estimatorn (färre par → snabbare)
• --evals_cap och --progress_every: begränsa antal utvärderingar och få progress
• Solver: robust mot Ctrl-C – returnerar bästa hittills om du avbryter
• Mindre sökytor och N=800 som default i solver för grovsök
"""
from __future__ import annotations
import numpy as np
import argparse, json, os, sys, math, time

# ==================== RT Canon ====================
K = 30               # ticks per e-varv
M = 30               # micro per huvudvarv
rho_e = 1
rho_p = 10

# tecken
e_main_sign = +1
e_micro_sign = +1
p_main_sign = -1
p_micro_sign = +1  # H4 LOCK (2026-01-06)
n_main_sign = -1
n_micro_sign = -1

# ytterradie (visningsram)
R_outer = 1.0

# Elektronradier & amplituder
R_e_inner, a_e_inner = 0.25, 0.020
R_e_lp,    a_e_lp    = 0.70, 0.030
R_e_bondO, a_e_bondO = 0.55, 0.035
R_e_bondH, a_e_bondH = 0.35, 0.030

# Proton/neutron radier
R_p_O, a_p_O = 0.08, 0.010
R_n_O, a_n_O = 0.08, 0.010
R_p_H, a_p_H = 0.06, 0.008

# Fasparametrar
dphi_lp = 0.18
delta_main_n_vs_p = -0.94  # δφ*

# Vibrations (RT-interna, dimensionslösa)
vib_amp_sym   = 0.03
vib_amp_bend  = 0.025
vib_amp_asym  = 0.02
vib_omega_sym = 1.0
vib_omega_ben = 1.0
vib_omega_asy = 1.0

# --- Matplotlib helpers (backend + 3D registration) ---
def _normalize_backend(name: str) -> str:
    if not name: return name
    n = name.strip().lower()
    mapping = {
        "qtagg": "QtAgg",
        "qt5agg": "Qt5Agg",
        "qt": "QtAgg",
        "tkagg": "TkAgg",
        "wxagg": "WXAgg",
        "macosx": "MacOSX",
        "agg": "Agg",
        "webagg": "WebAgg",
        "svg": "svg",
        "pdf": "pdf",
        "pgf": "pgf",
    }
    return mapping.get(n, name)

def _ensure_mpl3d():
    try:
        from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
    except Exception:
        pass

# ==================== Helpers ====================
def er_et(theta):
    c, s = np.cos(theta), np.sin(theta)
    e_r = np.stack((c, s), axis=-1)
    e_t = np.stack((-s, c), axis=-1)
    return e_r, e_t

def rotor_curve(center_xy, R, a, t, rho, s_main, M_micro, s_micro, phi_main=0.0, phi_micro=None, phi_R=0.0):
    theta_main = s_main * rho * (2*np.pi*t) + (phi_main + phi_R)
    if phi_micro is None:
        phi_micro = -M_micro * (phi_main + phi_R)
    theta_micro = M_micro * theta_main + phi_micro
    center = np.asarray(center_xy, dtype=float).reshape(1,2)
    e_r_vec, e_t_vec = er_et(theta_main)
    C_main = R * e_r_vec
    dR_micro = a * (np.cos(theta_micro)[:,None]*e_r_vec + s_micro*np.sin(theta_micro)[:,None]*e_t_vec)
    XY = center + C_main + dR_micro
    return XY[:,0], XY[:,1]

def angle_of(v):
    return math.atan2(v[1], v[0])

def iso_mass(tag: str) -> float:
    return {"H":1.0, "D":2.0, "T":3.0}[tag]

def place_geometry(HOH_deg=104.5, base_OH=2*(R_outer - R_e_bondO), vib_phase=0.0, H1_iso="H", H2_iso="H"):
    theta = math.radians(HOH_deg)
    d = base_OH
    s = vib_phase

    m1 = iso_mass(H1_iso); m2 = iso_mass(H2_iso)
    w1 = 1.0/np.sqrt(m1);  w2 = 1.0/np.sqrt(m2)

    d_sym  = vib_amp_sym  * math.sin(vib_omega_sym*s)
    d_asym = vib_amp_asym * math.sin(vib_omega_asy*s)
    d_bend = vib_amp_bend * math.sin(vib_omega_ben*s)

    O = np.array([0.0, 0.0])
    H1 = np.array([ math.sin(theta/2)*(d + w1*(d_sym + d_asym)),  math.cos(theta/2)*(d + w1*(d_sym - d_asym)) ])
    H2 = np.array([-math.sin(theta/2)*(d + w2*(d_sym - d_asym)),  math.cos(theta/2)*(d + w2*(d_sym + d_asym)) ])

    # Bend-rotationer (små) kring O
    c,sn = math.cos(d_bend), math.sin(d_bend)
    Rm = np.array([[c,-sn],[sn,c]])
    H1 = Rm @ H1
    H2 = Rm.T @ H2

    M1 = 0.5*(O + H1)
    M2 = 0.5*(O + H2)
    return O, H1, H2, M1, M2

def make_curves(N=2400, vib_phase=0.0, show_ab="both", phi_R=0.0, H1_iso="H", H2_iso="H", tp_eps=0.0, HOH_deg=104.5):
    t = np.linspace(0.0, 1.0, N)
    z = (2*R_outer)*t - R_outer

    O, H1, H2, M1, M2 = place_geometry(HOH_deg=HOH_deg, vib_phase=vib_phase, H1_iso=H1_iso, H2_iso=H2_iso)

    curves, labels, specs = [], [], []

    def add_ab(center, R, a, rho, s_main, M_micro, s_micro, phi0, tagbase, tp=False):
        for phi,AB,sgn in ((phi0, "A", +1), (phi0+math.pi, "B", -1)):
            c,s = np.cos(phi), np.sin(phi)
            e_t = np.array([-s, c])
            c_xy = center + (tp_eps * sgn) * e_t if tp and tp_eps!=0.0 else center
            x,y = rotor_curve(c_xy, R, a, t, rho, s_main, M_micro, s_micro, phi_main=phi, phi_R=phi_R)
            curves.append((x,y,z)); labels.append(f"{tagbase}_{AB}")
            specs.append({
                'label': f"{tagbase}_{AB}", 'center': np.asarray(c_xy, dtype=float).tolist(),
                'R': float(R), 'a': float(a), 'rho': float(rho),
                's_main': int(s_main), 'M': int(M_micro), 's_micro': int(s_micro),
                'phi_main': float(phi), 'phi_R': float(phi_R)
            })

    # Elektroner
    add_ab(O, R_e_inner, a_e_inner, rho_e, e_main_sign, M, e_micro_sign, phi0=0.0,       tagbase="e_inner1")
    add_ab(O, R_e_inner, a_e_inner, rho_e, e_main_sign, M, e_micro_sign, phi0=math.pi/2, tagbase="e_inner2")

    add_ab(O, R_e_lp, a_e_lp, rho_e, e_main_sign, M, e_micro_sign, phi0=0.0 + dphi_lp,       tagbase="e_lp1a")
    add_ab(O, R_e_lp, a_e_lp, rho_e, e_main_sign, M, e_micro_sign, phi0=0.0 - dphi_lp,       tagbase="e_lp1b")
    add_ab(O, R_e_lp, a_e_lp, rho_e, e_main_sign, M, e_micro_sign, phi0=math.pi/2 + dphi_lp, tagbase="e_lp2a")
    add_ab(O, R_e_lp, a_e_lp, rho_e, e_main_sign, M, e_micro_sign, phi0=math.pi/2 - dphi_lp, tagbase="e_lp2b")

    ang1 = angle_of(H1 - O)
    ang2 = angle_of(H2 - O)
    add_ab(O,  R_e_bondO, a_e_bondO, rho_e, e_main_sign, M, e_micro_sign, phi0=ang1,          tagbase="e_bond1O")
    add_ab(H1, R_e_bondH, a_e_bondH, rho_e, e_main_sign, M, e_micro_sign, phi0=ang1+math.pi,  tagbase="e_bond1H")
    add_ab(O,  R_e_bondO, a_e_bondO, rho_e, e_main_sign, M, e_micro_sign, phi0=ang2,          tagbase="e_bond2O")
    add_ab(H2, R_e_bondH, a_e_bondH, rho_e, e_main_sign, M, e_micro_sign, phi0=ang2+math.pi,  tagbase="e_bond2H")

    # O-kärna: 8p + 8n
    for k in range(8):
        phi = (2*np.pi*k)/8
        add_ab(O, R_p_O, a_p_O, rho_p, p_main_sign, M, p_micro_sign, phi0=phi, tagbase=f"p_O{k+1}", tp=True)
    for k in range(8):
        phi = (2*np.pi*k)/8 + delta_main_n_vs_p
        add_ab(O, R_n_O, a_n_O, rho_p, n_main_sign, M, n_micro_sign, phi0=phi, tagbase=f"n_O{k+1}", tp=True)

    # Väte-kärnor
    add_ab(H1, R_p_H, a_p_H, rho_p, p_main_sign, M, p_micro_sign, phi0=0.0, tagbase="p_H1", tp=True)
    add_ab(H2, R_p_H, a_p_H, rho_p, p_main_sign, M, p_micro_sign, phi0=0.0, tagbase="p_H2", tp=True)

    bound = max(R_outer, float(np.max(np.abs([H1[0],H2[0],H1[1],H2[1]])) + R_p_H + 0.2))

    meta = {
        "K": K, "rho_e": rho_e, "rho_p": rho_p, "M": M,
        "signs": {"e_main": e_main_sign, "e_micro": e_micro_sign, "p_main": p_main_sign, "p_micro": p_micro_sign},
        "delta_main_n_vs_p": delta_main_n_vs_p,
        "R_outer": R_outer, "bound": bound,
        "centers": {"O": O.tolist(), "H1": H1.tolist(), "H2": H2.tolist(), "M1": M1.tolist(), "M2": M2.tolist()},
        "show_ab": show_ab,
        "vib_phase": vib_phase,
        "phi_R": phi_R,
        "lambda_z": 1.0,
        "qa_metric_space": "PP",
        "H1_iso": H1_iso, "H2_iso": H2_iso,
        "tp_eps": tp_eps,
        "HOH_deg": HOH_deg,
        # speed knobs
        "qa_skip_peaks": False,
        "peaks_stride": 4
    }
    return curves, labels, specs, meta

# ==================== Rendering ====================
def _ortho_axes3d(bounds, title, elev, azim):
    import matplotlib.pyplot as plt
    _ensure_mpl3d()
    fig = plt.figure(figsize=(10,8))
    ax = fig.add_subplot(projection='3d')
    try: ax.set_proj_type('ortho')
    except Exception: pass
    mn, mx = -bounds, bounds
    ax.set_xlim(mn, mx); ax.set_ylim(mn, mx); ax.set_zlim(mn, mx)
    try: ax.set_box_aspect((1,1,1))
    except Exception: pass
    ax.view_init(elev=elev, azim=azim)
    ax.set_xlabel("x"); ax.set_ylabel("y"); ax.set_zlabel("z (ticks)")
    ax.set_title(title)
    return fig, ax

def _should_show_ab(label: str, show_ab: str) -> bool:
    if label.endswith("_A"):
        return show_ab in ("A","both")
    if label.endswith("_B"):
        return show_ab in ("B","both")
    return True

def _match_only(label: str, only_patterns):
    if not only_patterns:
        return True
    s = label.lower()
    for p in only_patterns:
        if p in s:
            return True
    return False

def render_debug_pair(meta, center, idxA, idxB, curves, labels, ax):
    cx, cy = center
    (XA,YA,ZA) = curves[idxA]; (XB,YB,ZB) = curves[idxB]
    rA = np.mean(np.sqrt((XA-cx)**2+(YA-cy)**2))
    rB = np.mean(np.sqrt((XB-cx)**2+(YB-cy)**2))
    Rm = 0.5*(rA+rB); R = meta["R_outer"]
    th = np.linspace(0,2*np.pi,361)
    ax.plot(cx+Rm*np.cos(th), cy+Rm*np.sin(th), -R*np.ones_like(th), linestyle=":", linewidth=1.0, alpha=0.5)
    ax.plot(cx+Rm*np.cos(th), cy+Rm*np.sin(th),  R*np.ones_like(th), linestyle=":", linewidth=1.0, alpha=0.5)
    MX, MY = 0.5*(XA+XB), 0.5*(YA+YB)
    ax.scatter(MX, MY, ZA, s=5, alpha=0.5)

def render_view(curves, labels, meta, view="pp_side", save_path=None, debug_h=None):
    import matplotlib.pyplot as plt
    _ensure_mpl3d()
    bound = meta["bound"]; lam_z = meta.get("lambda_z", 1.0)
    if view == "pp_side":
        elev, azim, title = 12, 80, "H₂O — PP side view (orthographic, RCC, harmoniserad)"
    elif view == "rp_front":
        elev, azim, title = 90, 0, "H₂O — RP front view (orthographic, RCC, harmoniserad)"
    elif view == "rp_tilt":
        elev, azim, title = 15, 60, "H₂O — RP tilted view (orthographic, RCC, harmoniserad)"
    else:
        raise ValueError("Unknown view")

    fig, ax = _ortho_axes3d(bound, title, elev, azim)

    only_patterns = meta.get('only_patterns', [])
    for i, ((X,Y,Z), lab) in enumerate(zip(curves, labels)):
        if not _should_show_ab(lab, meta.get('show_ab','both')):
            continue
        if not _match_only(lab, only_patterns):
            continue
        Zp = lam_z * Z
        lw = 1.15 if lab[0]=='e' else 1.1
        alp = 0.65 if lab[0]=='e' else 0.95
        if lab.startswith(("p_H1","p_H2")): lw,alp = 2.0,1.0
        ax.plot(X, Y, Zp, linewidth=lw, alpha=alp, linestyle='-' if lab.endswith('_A') else '--')

    O = np.array(meta["centers"]["O"]); H1 = np.array(meta["centers"]["H1"]); H2 = np.array(meta["centers"]["H2"])
    R = meta["R_outer"]
    ax.scatter([O[0], H1[0], H2[0]], [O[1], H1[1], H2[1]], [-R]*3, s=40)
    ax.scatter([O[0], H1[0], H2[0]], [O[1], H1[1], H2[1]], [ R]*3, s=40)

    if debug_h in ("H1","H2","both"):
        labs = {l:i for i,l in enumerate(labels)}
        if debug_h in ("H1","both"):
            if "p_H1_A" in labs and "p_H1_B" in labs:
                render_debug_pair(meta, H1, labs["p_H1_A"], labs["p_H1_B"], curves, labels, ax)
        if debug_h in ("H2","both"):
            if "p_H2_A" in labs and "p_H2_B" in labs:
                render_debug_pair(meta, H2, labs["p_H2_A"], labs["p_H2_B"], curves, labels, ax)

    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True) if os.path.dirname(save_path) else None
        import matplotlib.pyplot as plt
        plt.savefig(save_path, dpi=220, bbox_inches="tight")
    return fig, ax

# ==================== QA ====================
def _smooth_series(y, win):
    y = np.asarray(y, dtype=float)
    win = int(max(1, win))
    if win <= 1: return y.copy()
    if win % 2 == 0: win += 1
    k = np.ones(win, dtype=float)/win
    return np.convolve(y, k, mode='same')

def _main_positions(spec, N):
    t = np.linspace(0.0, 1.0, N)
    center = np.array(spec['center'])
    s_main = spec['s_main']; rho = spec['rho']; phi_main = spec['phi_main']; phi_R = spec['phi_R']; R = spec['R']
    theta_main = s_main * rho * (2*np.pi*t) + (phi_main + phi_R)
    c, s = np.cos(theta_main), np.sin(theta_main)
    e_r = np.stack((c, s), axis=-1)
    return center + R * e_r

def _wrap_to_pi(x):
    return (x + np.pi) % (2*np.pi) - np.pi

def _micro_phase_from_xy(X, Y, spec):
    N = len(X)
    t = np.linspace(0.0, 1.0, N)
    center = np.array(spec['center'])
    s_main = spec['s_main']; rho = spec['rho']; M = spec['M']; s_micro = spec['s_micro']
    phi_main = spec['phi_main']; phi_R = spec['phi_R']
    R = spec['R']; a = spec['a']

    theta_main = s_main * rho * (2*np.pi*t) + (phi_main + phi_R)
    c, s = np.cos(theta_main), np.sin(theta_main)
    e_r = np.stack((c, s), axis=-1)
    e_t = np.stack((-s, c), axis=-1)
    XY = np.stack((X, Y), axis=-1)
    C_main = R * e_r
    delta = XY - center - C_main
    Ar = np.einsum('ij,ij->i', delta, e_r) / max(a, 1e-9)
    At = np.einsum('ij,ij->i', delta, e_t) / max(a * (s_micro if s_micro!=0 else 1), 1e-9)
    theta_mu_hat = np.arctan2(At, Ar)
    return np.unwrap(theta_mu_hat)

def qa_g1_numeric(curves, labels, specs, K):
    out = {}
    for idx, lab in enumerate(labels):
        spec = specs[idx] if idx < len(specs) and specs[idx]['label']==lab else None
        if spec is None: continue
        X,Y,_ = curves[idx]
        th = _micro_phase_from_xy(X,Y,spec)  # unwrapped
        N = len(th)
        ticks = [int(round(k * N / K)) for k in range(K+1)]
        ticks[-1] = N-1
        devs = []
        for i in ticks:
            devs.append(float(_wrap_to_pi(th[i])))
        devs = np.array(devs, dtype=float)
        out[lab] = {
            "per_tick_phase_dev_rad": devs.tolist(),
            "RMS_rad": float(np.sqrt(np.mean(devs**2))),
            "max_abs_rad": float(np.max(np.abs(devs)))
        }
    return out

def qa_g4_discrete(curves, labels, specs, K, smooth_factor=0.15):
    rep = {}
    for idx, lab in enumerate(labels):
        spec = specs[idx] if idx < len(specs) and specs[idx]['label']==lab else None
        if spec is None: continue
        X,Y,_ = curves[idx]
        theta_mu = _micro_phase_from_xy(X,Y,spec)
        N = len(theta_mu)
        win = max(3, int(round(smooth_factor * max(1, N//K))))
        theta_mu = _smooth_series(theta_mu, win)
        dtheta = np.diff(theta_mu)
        dtheta = (dtheta + np.pi) % (2*np.pi) - np.pi
        per_tick = []
        step = N//K
        for k in range(K):
            i0 = k*step
            i1 = (k+1)*step if k < K-1 else (N-1)
            s = np.sum(dtheta[i0:i1])
            per_tick.append(float(s/(2*np.pi)))
        arr = np.array(per_tick, dtype=float)
        if len(arr) > 2:
            inner = arr[1:-1]
            rep[lab] = {"per_tick_cycles": per_tick, "mean": float(np.mean(arr)), "mean_inner": float(np.mean(inner)), "std": float(np.std(arr))}
        else:
            rep[lab] = {"per_tick_cycles": per_tick, "mean": float(np.mean(arr)), "mean_inner": float(np.mean(arr)), "std": float(np.std(arr))}
    return rep

def _norm_delta(dxy, dz, lam_z, metric):
    if metric == "RP":
        return float(np.sqrt(np.dot(dxy, dxy) + (lam_z*dz)**2))
    else:
        return float(np.sqrt(np.dot(dxy, dxy)))

def qa_chord_ratio_data(curves, labels, specs, K, metric="PP", lam_z=1.0):
    out = {}
    for idx, lab in enumerate(labels):
        spec = specs[idx] if idx < len(specs) and specs[idx]['label']==lab else None
        if spec is None: continue
        X,Y,Z = curves[idx]
        XY = np.stack((X,Y), axis=-1)
        N = len(X)
        C = _main_positions(spec, N)
        window = max(1, N//K)
        Mrho = max(1, int(spec['M'] * spec['rho']))
        s_micro = max(1, int(round(N / Mrho)))
        ratios = []
        for n in range(K):
            i0 = n*window
            i1 = N if n==K-1 else (n+1)*window
            dcm_vec = C[i1-1] - C[i0]
            cm = np.linalg.norm(dcm_vec)
            residuals = []
            j = i0
            while j + s_micro < i1:
                dxy = XY[j+s_micro] - XY[j]
                dcm = C[j+s_micro] - C[j]
                dmu = dxy - dcm
                if metric == "RP":
                    dz = (Z[j+s_micro] - Z[j])
                    val = _norm_delta(dmu, dz, lam_z, metric) / (np.linalg.norm(dcm_vec) if cm>1e-12 else 1.0)
                else:
                    val = (np.linalg.norm(dmu)) / (cm if cm>1e-12 else 1.0)
                residuals.append(float(val))
                j += s_micro
            if residuals:
                ratios.append(float(np.median(residuals)))
        if ratios:
            arr = np.array(ratios, dtype=float)
            out[lab] = {"per_tick_ratio": ratios, "mean": float(np.nanmean(arr)), "std": float(np.nanstd(arr))}
    return out

def qa_chord_ratio_peaks(curves, labels, specs, K, metric="PP", lam_z=1.0, stride=4):
    out = {}
    for idx, lab in enumerate(labels):
        spec = specs[idx] if idx < len(specs) and specs[idx]['label']==lab else None
        if spec is None: continue
        X,Y,Z = curves[idx]
        XY = np.stack((X,Y), axis=-1)
        N = len(X)
        C = _main_positions(spec, N)
        th = _micro_phase_from_xy(X,Y,spec)
        k_series = (th / (2*np.pi))
        k_floor = np.floor(k_series).astype(int)
        crossings = np.where(np.diff(k_floor) > 0)[0]
        if crossings.size == 0:
            continue
        pairs = [(int(c), int(c+1)) for c in crossings[::max(1,int(stride))] if (c+1) < N]
        if not pairs:
            continue
        win = max(1, N//K)
        for n in range(K):
            i0 = n*win
            i1 = N if n==K-1 else (n+1)*win
            vals = []
            for (i,j) in pairs:
                if i < i0 or j >= i1:
                    continue
                dcm = C[j]-C[i]
                cm = np.linalg.norm(dcm)
                if cm <= 1e-12:
                    continue
                dxy = XY[j]-XY[i]
                if metric == "RP":
                    dz = (Z[j]-Z[i])
                    vals.append(float(_norm_delta(dxy - dcm, dz, lam_z, metric) / cm))
                else:
                    vals.append(float(np.linalg.norm((dxy - dcm))/cm))
            if vals:
                arr = np.array(vals, dtype=float)
                out.setdefault(lab, {"per_tick_ratio": []})
                out[lab]["per_tick_ratio"].append(float(np.median(arr)))
        if lab in out:
            arr = np.array(out[lab]["per_tick_ratio"], dtype=float)
            out[lab]["mean"] = float(np.nanmean(arr))
            out[lab]["std"]  = float(np.nanstd(arr))
    return out

def qa_charge_window(curves, labels, K):
    N = len(curves[0][0])
    window = max(1, N // K)
    q_series = np.zeros((K,), dtype=float)
    for (X,Y,Z), lab in zip(curves, labels):
        if lab.startswith('e_'): q = -1.0
        elif lab.startswith('p_'): q = +1.0
        else: q = 0.0
        if q == 0.0: continue
        contrib = q / N
        for n in range(K):
            i0 = n*window
            i1 = N if n==K-1 else (n+1)*window
            q_series[n] += contrib * (i1 - i0)
    return q_series.tolist()

def qa_midpoint_drift(curves, labels, centers, K, metric="PP", lam_z=1.0):
    out = {}
    lbl_to_idx = {l:i for i,l in enumerate(labels)}

    def proc(tag, center_xy):
        a = f"{tag}_A"; b=f"{tag}_B"
        if a not in lbl_to_idx or b not in lbl_to_idx:
            return
        ia, ib = lbl_to_idx[a], lbl_to_idx[b]
        XA,YA,ZA = curves[ia]; XB,YB,ZB = curves[ib]
        Cx, Cy = np.array(center_xy, dtype=float)
        MX = 0.5*(XA+XB) - Cx
        MY = 0.5*(YA+YB) - Cy
        if metric == "RP":
            MZ = 0.5*(ZA+ZB)  # center z=0
            R = np.sqrt(MX*MX + MY*MY + (lam_z*MZ)*(lam_z*MZ))
        else:
            R = np.sqrt(MX*MX + MY*MY)
        N = len(R)
        win = max(1, N//K)
        per_tick = []
        for n in range(K):
            i0 = n*win
            i1 = N if n==K-1 else (n+1)*win
            seg = R[i0:i1]
            per_tick.append(float(np.sqrt(np.mean(seg*seg))))
        out[tag] = {"RMS": float(np.sqrt(np.mean(R*R))), "per_tick_RMS": per_tick}

    O  = centers["O"]; H1 = centers["H1"]; H2 = centers["H2"]
    keys_centers = {
        "p_H1": H1, "p_H2": H2,
        "e_inner1": O, "e_inner2": O,
        "e_lp1a": O, "e_lp1b": O, "e_lp2a": O, "e_lp2b": O,
        "e_bond1O": O, "e_bond2O": O,
        "e_bond1H": H1, "e_bond2H": H2,
    }
    for tag, cen in keys_centers.items():
        proc(tag, cen)

    return out

def _group_name(label: str) -> str:
    if label.startswith("p_O"): return "p_O"
    if label.startswith("n_O"): return "n_O"
    if label.startswith("p_H1"): return "p_H1"
    if label.startswith("p_H2"): return "p_H2"
    if label.startswith("e_inner"): return "e_inner"
    if label.startswith("e_lp"): return "e_lp"
    if label.startswith("e_bond1O"): return "e_bondO"
    if label.startswith("e_bond2O"): return "e_bondO"
    if label.startswith("e_bond1H"): return "e_bondH"
    if label.startswith("e_bond2H"): return "e_bondH"
    if label.startswith("e_bond"): return "e_bond"
    if label.startswith("e_"): return "e_other"
    return "other"

def _groups_summary(rep):
    g1 = rep.get("G1_numeric", {})
    g4 = rep.get("G4_discrete", {})
    ch = rep.get("chord_ratio_data", {})
    groups = {}
    labels = sorted(set(list(g1.keys()) + list(g4.keys()) + list(ch.keys())))
    for lab in labels:
        g = _group_name(lab)
        d = groups.setdefault(g, {"G1_RMS_rad": [], "G4_mean": [], "Chord_mean": []})
        if lab in g1: d["G1_RMS_rad"].append(g1[lab]["RMS_rad"])
        if lab in g4: d["G4_mean"].append(g4[lab]["mean_inner"] if "mean_inner" in g4[lab] else g4[lab]["mean"])
        if lab in ch: d["Chord_mean"].append(ch[lab]["mean"] if "mean" in ch[lab] else float('nan'))
    out = {}
    for g,vals in groups.items():
        out[g] = {
            "G1_RMS_rad_mean": float(np.nanmean(vals["G1_RMS_rad"])) if vals["G1_RMS_rad"] else None,
            "G4_mean_mean": float(np.nanmean(vals["G4_mean"])) if vals["G4_mean"] else None,
            "Chord_mean_mean": float(np.nanmean(vals["Chord_mean"])) if vals["Chord_mean"] else None,
            "count": { "labels": len([1 for lab in labels if _group_name(lab)==g]) }
        }
    return out

def _save_g1_heatmap(g1_dict, K, out_path):
    import matplotlib.pyplot as plt
    out_dir = os.path.dirname(out_path)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)
    keys = [k for k in g1_dict.keys() if k.startswith('e_')]
    if not keys:
        return
    mat = []
    for k in keys:
        devs = g1_dict[k]["per_tick_phase_dev_rad"]
        mat.append(devs)
    fig = plt.figure(figsize=(10, max(3, 0.3*len(keys))))
    ax = fig.add_subplot(111)
    arr = np.array(mat, dtype=float)
    ax.imshow(arr, aspect='auto', interpolation='nearest')
    ax.set_ylabel("rotor (e_*)")
    ax.set_xlabel("tick index (0..K)")
    ax.set_yticks(range(len(keys)))
    ax.set_yticklabels(keys, fontsize=6)
    ax.set_xticks(range(0, K+1, max(1, K//10)))
    ax.set_title("G1 phase deviation heatmap [rad]")
    fig.tight_layout()
    fig.savefig(out_path, dpi=220, bbox_inches="tight")
    plt.close(fig)

def qa_report(curves, labels, specs, meta):
    rep = {"diametric_error":{}, "midpoint_drift":{}, "charge_window":{}}
    only_patterns = meta.get('only_patterns', [])
    filt = [i for i,l in enumerate(labels) if _match_only(l, only_patterns)]
    if not filt:
        filt = list(range(len(labels)))
    labels = [labels[i] for i in filt]
    curves = [curves[i] for i in filt]
    specs  = [specs[i]  for i in filt]

    rep["G4_discrete"] = qa_g4_discrete(curves, labels, specs, meta["K"], smooth_factor=meta.get('g4_smooth',0.15))

    centers = meta["centers"]
    # Diametric: maxavvikelse från centrum (A/B-mitt)
    for tag, cen in [
        ("p_H1", centers["H1"]), ("p_H2", centers["H2"]),
        ("e_inner1", centers["O"]), ("e_inner2", centers["O"]),
        ("e_lp1a", centers["O"]), ("e_lp1b", centers["O"]),
        ("e_lp2a", centers["O"]), ("e_lp2b", centers["O"]),
        ("e_bond1O", centers["O"]), ("e_bond1H", centers["H1"]),
        ("e_bond2O", centers["O"]), ("e_bond2H", centers["H2"]),
    ]:
        labs = {l:i for i,l in enumerate(labels)}
        if f"{tag}_A" in labs and f"{tag}_B" in labs:
            cx, cy = np.array(cen)
            (XA,YA,ZA) = curves[labs[f"{tag}_A"]]
            (XB,YB,ZB) = curves[labs[f"{tag}_B"]]
            midx = 0.5*(XA+XB) - cx
            midy = 0.5*(YA+YB) - cy
            if meta.get("qa_metric_space","PP") == "RP":
                midz = 0.5*(ZA+ZB)  # center z=0
                err = np.max(np.sqrt(midx*midx + midy*midy + (meta.get("lambda_z",1.0)*midz)**2))
            else:
                err = np.max(np.sqrt(midx*midx + midy*midy))
            rep["diametric_error"][tag] = float(err)

    rep["charge_window"]["sum_per_tick"] = qa_charge_window(curves, labels, meta["K"])

    rep["G1_numeric"] = qa_g1_numeric(curves, labels, specs, meta["K"])
    rep["chord_ratio_data"]  = qa_chord_ratio_data(curves, labels, specs, meta["K"], metric=meta.get("qa_metric_space","PP"), lam_z=meta.get("lambda_z",1.0))
    if not meta.get("qa_skip_peaks", False):
        rep["chord_ratio_peaks"] = qa_chord_ratio_peaks(curves, labels, specs, meta["K"], metric=meta.get("qa_metric_space","PP"), lam_z=meta.get("lambda_z",1.0), stride=int(meta.get("peaks_stride",4)))
    else:
        rep["chord_ratio_peaks"] = {"_skipped": True}

    rep["groups"] = _groups_summary(rep)
    rep["midpoint_drift"] = qa_midpoint_drift(curves, labels, meta["centers"], meta["K"], metric=meta.get("qa_metric_space","PP"), lam_z=meta.get("lambda_z",1.0))

    if meta.get('g1_heatmap'):
        try:
            _save_g1_heatmap({k:v for k,v in rep["G1_numeric"].items() if k.startswith('e_')}, meta["K"], meta['g1_heatmap'])
            rep['g1_heatmap_saved'] = meta['g1_heatmap']
        except Exception as e:
            rep['g1_heatmap_error'] = str(e)

    return rep

# ==================== SCOREBOARD ====================
DEFAULT_THRESHOLDS = {
    "G1_RMS_e": 0.05, "G1_RMS_p": 0.05,
    "G4_e_mean_tol": 0.02, "G4_p_mean_tol": 0.2,
    "G4_e_std_tol": 0.05,  "G4_p_std_tol": 0.3,
    "chord_ratio_target": 0.10, "chord_ratio_tol": 0.02,
    "diametric_over_a_tol": 0.2, "midpoint_over_a_tol": 0.2,
    "charge_window_tol": 0.05,
    "weights": { "G1": 25, "G4": 25, "Chord": 15, "Diametric": 15, "Midpoint": 10, "Charge": 10 }
}

def _base_tag(label: str) -> str:
    return label.rsplit("_", 1)[0] if "_" in label else label

def _label_kind(label: str) -> str:
    if label.startswith("e_"): return "e"
    if label.startswith("p_") or label.startswith("n_"): return "p"
    return "other"

def _score_component(delta, tol):
    if tol <= 0: return 0.0
    s = 1.0 - max(0.0, float(delta)/float(tol))
    return max(0.0, min(1.0, s))

def compute_scoreboard(rep, specs, thresholds=None):
    thr = dict(DEFAULT_THRESHOLDS)
    if thresholds:
        for k,v in thresholds.items():
            if k == "weights" and isinstance(v, dict):
                thr["weights"].update(v)
            else:
                thr[k] = v
    W = thr["weights"]
    labels = sorted({s["label"] for s in specs})

    diam = rep.get("diametric_error", {})
    mid  = rep.get("midpoint_drift", {})
    g1n  = rep.get("G1_numeric", {})
    g4d  = rep.get("G4_discrete", {})
    chd  = rep.get("chord_ratio_data", {})
    chp  = rep.get("chord_ratio_peaks", {})
    charge = rep.get("charge_window",{}).get("sum_per_tick", [])
    charge_max = float(max(abs(x) for x in charge)) if charge else 0.0

    per_label = {}
    for lab in labels:
        base = _base_tag(lab)
        kind = _label_kind(lab)
        g1_rms = g1n.get(lab,{}).get("RMS_rad", None)
        g1_tol = thr["G1_RMS_e"] if kind=="e" else thr["G1_RMS_p"]
        s_g1 = _score_component(g1_rms, g1_tol) if g1_rms is not None else None

        if lab in g4d:
            mean = g4d[lab].get("mean_inner", g4d[lab].get("mean"))
            std  = g4d[lab].get("std", 0.0)
            target = 1.0 if kind=="e" else 10.0
            tol_m  = thr["G4_e_mean_tol"] if kind=="e" else thr["G4_p_mean_tol"]
            tol_s  = thr["G4_e_std_tol"]  if kind=="e" else thr["G4_p_std_tol"]
            s_g4_mean = _score_component(abs(mean - target), tol_m)
            s_g4_std  = _score_component(std, tol_s)
            s_g4 = min(s_g4_mean, s_g4_std)
        else:
            s_g4 = None

        chord_mean = None
        if lab in chd:
            chord_mean = chd[lab].get("mean", None)
        elif isinstance(chp, dict) and (lab in chp) and ("_skipped" not in chp):
            chord_mean = chp[lab].get("mean", None)
        s_ch = _score_component(abs((chord_mean or 0.0) - thr["chord_ratio_target"]), thr["chord_ratio_tol"]) if chord_mean is not None else None

        a = None
        for sp in specs:
            if sp["label"] == lab:
                a = sp.get("a", None); break
        s_diam = None; s_mid = None
        if a and a>0:
            if base in diam:
                s_diam = _score_component(diam[base]/a, thr["diametric_over_a_tol"])
            if base in mid and "RMS" in mid[base]:
                s_mid  = _score_component(mid[base]["RMS"]/a, thr["midpoint_over_a_tol"])

        comps = {"G1": s_g1, "G4": s_g4, "Chord": s_ch, "Diametric": s_diam, "Midpoint": s_mid}
        used = {k:v for k,v in comps.items() if v is not None and not np.isnan(v)}
        wsum = sum(W[k] for k in used.keys()) if used else 0.0
        if wsum > 0:
            score = sum(W[k]*used[k] for k in used.keys()) / wsum
        else:
            score = None

        per_label[lab] = {
            "score": score,
            "components": comps,
            "used_weights": {k:W[k] for k in used.keys()},
            "PASS": all(v is not None and v >= 1.0 for v in used.values()) if used else False
        }

    groups = {}
    for lab,entry in per_label.items():
        g = _group_name(lab)
        if entry["score"] is None: continue
        groups.setdefault(g, []).append(entry["score"])
    groups_score = {g: float(np.mean(v)) for g,v in groups.items() if v}

    label_scores = [v["score"] for v in per_label.values() if v["score"] is not None]
    global_no_charge = float(np.mean(label_scores)) if label_scores else None
    s_charge = _score_component(charge_max, thr["charge_window_tol"]) if charge else None

    if global_no_charge is not None:
        w_labels = 100.0 - float(DEFAULT_THRESHOLDS["weights"]["Charge"])
        w_charge = float(DEFAULT_THRESHOLDS["weights"]["Charge"])
        if s_charge is None:
            global_score = global_no_charge
        else:
            global_score = (w_labels*global_no_charge + w_charge*s_charge) / (w_labels + w_charge)
    else:
        global_score = None

    return {
        "thresholds_used": thr,
        "per_label": per_label,
        "groups": groups_score,
        "global": {
            "score": global_score,
            "charge_max_abs": charge_max,
            "charge_score": s_charge
        }
    }

# ==================== Solver ====================
def _parse_range(s, default):
    if s is None: return default
    parts = [p.strip() for p in str(s).split(",")]
    if len(parts) != 3: return default
    try:
        a = float(eval(parts[0], {"__builtins__":None, "pi":math.pi, "np":np}))
        b = float(eval(parts[1], {"__builtins__":None, "pi":math.pi, "np":np}))
        st= float(eval(parts[2], {"__builtins__":None, "pi":math.pi, "np":np}))
        return (a,b,st)
    except Exception:
        return default

def _frange(a,b,st):
    x = a
    out = []
    if st == 0: return [a]
    if a <= b and st > 0:
        while x <= b + 1e-12:
            out.append(x); x += st
    elif a >= b and st < 0:
        while x >= b - 1e-12:
            out.append(x); x += st
    else:
        out = [a,b]
    return out

def solve_best(N, base_args, ranges, thresholds, quiet=True, evals_cap=None, progress_every=100):
    best = None
    eval_count = 0
    start_time = time.time()

    def evaluate(params):
        curves, labels, specs, meta = make_curves(
            N=N,
            vib_phase=params["vib_phase"],
            show_ab=base_args.show_ab,
            phi_R=params["phi_R"],
            H1_iso=base_args.H1_iso, H2_iso=base_args.H2_iso,
            tp_eps=params["tp_eps"],
            HOH_deg=params["HOH_deg"],
        )
        meta['lambda_z'] = base_args.lambda_z
        meta['g4_smooth'] = base_args.g4_smooth
        meta['only_patterns'] = [] if (base_args.only is None or base_args.only.strip()=="") else [p.strip().lower() for p in base_args.only.split(',')]
        meta['g1_heatmap'] = base_args.g1_heatmap
        meta['qa_metric_space'] = base_args.qa_metric_space
        # speed knobs
        meta['qa_skip_peaks'] = base_args.skip_peaks or (base_args.qa_speed == "fast")
        meta['peaks_stride'] = base_args.peaks_stride

        rep = qa_report(curves, labels, specs, meta)
        board = compute_scoreboard(rep, specs, thresholds=thresholds)
        score = board["global"]["score"] or 0.0
        return score, (curves, labels, specs, meta, rep, board)

    H = _frange(*ranges["HOH"])
    P = _frange(*ranges["phiR"])
    T = _frange(*ranges["tp_eps"])
    V = _frange(*ranges["vib_phase"])

    total = len(H)*len(P)*len(T)*len(V)
    if not quiet:
        print(f"[solve] coarse grid: H={len(H)} P={len(P)} T={len(T)} V={len(V)} → {total} evals")

    try:
        for hoh in H:
            for pr in P:
                for te in T:
                    for vp in V:
                        sc, bundle = evaluate({"HOH_deg":hoh, "phi_R":pr, "tp_eps":te, "vib_phase":vp})
                        eval_count += 1
                        if (best is None) or (sc > best[0]):
                            best = (sc, {"HOH_deg":hoh, "phi_R":pr, "tp_eps":te, "vib_phase":vp}, bundle)
                            if not quiet:
                                print(f"[solve] new best score={sc:.4f} @ HOH={hoh:.2f}, phi_R={pr:.3f}, tp_eps={te:.4f}, vib_phase={vp:.3f}")
                        if (progress_every is not None) and (eval_count % int(progress_every) == 0) and not quiet:
                            dt = time.time()-start_time
                            print(f"[solve] progress {eval_count}/{total} evals  ({100.0*eval_count/max(1,total):.1f}%)  elapsed {dt:.1f}s")
                        if (evals_cap is not None) and (eval_count >= int(evals_cap)):
                            raise StopIteration  # graceful stop
    except StopIteration:
        if not quiet and best is not None:
            print(f"[solve] stopped at evals_cap={evals_cap} with best={best[0]:.4f}")
    except KeyboardInterrupt:
        if not quiet and best is not None:
            print("[solve] CTRL-C – returning best found so far.")
    # local refine (smal)
    if best is None:
        return None

    sc0, p, _b = best
    for _ in range(2):
        def refine_list(span_val, span):
            a = max(span[0], span_val - span[2])
            b = min(span[1], span_val + span[2])
            st = max(span[2]/4.0, 1e-3)
            return _frange(a,b,st)
        H2 = refine_list(p["HOH_deg"], ranges["HOH"])
        P2 = refine_list(p["phi_R"],   ranges["phiR"])
        T2 = refine_list(p["tp_eps"],  ranges["tp_eps"])
        V2 = refine_list(p["vib_phase"], ranges["vib_phase"])
        for hoh in H2:
            for pr in P2:
                for te in T2:
                    for vp in V2:
                        sc2, bundle2 = evaluate({"HOH_deg":hoh, "phi_R":pr, "tp_eps":te, "vib_phase":vp})
                        if sc2 > best[0]:
                            best = (sc2, {"HOH_deg":hoh, "phi_R":pr, "tp_eps":te, "vib_phase":vp}, bundle2)
    return best

# ==================== CLI ====================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", default=None, help="Matplotlib backend (t.ex. QtAgg, TkAgg). Case-insensitive; qtagg→QtAgg")
    ap.add_argument("--view", choices=["pp_side","rp_front","rp_tilt"], default="pp_side")
    ap.add_argument("--out", default=None, help="output PNG path")
    ap.add_argument("--show_ab", choices=["A","B","both"], default="both", help="visa endast A, endast B eller båda")
    ap.add_argument("--debug_h", choices=["H1","H2","both"], default=None, help="overlay H A/B + C_main + mittpunkter")
    ap.add_argument("--vib_phase", type=float, default=0.0, help="vibrationsfas (radianer) för snapshot")
    ap.add_argument("--phi_R", type=float, default=0.0, help="global rigid rotationsfas (radianer) adderas till alla huvudfaser")
    ap.add_argument("--lambda_z", type=float, default=1.0, help="RP-tilt/axial skala för z-visning")
    ap.add_argument("--qa_metric_space", choices=["PP","RP"], default="PP", help="QA-metrik: PP (XY-norm) eller RP (3D-norm med λ_z)")
    ap.add_argument("--H1_iso", choices=["H","D","T"], default="H", help="isotop för H1")
    ap.add_argument("--H2_iso", choices=["H","D","T"], default="H", help="isotop för H2")
    ap.add_argument("--tp_eps", type=float, default=0.0, help="liten TP-diagonal offset ±ε för p/n (eliminerar tvärdipol)")
    ap.add_argument("--manifest", default=None, help="spara meta+QA till JSON-fil")
    ap.add_argument("--only", default=None, help="komma-separerad lista av substrings; render/QA endast labels som matchar")
    ap.add_argument("--g1_heatmap", default=None, help="spara G1-heatmap (elektroner) till denna PNG-fil")
    ap.add_argument("--lock_hoh", action="store_true", help="sök HOH-vinkel via fas-kopplingskostnad (legacy)")
    ap.add_argument("--hoh_min_deg", type=float, default=90.0)
    ap.add_argument("--hoh_max_deg", type=float, default=120.0)
    ap.add_argument("--hoh_step_deg", type=float, default=0.5)
    ap.add_argument("--g4_smooth", type=float, default=0.15, help="glättningsfaktor för G4 (andel av samples per tick)")
    ap.add_argument("--quiet", action="store_true", help="tyst solver")
    ap.add_argument("--verbose", action="store_true", help="skriv full QA/scoreboard till terminal")
    ap.add_argument("--no_show", action="store_true", help="visa inte interaktivt fönster (batch/headless)")
    ap.add_argument("--qa_thresholds", default=None, help="JSON med trösklar/weights för scoreboard")
    ap.add_argument("--scoreboard_out", default=None, help="spara scoreboard till JSON")
    ap.add_argument("--skip_peaks", action="store_true", help="hoppa över chord_ratio_peaks (snabbare)")
    ap.add_argument("--peaks_stride", type=int, default=4, help="sampling-steg i peaks (>=1)")
    ap.add_argument("--qa_speed", choices=["fast","normal","max"], default="normal", help="fast = skip peaks och andra snabba val")
    ap.add_argument("--solve", action="store_true", help="aktivera auto-solver (coarse→refine)")
    ap.add_argument("--solve_hoh", default=None, help="min,max,step t.ex. 95,115,2.0")
    ap.add_argument("--solve_phiR", default=None, help="min,max,step t.ex. -0.5,0.5,0.1")
    ap.add_argument("--solve_tp_eps", default=None, help="min,max,step t.ex. 0.0,0.03,0.006")
    ap.add_argument("--solve_vib_phase", default=None, help="min,max,step t.ex. 0.0,6.28318,0.6")
    ap.add_argument("--solve_out", default=None, help="JSON med bästa parametrar + score + QA")
    ap.add_argument("--evals_cap", type=int, default=None, help="max antal utvärderingar i coarse grid")
    ap.add_argument("--progress_every", type=int, default=200, help="skriv progress var N:e eval")
    ap.add_argument("--N", type=int, default=2400, help="antal samples per kurva (render/QA); solver nedjusterar till 800 om >800)")
    args = ap.parse_args()

    if args.backend:
        import matplotlib as _mpl
        try:
            _mpl.use(_normalize_backend(args.backend), force=True)
        except Exception as e:
            print(f"[warn] kunde inte sätta backend {args.backend!r}: {e}", file=sys.stderr)

    if args.lock_hoh:
        def _wrap_pi(a): return (a + np.pi) % (2*np.pi) - np.pi
        def hoh_cost(theta_deg):
            th = math.radians(theta_deg)
            u1 = (math.pi/2) - th/2
            u2 = (math.pi/2) + th/2
            lp_axes = [0.0, math.pi/2]
            def cost_to_axes(u):
                return sum((math.cos(_wrap_pi(u - a))**2 for a in lp_axes))
            w = (R_e_lp / max(R_e_bondO, 1e-6))**2
            return w*(cost_to_axes(u1) + cost_to_axes(u2))
        best = None
        th = args.hoh_min_deg
        while th <= args.hoh_max_deg + 1e-9:
            c = hoh_cost(th)
            if best is None or c < best[0]:
                best = (c, th)
            th += args.hoh_step_deg
        hoh_deg = best[1]
    else:
        hoh_deg = 104.5

    thresholds = None
    if args.qa_thresholds:
        try:
            with open(args.qa_thresholds, "r", encoding="utf-8") as f:
                thresholds = json.load(f)
        except Exception as e:
            print(f"[warn] kunde inte läsa --qa_thresholds: {e}", file=sys.stderr)

    # I solver-läge, välj snabba default
    if args.solve and args.qa_speed == "normal":
        args.qa_speed = "fast"
        args.skip_peaks = True

    if args.solve:
        rg = {
            "HOH": (95.0, 115.0, 2.0) if args.solve_hoh is None else _parse_range(args.solve_hoh, (95.0,115.0,2.0)),
            "phiR": (-0.5, 0.5, 0.1)   if args.solve_phiR is None else _parse_range(args.solve_phiR, (-0.5,0.5,0.1)),
            "tp_eps": (0.0, 0.03, 0.006) if args.solve_tp_eps is None else _parse_range(args.solve_tp_eps, (0.0,0.03,0.006)),
            "vib_phase": (0.0, 2*math.pi, 0.6) if args.solve_vib_phase is None else _parse_range(args.solve_vib_phase, (0.0,2*math.pi,0.6)),
        }
        N_solve = min(args.N, 800)

        try:
            best = solve_best(
                N=N_solve,
                base_args=args,
                ranges=rg,
                thresholds=thresholds,
                quiet=args.quiet and not args.verbose,
                evals_cap=args.evals_cap,
                progress_every=args.progress_every
            )
        except KeyboardInterrupt:
            print("[ERR] avbruten innan solver hann returnera.", file=sys.stderr)
            sys.exit(2)

        if best is None:
            print("[ERR] solver hittade inget", file=sys.stderr); sys.exit(2)
        score, params, bundle = best
        (curves, labels, specs, meta, rep, board) = bundle
        meta.update({
            'lambda_z': args.lambda_z,
            'g4_smooth': args.g4_smooth,
            'only_patterns': [] if (args.only is None or args.only.strip()=="") else [p.strip().lower() for p in args.only.split(',')],
            'g1_heatmap': args.g1_heatmap,
            'qa_metric_space': args.qa_metric_space,
            'HOH_deg': params["HOH_deg"],
            'phi_R': params["phi_R"],
            'tp_eps': params["tp_eps"],
            'vib_phase': params["vib_phase"],
            "K": K, "M": M, "rho_e": rho_e, "rho_p": rho_p,
            'qa_skip_peaks': args.skip_peaks or (args.qa_speed=="fast"),
            'peaks_stride': args.peaks_stride
        })

        view = args.view
        if args.out is None:
            args.out = f"H2O_best_{view}.png"
        render_view(curves, labels, meta, view=view, save_path=args.out, debug_h=args.debug_h)

        if args.manifest:
            out_dir = os.path.dirname(args.manifest); os.makedirs(out_dir, exist_ok=True) if out_dir else None
            with open(args.manifest, 'w', encoding='utf-8') as f:
                json.dump({"schema":"qa.v1", "meta": meta, "qa": rep, "scoreboard": board}, f, indent=2)

        if args.scoreboard_out:
            out_dir = os.path.dirname(args.scoreboard_out); os.makedirs(out_dir, exist_ok=True) if out_dir else None
            with open(args.scoreboard_out, 'w', encoding='utf-8') as f:
                json.dump(board, f, indent=2)

        if args.solve_out:
            out_dir = os.path.dirname(args.solve_out); os.makedirs(out_dir, exist_ok=True) if out_dir else None
            with open(args.solve_out, 'w', encoding='utf-8') as f:
                json.dump({"best_params": params, "global_score": score, "meta": meta, "scoreboard": board}, f, indent=2)

        if not args.no_show:
            import matplotlib.pyplot as plt
            plt.show()
        else:
            print(f"[SOLVED] score={score:.4f} file={args.out} HOH={params['HOH_deg']:.2f} phi_R={params['phi_R']:.3f} tp_eps={params['tp_eps']:.4f} vib_phase={params['vib_phase']:.3f}")
        return

    curves, labels, specs, meta = make_curves(
        N=args.N,
        vib_phase=args.vib_phase,
        show_ab=args.show_ab,
        phi_R=args.phi_R,
        H1_iso=args.H1_iso,
        H2_iso=args.H2_iso,
        tp_eps=args.tp_eps,
        HOH_deg=hoh_deg,
    )
    if args.out is None:
        args.out = f"H2O_{args.view}.png"
    meta.update({
        'lambda_z': args.lambda_z,
        'g4_smooth': args.g4_smooth,
        'only_patterns': [] if (args.only is None or args.only.strip()=="") else [p.strip().lower() for p in args.only.split(',')],
        'g1_heatmap': args.g1_heatmap,
        'qa_metric_space': args.qa_metric_space,
        "K": K, "M": M, "rho_e": rho_e, "rho_p": rho_p,
        'qa_skip_peaks': args.skip_peaks or (args.qa_speed=="fast"),
        'peaks_stride': args.peaks_stride
    })

    render_view(curves, labels, meta, view=args.view, save_path=args.out, debug_h=args.debug_h)

    rep = qa_report(curves, labels, specs, meta)
    board = compute_scoreboard(rep, specs, thresholds=thresholds)

    if args.verbose:
        print(json.dumps({ "qa": rep, "scoreboard": board }, indent=2))
    else:
        hoh = meta.get("HOH_deg"); g4s = meta.get("g4_smooth")
        nlab = len(labels)
        print(f"[OK] view={args.view} HOH={hoh:.2f}° g4_smooth={g4s:.2f} labels={nlab} only={bool(meta.get('only_patterns'))}")
        e_rms = [v['RMS_rad'] for k,v in rep.get('G1_numeric',{}).items() if k.startswith('e_')]
        g4_means = [v.get('mean_inner', v.get('mean')) for k,v in rep.get('G4_discrete',{}).items() if k.startswith('e_')]
        if e_rms:
            import numpy as _np
            print(f"   G1_RMS_e (mean) = {float(_np.mean(e_rms)):.4g} rad")
        if g4_means:
            import numpy as _np
            print(f"   G4_e (mean cycles/tick) = {float(_np.mean(g4_means)):.4g}")
        if board and board.get("global",{}).get("score") is not None:
            print(f"   SCORE global = {board['global']['score']:.3f} (charge_max_abs={board['global'].get('charge_max_abs',0.0):.3f})")

    if args.manifest:
        out_dir = os.path.dirname(args.manifest); os.makedirs(out_dir, exist_ok=True) if out_dir else None
        with open(args.manifest, 'w', encoding='utf-8') as f:
            json.dump({"schema":"qa.v1", "meta": meta, "qa": rep, "scoreboard": board}, f, indent=2)

    if args.scoreboard_out:
        out_dir = os.path.dirname(args.scoreboard_out); os.makedirs(out_dir, exist_ok=True) if out_dir else None
        with open(args.scoreboard_out, 'w', encoding='utf-8') as f:
            json.dump(board, f, indent=2)

    if not args.no_show:
        import matplotlib.pyplot as plt
        plt.show()

if __name__ == "__main__":
    main()
