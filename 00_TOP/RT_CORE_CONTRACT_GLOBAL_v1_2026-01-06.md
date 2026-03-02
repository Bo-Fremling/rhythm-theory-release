# RT Core Contract (GLOBAL) — v1 (2026-01-06)

Purpose: prevent “hidden assumptions” between work streams and keep **Core (RT-internal)** strictly separated from **Overlay (SI / measurement data)**.

## 0) Core vs Overlay

- **Core**: RT objects, RT symmetries, integers, gates, and PP→RP projection (strobe). No SI numbers as inputs/anchors.
- **Overlay**: κ/SI mapping, CODATA/NIST/PDG reference values, numerical Hz/s/nm/fm, and comparison plots in SI.

## 1) Bf, Tick, c are symbols in Core

- In Core, **Bf**, **Tick**, and **c** are treated as **symbols**. Identities like Tick = 1/Bf and ℓ_tick = c·Tick are allowed, but **numerical values are not**.
- Integers are allowed in Core: e.g. K=30, ρ=10, micro=30, L*=1260, M, and N_λ = L*/M.
- All numerical values live in Overlay and must never be required for PASS in Core gates.

## 1.5) Ξ_RT (“2α”) is a Core invariant — not an SI anchor

- Core defines \(\Xi_{RT}:=Z0_{RT}\,G0_{RT}\) as a **pure number** (the “two-edge measure”).
- Factors 2/4 must be interpreted as **channel multiplicity** (one channel vs doublet), not as rescaling.
- Any numeric comparison to \(\alpha\) happens in Overlay; \(\alpha\) must never be used as input/tuning in Core.

See: `00_TOP/RT_CORE_EM_INVARIANT_XI_RT_2ALPHA_v1_2026-02-19.md`.

## 2) “Pull far / push near” must be written as field/flow

- Core language: define a tension σ≥0 (e.g. σ = ⟨wrap(Δψ)^2⟩) and a potential Φ(x) = −∑_A σ_A/(4π|x−X_A|).
- Discrete geodesic (strobe): X_{k+1} − 2X_k + X_{k-1} = −∇Φ(X_k).
- Repulsion (“push”) occurs when a local alternative configuration reduces total σ_link better; the effective gradient flips.

## 3) Remove “one helix-turn = one wave” from Core

- Core: a photon (TP-f) is a **mode excitation** on the global loop L*=1260 tick, with integers M and N_λ = L*/M.
- “Wave/period” in SI is Overlay. Core speaks in N_λ and the C30 mode gate (30 | N_λ ⇔ M | 42).
- Local helix-turns may be used as pedagogy, not as definition.

## 4) Micro-sign (H4)

- Distinguish **p_main** (main handedness / ρ direction) from **p_micro** (micro-twist in the local transverse frame).
- H4 observable (Core-only): micro-handedness proxy

  h(t) = μ_x·dμ_y/dt − μ_y·dμ_x/dt

  where μ(t) is the micro-displacement around the main centerline.
- Result (from the project CI in the full repository):
  - p_micro = +1 ⇒ e and p have the **same** handedness (A-half).
  - p_micro = −1 ⇒ e and p have **opposite** handedness.
- Canonical choice: lock **p_micro=+1** to keep “same canonical PP chirality” (differences should live in scale/pitch/phase/Z3, not mirror-flips).
- NEG: p_micro=−1 is treated as a mirror-variant and should FAIL the H4 lock.

## 5) Emission in Core: tangent-ray on the C30 strobe (no cone)

- Emission direction at u_k=2πk/30 is defined as ê_k = norm((t_x(u_k), t_y(u_k))) where t = dr/du in PP.
- No cone model in Core; any “cone” is Overlay / visualization only.

## 6) Forbid “slot permutation” as a mechanism

- Core does not assume that 30-slot labels can be freely permuted to rescue locks.
- Only legal symmetries: Z3, A/B (Z2), and deterministic gauge-fix (center + seam).

## 7) Why 30: treat it as a testable gate (H7)

- For now: K=30 is canonical via the C30 gate, with negative controls (K=29/31) and other NEG switches.
- The goal is a generative mechanism (robustness/minimality), not an axiom.
