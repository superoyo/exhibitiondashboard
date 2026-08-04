#!/usr/bin/env python3
"""Check every package in nixpacks.toml's setup phase exists in the pinned nixpkgs.

WHY: `nixpacks plan` emits package NAMES without resolving them, so a wrong name
passes every local check and only fails on Railway, minutes later, with
`error: undefined variable '<name>'`. That is how `pnpm-9_x` reached production —
it is a valid name in the Node provider's nixpkgs archive but not in the Python
provider's, and the two providers pin DIFFERENT archives.

Each Nixpacks provider pins its own archive, so the archive is read from the plan
rather than hardcoded: change providers and this keeps checking the right one.

Run:  python3 scripts/verify-nixpacks-pkgs.py
Needs the nixpacks binary (same version Railway uses -- see its build log):
  curl -sSL https://github.com/railwayapp/nixpacks/releases/download/v1.41.0/\
nixpacks-v1.41.0-aarch64-apple-darwin.tar.gz | tar xz
  NIXPACKS_BIN=./nixpacks python3 scripts/verify-nixpacks-pkgs.py
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent


def find_nixpacks() -> str | None:
    return os.environ.get("NIXPACKS_BIN") or shutil.which("nixpacks")


def declared_attrs(rev: str) -> set[str]:
    """Top-level attribute names in nixpkgs at `rev`."""
    url = f"https://raw.githubusercontent.com/NixOS/nixpkgs/{rev}/pkgs/top-level/all-packages.nix"
    src = urllib.request.urlopen(url, timeout=120).read().decode()
    # Two spellings: `name = ...;` and `inherit (callPackage ...) a b c;`
    attrs = set(re.findall(r"^\s{2}([A-Za-z0-9_.-]+)\s*=", src, re.M))
    for m in re.finditer(r"inherit\s*\([^)]*\)\s*([^;]+);", src):
        attrs.update(m.group(1).split())
    return attrs


def main() -> int:
    binary = find_nixpacks()
    if not binary:
        print("SKIP: nixpacks binary not found. See this file's docstring.")
        return 0  # not a failure -- the tool is optional tooling, not a dep

    plan = json.loads(
        subprocess.run(
            [binary, "plan", "."], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout
    )
    setup = plan.get("phases", {}).get("setup", {})
    rev = setup.get("nixpkgsArchive")
    pkgs = setup.get("nixPkgs") or []
    if not rev:
        print("FAIL: plan has no nixpkgsArchive -- cannot verify package names.")
        return 1

    print(f"archive : {rev}")
    attrs = declared_attrs(rev)
    bad = []
    for p in pkgs:
        base = p.split(".")[0]  # postgresql_16.dev -> postgresql_16
        ok = base in attrs
        print(f"  {'OK  ' if ok else 'MISS'} {p}")
        if not ok:
            bad.append(p)

    # The whole point of the file is that BOTH toolchains get installed.
    for want, label in (("python", "Python (uvicorn/alembic)"), ("nodejs", "Node (SPA build)")):
        if not any(want in p for p in pkgs):
            print(f"FAIL: no {want}* package -- {label} would be missing at run time.")
            bad.append(f"<missing {want}>")

    if bad:
        print(f"\nFAIL: {len(bad)} problem(s): {', '.join(bad)}")
        return 1
    print(f"\nOK: all {len(pkgs)} packages resolve, and both toolchains are present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
