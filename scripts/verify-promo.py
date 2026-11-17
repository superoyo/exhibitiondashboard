#!/usr/bin/env python3
"""Promotion Page Package: sheet reader + API on a throwaway local Postgres.

LOCAL-ONLY dev check (needs the embedded pgserver, like verify-advisor.py):

    .venv/bin/python scripts/verify-promo.py

The four workbooks built here reproduce the four layouts the team really uses
(see app/promo_sheet.py) with made-up content. They pin the counting rules the
page shows: used = ticked / status says so / has a post link; reserved = names
a brand or job; free = empty. Also covered: money never reaches the payload,
a failed re-read keeps the last good snapshot, and every route needs a login.
"""
import datetime as dt
import io
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import pgserver  # noqa: E402
import sqlalchemy as sa  # noqa: E402
from openpyxl import Workbook  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'} {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def xlsx(wb) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def layout_a() -> bytes:
    """One sheet per page, "No. Post", one Link Post cell, Used ticks."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Sale Here"
    ws.append([])
    ws.append([None, "Influ Buyer", "Account", "Campaign", "No. Post", "Package", "งบบูสโพส",
               "ใช้จริง", "วันหมดอายุ\nของ Package", "Conditions", "Post Date", "Link Post",
               "Used", "Note"])
    ws.append([None, "SALZ"])
    ws.merge_cells("B3:M3")
    ws.append([None, "Jean", "Salz", "Salz x Cha Tra Mue", "Sale Here 1", "Photo Album", 15000,
               15000, None, None, dt.datetime(2026, 3, 28),
               "https://www.facebook.com/story.php?story_fbid=1&id=2", True, None])
    ws.append([None, "Haru", "Salz", "Tops of Beauty", "Sale Here 2", "Photo Album", 10000, 10000,
               None, None, dt.datetime(2026, 2, 26),
               "https://www.facebook.com/100070071710681/posts/134", True, None])
    ws.append([None, "Jean", "Salz", "SALZ Dental Pack - Toy Story", "Sale Here 3", "Photo Album",
               15000, None, None, None, None, None, False, None])
    ws.append([None, None, None, None, "Sale Here 4", "Photo Album", None, None, None, None,
               None, None, False, None])
    ws.append([None, "SYSTEMA"])
    ws.merge_cells("B8:M8")
    ws.append([None, "Nat", "SYSTEMA", "Brush Alarm", "Sale Here 5", "Photo Album", None, None,
               None, None, None, None, True, None])
    ws.append([None, "Nat", "SYSTEMA", "Pack 6 (Proxie)", "Sale Here 6", "Photo Album", 48000,
               29000, None, None, dt.datetime(2026, 9, 1),
               "Facebook: https://www.facebook.com/salehere/posts/9\n"
               "Instagram : https://www.instagram.com/p/AAA/?img_index=1\n"
               "X : https://x.com/salehere1/status/99?s=20", True, "ออก PO ยอดบูสแล้ว May"])
    ws.append([None, "Complimentary VDO*5 Post"])
    ws.merge_cells("B11:M11")
    ws.append([None, "Jean", "Salz", "Salz x Cha Tra Mue", "Sale Here 7", "Shot VDO on TikTok #1",
               10000, None, None, None, None,
               "https://www.tiktok.com/@salehere/video/7636298657385549076", True, None])
    ws.append([None, None, None, None, None, None, None, None, None, None, None, "ใช้", 5])
    ws.append([None, None, None, None, None, None, None, None, None, None, None, "เหลือ", 2])

    ws2 = wb.create_sheet("ProHub")  # no Used column on this one
    ws2.append([])
    ws2.append([None, "Influ Buyer", "Account", "Campaign", "No. Post", "Package", "งบบูสโพส",
                "วันหมดอายุ\nของ Package", "Conditions", "Post Date", "Link Post", "Note"])
    ws2.append([None, "Jean", "SALZ", "Salz x Cha Tra Mue", "ProHub 1", "Photo Album", 15000,
                dt.datetime(2026, 12, 31), None, dt.datetime(2026, 4, 30),
                "https://www.facebook.com/prohub/posts/1", None])
    ws2.append([None, "Nat", "SYSTEMA", "Pack 6 (Proxie)", "ProHub 2", "Photo Album", 48000,
                None, None, None, None, "ออก PO ยอดบูสแล้ว May"])
    ws2.append([None, "Jean", "Zact", None, "ProHub #3", "Photo Album", None, None, None,
                dt.datetime(2026, 9, 17), None, None])
    return xlsx(wb)


def layout_b() -> bytes:
    """Every page on one sheet; the link sits in the matching Post N column."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Quota Post"
    ws.append(["Influ Buyer", "Account", "Influencer", "Package", "งบบูสโพส", "KPI (Reach)",
               "หมดเขต", "Post 1", "Post 2", "Post 3", "Conditions", "Post all platform"])
    ws.append(["HARU", "Shokubutsu Talcum", "Sale Here 1", "Photo Album 5 Post Free 1 Post",
               None, None, "31 Dec 2026", "เปิดโพสต์", None, None,
               "ไม่สามารถแบ่งทำจ่ายได้เนื่องจากจำนวนครั้งที่ซื้อน้อย", None])
    ws["H2"].hyperlink = "https://www.facebook.com/salehere/posts/pfbid0AAA"
    ws.append(["BAM", "Falles", "Sale Here 2", "Photo Album 5 Post Free 1 Post", 12000,
               "400,000 Reach", "5 August 2026", None,
               "https://www.facebook.com/571635115182207/posts/147", None,
               "โควต้าของ Free&Free ใช้จริงของ Falles",
               "Facebook : https://www.facebook.com/salehere/posts/other-form\n"
               "IG : https://www.instagram.com/p/Da4/?img_index=1"])
    ws.append([])
    ws.append(["HARU", "Shokubutsu Shower", "Event Pass 1 Post", "Photo Album 1 Post", None, None,
               "31 Dec 2026", "https://www.facebook.com/EventPassfanpage/posts/1", None, None,
               None, None])
    ws.append(["BAM", "Q'Lean", "Event Pass 2 Post", "Photo Album 2 Post", 10000,
               "830,000 Reach", "2 December 2026", None, None, None, "ใช้โควต้าของ Falles",
               "IG : https://www.instagram.com/p/Deg/"])
    ws.append([None, None, "Event Pass 3 Post", "Photo Album 3 Post"])

    money = wb.create_sheet("Remark")
    money.append(["No.", "Name", "Platforms", "SOW", "Rate Card", "Boost Post", "Total Budget",
                  "Total Post"])
    money.append([1, "Sale here 5 Post", "Facebook", "Package Photo Album", 262500, 150000,
                  534450, 6])
    return xlsx(wb)


def layout_c() -> bytes:
    """Merged page name, "Post 1/6", STATUS dropdown; a timeline sheet in front."""
    wb = Workbook()
    tl = wb.active
    tl.title = "Timeline"
    tl.append(["No", "Name", "Product", "Address", "No. Post", "Post Date", "Remark", "Link Post"])
    tl.append([1, "ปันโปร", "Zilk", "196 ถนนประดิพัทธ์", "Post 1/6", "10/06/2026\n(10.00)",
               "ทางเพจแก้ได้แค่ 1 ครั้ง", None])

    ws = wb.create_sheet("Status")
    ws.append(["No.", "Name", "No. Post", "Product ", "STATUS", "Post Date", "Link Post", "Remark"])
    ws.append([1, "Sale Here", "Post 1/6", "Maxmo Big Roll", "Post", dt.datetime(2026, 5, 29),
               "https://www.facebook.com/salehere/posts/pfbid0YH", None])
    ws.append([None, None, "Post 2/6", "Zilk & Cellox Facial", "Post", None, None, None])
    ws.append([None, None, "Post 3/6", "Cellox NPD", "Wait idea", None, None, None])
    ws.append([None, None, "Post 4/6", None, None, None, None, None])
    ws.append([])
    ws.append([])
    ws.merge_cells("B2:B7")
    ws.append([2, "ปันโปร", "Post 1/6", "Zilk & Cellox Facial", "Post", dt.datetime(2026, 6, 19),
               "https://www.facebook.com/788494752840719/posts/162", None])
    ws.append([])
    ws.merge_cells("B8:B9")

    old = wb.create_sheet("เก่า")
    old.append(["No. Post", "Link Post"])
    old.append(["Old Page 1", "https://www.facebook.com/old/posts/1"])
    old.sheet_state = "hidden"
    return xlsx(wb)


def layout_d(all_used: bool = False) -> bytes:
    """Bare slot numbers, Status = Published, and a stale summary box on top."""
    wb = Workbook()
    ws = wb.active
    ws.title = "ชี้เป้าเซเว่น"
    ws.append([])
    ws.append([None, None, "Post", "Quota", "Published", "คงเหลือ"])
    ws.append([None, None, "Photo Album", 10, 1, 9])
    ws.append([])
    ws.append([None, None, "Report Campaign:", "https://docs.google.com/presentation/d/x/edit"])
    ws.append([])
    ws.append([None, "Post", "Campaign", "Media", "Post Date", "Link Post", "Status"])
    ws.append([None, 1, "Kodomo Toothpaste 1 แถม 1 ราคา 26.-", "Photo Album", "19 June 2026",
               "Facebook: https://www.facebook.com/cheepaoseven/posts/1\n"
               "Instagram: https://www.instagram.com/p/DZw", "Published"])
    ws.append([None, 2, "Toothpaste Monchichi", "Photo Album", "24 Sep",
               "https://www.facebook.com/share/p/19K1HHStoY/", "Published"])
    if not all_used:
        ws.append([None, 3, None, "Photo Album", None, "FB : \nIG : \nX : ", None])
        ws.append([None, 4, None, "Photo Album", None, "FB : \nIG : \nX : ", None])
    return xlsx(wb)


def pack(data, page):
    return next(p for p in data["packs"] if p["page"] == page)


def slot(p, n):
    return next(s for s in p["slots"] if s["n"] == n)


def platforms(s):
    return [link["platform"] for link in s["links"]]


def counts(p):
    return (p["quota"], p["used"], p["reserved"], p["free"])


# ---------------------------------------------------------------- reader ----
from app.promo_sheet import parse_workbook, totals  # noqa: E402

print("layout A — sheet per page, Used ticks")
a = parse_workbook(layout_a())
sh = pack(a, "Sale Here")
check("pages come from the sheets", [p["page"] for p in a["packs"]] == ["Sale Here", "ProHub"])
check("Sale Here: 7 slots, 5 used, 1 reserved, 1 free", counts(sh) == (7, 5, 1, 1), str(counts(sh)))
check("ticked without a link is still used", slot(sh, 5)["status"] == "used" and not slot(sh, 5)["links"])
check("unticked row naming a job is reserved", slot(sh, 3)["status"] == "reserved")
check("one cell, three platforms", platforms(slot(sh, 6)) == ["facebook", "instagram", "x"])
check("section banners carry down", [slot(sh, n)["section"] for n in (1, 5, 7)]
      == ["SALZ", "SYSTEMA", "Complimentary VDO*5 Post"])
check("real date cells become ISO dates", slot(sh, 1)["date_iso"] == "2026-03-28")
check("the footer tally is not a slot", all(s["n"] <= 7 for s in sh["slots"]))
ph = pack(a, "ProHub")
check("ProHub (no Used column): 1 used, 2 reserved", counts(ph) == (3, 1, 2, 0), str(counts(ph)))
check("\"ProHub #3\" is slot 3 of ProHub", slot(ph, 3)["account"] == "Zact")
check("expiry read from its own column", ph["expiry"] == "2026-12-31")

print("layout B — one sheet, link in the matching Post N column")
b = parse_workbook(layout_b())
check("two pages, money sheet ignored", [p["page"] for p in b["packs"]] == ["Sale Here", "Event Pass"])
sh, ev = pack(b, "Sale Here"), pack(b, "Event Pass")
check("Sale Here: 2 of 2 used", counts(sh) == (2, 2, 0, 0), str(counts(sh)))
check("hyperlinked text counts as a link", slot(sh, 1)["links"][0]["url"].endswith("pfbid0AAA"))
check("first row's หมดเขต is the pack expiry", sh["expiry"] == "31 Dec 2026" and slot(sh, 1)["date"] == "")
check("later rows' หมดเขต is the post date", slot(sh, 2)["date"] == "5 August 2026")
check("all-platform adds only missing platforms", platforms(slot(sh, 2)) == ["facebook", "instagram"])
check("Event Pass: 1 used, 1 reserved, 1 free", counts(ev) == (3, 1, 1, 1), str(counts(ev)))
check("extra-platform links alone do not mean used",
      slot(ev, 2)["status"] == "reserved" and platforms(slot(ev, 2)) == ["instagram"])
check("quota notes survive", slot(ev, 2)["note"] == "ใช้โควต้าของ Falles")

print("layout C — merged page name, Post n/6, STATUS")
c = parse_workbook(layout_c())
check("tracker sheet sets the order; hidden sheet skipped",
      [p["page"] for p in c["packs"]] == ["Sale Here", "ปันโปร"])
sh, pp = pack(c, "Sale Here"), pack(c, "ปันโปร")
check("Sale Here: 6 from \"/6\", 2 used, 1 reserved, 3 free", counts(sh) == (6, 2, 1, 3), str(counts(sh)))
check("STATUS Post without a link is used", slot(sh, 2)["status"] == "used")
check("other statuses are shown as written", slot(sh, 3)["status_text"] == "Wait idea")
check("ปันโปร: timeline duplicate dropped", counts(pp) == (6, 1, 0, 5), str(counts(pp)))
check("the kept row is the tracker's", slot(pp, 1)["campaign"] == "Zilk & Cellox Facial")

print("layout D — bare numbers, Published, stale summary box")
d = parse_workbook(layout_d())
p = d["packs"][0]
check("page is the sheet name", p["page"] == "ชี้เป้าเซเว่น")
check("counted from rows, not the summary box", counts(p) == (4, 2, 0, 2), str(counts(p)))
check("empty FB/IG/X template is not a link", slot(p, 3)["links"] == [] and slot(p, 3)["status"] == "free")
check("totals add up", totals(d) == {"pack_count": 1, "quota": 4, "used": 2, "reserved": 0, "free": 2})

print("money stays out")
blob = json.dumps([a, b, c, d], ensure_ascii=False)
check("no budget figures or payment notes",
      not any(x in blob for x in ("15000", "48000", "262500", "Rate Card", "ออก PO", "แบ่งทำจ่าย")))

print("unreadable files")
for label, raw in (("not a workbook", b"<html>login</html>"),
                   ("a workbook with no quota table", xlsx(Workbook()))):
    try:
        parse_workbook(raw)
        check(f"{label} is refused", False)
    except ValueError:
        check(f"{label} is refused", True)

# ------------------------------------------------------------------- API ----
data = pathlib.Path.home() / ".local/share/kol-pgdata"
pgserver.get_server(data)
sock = str(data)
admin = sa.create_engine(f"postgresql://postgres:@/postgres?host={sock}",
                         isolation_level="AUTOCOMMIT")
with admin.connect() as conn:
    conn.exec_driver_sql("DROP DATABASE IF EXISTS promotest")
    conn.exec_driver_sql("CREATE DATABASE promotest")
os.environ["DATABASE_URL"] = f"postgresql://postgres:@/promotest?host={sock}"

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
command.upgrade(Config(str(ROOT / "alembic.ini")), "head")

from fastapi.testclient import TestClient  # noqa: E402

import app.api.promo as promo  # noqa: E402
import app.auth as auth  # noqa: E402
from app.main import app  # noqa: E402

FILES = {"https://sheets.test/b": layout_b(), "https://sheets.test/d": layout_d(),
         "https://sheets.test/done": layout_d(all_used=True)}
DOWN = set()
FETCHED = []


def fake_fetch(url):
    FETCHED.append(url)
    if url in DOWN or url not in FILES:
        raise ValueError("เปิดไฟล์ไม่ได้")
    return FILES[url]


promo.fetch_sheet = fake_fetch
promo._creator_info = lambda authorization: ("ผู้ทดสอบ", None)
auth.validate_token = lambda token: token == "good"

client = TestClient(app)
H = {"Authorization": "Bearer good"}

print("API — login required")
for method, path in (("get", "/api/promo/campaigns"), ("get", "/api/promo/campaigns/1"),
                     ("post", "/api/promo/sync"), ("post", "/api/promo/campaigns/1/sync"),
                     ("delete", "/api/promo/campaigns/1")):
    r = getattr(client, method)(path)
    check(f"{method.upper()} {path} → 401 without a session", r.status_code == 401, str(r.status_code))

print("API — register, read, re-read")
r = client.post("/api/promo/campaigns", headers=H,
                json={"name": " Lion Beauty 2026 ", "team": "BAM / Haru", "sheet_url": "https://sheets.test/b"})
lion = r.json()
check("create reads the sheet at once", r.status_code == 200 and lion["quota"] == 5 and lion["used"] == 3,
      r.text[:200])
check("name trimmed, creator recorded", lion["name"] == "Lion Beauty 2026" and lion["created_by"] == "ผู้ทดสอบ")
check("a deal with quota left is not complete", lion["complete"] is False)

r = client.post("/api/promo/campaigns", headers=H,
                json={"name": "Salz", "team": "Jean", "sheet_url": "https://sheets.test/private"})
salz = r.json()
check("an unreadable sheet still registers, with the reason",
      r.status_code == 200 and salz["quota"] == 0 and salz["sync_error"] and salz["synced_at"] is None)
check("a deal that never read is not complete", salz["complete"] is False)

check("blank name refused", client.post("/api/promo/campaigns", headers=H,
      json={"name": " ", "sheet_url": "https://sheets.test/b"}).status_code == 400)
check("non-link refused", client.post("/api/promo/campaigns", headers=H,
      json={"name": "x", "sheet_url": "sheet.xlsx"}).status_code == 400)

lst = client.get("/api/promo/campaigns", headers=H).json()["campaigns"]
check("list has both, oldest first", [x["name"] for x in lst] == ["Lion Beauty 2026", "Salz"])
check("list rows carry per-page counts but no slots",
      lst[0]["packs"][0] == {"page": "Sale Here", "expiry": "31 Dec 2026", "quota": 2,
                             "used": 2, "reserved": 0, "free": 0})
det = client.get(f"/api/promo/campaigns/{lion['id']}", headers=H).json()
check("detail carries slots and links", det["packs"][0]["slots"][0]["links"][0]["platform"] == "facebook")

FETCHED.clear()
r = client.post("/api/promo/sync", headers=H, json={"stale_minutes": 30}).json()
check("stale-only sync re-reads just the one that never read",
      r["synced"] == 1 and FETCHED == ["https://sheets.test/private"], str(FETCHED))
FETCHED.clear()
r = client.post("/api/promo/sync", headers=H, json={}).json()
check("sync-all re-reads every deal", r["synced"] == 2 and len(FETCHED) == 2)

r = client.patch(f"/api/promo/campaigns/{salz['id']}", headers=H,
                 json={"sheet_url": "https://sheets.test/d", "team": "Jean / nut"}).json()
check("fixing the link reads the new file", r["quota"] == 4 and r["used"] == 2 and r["sync_error"] is None)
check("team updated", r["team"] == "Jean / nut")

DOWN.add("https://sheets.test/d")
r = client.post(f"/api/promo/campaigns/{salz['id']}/sync", headers=H).json()
check("a failed re-read keeps the last good numbers", r["quota"] == 4 and r["used"] == 2)
check("…and says why", bool(r["sync_error"]))
DOWN.clear()
r = client.post(f"/api/promo/campaigns/{salz['id']}/sync", headers=H).json()
check("the next good read clears the warning", r["sync_error"] is None)

r = client.post("/api/promo/campaigns", headers=H,
                json={"name": "จบแล้ว", "sheet_url": "https://sheets.test/done"}).json()
check("every post used → complete", r["complete"] is True and r["quota"] == 2 and r["free"] == 0)

r = client.delete(f"/api/promo/campaigns/{r['id']}", headers=H)
check("remove hides the deal", r.status_code == 200
      and len(client.get("/api/promo/campaigns", headers=H).json()["campaigns"]) == 2)
check("removed deal is gone from detail",
      client.get(f"/api/promo/campaigns/{r.json()['id']}", headers=H).status_code == 404)

print()
if FAILS:
    print(f"FAIL: {len(FAILS)} check(s) failed")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("OK: all promo checks passed")
