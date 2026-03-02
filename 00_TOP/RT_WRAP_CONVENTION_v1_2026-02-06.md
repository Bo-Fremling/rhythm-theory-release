# RT — wrap convention (v1, 2026-02-06)

Purpose: make “wrap” unambiguous so that spec, CI, and code cannot diverge around the branch cut.

## Normative definition
We always use:

- **wrap(x) ∈ [-π, π)**
- **wrap(π) = -π**
- **wrap(-π) = -π** (i.e. -π is the representative; +π is never used)

One explicit formula that satisfies this:

wrap(x) := (x + π) mod (2π) − π

## Why this matters
- Many locks use wrapped phase differences: δ = wrap(Δψ).
- The branch-cut case (near ±π) otherwise creates different “stress” in different implementations.
- If CI uses (-π, π] but the spec uses [-π, π) you get a *different* δ right at the boundary, and locks can flip.
