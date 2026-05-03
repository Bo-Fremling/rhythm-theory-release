---
title: "RT EM Party Trick — A Unit-Clean Route to the Fine-Structure Constant"
author: "Bo Fremling"
status: "Release note (Core-first)"
scope: "One explicit route (k=3, Family H) inside EM_LOCK candidate space"
---

# RT EM Party Trick — a unit-clean route to the fine-structure constant
> **Geometry note for reviewers**
>
> The alpha expression is not intended as a standalone number fit.
> The intended route is:
>
> `PP/RP spiral geometry → closure hierarchy → EM candidate route → alpha`
>
> See:
>
> `RT_ADDENDUM_PP_RP_ALPHA_GEOMETRY_v1.md`
>
> for the executable geometry bridge.
>
> This addendum is explanatory, not a new `verify_all.sh` lock. It is included to make the underlying spiral/closure geometry visible before judging the alpha route as constrained or post hoc.

## What I am showing (up front)

Here is the *party trick* in its compact form:

```txt
pi*(3*30-(2+2/10-1/(10*(42-3))-20/(21*10*(42-3)*30*7)))/(30*1260)
```

The same expression, typeset (same content, just easier to read):

$$
\alpha_{\mathrm{RT}} 
= \pi\,\frac{3\cdot 30-\left(2+\frac{2}{10}-\frac{1}{10(42-3)}-\frac{20}{21\cdot 10\cdot (42-3)\cdot 30\cdot 7}\right)}{30\cdot 1260}.
$$

This expression is **dimensionless** and evaluates to the **fine-structure constant** $\alpha$ (numerically $\approx 0.00729735256$).

> **Note to the reader (from the author):** In Rhythm Theory (RT) this is presented as **one route** to $\alpha$, not as “the only derivation”. In Core, $\alpha$ belongs to a *small, explicit candidate space* (finite, deterministic, facit-free), and this formula is one particular member of that space.

---

## 1) Units: choose a dimensionless landing variable

A fast way to make the unit story completely unambiguous is to work with

$$
\Xi \equiv 2\alpha.
$$

A convenient metrology identity is

$$
\alpha = \frac{Z_0}{2R_K}\quad\Rightarrow\quad\Xi = \frac{Z_0}{R_K},
$$

where $Z_0$ and $R_K$ both have units of ohms ($[\Omega]$), so $\Xi$ is manifestly **dimensionless**.

**RT policy statement (Core-first):** RT **Core** operates on such dimensionless invariants; any SI mapping (like $Z_0/R_K$) is **Overlay/Compare-only**.

---

## 2) Core/Overlay separation (why this is not a fit)

RT enforces a hard split:

- **Core** must not read `00_TOP/OVERLAY/**` nor any `*reference*.json`, and must not use PDG/CODATA/targets for selection, scoring, or tuning.
- **Compare/Overlay** may read reference values, but must never feed back into Core generation or candidate ordering.

This policy is defined in `00_TOP/CORE_CONTRACT_NO_FACIT.md` and implemented by the lock layout:

- Core generator: `00_TOP/LOCKS/EM_LOCK/em_lock_coregen.py`
- Overlay compare: `00_TOP/LOCKS/EM_LOCK/em_lock_compare.py`

---

## 3) Where the party trick sits in Core: EM_LOCK candidate space

### 3.1 The candidate generator

In `00_TOP/LOCKS/EM_LOCK/em_lock_coregen.py`, Core generates a *deterministic* candidate list for $\Xi_{\mathrm{RT}}$ using only Core integers and $\pi$ (symbolic in a deliberately tiny expression language).

The generator uses:

- $K = 30$ (C30 strobe ticks), $M = 42$, $L_* = K\cdot M = 1260$
- $\rho = 10$ (micro-division)
- $L_{\mathrm{cap}} = 7$
- duty factor $20/21$
- $k \in \mathrm{divisors}(42) = \{1,2,3,6,7,14,21,42\}$

Mode-gated families skip $k=42$ to avoid the denominator $(42-k)=0$.

The expression language is intentionally tiny: it permits only digits, `+ - * / ( )`, and the single name `pi`.

### 3.2 Candidate families and size

The EM candidate space is built from families **A, B, E, F, G, H, C, D** in the Core generator.

Counting directly from the loops in `_build_candidates()` gives **61 total candidates** for $\Xi_{\mathrm{RT}}$:

- A: 8, B: 8, E: 8
- F: 7, G: 7, H: 7
- C: 14
- D: 2

Total: $8+8+8+7+7+7+14+2 = 61$.

> **Why this matters:** it makes the “how many tries?” question concrete. The Core generator is not an open-ended search; it enumerates an explicit, finite candidate set.

---

## 4) The exact route: Family H with $k = 3$

In the EM generator, **Family H** is the cap-arming correction with duty-cycle weighting $20/21$.

Written in compact analytic form:

$$
\Xi_{\mathrm{RT}}(k)=
\frac{2\pi}{K L_*}\left(
 kK-
\Big[
2+\frac{2}{\rho}
-\frac{1}{\rho(42-k)}
-\frac{20}{21}\cdot\frac{1}{\rho(42-k)\,K\,L_{\mathrm{cap}}}
\Big]\right).
$$

Then

$$
\alpha_{\mathrm{RT}}(k)=\frac{1}{2}\,\Xi_{\mathrm{RT}}(k).
$$

Choosing **$k=3$** yields exactly the “party trick” expression shown at the top (the signature terms $(42-3)$ and $3\cdot 30$ appear verbatim). This is one explicit route from the Core candidate space to $\alpha$.

---

## 5) “Where does pi come from?” (Core view)

In this context, $\pi$ is treated as a **geometric closure invariant** (full-turn phase $2\pi$) that may appear in Core expressions as a symbolic constant.

Crucially:

- Core does **not** import $\alpha$, $Z_0$, $R_K$, CODATA, PDG, or any reference values.
- Core does **not** tune coefficients against a target.
- Overlay/Compare may later map the dimensionless Core candidate(s) against reference values for reporting.

So the appearance of $\pi$ in Core is not a “fitting knob”; it is simply part of the allowed (and deliberately tiny) expression language in the EM lock.

---

## 6) How to reproduce from the Release bundle

From repo root:

1. Run Core-only:
   - `bash verify_core.sh`
2. Run Compare (Overlay allowed):
   - `bash verify_compare.sh`

Inspect:

- Core artifacts: `out/CORE_EM_LOCK/` (candidate list and ordering)
- Compare artifacts: `out/COMPARE_EM_LOCK/` (post-hoc comparison)

---

## 7) One-paragraph summary

The EM “party trick” is not an isolated numerical coincidence. It is the $k=3$ member of **Family H** inside a finite, explicit **61-candidate** Core-generated space for the **dimensionless** invariant $\Xi=2\alpha$. Core enumerates candidates deterministically from internal invariants $(K=30, L_*=1260, \rho=10, L_{\mathrm{cap}}=7, 20/21, k\mid 42)$ and a tiny expression language that allows only `pi` as a name; Core never reads experimental constants or targets. Any SI mapping (e.g. via $Z_0/R_K$) is strictly Overlay/Compare-only.
