#!/usr/bin/env python3
# rt_spiral_origin_viewer_AB.py — minimal, RCC-correct helix viewer (A/B diametrisk)
# Canonical defaults: K=30, rho_e=1, rho_p=10, M=30
# e: s_main=+1, s_micro=+1; p: s_main=-1, s_micro=+1 (H4 LOCK 2026-01-06)
import argparse, math, sys
import numpy as np

# Matplotlib import with backend fallback
import matplotlib
try:
    if matplotlib.get_backend().lower() in ("agg",):
        matplotlib.use("TkAgg")
except Exception:
    try:
        matplotlib.use("TkAgg")
    except Exception:
        pass
from matplotlib import pyplot as plt
from mpl_toolkits.mplot3d import Axes3D  # noqa

K = 30
M = 30

def unit_vectors(phi):
    c, s = np.cos(phi), np.sin(phi)
    e_r = np.stack((c, s), axis=-1)
    e_t = np.stack((-s, c), axis=-1)
    return e_r, e_t

def z_ticks(t):  # z=ticks (centered)
    return K*(t - 0.5)

def rotor_pair(R, a, rho, s_main, M_micro, s_micro, nsamp=2400, phi0=0.0):
    t = np.linspace(0.0, 1.0, nsamp, endpoint=False)
    phiA = s_main * rho * (2*np.pi*t) + phi0
    phiB = phiA + np.pi  # diametrisk

    thetaA = M_micro * phiA  # linear microphase (G1≈0)
    thetaB = M_micro * phiB

    e_rA, e_tA = unit_vectors(phiA); e_rB, e_tB = unit_vectors(phiB)
    C_A = R*e_rA; C_B = R*e_rB

    XY_A = C_A + a*(np.cos(thetaA)[:,None]*e_rA + s_micro*np.sin(thetaA)[:,None]*e_tA)
    XY_B = C_B + a*(np.cos(thetaB)[:,None]*e_rB + s_micro*np.sin(thetaB)[:,None]*e_tB)

    ZA = z_ticks(t); ZB = z_ticks(t)
    return (t, XY_A[:,0], XY_A[:,1], ZA), (t, XY_B[:,0], XY_B[:,1], ZB)

def draw(ax, args):
    plotted = False

    # Electron defaults
    Re, ae = 1.0, 0.05
    # Proton defaults (QA-optimum)
    Rp, ap = 0.60, 0.03

    if not args.no_e:
        (t, xA, yA, zA), (_, xB, yB, zB) = rotor_pair(Re, ae, rho=1, s_main=+1, M_micro=M, s_micro=+1, nsamp=args.samples)
        ax.plot3D(xA, yA, zA, lw=0.8, label="e_A")
        ax.plot3D(xB, yB, zB, lw=0.8, label="e_B", alpha=0.9)
        plotted = True
        xe = np.r_[xA, xB]; ye = np.r_[yA, yB]
    else:
        xe = ye = np.array([0.0])

    if not args.no_p:
        (t, xA, yA, zA), (_, xB, yB, zB) = rotor_pair(Rp, ap, rho=10, s_main=-1, M_micro=M, s_micro=+1, nsamp=args.samples)
        ax.plot3D(xA, yA, zA, lw=0.8, label="p_A")
        ax.plot3D(xB, yB, zB, lw=0.8, label="p_B", alpha=0.9)
        plotted = True

    # Axes limits: scale XY to let electron fill cube
    xr = (xe.min(), xe.max()); yr = (ye.min(), ye.max())
    rmax = max(abs(xr[0]), abs(xr[1]), abs(yr[0]), abs(yr[1]), 1.0)
    ax.set_xlim(-rmax, rmax); ax.set_ylim(-rmax, rmax)
    ax.set_zlim(-K/2.0, K/2.0)

    # Equal aspect (fallback if not supported)
    try:
        ax.set_box_aspect((1,1,K/(2*rmax)))
    except Exception:
        # Manual equal aspect: draw invisible frame points to force similar scale perception
        for xb, yb, zb in [
            ( rmax,  rmax,  K/2), ( rmax, -rmax,  K/2), (-rmax,  rmax,  K/2), (-rmax, -rmax,  K/2),
            ( rmax,  rmax, -K/2), ( rmax, -rmax, -K/2), (-rmax,  rmax, -K/2), (-rmax, -rmax, -K/2)
        ]:
            ax.plot([xb], [yb], [zb], '.', alpha=0.0)

    ax.set_xlabel("X (RT)"); ax.set_ylabel("Y (RT)"); ax.set_zlabel("Z = ticks")
    ax.legend(loc="upper right")
    ax.set_title("RT: Helix med A/B (RCC, diametrik) — G1≈0, G4_e=1, G4_p=10")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-e", action="store_true", help="Visa inte elektronspiralen")
    ap.add_argument("--no-p", action="store_true", help="Visa inte protonspiralen")
    ap.add_argument("--samples", type=int, default=2400, help="Antal punkter per stråk (default 2400)")
    args = ap.parse_args()

    fig = plt.figure(figsize=(8,8))
    ax = fig.add_subplot(111, projection="3d")
    draw(ax, args)
    plt.show()

if __name__ == "__main__":
    main()