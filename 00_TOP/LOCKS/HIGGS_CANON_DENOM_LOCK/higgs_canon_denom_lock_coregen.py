#!/usr/bin/env python3
"""Higgs canon denom lock (Core-only; NO-FACIT).

Goal
- Reduce HIGGS_VEV_LOCK candidate sets (v_hat, lambda_H, mH_hat) using
  a purely Core-internal *canon denom* + *canon quartic* rule.

Rules (Core semantics)
- Canon denom for v_hat is determined by **C30 strobe closure**:
    require K * v_hat ∈ Z for one full C30 cycle (K=30 ticks).
  For the candidate family v_hat = 1/d this is equivalent to d | K.
  Given the current candidate set {1/30, 1/42, 1/60, 1/90} this keeps only 1/30.
- Canon quartic for lambda_H is the minimal integer choice lambda_H = 1.
  (This is a structural tie-break: minimal polynomial degree/coeffs.)

No SI, no PDG/CODATA, no overlay, no reference json.

Reads
- out/CORE_HIGGS_VEV_LOCK/higgs_vev_lock_core_v*.json

Writes
- out/CORE_HIGGS_CANON_DENOM_LOCK/higgs_canon_denom_lock_core_v0_2.json
- out/CORE_HIGGS_CANON_DENOM_LOCK/higgs_canon_denom_lock_core_v0_2.md
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[3]


def _parse_unit_over_d(expr: str) -> Optional[int]:
    """Parse expressions of the form '1/<int>' and return the denominator."""
    s = str(expr).strip().replace(' ', '')
    if not s.startswith('1/'):
        return None
    try:
        d = int(s.split('/', 1)[1])
        return d if d > 0 else None
    except Exception:
        return None


def _strobe_closure_ok(v_hat_expr: str, K: int) -> tuple[bool, str]:
    """Return (ok, note) for the invariant K * v_hat ∈ Z."""
    d = _parse_unit_over_d(v_hat_expr)
    if d is None:
        return False, 'unparsed_expr'
    if K % d != 0:
        return False, f'FAIL: denom {d} does not divide K={K} (K/d={K}/{d})'
    return True, f'PASS: denom {d} divides K={K} (K/d={K//d})'


def _pick_latest(out_dir: Path, pattern: str) -> Optional[Path]:
    cands = sorted(out_dir.glob(pattern))
    return cands[-1] if cands else None


def _filter_by_expr(cands: list[dict], expr: str) -> list[dict]:
    return [c for c in cands if isinstance(c, dict) and str(c.get('expr')) == expr]


def main() -> int:
    higgs_path = _pick_latest(REPO / 'out' / 'CORE_HIGGS_VEV_LOCK', 'higgs_vev_lock_core_v*.json')
    if not higgs_path:
        print('MISSING CORE_HIGGS_VEV_LOCK output; run higgs_vev_lock_coregen first')
        return 2

    higgs = json.loads(higgs_path.read_text(encoding='utf-8'))
    if not isinstance(higgs, dict):
        print('INVALID CORE_HIGGS_VEV_LOCK json')
        return 3

    cs = higgs.get('candidate_space')
    if not isinstance(cs, dict):
        print('INVALID CORE_HIGGS_VEV_LOCK candidate_space')
        return 3

    vhat_blk = cs.get('v_hat') if isinstance(cs.get('v_hat'), dict) else {}
    lam_blk = cs.get('lambda_H') if isinstance(cs.get('lambda_H'), dict) else {}
    mhat_blk = cs.get('mH_hat') if isinstance(cs.get('mH_hat'), dict) else {}

    vhat_c = vhat_blk.get('candidates')
    lam_c = lam_blk.get('candidates')
    mhat_c = mhat_blk.get('candidates')

    if not isinstance(vhat_c, list) or not isinstance(lam_c, list) or not isinstance(mhat_c, list):
        print('INVALID CORE_HIGGS_VEV_LOCK candidates')
        return 3

    # Canon denom for v_hat via C30 strobe closure
    K = 30
    kept_v = []
    vhat_closure_notes: dict[str, str] = {}
    for c in vhat_c:
        if not isinstance(c, dict):
            continue
        expr = str(c.get('expr'))
        ok, note = _strobe_closure_ok(expr, K)
        vhat_closure_notes[expr] = note
        if ok:
            kept_v.append(c)

    # Canon quartic for lambda_H
    keep_l_expr = '1'
    kept_l = _filter_by_expr(lam_c, keep_l_expr)

    # Reduce mH_hat by requiring parent ids match (if present)
    kept_m = []
    if kept_v and kept_l:
        v_id = kept_v[0].get('id')
        l_id = kept_l[0].get('id')
        for c in mhat_c:
            if not isinstance(c, dict):
                continue
            parents = c.get('parents')
            if not isinstance(parents, dict):
                continue
            if parents.get('v_hat') == v_id and parents.get('lambda_H') == l_id:
                kept_m.append(c)

    derived = (len(kept_v) == 1 and len(kept_l) == 1 and len(kept_m) == 1)

    # Evaluate explicit NEG controls (reported, facit-free)
    neg_eval = []
    for nc in [
        {'name': 'NEG_vhat_denom_42', 'expr': '1/42', 'kind': 'v_hat'},
        {'name': 'NEG_vhat_denom_60', 'expr': '1/60', 'kind': 'v_hat'},
        {'name': 'NEG_vhat_denom_90', 'expr': '1/90', 'kind': 'v_hat'},
        {'name': 'NEG_lambda_half', 'expr': '1/2', 'kind': 'lambda_H'},
        {'name': 'NEG_lambda_two', 'expr': '2', 'kind': 'lambda_H'},
    ]:
        if nc['kind'] == 'v_hat':
            ok, note = _strobe_closure_ok(nc['expr'], K)
            neg_eval.append({**nc, 'passes': bool(ok), 'reason': note})
        else:
            # tie-break invariant: minimal integer quartic
            ok = (str(nc['expr']) == '1')
            neg_eval.append({**nc, 'passes': bool(ok), 'reason': 'FAIL: not minimal integer quartic' if not ok else 'PASS'})

    out = {
        'version': 'v0_2',
        'generated_utc': datetime.utcnow().isoformat(timespec='seconds') + 'Z',
        'lock': 'HIGGS_CANON_DENOM_LOCK',
        'inputs': {
            'higgs_vev_lock': str(higgs_path.relative_to(REPO)).replace('\\', '/'),
        },
        'policy': {
            'canon_denom_rule': 'require strobe closure: K * v_hat ∈ Z (K=30); for v_hat=1/d this means d | K',
            'canon_quartic_rule': 'prefer lambda_H == 1 (minimal integer quartic)',
            'no_facit': True,
            'no_overlay': True,
            'invariants': {
                'K': K,
                'strobe_closure': 'K * v_hat ∈ Z over one C30 cycle',
            },
        },
        'reduced': {
            'v_hat': {
                'candidate_count': int(len(vhat_c)),
                'kept': int(len(kept_v)),
                'candidates': kept_v,
                'preferred': kept_v[0] if kept_v else None,
            },
            'lambda_H': {
                'candidate_count': int(len(lam_c)),
                'kept': int(len(kept_l)),
                'candidates': kept_l,
                'preferred': kept_l[0] if kept_l else None,
            },
            'mH_hat': {
                'candidate_count': int(len(mhat_c)),
                'kept': int(len(kept_m)),
                'candidates': kept_m,
                'preferred': kept_m[0] if kept_m else None,
            },
        },
        'derivation_status': 'DERIVED' if derived else 'CANDIDATE-SET',
        'neg_controls': neg_eval,
        'evidence': {
            'v_hat_closure': vhat_closure_notes,
        },
        'notes': [
            'This lock is a Core semantic reduction; it does not consult overlay refs.',
            'Tick remains symbolic: v_RT := v_hat/Tick and mH_RT := mH_hat/Tick.',
        ],
    }

    out_dir = REPO / 'out' / 'CORE_HIGGS_CANON_DENOM_LOCK'
    out_dir.mkdir(parents=True, exist_ok=True)

    jp = out_dir / 'higgs_canon_denom_lock_core_v0_2.json'
    mp = out_dir / 'higgs_canon_denom_lock_core_v0_2.md'

    jp.write_text(json.dumps(out, indent=2, sort_keys=True) + '\n', encoding='utf-8')

    lines = [
        '# Higgs canon denom lock (Core-only)',
        '',
        f"- generated_utc: {out['generated_utc']}",
        f"- input higgs_vev_lock: `{out['inputs']['higgs_vev_lock']}`",
        '',
        '## Rules',
        '- v_hat: choose by **C30 strobe closure**: require `K * v_hat ∈ Z` (K=30 ticks).',
        '  - for v_hat = 1/d this is d | K; among current candidates this keeps only `1/30`.',
        '- lambda_H: choose `1` (minimal integer quartic).',
        '',
        '## Reduced sets',
        f"- v_hat: kept {out['reduced']['v_hat']['kept']} / {out['reduced']['v_hat']['candidate_count']}",
        f"- lambda_H: kept {out['reduced']['lambda_H']['kept']} / {out['reduced']['lambda_H']['candidate_count']}",
        f"- mH_hat: kept {out['reduced']['mH_hat']['kept']} / {out['reduced']['mH_hat']['candidate_count']}",
        '',
        f"- derivation_status: **{out['derivation_status']}**",
    ]

    if out['reduced']['mH_hat']['preferred']:
        lines += [
            '',
            '## Preferred',
            f"- v_hat: `{out['reduced']['v_hat']['preferred'].get('expr')}`",
            f"- lambda_H: `{out['reduced']['lambda_H']['preferred'].get('expr')}`",
            f"- mH_hat: `{out['reduced']['mH_hat']['preferred'].get('expr')}`",
        ]

    lines += [
        '',
        '## NEG controls (evaluated)',
        '',
        '| Name | Kind | Expr | Pass | Reason |',
        '|---|---|---:|:---:|---|',
    ]
    for nc in out['neg_controls']:
        lines.append(f"| {nc.get('name')} | {nc.get('kind')} | `{nc.get('expr')}` | {'✅' if nc.get('passes') else '❌'} | {nc.get('reason')} |")

    mp.write_text('\n'.join(lines) + '\n', encoding='utf-8')

    print(f"WROTE: {jp}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
