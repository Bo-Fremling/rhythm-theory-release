#!/usr/bin/env python3
"""GS canon denom lock (Core-only; NO-FACIT).

Goal
- Reduce the GS_LOCK candidate space for alpha_s_RT (and derived g_s)
  using a Core-internal *canon denom* rule.

Canon denom rule (Core semantics)
- Strong-sector quantities that live on the **C30 strobe lattice** must close
  on the lattice: for an expression `1/d`, we require **d | K** (with K=30).
- Among candidates, keep those that satisfy the closure invariant; prefer the
  unique survivor (expected: `1/30`).

No SI, no PDG/CODATA, no overlay.

Reads
- out/CORE_GS_LOCK/gs_lock_core_v*.json

Writes
- out/CORE_GS_CANON_DENOM_LOCK/gs_canon_denom_lock_core_v0_1.json
- out/CORE_GS_CANON_DENOM_LOCK/gs_canon_denom_lock_core_v0_1.md
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
import re
from typing import Optional

REPO = Path(__file__).resolve().parents[3]
K = 30


_DENOM_RE = re.compile(r'^\s*1\s*/\s*(\d+)\s*$')


def _denom(expr: str) -> Optional[int]:
    m = _DENOM_RE.match(expr or '')
    return int(m.group(1)) if m else None


def _pick_latest(out_dir: Path, pattern: str) -> Optional[Path]:
    cands = sorted(out_dir.glob(pattern))
    return cands[-1] if cands else None


def main() -> int:
    gs_path = _pick_latest(REPO / 'out' / 'CORE_GS_LOCK', 'gs_lock_core_v*.json')
    if not gs_path:
        print('MISSING CORE_GS_LOCK output; run gs_lock_coregen first')
        return 2

    gs = json.loads(gs_path.read_text(encoding='utf-8'))
    cs = (gs.get('candidate_space') or {}) if isinstance(gs, dict) else {}
    a = cs.get('alpha_s_RT') if isinstance(cs, dict) else None
    g = cs.get('g_s') if isinstance(cs, dict) else None

    a_cands = (a or {}).get('candidates') if isinstance(a, dict) else None
    g_cands = (g or {}).get('candidates') if isinstance(g, dict) else None

    if not isinstance(a_cands, list) or not isinstance(g_cands, list):
        print('INVALID CORE_GS_LOCK candidate_space')
        return 3

    # Canon denom invariant: C30 closure requires denom | K.
    kept_exprs: set[str] = set()
    kept_a = []
    neg_eval = []
    for c in a_cands:
        if not isinstance(c, dict):
            continue
        expr = str(c.get('expr'))
        d = _denom(expr)
        ok = bool(d) and (K % d == 0)
        kept_exprs.add(expr) if ok else None
        c2 = dict(c)
        c2['c30_closure'] = {'K': K, 'denom': d, 'pass': ok}
        if ok:
            kept_a.append(c2)
        if expr in {'1/42', '1/60', '1/90'}:
            neg_eval.append({'expr': expr, 'denom': d, 'pass': ok, 'reason': 'denom|K' if ok else 'denom∤K'})

    # Map to matching g_s candidates (keep those sourced from kept alpha_s exprs)
    kept_g = []
    for c in g_cands:
        if not isinstance(c, dict):
            continue
        src = str(c.get('source_alpha_s_expr'))
        if src in kept_exprs:
            c2 = dict(c)
            d = _denom(src)
            ok = bool(d) and (K % d == 0)
            c2['c30_closure'] = {'K': K, 'denom': d, 'pass': ok}
            kept_g.append(c2)

    # Determine statuses
    derived = (len(kept_a) == 1 and len(kept_g) == 1)

    out = {
        'version': 'v0_2',
        'generated_utc': datetime.utcnow().isoformat(timespec='seconds') + 'Z',
        'lock': 'GS_CANON_DENOM_LOCK',
        'inputs': {
            'gs_lock': str(gs_path.relative_to(REPO)).replace('\\', '/'),
        },
        'policy': {
            'canon_denom_rule': 'C30 closure: for alpha_s_RT=1/d require d|K with K=30',
            'no_facit': True,
            'no_overlay': True,
        },
        'reduced': {
            'alpha_s_RT': {
                'candidate_count': int(len(a_cands)),
                'kept': int(len(kept_a)),
                'candidates': kept_a,
                'preferred': kept_a[0] if kept_a else None,
            },
            'g_s': {
                'candidate_count': int(len(g_cands)),
                'kept': int(len(kept_g)),
                'candidates': kept_g,
                'preferred': kept_g[0] if kept_g else None,
            },
        },
        'derivation_status': 'DERIVED' if derived else 'CANDIDATE-SET',
        'neg_controls': [
            {'name': 'NEG_denom_42', 'expr': '1/42'},
            {'name': 'NEG_denom_60', 'expr': '1/60'},
            {'name': 'NEG_denom_90', 'expr': '1/90'},
        ],
        'neg_controls_evaluated': neg_eval,
        'notes': [
            'This lock is purely a Core semantic reduction; it does not consult overlay refs.',
            'If future Core semantics change the definition of strong normalization, this rule must be revisited.',
        ],
    }

    out_dir = REPO / 'out' / 'CORE_GS_CANON_DENOM_LOCK'
    out_dir.mkdir(parents=True, exist_ok=True)

    jp = out_dir / 'gs_canon_denom_lock_core_v0_2.json'
    mp = out_dir / 'gs_canon_denom_lock_core_v0_2.md'

    jp.write_text(json.dumps(out, indent=2, sort_keys=True) + '\n', encoding='utf-8')

    lines = [
        '# GS canon denom lock (Core-only)',
        '',
        f"- generated_utc: {out['generated_utc']}",
        f"- input gs_lock: `{out['inputs']['gs_lock']}`",
        '',
        '## Canon denom rule (C30 closure)',
        f'- Require **d | K** for alpha_s_RT = 1/d on the C30 lattice (K={K}).',
        '- Only surviving candidate in the current finite-set is expected to be `1/30`.',
        '',
        '## Reduced sets',
        f"- alpha_s_RT: kept {out['reduced']['alpha_s_RT']['kept']} / {out['reduced']['alpha_s_RT']['candidate_count']}",
        f"- g_s: kept {out['reduced']['g_s']['kept']} / {out['reduced']['g_s']['candidate_count']}",
        '',
        '## NEG evaluation (near denominators)',
    ]
    if out.get('neg_controls_evaluated'):
        for r in out['neg_controls_evaluated']:
            lines.append(f"- {r['expr']}: {'PASS' if r['pass'] else 'FAIL'} ({r['reason']})")
    else:
        lines.append('- (none)')

    lines += [
        '',
        '## Preferred',
    ]
    if out['reduced']['alpha_s_RT']['preferred']:
        lines.append(f"- alpha_s_RT preferred: `{out['reduced']['alpha_s_RT']['preferred'].get('expr')}`")
    if out['reduced']['g_s']['preferred']:
        lines.append(f"- g_s preferred: `{out['reduced']['g_s']['preferred'].get('expr')}`")

    mp.write_text('\n'.join(lines) + '\n', encoding='utf-8')

    print(f"WROTE: {jp}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
