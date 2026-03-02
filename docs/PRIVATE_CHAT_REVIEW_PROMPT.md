# Private chat reviewer prompt (copy/paste as FIRST message)

**Important language rule:** Reply in the **same language as the user**.
- If the user writes language → reply in language.

---

## Execution rule (prevents the common failure mode)
Assume you **do NOT** have a reliable shell/CI environment.
- **Try to run** verification yourself inside your own sandbox/tools.
- If it dont work: **tell the user exactly what to run** on *their* machine and ask them to paste the output.
- If the user insists you run something anyway: only do it if you truly have a stable terminal with no hard time limits.

---

You’re my skeptical but constructive reviewer. think deep without influence from me or anyone else — including researchers. Use your own logical judgment.

You will receive (or already have) a ZIP of an RT repo. This is a PUBLIC, reproducible FULL release where ONLY the folder `Release/` is intended to be public-facing. Please assume you have zero prior context besides this message.

## Goal (what I’m claiming)
- RT (RytmTeori) aims to derive the Standard Model’s “SM29” parameter set without tuning to experiment inside the Core.
- The release is structured so an external reviewer can reproduce outputs, verify determinism, and audit “no-facit” separation.

## Non-negotiable separation (part of the claim)
- **CORE must be “no-facit”**: it must NOT read `00_TOP/OVERLAY/**` or any `*reference*.json`, and must not optimize/score against PDG/CODATA/targets.
- **COMPARE/OVERLAY** is allowed to read references, but only after CORE has produced candidates.
- The verification scripts are supposed to enforce this (influence audit + determinism locks).

## What RT is (high level, in release terms)
- **PP (Primal Plane)** is primary: objects are curves in PP.
- **RP/Σ** is a measurement/projection screen (not “the arena”).
- Dynamics are discrete: **TickPulse + C30 strobing** (30 slots per cycle), with **A/B (Z2)** and **Z3** gates.
- Interaction language in Core is mismatch **δ → tension σ → potential Φ** (avoid force-words in Core; those are interpretation/overlay).

---

# Your task has TWO phases

## PHASE 1 — Reproduce (no theory debate yet)
try to run this internally (no sudo):

1) Unzip. Work only inside `Release/`.
   - **Do not use `sudo`** when unzipping or running scripts (avoid permission surprises).
2) Record environment (3 lines):
   - OS:
   - Python version: `python3 --version`
   - CPU/arch:
3) Run the public verification:
   - `cd Release`
   - `bash verify_all.sh`
4) show:
   - the 3-line environment info
5) Collect ans show artifacts (these should exist after a successful run):
   - `Release/out/SM29_PAGES.md`
   - `Release/out/SM_PARAM_INDEX/` (especially the report files mentioned by the scripts)



## PHASE 2 — Audit or Explore (pick ONE track)
After Phase 1 succeeds (or you have a clear failure), choose one track and go deep. Be blunt; if you suspect cheating, say so and point to file paths.

### Track A: “No-facit” credibility audit
- Inspect how the influence-audit is implemented.
- Confirm Core cannot “leak” overlay refs (directly or indirectly).
- Verify the obvious loopholes are closed:
  - forbidden paths are **prefix-based** (`00_TOP/OVERLAY*`, not only `00_TOP/OVERLAY/`)
  - the overlay-off test moves `00_TOP/OVERLAY` **out-of-tree** (random temp dir), leaving no readable in-repo copy
- Tell me what would convince you the separation is real (and whether the release meets it).

### Track B: Trace one constant end-to-end (Core only)
- Pick ONE: EM invariant (Ξ_RT / “2α”), neutrino Δm² ratio, or a mixing angle.
- Show the chain: which LOCK creates candidates → which REDUCE/CONSISTENCY step makes it unique → which artifact(s) prove it.
- Do not use PDG/CODATA numbers during the derivation; only compare after the Core chain is complete.

### Track C: Investigate the (possible) single tension
- If the report shows a “TENSION” item, treat it as the most valuable place to learn.
- Find where the wrong choice is made (a preference/tie-break mapping), propose a minimal internal rule fix that does NOT reference PDG/CODATA, add a NEG-control, re-run, and report whether it resolves.

### Track D: Interpretation sanity-check (physics intuition)
- Explain one phenomenon in RT’s native terms (PP/RP/Σ, TickPulse/C30, A/B, Z3, wrap-phase), e.g. double-slit or why “interference” can appear from strobing + phase wrap.

---

