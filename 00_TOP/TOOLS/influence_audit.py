"""Influence Audit: runtime logging + HARD FAIL on forbidden file dependencies.

Design goals
- Catch accidental/indirect reads (imports, json, config, etc.)
- Minimal, no external deps
- Works as a wrapper around *_coregen.py

Core policy
- Core must not open 00_TOP/OVERLAY* (prefix-based, no trailing slash)
- Core must not open any *reference*.json
- Core must not open "facit" targets by name heuristics (PDG/CODATA/target)
- Core must not open arbitrary files outside the repo tree
  (exception: Python/runtime system files such as stdlib + site-packages)

This module is intentionally small and explicit.
"""

from __future__ import annotations

import builtins
import fnmatch
import io
import os
import pathlib
import shutil
import sys
import sysconfig
import site
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Optional, Tuple


def _norm_path(p: str) -> str:
    """Normalize to absolute path with forward slashes."""
    try:
        pp = pathlib.Path(p)
        if not pp.is_absolute():
            pp = (pathlib.Path.cwd() / pp)
        s = str(pp)
    except Exception:
        s = str(p)
    return s.replace("\\", "/")


def _norm_prefix(p: str) -> str:
    s = _norm_path(p)
    if not s.endswith("/"):
        s += "/"
    return s


def _default_system_allow_roots() -> Tuple[str, ...]:
    """Compute a conservative allowlist for runtime/system reads.

    Goal: allow Python stdlib/site-packages + a few common read-only system roots,
    while still forbidding /tmp, $HOME, mounted drives, etc.
    """
    roots = set()

    # stdlib / site-packages
    try:
        paths = sysconfig.get_paths() or {}
        for k in ("stdlib", "platstdlib", "purelib", "platlib"):
            v = paths.get(k)
            if v:
                roots.add(_norm_prefix(v))
    except Exception:
        pass

    try:
        for v in (site.getsitepackages() or []):
            if v:
                roots.add(_norm_prefix(v))
    except Exception:
        pass

    try:
        v = site.getusersitepackages()
        if v:
            roots.add(_norm_prefix(v))
    except Exception:
        pass

    # common prefixes used by Python installs
    for v in {getattr(sys, "base_prefix", ""), getattr(sys, "prefix", ""), getattr(sys, "exec_prefix", "")}:
        if v:
            roots.add(_norm_prefix(v))

    # conservative read-only system roots (for certs/locale/zoneinfo/etc.)
    for v in ("/usr/", "/lib/", "/etc/ssl/", "/etc/pki/", "/System/Library/", "/Library/"):
        roots.add(_norm_prefix(v))

    # specific device files occasionally touched by Python
    for v in ("/dev/null", "/dev/urandom"):
        roots.add(_norm_path(v))

    # normalize & sort
    out = sorted(roots)
    return tuple(out)


@dataclass
class AuditConfig:
    repo_root: pathlib.Path

    # Prefix-based (no trailing slash on purpose): blocks
    #   00_TOP/OVERLAY/...
    #   00_TOP/OVERLAY__OFF/...
    #   00_TOP/OVERLAY__STUBBED__.../...
    forbidden_roots: Tuple[str, ...] = ("00_TOP/OVERLAY",)

    forbidden_globs: Tuple[str, ...] = ("*reference*.json",)

    # extra name heuristics (optional; still counts as forbidden)
    forbidden_name_substrings: Tuple[str, ...] = ("PDG", "CODATA", "targets", "target")

    # In-repo allowlist (repo-relative prefixes). Core should normally stay in these.
    allow_roots: Tuple[str, ...] = ("out/", "00_TOP/", "01_V6_ARCHIVE/", "02_V7_ATOM/", "03_DATA/")

    # Out-of-repo allowlist for Python/runtime/system reads.
    system_allow_roots: Tuple[str, ...] = field(default_factory=_default_system_allow_roots)


@dataclass
class OpenEvent:
    path: str
    mode: str
    op: str
    when_utc: float
    scope: str
    stack: Optional[str] = None


class ForbiddenDependency(RuntimeError):
    pass


class InfluenceAudit:
    def __init__(self, cfg: AuditConfig, capture_stack: bool = False):
        self.cfg = cfg
        self.capture_stack = capture_stack
        self.opened: list[OpenEvent] = []
        self._orig_open = None
        self._orig_io_open = None
        self._orig_os_open = None
        self._orig_path_open = None

    def _rel_to_repo(self, norm_abs_path: str) -> Optional[str]:
        try:
            rel = pathlib.Path(norm_abs_path).resolve().relative_to(self.cfg.repo_root.resolve())
            return str(rel).replace("\\", "/")
        except Exception:
            return None

    def _is_allowed_in_repo(self, rel_s: str) -> bool:
        for pfx in self.cfg.allow_roots:
            p = pfx.rstrip("/")
            if rel_s == p or rel_s.startswith(p + "/"):
                return True
        return False

    def _is_system_allowed(self, norm_abs_path: str) -> bool:
        # exact device file allow
        if norm_abs_path in ("/dev/null", "/dev/urandom"):
            return True
        for pfx in self.cfg.system_allow_roots:
            if pfx.endswith("/"):
                if norm_abs_path.startswith(pfx):
                    return True
            else:
                if norm_abs_path == pfx:
                    return True
        return False

    def _classify_scope(self, norm_abs_path: str) -> Tuple[str, str]:
        rel = self._rel_to_repo(norm_abs_path)
        if rel is not None:
            if not self._is_allowed_in_repo(rel):
                return "other", rel
            return "repo", rel
        if self._is_system_allowed(norm_abs_path):
            return "system", norm_abs_path
        return "other", norm_abs_path

    def _is_forbidden(self, rel_or_abs: str) -> Tuple[bool, str]:
        """Forbidden checks on a string that is either repo-relative or absolute."""

        rel_s = rel_or_abs

        # Prefix forbids
        for r in self.cfg.forbidden_roots:
            rr = r.rstrip("/")
            if rel_s.startswith(rr):
                return True, f"forbidden_root_prefix:{rr}"

        # Glob forbids (match on basename and full rel path)
        base = rel_s.split("/")[-1]
        for g in self.cfg.forbidden_globs:
            if fnmatch.fnmatch(base, g) or fnmatch.fnmatch(rel_s, g):
                return True, f"forbidden_glob:{g}"

        # Heuristic forbids
        upper = rel_s.upper()
        for sub in self.cfg.forbidden_name_substrings:
            if sub.upper() in upper:
                return True, f"forbidden_name:{sub}"

        return False, ""

    def _record(self, path: str, mode: str, op: str, scope: str) -> None:
        ev = OpenEvent(path=path, mode=mode, op=op, when_utc=time.time(), scope=scope)
        if self.capture_stack:
            ev.stack = "".join(traceback.format_stack(limit=18))
        self.opened.append(ev)

    def _mode_writes(self, mode: str) -> bool:
        # builtins.open / Path.open modes
        if mode.startswith("flags="):
            # os.open flags
            try:
                flags = int(mode.split("=", 1)[1])
            except Exception:
                return True
            write_mask = (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            return (flags & write_mask) != 0
        m = mode
        return ("w" in m) or ("a" in m) or ("+" in m) or ("x" in m)

    def _check_and_record(self, path_obj: Any, mode: str, op: str) -> None:
        # Path can be str, bytes, os.PathLike, int fd, etc.
        if isinstance(path_obj, int):
            self._record(path=f"<fd:{path_obj}>", mode=mode, op=op, scope="fd")
            return

        if isinstance(path_obj, (bytes, bytearray)):
            try:
                path_s = path_obj.decode("utf-8", errors="replace")
            except Exception:
                path_s = str(path_obj)
        else:
            path_s = os.fspath(path_obj)

        norm_abs = _norm_path(path_s)
        scope, rel_or_abs = self._classify_scope(norm_abs)

        # Record with normalized absolute path for transparency
        self._record(path=norm_abs, mode=mode, op=op, scope=scope)

        # Strict sandbox: forbid any non-system open outside repo.
        if scope == "other":
            raise ForbiddenDependency(f"InfluenceAudit HARD FAIL: opened outside repo/allowlist: {norm_abs}")

        # Forbid writes outside repo even if system
        if scope != "repo" and self._mode_writes(mode):
            raise ForbiddenDependency(f"InfluenceAudit HARD FAIL: attempted write outside repo: {norm_abs} mode={mode}")

        # Forbidden patterns: apply to repo-relative path when available, else absolute
        forbidden, why = self._is_forbidden(rel_or_abs)
        if forbidden:
            raise ForbiddenDependency(f"InfluenceAudit HARD FAIL: opened forbidden path: {norm_abs} ({why})")

    def __enter__(self) -> "InfluenceAudit":
        self._orig_open = builtins.open
        self._orig_io_open = io.open
        self._orig_os_open = os.open
        self._orig_path_open = pathlib.Path.open

        def _open(file, mode="r", *args, **kwargs):
            self._check_and_record(file, str(mode), op="builtins.open")
            return self._orig_open(file, mode, *args, **kwargs)  # type: ignore[misc]

        def _io_open(file, mode="r", *args, **kwargs):
            self._check_and_record(file, str(mode), op="io.open")
            return self._orig_io_open(file, mode, *args, **kwargs)  # type: ignore[misc]

        def _os_open(path, flags, mode=0o777, *args, **kwargs):
            self._check_and_record(path, f"flags={flags}", op="os.open")
            return self._orig_os_open(path, flags, mode, *args, **kwargs)  # type: ignore[misc]

        def _path_open(self_path: pathlib.Path, mode="r", *args, **kwargs):
            self._check_and_record(str(self_path), str(mode), op="Path.open")
            return self._orig_path_open(self_path, mode, *args, **kwargs)  # type: ignore[misc]

        builtins.open = _open  # type: ignore[assignment]
        io.open = _io_open  # type: ignore[assignment]
        os.open = _os_open  # type: ignore[assignment]
        pathlib.Path.open = _path_open  # type: ignore[assignment]

        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if self._orig_open is not None:
            builtins.open = self._orig_open  # type: ignore[assignment]
        if self._orig_io_open is not None:
            io.open = self._orig_io_open  # type: ignore[assignment]
        if self._orig_os_open is not None:
            os.open = self._orig_os_open  # type: ignore[assignment]
        if self._orig_path_open is not None:
            pathlib.Path.open = self._orig_path_open  # type: ignore[assignment]
        return False


def stub_overlay(repo_root: pathlib.Path) -> Tuple[bool, Optional[pathlib.Path], Optional[pathlib.Path]]:
    """Temporarily moves 00_TOP/OVERLAY out of the way and replaces it with an empty stub dir.

    Robust against leftover state from a previously interrupted run.

    Returns (did_stub, overlay_path, moved_to)
    """
    overlay = repo_root / "00_TOP" / "OVERLAY"
    moved_base = repo_root / "00_TOP" / "OVERLAY__STUBBED__DO_NOT_USE"

    # If a previous run crashed after stubbing, we can end up with:
    #   overlay = stub dir (README_STUB.md)
    #   moved_base = real overlay
    # Heal by restoring real overlay first.
    if overlay.exists() and moved_base.exists():
        try:
            if (overlay / "README_STUB.md").exists():
                shutil.rmtree(overlay)
                moved_base.rename(overlay)
        except Exception:
            pass

    if not overlay.exists():
        if moved_base.exists():
            try:
                moved_base.rename(overlay)
            except Exception:
                pass
        if not overlay.exists():
            return False, None, None

    moved = moved_base
    if moved.exists():
        i = 1
        while True:
            cand = repo_root / "00_TOP" / f"OVERLAY__STUBBED__DO_NOT_USE__ALT{i}"
            if not cand.exists():
                moved = cand
                break
            i += 1

    overlay.rename(moved)
    overlay.mkdir(parents=True, exist_ok=True)
    (overlay / "README_STUB.md").write_text(
        "# OVERLAY (STUBBED)\n\nThis directory is intentionally stubbed during Core independence tests.\n",
        encoding="utf-8",
    )
    return True, overlay, moved


def restore_overlay(did_stub: bool, overlay_path: Optional[pathlib.Path], moved_to: Optional[pathlib.Path]) -> None:
    if not did_stub:
        return
    assert overlay_path is not None and moved_to is not None
    try:
        shutil.rmtree(overlay_path)
    except Exception:
        pass
    moved_to.rename(overlay_path)
