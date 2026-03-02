#!/usr/bin/env python3
"""CORE_ARTIFACT_HASH_LOCK coregen (NO-FACIT).

Goal
- Strengthen trust in Core determinism without using any facit/overlay.
- Compute *semantic* hashes of Core artifacts (JSON) after stripping volatile fields
  like generated_utc/utc/stamp.
- Compare against the previous manifest. If any semantic hash changes => HARD FAIL.

Rules
- Must not read 00_TOP/OVERLAY/**
- Must not read any *reference*.json
- No PDG/CODATA/targets

Reads
- out/CORE_*/**/*.json (excluding out/CORE_AUDIT and this lock's own outputs)

Writes
- out/CORE_CORE_ARTIFACT_HASH_LOCK/core_artifact_hash_lock_core_v0_2.json
- out/CORE_CORE_ARTIFACT_HASH_LOCK/core_artifact_hash_lock_core_v0_2.md

Behavior
- If no prior manifest exists, writes BASELINE and exits 0.
- If prior manifest exists, compares; mismatch => exit 10.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[3]
OUT_DIR = REPO / 'out' / 'CORE_CORE_ARTIFACT_HASH_LOCK'
MANIFEST_GLOB = 'manifest_semhash_v0_2*.json'

VOLATILE_KEYS = {
    'generated_utc', 'generated', 'utc', 'stamp', 'timestamp', 'time_utc', 'created_utc',
    'run_utc', 'started_utc', 'ended_utc', 'date_utc'
}

EXCLUDE_DIRS = {
    str((REPO / 'out' / 'CORE_AUDIT').resolve()),
}

EXCLUDE_FILES = {
    'core_artifact_hash_lock_core_v0_2.json',
    'core_artifact_hash_lock_core_v0_2.md',
}


def _strip_volatile(x: Any) -> Any:
    if isinstance(x, dict):
        out = {}
        for k, v in x.items():
            if (k in VOLATILE_KEYS) or k.startswith('generated') or k.endswith('_utc'):
                continue
            out[k] = _strip_volatile(v)
        return out
    if isinstance(x, list):
        return [_strip_volatile(v) for v in x]
    return x


def _sem_hash_json(obj: Any) -> str:
    clean = _strip_volatile(obj)
    blob = json.dumps(clean, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    return hashlib.sha256(blob).hexdigest()


def _pick_latest_manifest() -> Optional[Path]:
    if not OUT_DIR.exists():
        return None
    cands = sorted(OUT_DIR.glob(MANIFEST_GLOB))
    return cands[-1] if cands else None


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Collect JSON artifacts
    files = []
    for p in (REPO / 'out').rglob('*.json'):
        rp = str(p.resolve())
        if any(rp.startswith(d + '/') or rp == d for d in EXCLUDE_DIRS):
            continue
        if p.name in EXCLUDE_FILES:
            continue
        # exclude this lock directory (we want stable compare against previous manifest)
        if str(p.parent.resolve()).startswith(str(OUT_DIR.resolve())):
            continue
        # only CORE_* artifacts
        if '/out/CORE_' not in rp.replace('\\','/'):
            continue
        files.append(p)

    files = sorted(files)

    manifest = {
        'version': 'v0_2',
        'generated_utc': datetime.utcnow().isoformat(timespec='seconds') + 'Z',
        'lock': 'CORE_ARTIFACT_HASH_LOCK',
        'policy': {
            'no_facit': True,
            'no_overlay': True,
            'semantic_hash': 'sha256(json_with_volatile_fields_stripped)',
            'volatile_keys': sorted(VOLATILE_KEYS),
        },
        'tracked_count': len(files),
        'tracked': [],
        'compare': None,
        'status': 'UNKNOWN',
    }

    current = {}
    for p in files:
        rel = str(p.relative_to(REPO)).replace('\\','/')
        try:
            obj = json.loads(p.read_text(encoding='utf-8'))
        except Exception as e:
            manifest['tracked'].append({'path': rel, 'error': f'{type(e).__name__}: {e}'})
            continue
        h = _sem_hash_json(obj)
        current[rel] = h
        manifest['tracked'].append({'path': rel, 'semhash': h})

    prev_path = _pick_latest_manifest()
    if not prev_path:
        manifest['status'] = 'BASELINE'
        manifest['compare'] = {'previous': None, 'mismatches': [], 'match': None}
    else:
        prev = json.loads(prev_path.read_text(encoding='utf-8'))
        prev_map = {t.get('path'): t.get('semhash') for t in (prev.get('tracked') or []) if isinstance(t, dict)}
        mism = []
        # compare intersection + additions/removals
        all_keys = sorted(set(prev_map.keys()) | set(current.keys()))
        for k in all_keys:
            a = prev_map.get(k)
            b = current.get(k)
            if a != b:
                mism.append({'path': k, 'prev': a, 'now': b})
        manifest['compare'] = {
            'previous': str(prev_path.name),
            'mismatches': mism,
            'match': (len(mism) == 0),
        }
        manifest['status'] = 'PASS' if len(mism) == 0 else 'FAIL'

    # write manifest as v0_1 (overwrites latest for this run)
    man_path = OUT_DIR / 'manifest_semhash_v0_2.json'
    man_path.write_text(json.dumps({'tracked': manifest['tracked'], 'generated_utc': manifest['generated_utc']}, indent=2, sort_keys=True) + '\n', encoding='utf-8')

    jp = OUT_DIR / 'core_artifact_hash_lock_core_v0_2.json'
    jp.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8')

    # md
    lines = [
        '# CORE_ARTIFACT_HASH_LOCK (Core-only)',
        '',
        f"- generated_utc: {manifest['generated_utc']}",
        f"- tracked_count: {manifest['tracked_count']}",
        f"- status: **{manifest['status']}**",
    ]
    comp = manifest.get('compare') or {}
    if comp.get('previous'):
        lines += ['', f"- previous_manifest: `{comp.get('previous')}`", f"- match: **{comp.get('match')}**"]
    if comp.get('mismatches'):
        lines += ['', '## Mismatches']
        for m in comp['mismatches'][:50]:
            lines.append(f"- {m['path']}")
    (OUT_DIR / 'core_artifact_hash_lock_core_v0_2.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')

    print(f"WROTE: {jp}")

    if manifest['status'] == 'FAIL':
        return 10
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
