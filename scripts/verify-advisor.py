#!/usr/bin/env python3
"""Advisor end-to-end on a throwaway local Postgres (spec v2: grades).

LOCAL-ONLY dev check (needs the embedded pgserver, like scripts/dev_db.py):

    .venv/bin/python scripts/verify-advisor.py

Covers: the v2 grading prompt and input assembly (sold KPIs, boost budget,
channel history medians from our own past campaigns, hidden-likes null), the
run billing itself from the response's actual token usage into the advisor
cost line, storage + auth (401 without a session), and the leak checks
(no selling price on any open surface).
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
with admin.connect() as c:
    c.exec_driver_sql("DROP DATABASE IF EXISTS advtest")
    c.exec_driver_sql("CREATE DATABASE advtest")
os.environ["DATABASE_URL"] = f"postgresql://postgres:@/advtest?host={sock}"

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
command.upgrade(Config(str(ROOT / "alembic.ini")), "head")

VID_LINKS = json.dumps([
    {"platform": "tiktok", "url": "https://www.tiktok.com/@vidkol/video/1",
     "handle": "vidkol"},
    {"platform": "tiktok", "url": "https://www.tiktok.com/@vidkol",
     "handle": "vidkol"},
])

eng = sa.create_engine(os.environ["DATABASE_URL"])
with eng.begin() as c:
    c.execute(sa.text(
        "insert into campaigns (key, name, emoji, active, view_token) values "
        "('dm','Dutch Mill','🥛',true,'Tok111222333'), ('old','Old','📊',true,NULL)"))
    c.execute(sa.text(
        "insert into report_kols (username, display, content_group, campaign, "
        "followers, active, sort_order, cost_thb, boost_thb, kpi_json, links_json) "
        "values ('vidkol','Vid','Influ','dm',150000,true,0,30000,5000,:k,:v), "
        "('waitkol','Wait','Influ','dm',9000,true,1,NULL,NULL,NULL,NULL)"),
        {"k": json.dumps([{"metric": "views", "target": 100000}]), "v": VID_LINKS})
    c.execute(sa.text(
        "insert into report_group_kpis (campaign, group_name, kpi_json) "
        "values ('dm','Influ',:g)"),
        {"g": json.dumps([{"metric": "views", "target": 500000}])})
    c.execute(sa.text(
        "insert into report_posts (campaign, username, platform, video_id, url, "
        "views, likes, comments, shares, saves, posted_at) values "
        "('dm','vidkol','tiktok','dm_t_1','https://www.tiktok.com/@vidkol/video/1',"
        " 63700,79,1,1,1,'2026-08-02'), "
        "('dm','vidkol','facebook','dm_f_1','https://www.facebook.com/vidkol/posts/7',"
        " 0,15000,300,1500,0,'2026-08-02'), "
        "('old','vidkol','tiktok','old_t_1','https://www.tiktok.com/@vidkol/video/9',"
        " 40000,300,10,5,20,'2026-05-01'), "
        "('old','vidkol','tiktok','old_t_2','https://www.tiktok.com/@vidkol/video/8',"
        " 60000,500,20,10,30,'2026-05-08')"))
eng.dispose()

import app.auth as auth_mod  # noqa: E402
auth_mod.validate_token = lambda tok: tok == "t"

captured: dict = {}
CANNED = {"campaign_summary": "ทดสอบ", "posted_count": 1, "pending_count": 1,
          "median_er_by_platform": {"TikTok": 0.13},
          "posts": [{"handle": "@vidkol", "platform": "TikTok",
                     "grade": "ON_TRACK", "boost": False,
                     "reason": "views 63.7K = 64% ของ KPI 100K"}]}
import app.tiein as tiein_mod  # noqa: E402

# ---- fake the channel-page scrapes (ฟอร์มช่อง) ------------------------------
# vidkol posted on TikTok + Facebook. TikTok returns 3 clips, one of which is
# the tracked campaign post (dm_t_1) and must be EXCLUDED from the baseline;
# the organic two give median views 20000, engagement [230, 430] -> 330.
import app.channel_form as chform_mod  # noqa: E402

chform_calls = {"tiktok": 0, "fb": 0}


def fake_channel_tiktok(usernames, per=10, **kw):
    chform_calls["tiktok"] += 1
    items = [
        {"input": "vidkol", "id": "dm_t_1", "playCount": 999999,
         "diggCount": 9, "commentCount": 9, "shareCount": 9, "collectCount": 9,
         "webVideoUrl": "https://www.tiktok.com/@vidkol/video/1"},
        {"input": "vidkol", "id": "org_1", "playCount": 30000, "diggCount": 400,
         "commentCount": 10, "shareCount": 15, "collectCount": 5,
         "webVideoUrl": "https://www.tiktok.com/@vidkol/video/501"},
        {"input": "vidkol", "id": "org_2", "playCount": 10000, "diggCount": 200,
         "commentCount": 10, "shareCount": 10, "collectCount": 10,
         "webVideoUrl": "https://www.tiktok.com/@vidkol/video/502"},
    ]
    return items, {"cost_usd": 0.037}


def fake_channel_fb(page_url, per=10, **kw):
    chform_calls["fb"] += 1
    assert page_url == "https://www.facebook.com/vidkol", page_url
    return [], {"cost_usd": 0.001}


chform_mod.run_scrape_channel_tiktok = fake_channel_tiktok
chform_mod.run_scrape_channel_fb = fake_channel_fb


def fake_claude(content, max_tokens=1500, model=None, with_usage=False):
    captured["prompt"] = content[0]["text"]
    captured["model"] = model
    text = "```json\n" + json.dumps(CANNED, ensure_ascii=False) + "\n```"
    return (text, {"input_tokens": 8000, "output_tokens": 3000}) if with_usage else text


tiein_mod._claude = fake_claude

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app.advisor import run_advisor  # noqa: E402

cl = TestClient(app)
H = {"Authorization": "Bearer t"}
fails = []


def check(cond, msg):
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        fails.append(msg)


print("-- advisor run (spec v2: grades) --")
out = run_advisor("dm")
check(out.get("status") == "success", f"run: {out}")
check(captured.get("model") == "claude-opus-5", f"model: {captured.get('model')}")
check("ABOVE" in captured["prompt"] and "TOO_EARLY" in captured["prompt"],
      "v2 grading prompt in use")
rows = json.loads(captured["prompt"].split("ข้อมูลรายโพสต์:\n", 1)[1])
vrow = next(r for r in rows if r["handle"] == "@vidkol" and r["platform"] == "TikTok")
check(vrow["kpis"] == [{"metric": "views", "target": 100000}],
      f"sold KPI reaches the model: {vrow['kpis']}")
check(vrow["boost_thb"] == 5000.0, "boost budget reaches the model")
check(vrow["prior_history"] == {"posts": 2, "median_views": 50000,
                                "median_engagement": 447},
      f"channel history = medians of OUR past campaigns: {vrow['prior_history']}")

# ฟอร์มช่อง (channel form): fetched as step 0 of the run — one TikTok batch,
# one FB page — with OUR tracked campaign clip excluded from the sample.
check(chform_calls == {"tiktok": 1, "fb": 1},
      f"channel pages fetched once per platform: {chform_calls}")
check(vrow["channel_recent"] == {"posts": 2, "median_views": 20000,
                                 "median_engagement": 330, "median_er_pct": 1.87},
      f"channel form reaches the model, campaign clip excluded: {vrow['channel_recent']}")
check("เทียบฟอร์มช่องตัวเอง" in captured["prompt"],
      "prompt ranks the channel's own form as a comparator")

# Facebook post with no view count → graded on the engagement basis, never
# dumped into TOO_EARLY (Kirei Kirei feedback, 2026-09-01).
frow = next(r for r in rows if r["platform"] == "Facebook")
check(frow["views"] == 0 and frow["er_method"] == "followers"
      and frow["er_pct"] == 11.2,
      f"no-views post gets follower-based ER: {frow['er_pct']}/{frow['er_method']}")
check(frow["er_follow_pct"] == 11.2 and vrow["er_follow_pct"] == 0.05,
      "er_follow_pct on EVERY post — same-basis comparator across platforms")
check("ห้ามให้ TOO_EARLY เพียงเพราะไม่มี views" in captured["prompt"],
      "prompt forbids parking no-views posts in TOO_EARLY")

print("\n-- storage, billing, auth --")
r = cl.get("/api/report/advisor?campaign=dm", headers=H)
j = r.json()
check(r.status_code == 200 and j["is_set"]
      and j["result"]["posts"][0]["grade"] == "ON_TRACK",
      f"stored v2 result served: {r.text[:90]}")
r = cl.get("/api/report/data", params={"campaign": "dm"})
adv = (r.json().get("cost_by_kind") or {}).get("advisor") or {}
check(adv.get("total") == 0.115 and adv.get("count") == 1,
      f"cost from real usage (8K in + 3K out on Opus = $0.115): {adv}")
cf = (r.json().get("cost_by_kind") or {}).get("chform") or {}
check(cf.get("total") == 0.038 and cf.get("count") == 1,
      f"channel-form Apify spend on its own cost line: {cf}")
recs_json = json.dumps(r.json()["records"])
check("30000" not in recs_json and '"cost' not in recs_json
      and '"boost' not in recs_json and '"kpis"' not in recs_json,
      "no money fields in open records")
check(cl.get("/api/report/advisor?campaign=dm").status_code == 401,
      "advisor without login → 401 (campaign keys are guessable)")

# The client LINK shows the full commercial picture + the stored analysis
# (team decision 2026-09-01) — token-addressed, no session needed.
r = cl.get("/api/view/Tok111222333/advisor")
check(r.status_code == 200 and r.json()["result"]["posts"][0]["grade"] == "ON_TRACK",
      "client link reads the stored analysis by token")
r = cl.get("/api/view/Tok111222333/commercial")
j = r.json()
check(r.status_code == 200
      and j["kols"]["vidkol"] == {"cost_thb": 30000.0, "boost_thb": 5000.0,
                                  "kpis": [{"metric": "views", "target": 100000}]}
      and "waitkol" not in j["kols"]
      and j["group_kpis"] == {"Influ": [{"metric": "views", "target": 500000}]},
      f"client link reads KPI/price/boost + group KPIs by token: {r.text[:120]}")
check(cl.get("/api/view/WRONGTOKEN00/advisor").status_code == 404
      and cl.get("/api/view/WRONGTOKEN00/commercial").status_code == 404,
      "wrong token → 404, nothing served")

print("\n-- channel-form cache --")
out2 = run_advisor("dm")
check(out2.get("status") == "success"
      and chform_calls == {"tiktok": 1, "fb": 1},
      f"second run within 30 days scrapes NOTHING (cache): {chform_calls}")

from app.db import engine as app_engine  # noqa: E402
app_engine.dispose()
with admin.connect() as c:
    c.exec_driver_sql("DROP DATABASE IF EXISTS advtest")
print()
if fails:
    print(f"❌ {len(fails)} check(s) failed")
    sys.exit(1)
print("✅ all advisor checks passed")
