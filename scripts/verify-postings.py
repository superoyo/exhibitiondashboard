#!/usr/bin/env python3
"""One account, several sold postings — import, report rows, money, on a
throwaway local Postgres.

LOCAL-ONLY dev check (needs the embedded pgserver, like verify-advisor.py):

    .venv/bin/python scripts/verify-postings.py

A promotion page is often bought for several posts in one campaign, one sheet
row each, and the sheet numbers them ("โพสต์ที่ 7", "โพสต์ที่ 8"). This pins
what the report does with that: the page stays one roster row, and each
posting that has been posted becomes its own block with ITS links, ITS stats
and ITS boost budget.

Just as firmly pinned: NOTHING ELSE CHANGES. A KOL who merely appears on two
rows — a plan row and a links row, which is how most sheets look — is one job
in one block, exactly as before. Splitting on repetition alone once tore every
such report into "ครั้งที่ 1 / ครั้งที่ 2" (Kewpie, 2026-11-19). And none of
the money reaches the open report endpoint.
"""
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import pgserver  # noqa: E402
import sqlalchemy as sa  # noqa: E402

data = pathlib.Path.home() / ".local/share/kol-pgdata"
pgserver.get_server(data)
sock = str(data)
admin = sa.create_engine(f"postgresql://postgres:@/postgres?host={sock}",
                         isolation_level="AUTOCOMMIT")
with admin.connect() as conn:
    conn.exec_driver_sql("DROP DATABASE IF EXISTS posttest")
    conn.exec_driver_sql("CREATE DATABASE posttest")
os.environ["DATABASE_URL"] = f"postgresql://postgres:@/posttest?host={sock}"

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
command.upgrade(Config(str(ROOT / "alembic.ini")), "head")

from fastapi.testclient import TestClient  # noqa: E402

import app.auth as auth  # noqa: E402
from app.db import session_scope  # noqa: E402
from app.main import app  # noqa: E402
from app.models import ReportKol, ReportPost  # noqa: E402
from app.report_refresh import kol_links, link_vid  # noqa: E402

auth.validate_token = lambda token: token == "good"
client = TestClient(app)
H = {"Authorization": "Bearer good"}
FAILS = []


def check(name, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'} {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


eng = sa.create_engine(os.environ["DATABASE_URL"])
with eng.begin() as conn:
    conn.execute(sa.text(
        "insert into campaigns (key, name, emoji, active, view_token) "
        "values ('lb','Lion Beauty','🚿',true,'TokPOST12345')"))

FB_A = "https://www.facebook.com/788494752840719/posts/1721833052840213"
IG_A = "https://www.instagram.com/p/DegbapqoFUs/"
X_A = "https://x.com/punpromotion/status/2110635207863009754"
FB_B = "https://www.facebook.com/788494752840719/posts/1742038520819666"
IG_B = "https://www.instagram.com/p/DfoJt3jkr1n/"
FB_S = "https://www.facebook.com/salehere/posts/100200300"
TT_1 = "https://www.tiktok.com/@solo/video/7300000000000000001"
TT_2 = "https://www.tiktok.com/@solo/video/7300000000000000002"
TT_3 = "https://www.tiktok.com/@refone/video/7300000000000000003"
TT_4 = "https://www.tiktok.com/@reftwo/video/7300000000000000004"
FB_E = "https://www.facebook.com/early/posts/555000111"
FB_1 = "https://www.facebook.com/samebrand/posts/111000111"
FB_2 = "https://www.facebook.com/samebrand/posts/333000444"


def link(platform, url, handle):
    return {"platform": platform, "url": url, "handle": handle}


SHEET = [
    # a page the sheet numbers as three postings: two posted, one still to come
    {"username": "punpromotion", "display": "ปันโปร", "group": "KOL", "boost_thb": 10000,
     "kpis": [{"metric": "views", "target": 100000}],
     "post_no": "โพสต์ที่ 7", "post_label": "โพสต์ที่ 7 · Falles",
     "links": [link("facebook", FB_A, "punpromotion"), link("instagram", IG_A, "punpromotion"),
               link("x", X_A + "?s=46", "punpromotion")]},
    {"username": "salehere", "display": "Sale Here", "group": "KOL", "boost_thb": 10000,
     "post_no": "โพสต์ที่ 6", "post_label": "โพสต์ที่ 6 · Falles",
     "links": [link("facebook", FB_S, "salehere")]},
    {"username": "punpromotion", "display": "ปันโปร", "group": "KOL", "boost_thb": 12000,
     "kpis": [{"metric": "views", "target": 50000}],
     "post_no": "โพสต์ที่ 8", "post_label": "โพสต์ที่ 8 · Q'Lean",
     "links": [link("facebook", FB_B, "punpromotion"), link("instagram", IG_B, "punpromotion")]},
    {"username": "punpromotion", "display": "ปันโปร", "group": "KOL",
     "post_no": "โพสต์ที่ 9", "post_label": "โพสต์ที่ 9 · Falles Herbal Shampoo", "links": []},
    # two links on ONE row
    {"username": "solo", "display": "Solo", "group": "KOL", "cost_thb": 5000,
     "links": [link("tiktok", TT_1, "solo"), link("tiktok", TT_2, "solo")]},
    # the usual sheet: a plan row with the money, and a second row with links.
    # No posting numbers anywhere — this is ONE job.
    {"username": "kewpie", "display": "KEWPIE KOL", "group": "Review", "cost_thb": 45000,
     "boost_thb": 20000, "kpis": [{"metric": "reach", "target": 600000}], "links": []},
    {"username": "kewpie", "display": "kewpie", "group": "Brief", "boost_thb": 999,
     "links": [link("tiktok", TT_3, "kewpie"), link("tiktok", TT_4, "kewpie")]},
    # numbered postings, but only one of them posted so far
    {"username": "early", "display": "Early", "group": "KOL", "boost_thb": 7000,
     "post_no": "โพสต์ที่ 1", "post_label": "โพสต์ที่ 1 · A",
     "links": [link("facebook", FB_E, "early")]},
    {"username": "early", "display": "Early", "group": "KOL",
     "post_no": "โพสต์ที่ 2", "post_label": "โพสต์ที่ 2 · B", "links": []},
    # the same brand written on both rows is not a posting number
    {"username": "samebrand", "display": "Same", "group": "KOL", "post_label": "Falles",
     "links": [link("facebook", FB_1, "samebrand")]},
    {"username": "samebrand", "display": "Same", "group": "KOL", "post_label": "Falles",
     "links": [link("facebook", FB_2, "samebrand")]},
]

print("import")
check("import needs a login",
      client.post("/api/roster/report/bulk?campaign=lb", json={"kols": SHEET}).status_code == 401)
r = client.post("/api/roster/report/bulk?campaign=lb", headers=H, json={"kols": SHEET})
check("six accounts from eleven rows", r.status_code == 200 and r.json()["count"] == 6, r.text[:200])

# What a refresh stores: one post per link, keyed by that link. X is stored
# under its canonical URL (no ?s=46), as refresh persists it.
STATS = {("punpromotion", "facebook", FB_A): 987, ("punpromotion", "instagram", IG_A): 153,
         ("punpromotion", "x", X_A): 1321, ("punpromotion", "facebook", FB_B): 444,
         ("punpromotion", "instagram", IG_B): 55, ("salehere", "facebook", FB_S): 825,
         ("solo", "tiktok", TT_1): 9000, ("solo", "tiktok", TT_2): 300,
         ("kewpie", "tiktok", TT_3): 2500, ("kewpie", "tiktok", TT_4): 80,
         ("early", "facebook", FB_E): 61,
         ("samebrand", "facebook", FB_1): 10, ("samebrand", "facebook", FB_2): 20}
with session_scope() as session:
    for (user, plat, url), likes in STATS.items():
        session.add(ReportPost(
            campaign="lb", username=user, platform=plat,
            video_id=link_vid("lb", user, plat, url), url=url,
            views=likes * 10 if plat in ("tiktok", "x") else 0, likes=likes,
            comments=1, shares=2, saves=0))

print("report rows")
resp = client.get("/api/report/data?campaign=lb")  # the OPEN endpoint
rows = resp.json()["records"]


def block(user, slot):
    return [x for x in rows if x["username"] == user and x["slot"] == slot]


pun = [x for x in rows if x["username"] == "punpromotion"]
check("the page is one block per POSTED posting", sorted({x["slot"] for x in pun}) == [1, 2]
      and all(x["slot_count"] == 2 for x in pun))
check("the blocks carry no posting label — stats split, nothing else",
      "slot_label" not in resp.text and "โพสต์ที่" not in resp.text)
check("posting 1 has its own three links",
      [(x["platform"], x["likes"]) for x in block("punpromotion", 1)]
      == [("facebook", 987), ("instagram", 153), ("x", 1321)],
      str([(x["platform"], x["likes"]) for x in block("punpromotion", 1)]))
check("posting 2 shows ITS stats, not posting 1's again",
      [(x["platform"], x["likes"]) for x in block("punpromotion", 2)]
      == [("facebook", 444), ("instagram", 55)])
check("the posting still to come adds no row", len(pun) == 5)
check("the sheet's ?s=46 spelling still finds the stored X post",
      next(x for x in pun if x["platform"] == "x")["views"] == 13210)

print("everyone else is untouched")
sale = block("salehere", 1)
check("a one-row account is one unlabelled block",
      len(sale) == 1 and sale[0]["slot_count"] == 1)
kew = [x for x in rows if x["username"] == "kewpie"]
check("a KOL on two rows WITHOUT posting numbers is one job, one block",
      len(kew) == 2 and all(x["slot"] == 1 and x["slot_count"] == 1 for x in kew),
      str([(x["slot"], x["slot_count"]) for x in kew]))
check("…named by its first row", all(x["nickname"] == "KEWPIE KOL" and x["category"] == "Review"
                                     for x in kew))
check("…with the report's usual best-post-per-platform stats",
      [x["likes"] for x in kew] == [2500, 2500], str([x["likes"] for x in kew]))
solo = block("solo", 1)
check("two links on one row: one block, usual stats",
      [x["likes"] for x in solo] == [9000, 9000] and all(x["slot_count"] == 1 for x in solo))
early = [x for x in rows if x["username"] == "early"]
check("numbered postings with only ONE posted stay an ordinary block",
      len(early) == 1 and early[0]["slot_count"] == 1)
same = [x for x in rows if x["username"] == "samebrand"]
check("a repeated brand name is not a posting number",
      len(same) == 2 and all(x["slot_count"] == 1 for x in same))
blob = resp.text
# (cost_total / cost_by_kind on this payload are the Apify bill, by design)
leaked = [x for x in ("boost", "cost_thb", "cost_note", "kpi", "postings",
                      "45000", "12000", "22000", "600000") if x in blob]
check("no selling price, boost or KPI on the open endpoint", not leaked, str(leaked))

print("money per posting")
roster = {k["username"]: k for k in client.get("/api/roster/report?campaign=lb", headers=H).json()["kols"]}
p = roster["punpromotion"]
check("account total is the SUM of its postings", p["boost_thb"] == 22000.0, str(p["boost_thb"]))
check("KPI total is summed per unit", p["kpis"] == [{"metric": "views", "target": 150000}])
check("each posting keeps its own boost and KPI",
      [(x["slot"], x["boost_thb"]) for x in p["postings"]] == [(1, 10000.0), (2, 12000.0), (3, None)]
      and p["postings"][1]["kpis"] == [{"metric": "views", "target": 50000}])
check("one-row accounts carry no postings", roster["salehere"]["postings"] == []
      and roster["salehere"]["boost_thb"] == 10000.0 and roster["solo"]["cost_thb"] == 5000.0)
kw = roster["kewpie"]
check("an unnumbered two-row KOL keeps the FIRST row's money, as before",
      kw["postings"] == [] and kw["cost_thb"] == 45000.0 and kw["boost_thb"] == 20000.0
      and kw["kpis"] == [{"metric": "reach", "target": 600000}], json.dumps(kw, ensure_ascii=False)[:200])
view = client.get("/api/view/TokPOST12345/commercial").json()["kols"]
check("the client link gets the same per-posting figures",
      [x["boost_thb"] for x in view["punpromotion"]["postings"]] == [10000.0, 12000.0, None])

print("postings survive what touches the links")
with session_scope() as session:
    k = session.scalar(sa.select(ReportKol).where(ReportKol.campaign == "lb",
                                                  ReportKol.username == "punpromotion"))
    # refresh writes kol_links() back into links_json
    k.links_json = json.dumps(kol_links(k), ensure_ascii=False)
    pun_id = k.id
rows = client.get("/api/report/data?campaign=lb").json()["records"]
check("a refresh keeps the blocks apart",
      [len(block("punpromotion", n)) for n in (1, 2)] == [3, 2])

r = client.patch(f"/api/roster/report/{pun_id}", headers=H, json={"links": [
    {"url": FB_A}, {"url": IG_A}, {"url": X_A}, {"url": FB_B}, {"url": IG_B}]})
rows = client.get("/api/report/data?campaign=lb").json()["records"]
check("editing the links by hand keeps each link in its posting",
      r.status_code == 200 and [len(block("punpromotion", n)) for n in (1, 2)] == [3, 2],
      str([len(block("punpromotion", n)) for n in (1, 2)]))

print("rosters already in the database")
with eng.begin() as conn:
    conn.execute(sa.text(
        "insert into campaigns (key, name, emoji, active) values ('old','Old','📊',true)"))
    conn.execute(sa.text(
        "insert into report_kols (username, display, content_group, campaign, followers, "
        "active, sort_order, links_json, postings_json) values "
        "('merged','Merged','KOL','old',0,true,0,:two,NULL), "
        "('single','Single','KOL','old',0,true,1,:one,NULL), "
        "('v134','V134','KOL','old',0,true,2,:tagged,:unlabelled)"),
        {"two": json.dumps([link("facebook", FB_A, "merged"), link("facebook", FB_B, "merged")]),
         "one": json.dumps([link("tiktok", TT_1, "single")]),
         # what the short-lived v134 import stored for an unnumbered two-row KOL
         "tagged": json.dumps([{**link("tiktok", TT_3, "v134"), "slot": 2},
                               {**link("tiktok", TT_4, "v134"), "slot": 2}]),
         "unlabelled": json.dumps([{"slot": 1, "label": "", "cost_thb": 45000.0},
                                   {"slot": 2, "label": ""}])})
with session_scope() as session:
    for user, url, likes in (("merged", FB_A, 987), ("merged", FB_B, 444),
                             ("v134", TT_3, 2500), ("v134", TT_4, 80)):
        plat = "facebook" if "facebook" in url else "tiktok"
        session.add(ReportPost(campaign="old", username=user, platform=plat,
                               video_id=link_vid("old", user, plat, url), url=url,
                               views=0, likes=likes, comments=0, shares=0, saves=0))
    # a post stored under some older key: only findable as "its platform's post"
    session.add(ReportPost(campaign="old", username="single", platform="tiktok",
                           video_id="old_legacy_key", url="https://vt.tiktok.com/ZSabc/",
                           views=7777, likes=70, comments=0, shares=0, saves=0))
rows = client.get("/api/report/data?campaign=old").json()["records"]
merged = [x for x in rows if x["username"] == "merged"]
check("an old merged roster looks exactly as it did",
      [x["likes"] for x in merged] == [987, 987]
      and all(x["slot"] == 1 and x["slot_count"] == 1 for x in merged),
      str([x["likes"] for x in merged]))
check("a lone link still finds its platform's post",
      next(x for x in rows if x["username"] == "single")["views"] == 7777)
v134 = [x for x in rows if x["username"] == "v134"]
check("postings stored WITHOUT numbers are read as one job",
      len(v134) == 2 and all(x["slot"] == 1 and x["slot_count"] == 1 for x in v134)
      and [x["likes"] for x in v134] == [2500, 2500], str([(x["slot"], x["likes"]) for x in v134]))

print()
if FAILS:
    print(f"FAIL: {len(FAILS)} check(s) failed")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("OK: all posting checks passed")
