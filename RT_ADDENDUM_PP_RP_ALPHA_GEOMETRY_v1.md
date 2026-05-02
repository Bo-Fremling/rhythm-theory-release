# RT Addendum — PP/RP executable geometry and the alpha route

> **TL;DR**  
> This addendum shows how Rhythm Theory (RT) reads the alpha route as a nested **PP → RP closure/readout geometry**.  
> **π** measures continuous circular closure.  
> **α<sub>RT</sub>** is treated here as a dimensionless constant of gated, discrete closure/readout.

| Field | Value |
|---|---|
| Status | Explanatory addendum / visual ontology bridge |
| Scope | PP → RP geometry, closure hierarchy, and the geometric reading of the RT alpha route |
| Author | Bo Fremling |
| Release policy | Core-first; no SI input in Core; Compare/Overlay remains after-the-fact only |

---

## Reading path

These files are intended to sit together at repository root:

| Step | File | Role |
|---:|---|---|
| 1 | `DISCRETE_ALPHA_NOTE.md` | Isolates the compact discrete construction and asks whether it is constrained or post-hoc. |
| 2 | `RT_FINE_STRUCTURE_CONSTANT_CLEAN_ROUTE.md` | Places the expression inside the Core/EM_LOCK candidate route. |
| 3 | `RT_ADDENDUM_PP_RP_ALPHA_GEOMETRY_v1.md` | Adds the executable PP/RP geometry bridge. |

The three viewer scripts provide the visual path:

| Level | Script | What it shows |
|---|---|---|
| Local / C30 | `rt_spiral_origin_viewer_AB_microcell_rho10_v7_6slot_microcells_locallegends_RP.py` | `1 tp-e microturn ↔ 10 tp-p turns`; optional `--microcells 30`. |
| Beat | `rt_spiral_origin_viewer_AB_beat210_closure_staplar_v7.py` | `210 = 7×30 = 5×42 = 10×21`. |
| Full closure | `rt_spiral_origin_viewer_AB_fullclosure_staplar_v5.py` | `1260 = 6×210 = 42×30`. |

> **Boundary:** these viewers are not a new `verify_all.sh` lock. They are executable geometry viewers meant to make the ontology and alpha-route structure inspectable.

---

## 0. Purpose

This addendum explains the geometric reading behind the release-level alpha route.

The existing release already contains the formal policy and verification side:

- `00_TOP/CORE_CONTRACT_NO_FACIT.md`
- `00_TOP/RT_CORE_CONTRACT_GLOBAL_v1_2026-01-06.md`
- `00_TOP/RT_FOUNDATION_ONTOLOGY_CORE_THEORY_v1.md`
- `00_TOP/RT_ONTOLOGY_MAP_AND_GLOSSARY_v1.md`
- `00_TOP/RT_V7_EXPLAIN_RT_AND_ONTOLOGY_v1.md`
- `00_TOP/RT_Z3_Z6_RHO_LEMMAS_v1.md`
- `00_TOP/RT_CORE_EM_INVARIANT_XI_RT_2ALPHA_v1_2026-02-19.md`
- `RT_FINE_STRUCTURE_CONSTANT_CLEAN_ROUTE.md`
- `DISCRETE_ALPHA_NOTE.md`

This document adds the human-readable bridge:

```text
PP process geometry → closure hierarchy → RP readout → dimensionless alpha route
```

It does not replace the locks. It explains why the integer structure used in the alpha route is meant to be read as geometry rather than as a free numerical fit.

---

## 1. Ontology in one page

RT starts with three distinct layers.

| Layer | Short meaning | Addendum reading |
|---|---|---|
| **PP — PrimalPlane** | Primary process arena | TP traces live here; xy carries form; z is tick/time ordering. |
| **TP — TimeParticle** | Stable tick-driven process | A TP writes a curve/trace in PP. |
| **RP — RealPlane** | Readout surface | Stable PP closure becomes measurable/readable here. |

### 1.1 PrimalPlane (PP)

**PP is the primary process arena.**

In the current release ontology:

- PP is the underlying arena where TP traces live.
- The xy-plane carries form.
- The z-axis is time / tick ordering.
- A TP is best read as a moving process trace, not as a small billiard-ball object.

```text
PP = process geometry
```

### 1.2 TimeParticle / TP

A **TP** is a stable tick-driven process that writes a curve in PP.

The viewers in this addendum use the familiar `tp-e` / `tp-p` notation, but the purpose here is not to finalize the internal microstructure of every TP. The purpose is to show how local and global closure can be read geometrically.

> **Important boundary**  
> `tp-p` is shown as phase/reference structure in these viewers.  
> The final internal form of one `tp-p` turn is **not** locked by this addendum.

### 1.3 RealPlane (RP)

**RP is the readout surface.**

RP is not the generative arena. It is the surface / screen / readout where stable PP structure becomes observable.

```text
PP generates process.
RP reads stable closure.
```

The physical world is then read as stable, repeatable RP structure arising from PP closure.

---

## 2. Why executable viewers are included

The alpha route uses a compact set of discrete integers:

```text
2, 3, 6, 10, 21, 30, 42, 210, 1260
```

Without geometry, these look like numerology.

The viewers are included to show how the same numbers appear as a connected PP/RP closure hierarchy:

```text
local cell → C30 closure → 210 beat cell → 1260 full closure
```

Recommended placement in this release root:

```text
DISCRETE_ALPHA_NOTE.md
RT_FINE_STRUCTURE_CONSTANT_CLEAN_ROUTE.md
RT_ADDENDUM_PP_RP_ALPHA_GEOMETRY_v1.md

rt_spiral_origin_viewer_AB_microcell_rho10_v7_6slot_microcells_locallegends_RP.py
rt_spiral_origin_viewer_AB_beat210_closure_staplar_v7.py
rt_spiral_origin_viewer_AB_fullclosure_staplar_v5.py
```

---

## 3. Viewer 1 — local microcell and C30 closure

Run:

```bash
python3 rt_spiral_origin_viewer_AB_microcell_rho10_v7_6slot_microcells_locallegends_RP.py
```

Save a figure:

```bash
python3 rt_spiral_origin_viewer_AB_microcell_rho10_v7_6slot_microcells_locallegends_RP.py --save microcell.png
```

Show 30 stacked microcells:

```bash
python3 rt_spiral_origin_viewer_AB_microcell_rho10_v7_6slot_microcells_locallegends_RP.py --microcells 30 --save tpe30_closure.png
```

This viewer shows the local relation:

```text
1 tp-e microturn ↔ 10 tp-p turns
```

and, when `--microcells 30` is used:

```text
30 tp-e microturns = 1 full tp-e turn
```

The microcell viewer also carries the readout guide:

| Structure | Value |
|---|---:|
| A/B | 2 |
| sectors | 3 |
| RP slots | 6 = 3×2 |
| rho | 10 |

The number `10` is not introduced as a decimal convenience. In the C30 lattice, a one-third sector shift is exactly ten C30 steps:

```text
2π/3 = 10·(2π/30)
```

So `rho = 10` is the C30/Z3-compatible local divisor.

---

## 4. Viewer 2 — the 210 beat cell

Run:

```bash
python3 rt_spiral_origin_viewer_AB_beat210_closure_staplar_v7.py
```

Save a figure:

```bash
python3 rt_spiral_origin_viewer_AB_beat210_closure_staplar_v7.py --save beat210.png
```

This viewer shows the beat closure:

```text
210 = 7×30 = 5×42 = 10×21
```

The role of `210` is that it is the first common closure of the 30-rhythm and the 42-rhythm:

```text
lcm(30,42) = 210
```

So after 210 ticks:

```text
7 × 30 = 210
5 × 42 = 210
```

The same 210 cell also contains ten 21-windows:

```text
210 = 10×21
```

The alpha-relevant window is:

```text
alpha window     21 = 20 + 1
active fraction  20/21
```

The viewer marks one 21-window with a small `arming` bracket. This is deliberately only one window, not the whole `10×21` bar.

Intended reading:

```text
each 21-window = 20 active positions + 1 arming/seam position
```

Thus the active fraction is:

```text
20/21
```

The full physical interpretation of the alpha window is not asserted by the picture alone. The picture shows where the window lives in the closure hierarchy.

---

## 5. Viewer 3 — full closure 1260

Run:

```bash
python3 rt_spiral_origin_viewer_AB_fullclosure_staplar_v5.py
```

Save a figure:

```bash
python3 rt_spiral_origin_viewer_AB_fullclosure_staplar_v5.py --save fullclosure1260.png
```

This viewer shows the full closure:

```text
1260 = 6×210 = 42×30 = 60×21
```

It also marks:

```text
PrimalPlane (PP)
RealPlane (RP)
```

Intended reading:

```text
PP = the process body / generative geometry
RP = the upper readout surface
```

The full closure is not a separate arithmetic trick. It is the global frame in which the local microcell and the 210 beat cell sit.

---

## 6. How alpha belongs to this geometry

The alpha route in `RT_FINE_STRUCTURE_CONSTANT_CLEAN_ROUTE.md` gives the compact expression:

```text
pi*(3*30-(2+2/10-1/(10*(42-3))-20/(21*10*(42-3)*30*7)))/(30*1260)
```

Typeset:

```math
\alpha_{\mathrm{RT}}
=
\pi\,
\frac{
3\cdot 30
-
\left(
2+\frac{2}{10}
-\frac{1}{10(42-3)}
-\frac{20}{21\cdot 10\cdot (42-3)\cdot 30\cdot 7}
\right)
}
{30\cdot 1260}.
```

This addendum does not claim that the viewers alone prove this expression.

Instead, the viewers explain the geometry behind the ingredients:

| Symbol / number | Geometric reading in this addendum |
|---|---|
| `2` | A/B phase pairing |
| `3` | three-sector ledger |
| `6` | RP readout slots = `3×2` |
| `10` | C30/Z3-compatible divisor; one sector = ten C30 steps |
| `21` | alpha window = `20 + 1` |
| `20/21` | active fraction in the alpha window |
| `30` | C30 strobe / local closure |
| `42` | full-frame partner: `1260/30 = 42` |
| `210` | beat cell: `7×30 = 5×42 = 10×21` |
| `1260` | full closure: `6×210 = 42×30` |
| `7` | cap / arming length used by the alpha route |
| `42-3` | 42-mode read through the distinguished 3-sector route |

The point is not that these numbers are merely present. The point is that they occur in a nested closure hierarchy.

---

## 7. Alpha as “like pi, but different”

`π` is a dimensionless constant of continuous circular geometry.

It appears when a smooth full turn is measured:

```text
circle circumference / diameter = π
```

In RT, the alpha route treats `α` as a dimensionless constant of discrete closure/readout geometry.

A compact way to say the analogy is:

```text
π measures continuous circular closure.
α_RT measures discrete PP→RP closure/readout.
```

They are the same kind of object in one important sense:

```text
both are dimensionless geometric constants
```

But they arise from different kinds of geometry:

```text
π      → smooth continuous full-turn geometry
α_RT   → gated discrete closure geometry
```

The alpha expression contains `π` because the RT route still uses full-turn phase geometry. But the small value of alpha is not explained by `π` alone. It is explained by the discrete readout gates layered on top of full-turn phase:

```text
C30
A/B
three-sector ledger
rho = 10
21 = 20 + 1
210 beat closure
1260 full closure
```

So the intended claim is not:

```text
alpha is pi
```

It is:

```text
alpha is a dimensionless geometric readout constant,
analogous to pi,
but arising from discrete closure rather than from a smooth circle alone.
```

---

## 8. Relation to the existing alpha notes

This addendum is a bridge between the ontology files and the two alpha notes:

- `DISCRETE_ALPHA_NOTE.md` isolates the discrete construction and asks whether it is genuinely constrained or only a compact post-hoc fit.
- `RT_FINE_STRUCTURE_CONSTANT_CLEAN_ROUTE.md` places the expression inside the EM_LOCK candidate space and explains the Core/Overlay separation.

The present addendum adds the missing visual layer:

```text
the same numbers can be inspected as PP/RP geometry
```

It should be read as geometry support for the route, not as a replacement for the existing Core candidate-space documentation.

---

## 9. What this addendum does not claim

This addendum does **not** claim:

1. that the internal microstructure of one `tp-p` turn is finalized;
2. that the viewers are a new `verify_all.sh` lock;
3. that the standard-model derivation of alpha in accepted physics is replaced here;
4. that external reference values are used inside Core;
5. that visual similarity alone proves physical truth.

The intended claim is narrower:

```text
RT’s alpha route is not just a decimal expression.
It can be read as a nested PP→RP closure geometry.
```

---

## 10. Suggested reviewer path

For a skeptical reader, the intended order is:

1. Read `DISCRETE_ALPHA_NOTE.md`.
2. Read `RT_FINE_STRUCTURE_CONSTANT_CLEAN_ROUTE.md`.
3. Run the three viewers:
   - local microcell / C30 closure
   - 210 beat closure
   - 1260 full closure
4. Then inspect the release locks:
   - `00_TOP/LOCKS/EM_LOCK/em_lock_coregen.py`
   - `00_TOP/LOCKS/EM_XI_INVARIANT_LOCK/em_xi_invariant_lock_coregen.py`
   - `00_TOP/LOCKS/GLOBAL_FRAME_CAP_LOCK/global_frame_cap_lock_coregen.py`
5. Finally run:
   ```bash
   bash verify_all.sh
   ```

The central question remains the correct one:

```text
Is the construction genuinely constrained,
or is it only a compact post-hoc fit?
```

This addendum does not avoid that question. It makes the geometric constraint claim visible enough to inspect.
