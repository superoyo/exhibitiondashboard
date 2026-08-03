"""PYTHON reference for bulk roster import — the parity baseline for Express.

Lives in the repo (NOT a temp dir) on purpose: an earlier version of this lived
in a scratchpad and was lost between sessions, taking the reference output with
it. The Express counterpart is apps/api/scripts/roster-fixture.ts.

Exercises the behaviour changed by 24628c9 ("merge rows of the same account
instead of last-wins"):
  - the same account on several rows is MERGED, first row keeps name/group/order
  - links are concatenated, then deduped by (platform, url-without-query)
  - followers backfill only when the first row had none

Run:  .venv/bin/python scripts/parity/bulk_import_reference.py
"""
from __future__ import annotations

import json
import sys

sys.path.insert(0, "/Users/anan/Desktop/KOL")

from sqlalchemy import delete, select  # noqa: E402

from app.api import routes  # noqa: E402
from app.db import session_scope  # noqa: E402
from app.models import AppSetting, Campaign, ReportKol, ReportPost  # noqa: E402

C = "paritybulk"

# Two rows for the same account, plus an overlapping link that must dedupe, plus
# a blank-username row that must be skipped entirely.
PAYLOAD = [
    dict(username="@DupUser", display="First", group="A", subgroup="S1", followers=0,
         links=[dict(platform="tiktok", url="https://a.com/1"),
                dict(platform="tiktok", url="https://shared.com/p?utm=1")]),
    dict(username="dupuser", display="Second", group="ZZZ", subgroup="S2", followers=77,
         links=[dict(platform="tiktok", url="https://b.com/2", handle="h"),
                dict(platform="tiktok", url="https://shared.com/p/"),
                dict(url="   ")]),
    dict(username="", group="A", links=[dict(url="https://ignored.com/x")]),
    dict(username="solo", url=" https://c.com/3 ", followers="5"),
]


def wipe(s):
    s.execute(delete(ReportPost).where(ReportPost.campaign == C))
    s.execute(delete(ReportKol).where(ReportKol.campaign == C))
    s.execute(delete(Campaign).where(Campaign.key == C))
    s.execute(delete(AppSetting).where(AppSetting.key == f"sheet_url:{C}"))


with session_scope() as s:
    wipe(s)
    s.flush()
    s.add(Campaign(key=C, name="Parity Bulk", emoji="🧪", active=True))

out = {}
with session_scope() as s:
    try:
        out["bulk"] = routes.bulk_replace_report(
            routes.BulkRosterIn(
                kols=[routes.BulkKolIn(**k) for k in PAYLOAD],
                sheet_url="  https://sheet.example/s  ",
            ),
            campaign=C, session=s)
    except Exception as exc:  # noqa: BLE001
        out["bulk"] = {"status": getattr(exc, "status_code", None),
                       "detail": getattr(exc, "detail", str(exc))}

with session_scope() as s:
    rows = s.scalars(select(ReportKol).where(ReportKol.campaign == C)
                     .order_by(ReportKol.sort_order, ReportKol.id)).all()
    out["rows"] = [{
        "sort_order": r.sort_order, "username": r.username, "display": r.display,
        "group": r.content_group, "subgroup": r.subgroup, "url": r.url,
        "links_json": r.links_json, "followers": r.followers, "active": r.active,
    } for r in rows]
    st = s.get(AppSetting, f"sheet_url:{C}")
    out["sheet_url"] = st.value if st else None

with session_scope() as s:
    try:
        out["bulk_empty"] = routes.bulk_replace_report(
            routes.BulkRosterIn(kols=[]), campaign=C, session=s)
    except Exception as exc:  # noqa: BLE001
        out["bulk_empty"] = {"status": getattr(exc, "status_code", None),
                             "detail": getattr(exc, "detail", str(exc))}

with session_scope() as s:
    wipe(s)

print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
