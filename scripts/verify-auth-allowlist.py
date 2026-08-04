#!/usr/bin/env python3
"""Assert app.main._needs_auth matches scripts/auth-allowlist-cases.json.

Pure logic — no server, no database, no token. Run it before any change to the
allowlist:

    .venv/bin/python scripts/verify-auth-allowlist.py

Why this exists on top of apps/api/scripts/verify-open-paths.ts: that script
compares the two live services against EACH OTHER, so it passes whenever they are
wrong in the same way. /api/campaigns/summary was open in both, and the roster of
every client was public while the parity check stayed green. This file checks
against stated expectations instead.
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.main import _needs_auth  # noqa: E402


def main() -> int:
    cases = json.loads((ROOT / "scripts" / "auth-allowlist-cases.json").read_text())["cases"]
    failed = []
    for c in cases:
        got = _needs_auth(c["method"], c["path"])
        want = c["needsAuth"]
        ok = got == want
        if not ok:
            failed.append(c)
        label = "AUTH" if want else "OPEN"
        print(f"  {'ok  ' if ok else 'FAIL'} {label:4} {c['method']:6} {c['path']}")
        if not ok:
            print(f"       expected needsAuth={want}, got {got} — {c['why']}")

    print()
    if failed:
        print(f"FAIL: {len(failed)} of {len(cases)} cases wrong")
        return 1
    print(f"OK: all {len(cases)} cases match")
    return 0


if __name__ == "__main__":
    sys.exit(main())
