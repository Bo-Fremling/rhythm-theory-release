#!/usr/bin/env python3
# rt_spiral_origin_viewer_AB_microcell_rho10_v6_6slot_microcells_RP.py
#
# Local / stacked RT viewer:
#   1 tp-e microturn  <->  10 tp-p turns   per microcell
#   Default start view: RP/top-down (elev=90, azim=-90)
#
# Addendum policy:
#   tp-p is shown here as the corresponding phase reference only.
#   The internal form of a single tp-p turn is not fixed in this addendum.
#
# RP readout guide:
#   The floor guide is shown as 6 readout slots = 3 sectors x A/B.
#   This is a readout/orientation aid in RP, not a full Z3-dynamics derivation.
#
# Key option:
#   --microcells N
#     N=1  -> local primitive cell
#     N=30 -> tp-e 30-closure (30 microturns = 1 full tp-e turn)
#
# Legend scope:
#   --legend-scope local   (default)
#       keep local legends/measures frozen to the first microcell
#   --legend-scope global
#       expand legends/measures to the whole stacked object

import argparse
import numpy as np
import matplotlib.pyplot as plt


def set_clean_3d(ax, show_axes=False):
    ax.set_proj_type("ortho")
    ax.grid(False)
    if not show_axes:
        ax.set_axis_off()
    else:
        ax.set_xlabel("x")
        ax.set_ylabel("y")
        ax.set_zlabel("microcell z")
    for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
        try:
            axis.pane.fill = False
            axis.pane.set_edgecolor((1, 1, 1, 0))
        except Exception:
            pass


def equalize_axes(ax, xs, ys, zs, pad=0.12, z_weight=1.45):
    xmin, xmax = float(np.min(xs)), float(np.max(xs))
    ymin, ymax = float(np.min(ys)), float(np.max(ys))
    zmin, zmax = float(np.min(zs)), float(np.max(zs))
    cx, cy, cz = 0.5*(xmin+xmax), 0.5*(ymin+ymax), 0.5*(zmin+zmax)
    r = max(xmax-xmin, ymax-ymin, (zmax-zmin)*z_weight, 1e-9) * (0.5 + pad)
    ax.set_xlim(cx-r, cx+r)
    ax.set_ylim(cy-r, cy+r)
    ax.set_zlim(cz-r/z_weight, cz+r/z_weight)


def safe_text(ax, x, y, z, s, **kwargs):
    ax.text(float(x), float(y), float(z), s, **kwargs)


def make_e_microcells(t, R=0.95, a=0.16, main_fraction=1/30, strand="A"):
    """
    tp-e over t in [0, microcells].
    Each unit interval in t is one tp-e microturn.
    main_fraction=1/30 means 30 microturns per full tp-e main turn.
    A/B is diametric around the tp-p center (origin).
    """
    phi_main = 2*np.pi*main_fraction*t
    theta_micro = 2*np.pi*t

    c, s = np.cos(phi_main), np.sin(phi_main)
    e_r = np.vstack([c, s]).T
    e_t = np.vstack([-s, c]).T

    center = R * e_r
    off = a * (np.cos(theta_micro)[:, None]*e_r + np.sin(theta_micro)[:, None]*e_t)
    xy = center + off

    if strand.upper() == "B":
        xy = -xy
        center = -center

    z = t
    return xy[:, 0], xy[:, 1], z, center[:, 0], center[:, 1]


def make_p_phase_reference(t, R=0.46, turns_per_microcell=10, strand="A"):
    """
    tp-p shown only as the corresponding phase reference:
      10 tp-p turns during one tp-e microturn.
    """
    phase = 2*np.pi*turns_per_microcell*t
    x = R*np.cos(phase)
    y = R*np.sin(phase)
    if strand.upper() == "B":
        x, y = -x, -y
    z = t
    return x, y, z


def draw_reference_planes(ax, z_values, radius, color="0.65"):
    u = np.linspace(0, 2*np.pi, 240)
    for z in z_values:
        ax.plot(radius*np.cos(u), radius*np.sin(u), np.full_like(u, z),
                color=color, lw=0.7, alpha=0.35)


def draw_ab_diameters(ax, xa, ya, z, xb, yb, count=7, color="0.25"):
    idx = np.linspace(0, len(z)-1, count, dtype=int)
    for i in idx:
        ax.plot([xa[i], xb[i]], [ya[i], yb[i]], [z[i], z[i]],
                color=color, lw=0.6, alpha=0.42)


def draw_p_turn_ladder(ax, x, y, z0=0.0, z1=1.0, turns=10, color="#8C564B"):
    ax.plot([x, x], [y, y], [z0, z1], color=color, lw=1.5, alpha=0.9)
    tick = 0.055
    highlights = {0, turns//2, turns}
    for i in range(turns + 1):
        z = z0 + (z1-z0)*i/max(turns, 1)
        lw = 1.5 if i in highlights else 0.75
        ax.plot([x-tick, x+tick], [y, y], [z, z], color=color, lw=lw, alpha=0.9)
        if i in highlights:
            safe_text(ax, x-0.10, y, z, str(i), fontsize=8, color=color, ha="right", va="center")
    safe_text(ax, x-0.15, y, 0.5*(z0+z1), f"{turns} tp-p turns",
              fontsize=9, color=color, ha="right", va="center")


def draw_e_micro_ladder(ax, x, y, z0=0.0, z1=1.0, count=1, color="#1F77B4"):
    ax.plot([x, x], [y, y], [z0, z1], color=color, lw=1.5, alpha=0.85)
    tick = 0.065
    highlights = [0, count]
    if count > 1:
        highlights.insert(1, count//2)
    for i in highlights:
        z = z0 + (z1-z0)*i/max(count, 1)
        ax.plot([x-tick, x+tick], [y, y], [z, z], color=color, lw=1.4, alpha=0.9)
        lab = str(i) if i not in (0, count) else ("start" if i == 0 else "end")
        safe_text(ax, x+0.10, y, z, lab, fontsize=7, color=color, ha="left", va="center")
    if count == 1:
        label = "1 tp-e microturn"
    else:
        label = f"{count} tp-e microturns"
    safe_text(ax, x+0.12, y, 0.5*(z0+z1), label,
              fontsize=9, color=color, ha="left", va="center")


def draw_rp_6slot_guide(ax, z, radius, color="0.25"):
    """
    RP readout guide:
      6 slots = 3 sectors x A/B
    Drawn as 3 diameters -> 6 directed slots.
    This is a readout/orientation aid only.
    """
    for i in range(3):
        ang = 2*np.pi*i/3
        x = radius*np.cos(ang)
        y = radius*np.sin(ang)
        ax.plot([-x, x], [-y, y], [z, z], color=color, lw=0.60, alpha=0.38)

    tick_r0 = radius * 0.92
    tick_r1 = radius * 1.05
    for i in range(6):
        ang = 2*np.pi*i/6
        x0, y0 = tick_r0*np.cos(ang), tick_r0*np.sin(ang)
        x1, y1 = tick_r1*np.cos(ang), tick_r1*np.sin(ang)
        ax.plot([x0, x1], [y0, y1], [z, z], color=color, lw=0.55, alpha=0.45)

    safe_text(ax, -radius*1.08, radius*0.86, z, "RP 6-slot guide", fontsize=7, color=color, ha="left", va="center")
    safe_text(ax, -radius*1.08, radius*0.70, z, "3 sectors × A/B", fontsize=6.5, color=color, ha="left", va="center")


def annotation_scope(args):
    """
    local  -> legends/measures frozen to first microcell
    global -> legends/measures span the whole stacked object
    """
    if args.legend_scope == "global":
        return {
            "z0": 0.0,
            "z1": float(args.microcells),
            "e_count": int(args.microcells),
            "p_turns": int(args.p_turns) * int(args.microcells),
            "e_marks": [(0.0, "e0"),
                        (float(args.microcells)/2.0, f"e{int(args.microcells)//2}" if int(args.microcells) % 2 == 0 else "mid"),
                        (float(args.microcells), f"e{int(args.microcells)}")],
            "p_marks": [0, (int(args.p_turns) * int(args.microcells))//2, int(args.p_turns) * int(args.microcells)],
        }
    else:
        return {
            "z0": 0.0,
            "z1": 1.0,
            "e_count": 1,
            "p_turns": int(args.p_turns),
            "e_marks": [(0.0, "e0"), (0.5, "e1/2"), (1.0, "e1")],
            "p_marks": [0, int(args.p_turns)//2, int(args.p_turns)],
        }


def add_title_block(ax, microcells, p_turns_total, z_top):
    if microcells == 1:
        line1 = "Local RT microcell: 1 tp-e microturn = 10 tp-p turns"
        line2 = "rho_micro = 10   |   A/B diametric about tp-p center   |   local primitive cell"
        line3 = "RP floor guide: 6 readout slots = 3 sectors × A/B   |   tp-p shown as phase reference only"
    elif microcells == 30:
        line1 = "tp-e 30-closure: 30 tp-e microturns = 1 full tp-e turn"
        line2 = "30 = 3 × 10   |   rho_micro = 10 per cell   |   A/B diametric about tp-p center"
        line3 = "RP floor guide: 6 readout slots = 3 sectors × A/B   |   tp-p shown as phase reference only"
    else:
        line1 = f"RT stacked microcells: {microcells} tp-e microturns = {p_turns_total} tp-p turns"
        line2 = "rho_micro = 10 per cell   |   A/B diametric about tp-p center"
        line3 = "RP floor guide: 6 readout slots = 3 sectors × A/B   |   tp-p shown as phase reference only"

    safe_text(ax, -1.30, 1.00, z_top, line1, fontsize=11, color="0.08", ha="left", va="bottom")
    safe_text(ax, -1.30, 0.87, z_top, line2, fontsize=9, color="0.18", ha="left", va="bottom")
    safe_text(ax, -1.30, 0.74, z_top, line3, fontsize=8, color="0.18", ha="left", va="bottom")


def draw_scene(args):
    microcells = int(args.microcells)
    if microcells < 1:
        raise ValueError("--microcells must be >= 1")

    t = np.linspace(0.0, float(microcells), max(2, args.samples * microcells))

    xe_a, ye_a, ze, ce_x, ce_y = make_e_microcells(t, R=args.e_radius, a=args.e_micro_radius, main_fraction=1/30, strand="A")
    xe_b, ye_b, _, _, _ = make_e_microcells(t, R=args.e_radius, a=args.e_micro_radius, main_fraction=1/30, strand="B")

    xp_a, yp_a, zp = make_p_phase_reference(t, R=args.p_radius, turns_per_microcell=args.p_turns, strand="A")
    xp_b, yp_b, _ = make_p_phase_reference(t, R=args.p_radius, turns_per_microcell=args.p_turns, strand="B")

    p_turns_total = args.p_turns * microcells
    ann = annotation_scope(args)

    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection="3d")
    set_clean_3d(ax, show_axes=args.show_axes)

    if not args.no_planes:
        draw_reference_planes(ax, [0.0, float(microcells)], radius=max(args.e_radius+args.e_micro_radius, args.p_radius)*1.12)

    ax.plot(ce_x, ce_y, ze, color="0.45", lw=0.7, alpha=0.50)

    ax.plot(xe_a, ye_a, ze, color="#1F77B4", lw=2.2, alpha=0.98, label="tp-e A")
    if not args.no_b:
        ax.plot(xe_b, ye_b, ze, color="#6BAED6", lw=1.6, alpha=0.72, label="tp-e B")
        draw_ab_diameters(ax, xe_a, ye_a, ze, xe_b, ye_b, count=max(7, 2*microcells))

    if not args.no_p:
        ax.plot(xp_a, yp_a, zp, color="#8C564B", lw=1.20 if microcells > 1 else 1.45, alpha=0.70 if microcells > 1 else 0.76, label="tp-p A (phase ref)")
        if not args.no_b:
            ax.plot(xp_b, yp_b, zp, color="#C49C94", lw=0.95 if microcells > 1 else 1.05, alpha=0.38 if microcells > 1 else 0.45, label="tp-p B (phase ref)")
        for i in ann["p_marks"]:
            j = int(round((i/max(p_turns_total, 1)) * (len(t)-1)))
            ax.scatter([xp_a[j]], [yp_a[j]], [zp[j]], s=26, color="#8C564B", depthshade=False)
            safe_text(ax, xp_a[j]*1.05, yp_a[j]*1.05, zp[j], f"p{i}", fontsize=7, color="#8C564B", ha="left", va="center")

    # e markers
    for ti, lab in ann["e_marks"]:
        j = int(round((ti/max(float(microcells), 1e-9)) * (len(t)-1)))
        ax.scatter([xe_a[j]], [ye_a[j]], [ze[j]], s=35, color="#1F77B4", depthshade=False)
        safe_text(ax, xe_a[j]+0.05, ye_a[j]+0.05, ze[j], lab, fontsize=7, color="#1F77B4", ha="left", va="center")

    if not args.no_measures:
        draw_p_turn_ladder(ax, x=-1.06, y=-0.86, z0=ann["z0"], z1=ann["z1"], turns=ann["p_turns"])
        draw_e_micro_ladder(ax, x=1.28, y=-0.82, z0=ann["z0"], z1=ann["z1"], count=ann["e_count"])

    if not args.no_rp_guide:
        draw_rp_6slot_guide(ax, z=0.0, radius=0.34)

    z_top = float(microcells) + max(0.12 * max(1, microcells), 0.18)
    add_title_block(ax, microcells=microcells, p_turns_total=p_turns_total, z_top=z_top)

    safe_text(ax, args.e_radius + args.e_micro_radius + 0.12, 0.10, 0.82*microcells if microcells > 1 else 0.82,
              "tp-e microcells", fontsize=10, color="#1F77B4", ha="left", va="center")
    safe_text(ax, args.p_radius + 0.10, -0.06, 0.42*microcells if microcells > 1 else 0.42,
              f"tp-p x{p_turns_total}", fontsize=10, color="#8C564B", ha="left", va="center")
    if args.legend_scope == "local" and microcells > 1:
        safe_text(ax, -1.30, 0.61, z_top, "legends/measures frozen to first microcell",
                  fontsize=8, color="0.18", ha="left", va="bottom")

    all_x = np.concatenate([xe_a, xe_b, xp_a, xp_b, np.array([-1.35, 1.45])])
    all_y = np.concatenate([ye_a, ye_b, yp_a, yp_b, np.array([-1.00, 1.10])])
    all_z = np.concatenate([ze, zp, np.array([-0.05, z_top + 0.04*max(1, microcells)])])
    equalize_axes(ax, all_x, all_y, all_z, pad=0.10, z_weight=args.z_weight)

    ax.view_init(elev=args.elev, azim=args.azim)
    if args.title:
        ax.set_title(args.title, pad=18)
    if args.legend:
        ax.legend(loc="upper right")

    return fig, ax


def parse_args():
    ap = argparse.ArgumentParser(description="RT microcell viewer: tp-e microcells with tp-p phase reference and RP 6-slot readout guide.")
    ap.add_argument("--microcells", type=int, default=1, help="Number of tp-e microcells to stack. 1=local cell, 30=tp-e 30-closure")
    ap.add_argument("--samples", type=int, default=5000, help="Samples per microcell")
    ap.add_argument("--e-radius", type=float, default=0.95)
    ap.add_argument("--e-micro-radius", type=float, default=0.16)
    ap.add_argument("--p-radius", type=float, default=0.46)
    ap.add_argument("--p-turns", type=int, default=10, help="tp-p turns per tp-e microcell")
    ap.add_argument("--elev", type=float, default=90.0)
    ap.add_argument("--azim", type=float, default=-90.0)
    ap.add_argument("--z-weight", type=float, default=1.45)
    ap.add_argument("--show-axes", action="store_true")
    ap.add_argument("--legend", action="store_true")
    ap.add_argument("--legend-scope", choices=["local", "global"], default="local",
                    help="Scope of legends/measures: local=first microcell only, global=whole stacked object")
    ap.add_argument("--no-b", action="store_true")
    ap.add_argument("--no-p", action="store_true")
    ap.add_argument("--no-planes", action="store_true")
    ap.add_argument("--no-measures", action="store_true")
    ap.add_argument("--no-rp-guide", action="store_true")
    ap.add_argument("--title", default="")
    ap.add_argument("--save", default="", help="Save PNG")
    ap.add_argument("--dpi", type=int, default=160)
    return ap.parse_args()


def main():
    args = parse_args()
    fig, ax = draw_scene(args)
    if args.save:
        fig.savefig(args.save, dpi=args.dpi, bbox_inches="tight", pad_inches=0.2)
        print(f"WROTE: {args.save}")
    plt.show()


if __name__ == "__main__":
    main()
