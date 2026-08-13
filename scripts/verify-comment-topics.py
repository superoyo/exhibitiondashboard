#!/usr/bin/env python3
"""Assert the comment classifier's taxonomy, parser and prompt agree.

Pure logic — no server, no database, no AI key. Run it after any change to
CATEGORIES, _classify_prompt or _parse_classification:

    .venv/bin/python scripts/verify-comment-topics.py

Why this exists: the prompt, the parser, the label map and the frontend's colour
map are four separate lists of the same topic codes. Adding a topic to the prompt
and forgetting the label map does not crash — it ships a donut slice with an
undefined label, and the classifier silently drops every comment the model puts
in the new bucket, because _parse_classification rejects unknown codes. That is a
quiet loss of paid work, so it is checked rather than remembered.
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.comments import (  # noqa: E402
    CATEGORIES,
    CATEGORY_LABELS,
    PRODUCT_CATEGORIES,
    _classify_prompt,
    _parse_classification,
)

failed: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        failed.append(msg)


def main() -> int:
    print("-- taxonomy --")
    check(set(CATEGORY_LABELS) == set(CATEGORIES),
          f"every topic has a Thai label (missing: "
          f"{set(CATEGORIES) - set(CATEGORY_LABELS)})")
    check(set(PRODUCT_CATEGORIES) <= set(CATEGORIES),
          "the product topics are a subset of the whole set")
    check(set(CATEGORIES) - set(PRODUCT_CATEGORIES) == {"OFFTOPIC", "SPAM"},
          "only OFFTOPIC and SPAM sit outside 'about the product'")

    print("\n-- the frontend knows every topic --")
    panel = (ROOT / "apps/web/src/features/report/components/CommentPanel.tsx").read_text()
    coloured = set(re.findall(r"^  ([A-Z]+): '#", panel, re.M))
    check(coloured == set(CATEGORIES),
          f"CATEGORY_COLORS covers exactly the topics (extra/missing: "
          f"{coloured ^ set(CATEGORIES)})")
    chipped = set(re.findall(r"^  ([A-Z]+): '[^#]", panel, re.M))
    check(chipped == set(PRODUCT_CATEGORIES),
          f"CHIP_LABELS covers exactly the filterable topics "
          f"({chipped ^ set(PRODUCT_CATEGORIES)})")
    shared = (ROOT / "packages/shared/src/types/report.ts").read_text()
    union = set(re.findall(r"'([A-Z]+)'", shared.split("CommentCategory =")[1][:400]))
    check(union == set(CATEGORIES),
          f"the CommentCategory union matches ({union ^ set(CATEGORIES)})")

    print("\n-- the prompt defines what the parser accepts --")
    prompt = _classify_prompt("ทดสอบ", [type("C", (), {"text": "x"})()])
    for code in CATEGORIES:
        check(f"{code} =" in prompt, f"prompt defines {code}")
    check("เลข|CATEGORY|theme" in prompt, "prompt asks for `เลข|CATEGORY|theme`")
    check("บวกหรือลบ" in prompt,
          "prompt still tells the model NOT to judge direction")
    for rule in ("ของที่ใช้อยู่หมดพอดี", "ไม่ใช่ SPAM", "การตัดต่อ"):
        check(rule in prompt, f"the hard-won rule about '{rule}' survived")

    print("\n-- the parser --")
    reply = "\n".join([f"{i}|{c}|theme{i}" for i, c in enumerate(CATEGORIES, 1)])
    got = _parse_classification(reply, len(CATEGORIES))
    check(len(got) == len(CATEGORIES),
          f"every topic the prompt offers round-trips: {len(got)}/{len(CATEGORIES)}")
    check(all(len(v) == 2 for v in got.values()), "the parser yields (category, theme)")
    edge = _parse_classification(
        "1|EFFECT|-\n2|EFFECT|---\n3|NOPE|x\n4|EFFECT|pos|เห็นผล\n9|EFFECT|x\nnoise",
        4)
    check(edge.get(1) == ("EFFECT", None), f"'-' means no theme: {edge.get(1)}")
    check(edge.get(2) == ("EFFECT", None), f"'---' means no theme too: {edge.get(2)}")
    check(3 not in edge, "an unknown code is dropped, never stored")
    check(edge.get(4) == ("EFFECT", "เห็นผล"),
          f"a reply in the old 4-field shape still parses: {edge.get(4)}")
    check(9 not in edge and len(edge) == 3,
          f"out-of-range lines and noise dropped: {sorted(edge)}")

    print()
    if failed:
        print(f"❌ {len(failed)} check(s) failed")
        return 1
    print("✅ all comment-topic checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
