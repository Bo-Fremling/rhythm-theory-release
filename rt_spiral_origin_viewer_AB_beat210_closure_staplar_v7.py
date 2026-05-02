#!/usr/bin/env python3
# rt_spiral_origin_viewer_AB_beat210_closure_staplar_v1.py
#
# RT 210-closure viewer.
#
# Purpose:
#   Show the local beat/closure cell that is also used inside the global
#   1260 closure viewer:
#
#       210 = 7×30 = 5×42 = 10×21
#
# Relation to global closure:
#   global 1260 closure = 6 × 210
#
# This script focuses on ONE 210-cell.
# It uses the same drawing language as the global closure script:
#   - tp-e / tp-p A/B rotor paths
#   - RP start view by default
#   - measurement ladders / bars
#   - 6-slot RP readout guide = 3 sectors × A/B
#
# Addendum policy:
#   tp-p is shown as phase/reference structure in the same pedagogical style
#   as the global closure viewer. The final internal form of one tp-p turn is
#   not locked by this script.

import argparse
import math
import sys
import numpy as np
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
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401


K_DEFAULT = 30
WAVE_DEFAULT = 42
BEAT_DEFAULT = 210
MICRO_DEFAULT = 30
RHO_P_DEFAULT = 10


def gcd_int(a, b):
    a, b = abs(int(a)), abs(int(b))
    while b:
        a, b = b, a % b
    return a


def lcm_int(a, b):
    a, b = int(a), int(b)
    if a == 0 or b == 0:
        return 0
    return abs(a // gcd_int(a, b) * b)


def unit_vectors(phi):
    c, s = np.cos(phi), np.sin(phi)
    e_r = np.stack((c, s), axis=-1)
    e_t = np.stack((-s, c), axis=-1)
    return e_r, e_t


def safe_text(ax, x, y, z, text, **kwargs):
    try:
        ax.text(float(x), float(y), float(z), text, **kwargs)
    except Exception:
        ax.text(float(x), float(y), float(z), str(text))


def hide_coordinate_system(ax):
    ax.grid(False)
    ax.set_axis_off()
    try:
        ax.set_proj_type("ortho")
    except Exception:
        pass
    for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
        try:
            axis.pane.fill = False
            axis.pane.set_edgecolor((1, 1, 1, 0))
        except Exception:
            pass
        try:
            axis.set_ticks([])
            axis.set_ticklabels([])
        except Exception:
            pass


def z_ticks(t, closure):
    return closure * (t - 0.5)


def rotor_pair_closure(
    R,
    a,
    main_turns,
    s_main,
    M_micro,
    s_micro,
    closure,
    nsamp=18000,
    phi0=0.0,
):
    if nsamp < 1000:
        raise ValueError("nsamp bör vara minst 1000")

    t = np.linspace(0.0, 1.0, nsamp, endpoint=False)
    phiA = s_main * main_turns * (2*np.pi*t) + phi0
    phiB = phiA + np.pi

    thetaA = M_micro * phiA
    thetaB = M_micro * phiB

    e_rA, e_tA = unit_vectors(phiA)
    e_rB, e_tB = unit_vectors(phiB)

    C_A = R * e_rA
    C_B = R * e_rB

    XY_A = C_A + a * (
        np.cos(thetaA)[:, None] * e_rA
        + s_micro * np.sin(thetaA)[:, None] * e_tA
    )
    XY_B = C_B + a * (
        np.cos(thetaB)[:, None] * e_rB
        + s_micro * np.sin(thetaB)[:, None] * e_tB
    )

    Z = z_ticks(t, closure)
    return (t, XY_A[:, 0], XY_A[:, 1], Z), (t, XY_B[:, 0], XY_B[:, 1], Z)


def draw_circle(ax, radius, z, color="0.45", lw=0.6, alpha=0.7, n=240, ls="-"):
    u = np.linspace(0, 2*np.pi, n)
    ax.plot(
        radius*np.cos(u),
        radius*np.sin(u),
        np.full_like(u, z),
        color=color,
        lw=lw,
        alpha=alpha,
        ls=ls,
    )


def draw_z_measure(ax, x, y, z0, z1, label, color="0.15", lw=1.0,
                   cap=0.08, text_dx=0.06, fontsize=8, label_z_frac=0.5):
    zmin, zmax = min(z0, z1), max(z0, z1)
    if zmax <= zmin:
        return
    ax.plot([x, x], [y, y], [zmin, zmax], color=color, lw=lw, alpha=0.95)
    ax.plot([x-cap, x+cap], [y, y], [zmin, zmin], color=color, lw=lw, alpha=0.95)
    ax.plot([x-cap, x+cap], [y, y], [zmax, zmax], color=color, lw=lw, alpha=0.95)
    zlab = zmin + label_z_frac * (zmax - zmin)
    safe_text(ax, x+text_dx, y, zlab, label,
              color=color, fontsize=fontsize, ha="left", va="center")


def draw_segment_ticks(ax, x, y, z0, step, count, label, color="0.20",
                       lw=0.85, cap=0.06, tick_cap=0.045, text_dx=0.07, label_z_frac=0.5):
    z1 = z0 + count * step
    ax.plot([x, x], [y, y], [z0, z1], color=color, lw=lw, alpha=0.95)
    for i in range(count + 1):
        z = z0 + i * step
        ax.plot([x-tick_cap, x+tick_cap], [y, y], [z, z],
                color=color, lw=lw, alpha=0.95)
    draw_z_measure(
        ax, x, y, z0, z1, label, color=color, lw=lw,
        cap=cap, text_dx=text_dx, fontsize=8, label_z_frac=label_z_frac
    )



def draw_side_bracket(ax, x, y, z0, z1, label="", color="0.15",
                      arm=0.08, out=0.06, lw=1.1, text_dx=0.10):
    """
    Simple side bracket in the x-z plane at fixed y:
      ┐
      │
      ┘
    Used to mark one selected interval on a measure bar.
    """
    zmin, zmax = min(z0, z1), max(z0, z1)
    # upper hook
    ax.plot([x, x+arm], [y, y], [zmax, zmax], color=color, lw=lw, alpha=0.95)
    ax.plot([x+arm, x+arm], [y, y], [zmax, zmax-out], color=color, lw=lw, alpha=0.95)
    # spine
    ax.plot([x, x], [y, y], [zmin, zmax], color=color, lw=lw, alpha=0.95)
    # lower hook
    ax.plot([x, x+arm], [y, y], [zmin, zmin], color=color, lw=lw, alpha=0.95)
    ax.plot([x+arm, x+arm], [y, y], [zmin, zmin+out], color=color, lw=lw, alpha=0.95)

    if label:
        safe_text(ax, x+arm+text_dx, y, 0.5*(zmin+zmax), label,
                  color=color, fontsize=8, ha="left", va="center")


def draw_210_bar_group(ax, x0, y0, z0, K, wave, beat, dx=0.42):
    """
    Four bars placed side by side:
      blue   : 7×30 = 210
      red    : 5×42 = 210
      green  : 10×21 = 210
      orange : 210 beat closure

    Labels are intentionally staggered in height so they do not overlap in side view.
    """
    half_wave = wave // 2
    bars = [
        (x0 + 0*dx, y0, K,         beat // K,         "7×30 = 210",      "#1F77B4", 1.15, False, 0.38),
        (x0 + 1*dx, y0, wave,      beat // wave,      "5×42 = 210",      "#D62728", 1.15, False, 0.50),
        (x0 + 2*dx, y0, half_wave, beat // half_wave, "10×21 = 210",     "#2CA02C", 1.15, False, 0.62),
        (x0 + 3*dx, y0, beat,      1,                 "210 beat closure", "#E87500", 1.55, True, 0.74),
    ]
    for x, y, step, count, label, color, lw, is_master, label_z_frac in bars:
        draw_segment_ticks(
            ax, x, y, z0, step, count, label,
            color=color, lw=lw, cap=0.075 if is_master else 0.070,
            tick_cap=0.055, text_dx=0.12, label_z_frac=label_z_frac
        )

        # Mark exactly one 21-window on the green 10×21 bar.
        if label == "10×21 = 210":
            z_a0 = z0 + 9 * step
            z_a1 = z0 + 10 * step
            draw_side_bracket(
                ax,
                x=x + 0.09,
                y=y,
                z0=z_a0,
                z1=z_a1,
                label="arming",
                color=color,
                arm=0.08,
                out=0.06,
                lw=1.15,
                text_dx=0.10,
            )

        if is_master:
            for dz, lab, c in [
                (0, "0", "0.20"),
                (30, "30", "#1F77B4"),
                (42, "42", "#D62728"),
                (210, "210", "#E87500"),
            ]:
                z = z0 + dz
                ax.plot([x-0.05, x+0.05], [y, y], [z, z], color=c, lw=0.9, alpha=0.9)
                safe_text(ax, x-0.08, y, z, lab, color=c, fontsize=7, ha="right", va="center")


def draw_rp_6slot_guide(ax, z, radius, color="0.25"):
    """
    RP readout guide:
      6 slots = 3 sectors × A/B
    Drawn as 3 diameters -> 6 directed slots.
    """
    draw_circle(ax, radius, z, color="0.35", lw=0.9, alpha=0.48)
    for i in range(3):
        ang = 2*np.pi*i/3
        x = radius*np.cos(ang)
        y = radius*np.sin(ang)
        ax.plot([-x, x], [-y, y], [z, z], color=color, lw=0.70, alpha=0.45)

    tick_r0 = radius * 0.92
    tick_r1 = radius * 1.05
    for i in range(6):
        ang = 2*np.pi*i/6
        x0, y0 = tick_r0*np.cos(ang), tick_r0*np.sin(ang)
        x1, y1 = tick_r1*np.cos(ang), tick_r1*np.sin(ang)
        ax.plot([x0, x1], [y0, y1], [z, z], color=color, lw=0.55, alpha=0.50)

    # No text on the floor guide itself; the panel carries "RP slots = 6 = 3×2".


def draw_label_arrow(ax, text_x, text_y, target_x, target_y, z, label, color="0.05"):
    ax.plot([text_x, target_x], [text_y, target_y], [z, z], color=color, lw=1.0, alpha=0.95)
    ax.scatter([target_x], [target_y], [z], s=26, marker="o", color=color, depthshade=False)
    safe_text(ax, text_x, text_y, z, label, fontsize=10, color=color, ha="center", va="center")


def add_labels(ax, scene_r, zmax):
    draw_label_arrow(
        ax,
        text_x=-scene_r*1.52,
        text_y=scene_r*1.05,
        target_x=-scene_r*0.74,
        target_y=0.0,
        z=zmax,
        label="tp-e",
        color="0.05",
    )
    draw_label_arrow(
        ax,
        text_x=scene_r*1.44,
        text_y=-scene_r*1.08,
        target_x=scene_r*0.44,
        target_y=0.0,
        z=zmax,
        label="tp-p",
        color="0.05",
    )



def add_info_panel(fig):
    """
    Compact 2D info panel:
      - color legend for the four bars
      - locked/found minimal integer values used in the addendum
    """
    x0 = 0.72
    y0 = 0.84

    fig.text(x0, y0, "210 closure panel", fontsize=10, color="0.08", ha="left", va="top")
    yy = y0 - 0.050
    fig.text(x0, yy, "locked / found values", fontsize=8.5, color="0.25", ha="left", va="top")
    yy -= 0.032

    rows = [
        ("A/B", "2"),
        ("sectors", "3"),
        ("RP slots", "6 = 3×2"),
        ("rho", "10"),
        ("half-wave", "21 = 42/2"),
        ("alpha window", "21 = 20 + 1"),
        ("active fraction", "20/21"),
        ("K", "30"),
        ("wave", "42"),
        ("beat", "210 = 7×30 = 5×42"),
        ("global (not shown)", "1260 = 6×210"),
    ]
    for key, val in rows:
        fig.text(x0, yy, key, fontsize=8.0, color="0.15", ha="left", va="center")
        fig.text(x0 + 0.12, yy, val, fontsize=8.0, color="0.15", ha="left", va="center")
        yy -= 0.024

def validate_args(args):
    if args.beat <= 0:
        raise ValueError("--beat måste vara > 0")
    if args.K <= 0:
        raise ValueError("--K måste vara > 0")
    if args.wave <= 0:
        raise ValueError("--wave måste vara > 0")
    if args.wave % 2 != 0:
        raise ValueError("--wave måste vara jämn för 21-fönstret")
    if lcm_int(args.K, args.wave) != args.beat:
        print(
            f"VARNING: lcm({args.K},{args.wave})={lcm_int(args.K,args.wave)} men beat={args.beat}",
            file=sys.stderr,
        )
    if args.beat % args.K != 0 or args.beat % args.wave != 0 or args.beat % (args.wave//2) != 0:
        print("VARNING: beat är inte jämnt delbar i 30/42/21", file=sys.stderr)


def draw(ax, args):
    validate_args(args)

    beat = args.beat
    K = args.K
    wave = args.wave
    zmin = -beat / 2
    zmax = beat / 2

    Re, ae = 1.0, 0.05
    Rp, ap = 0.60, 0.03

    # Over one 210 cell:
    #   e_main_turns = 210/30 = 7
    #   p_main_turns = rho_p * e_main_turns
    e_main_turns = beat / K
    p_main_turns = args.rho_p * e_main_turns

    plotted = False
    xe = ye = np.array([0.0])

    if not args.no_e:
        (t, xA, yA, zA), (_, xB, yB, zB) = rotor_pair_closure(
            Re, ae,
            main_turns=e_main_turns,
            s_main=+1,
            M_micro=args.micro,
            s_micro=+1,
            closure=beat,
            nsamp=args.samples,
        )
        ax.plot3D(xA, yA, zA, lw=0.65, label="e_A", alpha=0.95)
        ax.plot3D(xB, yB, zB, lw=0.60, label="e_B", alpha=0.74)
        plotted = True
        xe = np.r_[xA, xB]
        ye = np.r_[yA, yB]

    if not args.no_p:
        p_samples = max(args.samples, 18000)
        (t, xA, yA, zA), (_, xB, yB, zB) = rotor_pair_closure(
            Rp, ap,
            main_turns=p_main_turns,
            s_main=-1,
            M_micro=args.micro,
            s_micro=+1,
            closure=beat,
            nsamp=p_samples,
        )
        ax.plot3D(xA, yA, zA, lw=0.48, label="p_A", alpha=0.58)
        ax.plot3D(xB, yB, zB, lw=0.45, label="p_B", alpha=0.44)
        plotted = True

    if not plotted:
        raise RuntimeError("Inget att plotta: både --no-e och --no-p är satta")

    rmax = max(abs(xe.min()), abs(xe.max()), abs(ye.min()), abs(ye.max()), 1.0)
    scene_r = rmax * args.scene_scale

    if not args.no_rp_guide:
        draw_rp_6slot_guide(ax, zmin, radius=scene_r*0.78)

    if not args.no_measures:
        # closure rings at bottom/top and some inner read levels
        draw_circle(ax, scene_r*1.05, zmin, color="0.20", lw=0.85, alpha=0.32)
        draw_circle(ax, scene_r*1.05, zmax, color="0.20", lw=0.85, alpha=0.32)

        draw_210_bar_group(
            ax,
            x0=-scene_r * 2.00,
            y0=-scene_r * 1.48,
            z0=zmin,
            K=K,
            wave=wave,
            beat=beat,
            dx=scene_r * 0.42,
        )

    add_labels(ax, scene_r, zmax)

    # Extra space for bars and labels.
    ax.set_xlim(-scene_r*2.35, scene_r*2.10)
    ax.set_ylim(-scene_r*2.00, scene_r*1.90)
    ax.set_zlim(zmin, zmax)

    try:
        ax.set_box_aspect((1.0, 1.0, args.z_aspect))
    except Exception:
        pass

    hide_coordinate_system(ax)

    safe_text(ax, -scene_r*1.60, scene_r*1.44, zmax, "Rhythm Theory 210 Beat Closure",
              fontsize=11, color="0.08", ha="left", va="center")
    safe_text(ax, -scene_r*1.60, scene_r*1.29, zmax, "210 = 7×30 = 5×42 = 10×21",
              fontsize=9, color="0.08", ha="left", va="center")
    safe_text(ax, -scene_r*1.60, scene_r*1.16, zmax, "global 1260 closure = 6 × 210",
              fontsize=8, color="0.08", ha="left", va="center")

    if args.legend:
        ax.legend(loc="upper right")

    ax.view_init(elev=args.elev, azim=args.azim)


def parse_args():
    ap = argparse.ArgumentParser(
        description="RT 210 beat closure viewer: 210 = 7×30 = 5×42 = 10×21."
    )
    ap.add_argument("--no-e", action="store_true", help="Visa inte tp-e")
    ap.add_argument("--no-p", action="store_true", help="Visa inte tp-p")
    ap.add_argument("--samples", type=int, default=24000)
    ap.add_argument("--beat", type=int, default=BEAT_DEFAULT)
    ap.add_argument("--K", type=int, default=K_DEFAULT)
    ap.add_argument("--wave", type=int, default=WAVE_DEFAULT)
    ap.add_argument("--micro", type=int, default=MICRO_DEFAULT)
    ap.add_argument("--rho-p", type=float, default=RHO_P_DEFAULT)
    ap.add_argument("--scene-scale", type=float, default=1.35)
    ap.add_argument("--z-aspect", type=float, default=2.7)
    ap.add_argument("--elev", type=float, default=90.0)
    ap.add_argument("--azim", type=float, default=-90.0)
    ap.add_argument("--legend", action="store_true")
    ap.add_argument("--no-rp-guide", action="store_true")
    ap.add_argument("--no-measures", action="store_true")
    ap.add_argument("--save", default="", help="Save PNG")
    ap.add_argument("--dpi", type=int, default=170)
    return ap.parse_args()


def main():
    args = parse_args()
    fig = plt.figure(figsize=(11.6, 9.0))
    ax = fig.add_subplot(111, projection="3d")
    draw(ax, args)
    add_info_panel(fig)

    if args.save:
        fig.savefig(args.save, dpi=args.dpi, bbox_inches="tight", pad_inches=0.2)
        print(f"WROTE: {args.save}")

    plt.show()


if __name__ == "__main__":
    main()
