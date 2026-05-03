# A discrete phase construction numerically close to the fine-structure constant

## Purpose

This note isolates a small discrete construction that produces a dimensionless quantity numerically close to the fine-structure constant.
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

The review task is narrow: is the construction genuinely constrained, or is it only a compact post hoc fit?

---

## Output quantity

Consider the dimensionless quantity

```math
\alpha_*=
\frac{\pi\left(3\cdot 30-\left(2+\frac{2}{10}-\frac{1}{10(42-3)}-\frac{20}{21\cdot 10\cdot (42-3)\cdot 30\cdot 7}\right)\right)}{30\cdot 1260}
```

Numerically,

```math
\alpha_* \approx 0.00729735256305
```

---

## Discrete ingredients

The construction uses the following ingredients.

### 1. A 30-point angular lattice

```math
u_k=\frac{2\pi k}{30}, \qquad k\in\{0,\dots,29\}
```

### 2. A two-way phase pairing

Points are paired by a phase offset of $\pi$.

### 3. A three-sector partition

The same 30-point lattice is partitioned into three sectors by residue class modulo $3$:

```math
s(k)=k \bmod 3
```

### 4. A wrapped phase convention

Phase differences are reduced to the interval

```math
[-\pi,\pi)
```

using

```math
\mathrm{wrap}(x)=(x+\pi)\bmod(2\pi)-\pi
```

### 5. Exact compatibility of the 30-grid with the three-sector partition

Because

```math
\frac{2\pi}{3}=10\cdot\frac{2\pi}{30}
```

a shift by one third of a full turn is represented exactly on the 30-point lattice.

### 6. A distinguished divisor

The value

```math
\rho=10
```

is the divisor of $30$ associated with that exact three-sector embedding.

---

## Local structure

The 30-point lattice, the two-way phase pairing, the three-sector partition, and the wrapped phase convention together define a constrained discrete phase ledger.

The quantity $\alpha_*$ is then obtained from that ledger.

---

## Question

The question is whether this construction carries genuine constraint, or merely reproduces the numerical value by a compact fit.

---

## Scope

This note does not claim a standard derivation of $\alpha$ from accepted physics, and it does not by itself establish physical significance.

It isolates a discrete construction and asks whether it is mathematically constrained enough to deserve further attention.
