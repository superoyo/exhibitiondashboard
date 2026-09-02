"""Campaign performance advisor — the team's own analyst prompt, run on demand.

One Claude call per press: the campaign's per-post numbers go in as JSON, and a
GRADE per posted post comes back. v2 of the spec (2026-08-27): the team judged
v1's verdict-plus-talking-point output "กว้างและเยอะไป" — the current spec is
numbers-only, one line per post, four grades anchored to the sold target
(ABOVE / ON_TRACK / BELOW / TOO_EARLY) plus a boost flag. New inputs since v1:
each KOL's sold KPIs, boost budget, and their prior-campaign history from OUR
OWN database (the only "other posts of the channel" the system truthfully
knows — stated as such rather than pretending to see the whole channel).

Results are stored (AppSetting advisor:<campaign>) so opening the report shows
the last analysis with its timestamp instead of silently re-billing AI. Boost
advice goes stale in days, so the panel shows WHEN it was generated and re-runs
only on an explicit press.

Exposure: everything here rides on authenticated endpoints only. The input
includes each KOL's selling price (for CPV/CPE in internal notes), which must
never reach the client link — same rule as the roster's commercial fields.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import re
from typing import Optional

from sqlalchemy import select

from app import config
from app.db import session_scope
from app.models import ReportKol, ReportPost
from app.report_refresh import _redact, state_for

log = logging.getLogger("advisor")

# Opus, at the team's explicit call (2026-08: "เอาเป็น Opus ไปเลย มันไม่ได้แพง"):
# one judgment-heavy call per press over the whole campaign, and the quality of
# the verdicts IS the product. ~5-12฿ per press vs Sonnet's ~2-5฿ — the delta is
# smaller than a single comment-analysis run. Thinking stays on (the model's
# default); max_tokens covers it.
ADVISOR_MODEL: str = os.getenv("ADVISOR_MODEL", "claude-opus-5")
ADVISOR_MAX_TOKENS = 20000

# First-party API rates, USD per MILLION tokens (input, output) — used to turn
# the response's actual usage counts into a recorded cost, so the report's
# spend table finally shows an AI line instead of "ไม่ขึ้นในตาราง". Output
# includes thinking tokens. Unknown model -> no line rather than a wrong one.
_PRICE_PER_MTOK = {
    "claude-opus-5": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
}


def _run_cost_usd(model: str, usage: dict) -> Optional[float]:
    rates = next((v for k, v in _PRICE_PER_MTOK.items() if model.startswith(k)), None)
    if not rates:
        return None
    cost = (usage.get("input_tokens") or 0) / 1e6 * rates[0] \
        + (usage.get("output_tokens") or 0) / 1e6 * rates[1]
    return round(cost, 4)

# Five rungs, matching apps/web/src/features/report/lib/tier.ts (Mid was merged
# into Macro at the team's request). If one side changes, change both.
def _tier(followers: int) -> Optional[str]:
    if not followers or followers <= 0:
        return None
    for floor, name in ((1_000_000, "Mega"), (100_000, "Macro"),
                        (10_000, "Micro"), (1_000, "Nano"), (1, "KOC")):
        if followers >= floor:
            return name
    return None


# ---------------------------------------------------------------------------
# The team's prompt, verbatim (drafted by the planning team, 2026-08).
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """คุณคือ Performance Analyst ของเอเจนซี่โฆษณา อ่านตัวเลขรายโพสต์ของแคมเปญ KOL แล้วให้คะแนน 1–10 ต่อโพสต์แบบกระชับที่สุด — ทีมต้องการตัวเลข ไม่ต้องการความเรียงความ

## ข้อมูลที่ได้รับ
JSON รายโพสต์: handle, platform, tier, followers, views, likes (null = แพลตฟอร์มซ่อนเลขไลก์), comments, shares, saves, er_pct, er_method ("views" หรือ "followers" สำหรับโพสต์ที่แพลตฟอร์มไม่เปิด views), er_follow_pct (engagement/followers — ฐานเดียวกันทุกโพสต์ทุกแพลตฟอร์ม), posted_date,
kpis = เป้าที่ขายของคนนั้น เช่น [{"metric":"impressions","target":700000}] (อาจว่าง),
boost_thb = งบบูสที่ขาย (อาจว่าง), cost = ค่าตัว (ใช้ชั่งใจภายใน ห้ามพิมพ์ก้อนเงินเต็มใน output),
cpm_sold_thb = เงินบูส ÷ KPI views × 1000 (CPM ที่ขาย) · cpm_actual_thb = เงินบูส ÷ views จริง × 1000 (CPM ที่ได้จริง) — คำนวณให้แล้ว null = ข้อมูลไม่ครบ,
channel_recent = ฟอร์มช่องจากคลิปล่าสุด ~10 คลิปบนหน้าช่องจริง (ไม่รวมคลิปงานของเรา) หรือ null · prior_history = สถิติงานจ้างเก่าของช่องนี้ในระบบเรา หรือ null — ทั้งคู่เป็นตัวเทียบสำรองเท่านั้น (ดูข้อ 4)

## วิธีตัดสิน (เรียงลำดับ)
1. หลักคือ Performance หน้าโพสต์เทียบ KPI ที่ขาย: metric "views" เทียบ views จริง · "interaction" เทียบ engagement จริง (likes+comments+shares+saves) · เมื่อวัดกับ KPI ได้แล้ว ให้จบที่ KPI — ห้ามเอา channel_recent/prior_history มาถ่วงคะแนนต่อ (มติทีม: เราไม่รู้ว่าคลิปอื่นของช่องตัวไหนมีบูส ตัวแปรไม่เท่ากัน เทียบกันไม่ได้)
2. "impressions"/"reach" วัดจากหน้าบ้านไม่ได้ — บอกสั้น ๆ แล้วใช้ค่ากลางแคมเปญแทน · คนไม่มี KPI ก็ใช้ค่ากลางแคมเปญ (median ต่อแพลตฟอร์ม ห้ามปน er_method ต่างชนิด — เทียบกันเองในแคมเปญยุติธรรม เพราะทุกโพสต์เป็นงานจ้างเงื่อนไขเดียวกัน)
3. โพสต์ที่แพลตฟอร์มไม่เปิด views (views = 0 เช่น Facebook): ตัดสินด้วย ER — เทียบ KPI interaction ถ้ามี ไม่มีก็เทียบ er_follow_pct กับ median er_follow_pct ของทั้งแคมเปญ · ระบุว่าเทียบฐานผู้ติดตาม · ห้ามงดให้คะแนนเพียงเพราะไม่มี views
4. channel_recent/prior_history ใช้เฉพาะเมื่อไม่มีทั้ง KPI และค่ากลางให้เทียบ (เช่น โพสต์เดียวบนแพลตฟอร์มเดียว) และต้องหมายเหตุว่าเป็นการเทียบหยาบ
5. CPM: เมื่อ cpm_sold_thb และ cpm_actual_thb มีค่า ให้เทียบเสมอและใส่ในเหตุผล — cpm_actual ต่ำกว่า cpm_sold = คุ้มกว่าที่ขาย (+) แพงกว่ามาก = ติดลบ (−) · เลข CPM เป็นเลขเงินที่อนุญาตให้พิมพ์ได้
6. โพสต์อายุน้อยกว่า 3 วัน → score เป็น null + เหตุผล "รอประเมิน" เสมอ อย่าเพิ่งตัดสิน (ใช้กับกรณีนี้เท่านั้น)
7. โพสต์ที่ likes เป็น null: engagement ขาดส่วนไลก์ — ระบุกำกับและอย่าเทียบ ER ตรง ๆ กับโพสต์ปกติ

## คะแนน (เต็ม 10 — จำนวนเต็มเท่านั้น)
คะแนนฐานจากอัตราส่วน R = ตัวเลขจริง ÷ เป้า/เกณฑ์หลัก:
10: R ≥ 1.5 · 9: 1.3–1.5 · 8: 1.15–1.3 · 7: 1.0–1.15 · 6: 0.85–1.0 · 5: 0.7–0.85 · 4: 0.55–0.7 · 3: 0.4–0.55 · 2: 0.25–0.4 · 1: < 0.25
แล้วปรับได้ไม่เกิน ±1: คุณภาพ engagement เด่น (ER สูงกว่าค่ากลางชัด หรือ save+share ≥ 15%) +1 · CPM จริงถูกกว่าที่ขายชัดเจน +1 · ER ต่ำผิดปกติหรือ CPM แพงกว่าที่ขายมาก −1 · รวมแล้วไม่ต่ำกว่า 1 ไม่เกิน 10
คะแนนต่ำ: ระบุตัวเลขตรง ๆ แต่ห้ามใช้ภาษาด้อยค่าครีเอเตอร์ (รายงานถึงมือลูกค้าและครีเอเตอร์ได้)

boost = true เมื่อครบทุกข้อ: ER ≥ 1.2× median แพลตฟอร์ม + (save+share)/engagement ≥ 15% + โพสต์อายุไม่เกิน 7 วัน · ห้าม true เมื่อ score ≤ 5 (เอาเงินไปขยายของที่ organic ไม่เวิร์ก = เผางบ)

## Output — JSON เท่านั้น ห้ามมีข้อความอื่น
{"campaign_summary": "ไม่เกิน 2 บรรทัด: ภาพรวม + สิ่งที่ควรทำตอนนี้",
 "posted_count": n, "pending_count": n,
 "median_er_by_platform": {"TikTok": x.x},
 "posts": [{"handle": "", "platform": "", "score": 1-10 หรือ null, "boost": false,
   "reason": "1 บรรทัด ต้องบอกว่าคิดจากปัจจัยอะไร เช่น 'คิดจาก: views 132% ของ KPI 100K · CPM จริง 78 ถูกกว่าที่ขาย 120 · ER 1.3× ค่ากลาง'"}]

## ห้ามเด็ดขาด
- แต่งตัวเลขหรือ metric ที่ไม่มีในข้อมูล (impressions จริงไม่มีในระบบ — มีแต่เป้า)
- reason เกิน 1 บรรทัดต่อโพสต์ และทุก reason ต้องขึ้นต้น "คิดจาก:"
- ก้อนเงินเต็ม (ค่าตัว/งบบูสเป็นบาท) โผล่ใน output — พิมพ์ได้เฉพาะเลข CPM
- แนะนำ boost โพสต์ที่ ER ต่ำกว่า median"""

FEW_SHOT = """ตัวอย่างรูปแบบที่ถูกต้อง (ข้อมูลสมมติ ใช้เทียบรูปแบบเท่านั้น):
{"campaign_summary": "ลงงาน 5/7 คน — คะแนนเฉลี่ย 6.5 มี 1 โพสต์เข้าเกณฑ์บูส ควรเสนอภายในสัปดาห์นี้ · อีก 2 คนรอคิวลงงาน",
 "posted_count": 5, "pending_count": 2,
 "median_er_by_platform": {"TikTok": 4.1},
 "posts": [
  {"handle": "@aooomtwp", "platform": "TikTok", "score": 10, "boost": true,
   "reason": "คิดจาก: views 173K = 173% ของ KPI 100K (ฐาน 9) · CPM จริง 46 ถูกกว่าที่ขาย 80 · save+share 21% (+1)"},
  {"handle": "@teenny.10", "platform": "TikTok", "score": 5, "boost": false,
   "reason": "คิดจาก: views 82% ของ KPI (ฐาน 6) · CPM จริง 130 แพงกว่าที่ขาย 95 (−1) · ER 0.9× ค่ากลาง"},
  {"handle": "@mewchi5", "platform": "TikTok", "score": 3, "boost": false,
   "reason": "คิดจาก: KPI เป็น Imp วัดหน้าบ้านไม่ได้ จึงเทียบค่ากลางแคมเปญ: views 0.45× median (ฐาน 3)"},
  {"handle": "@baanmali.kitchen", "platform": "Facebook", "score": 9, "boost": false,
   "reason": "คิดจาก: Facebook ไม่เปิด views จึงใช้ ER ฐานผู้ติดตาม 3.9% = 2.2× ค่ากลางแคมเปญ (1.8%) (ฐาน 10 ปรับ −1 เพราะไลก์กระจุกโพสต์เดียว)"},
  {"handle": "@sjpingg", "platform": "TikTok", "score": null, "boost": false,
   "reason": "คิดจาก: โพสต์อายุ 2 วัน ตัวเลขยังโต — รอประเมินหลัง 3 วัน"}]}
หมายเหตุ: ใส่เฉพาะโพสต์ที่ลงงานแล้วใน posts · คนที่ยังไม่ลงงานรวมใน pending_count"""


# ---------------------------------------------------------------------------
# input assembly
# ---------------------------------------------------------------------------

_PLAT_LABEL = {"tiktok": "TikTok", "facebook": "Facebook", "instagram": "Instagram",
               "youtube": "YouTube", "x": "X", "website": "Website"}


def _build_input(campaign: str) -> tuple[list, int]:
    """(per-post rows for the model, pending KOL count).

    Every post of every ACTIVE roster KOL — per POST, not best-per-platform,
    because boost advice is about a specific post. likes == -1 is the hidden-
    like sentinel and goes out as null, never as a negative engagement.
    """
    import statistics

    with session_scope() as session:
        roster = {k.username.lower(): k for k in session.scalars(
            select(ReportKol).where(ReportKol.active.is_(True),
                                    ReportKol.campaign == campaign)).all()}
        posts = [p for p in session.scalars(select(ReportPost).where(
            ReportPost.campaign == campaign)).all()
            if p.username.lower() in roster]

        # "งานเก่าของช่อง" as far as this system truthfully knows it: the same
        # handle's posts from OTHER campaigns in our own database. Summarised to
        # medians here rather than dumped raw — the model needs a baseline, not
        # a second campaign's worth of rows.
        history: dict = {}
        if roster:
            prior = session.scalars(select(ReportPost).where(
                ReportPost.campaign != campaign,
                ReportPost.username.in_(list(roster)))).all()
            by_user: dict = {}
            for pp in prior:
                if pp.views or pp.url:
                    by_user.setdefault(pp.username.lower(), []).append(pp)
            for u, rows_u in by_user.items():
                eng = [max(0, pp.likes or 0) + (pp.comments or 0)
                       + (pp.shares or 0) + (pp.saves or 0) for pp in rows_u]
                history[u] = {
                    "posts": len(rows_u),
                    "median_views": int(statistics.median([pp.views or 0 for pp in rows_u])),
                    "median_engagement": int(statistics.median(eng)),
                }

        # ฟอร์มช่อง: the channel's own recent organic posts, per platform —
        # cached by app/channel_form.py; run_advisor refreshes stale ones first.
        from app.channel_form import baselines_for
        channel = baselines_for(list(roster))

        rows = []
        posted_users = set()
        for p in posts:
            k = roster[p.username.lower()]
            kpis = json.loads(k.kpi_json) if k.kpi_json else []
            boost = float(k.boost_thb) if k.boost_thb is not None else None
            # CPM per the team's chosen base (2026-09-02): boost money only.
            # Precomputed here so the model compares, never does arithmetic.
            kpi_views = next((x.get("target") for x in kpis
                              if x.get("metric") == "views" and x.get("target")), None)
            cpm_sold = round(boost / kpi_views * 1000, 2) if boost and kpi_views else None
            cpm_actual = round(boost / p.views * 1000, 2) if boost and p.views else None
            likes = None if (p.likes or 0) < 0 else (p.likes or 0)
            engagement = ((likes or 0) + (p.comments or 0)
                          + (p.shares or 0) + (p.saves or 0))
            if p.views:
                er, method = round(100 * engagement / p.views, 2), "views"
            elif k.followers:
                er, method = round(100 * engagement / k.followers, 2), "followers"
            else:
                er, method = None, None
            if p.views or p.url:
                posted_users.add(p.username.lower())
            rows.append({
                "category": k.subgroup or k.content_group,
                "handle": f"@{k.username}",
                "platform": _PLAT_LABEL.get(p.platform or "", p.platform or ""),
                "followers": k.followers or 0,
                "tier": _tier(k.followers or 0),
                "views": p.views or 0,
                "likes": likes,           # null = Instagram hid the count
                "comments": p.comments or 0,
                "shares": p.shares or 0,
                "saves": p.saves or 0,
                "er_pct": er,
                "er_method": method,
                # Same basis for every post regardless of platform — the only
                # honest comparator for posts whose platform hides views.
                "er_follow_pct": (round(100 * engagement / k.followers, 2)
                                  if k.followers else None),
                "posted_date": p.posted_at.date().isoformat() if p.posted_at else None,
                "post_url": p.url,
                # sold targets + money — weighed in the scoring; only the CPM
                # figures may be echoed in the output, never the raw sums
                "kpis": kpis,
                "boost_thb": boost,
                "cost": float(k.cost_thb) if k.cost_thb is not None else None,
                "cpm_sold_thb": cpm_sold,
                "cpm_actual_thb": cpm_actual,
                "channel_recent": channel.get(
                    (p.username.lower(), (p.platform or "").lower())),
                "prior_history": history.get(p.username.lower()),
            })
        pending = len([u for u in roster if u not in posted_users])
        return rows, pending


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def run_advisor(campaign: str) -> dict:
    """Analyse one campaign and store the result. Never raises — progress and
    failure land in state_for('adv:'+campaign), like every other job."""
    st = state_for("adv:" + campaign)
    st.update(status="running", message="กำลังรวบรวมตัวเลขของแคมเปญ…",
              started_at=dt.datetime.now(config.TZ).isoformat(), finished_at=None,
              posts=0, total=0, cost_usd=None)
    try:
        # Step 0 — ฟอร์มช่อง: refresh stale channel baselines (30-day cache,
        # fixed 10-clip cap per channel, posted KOLs only). Best-effort: the
        # grading must still run when a channel page can't be read.
        try:
            from app.channel_form import ensure_baselines
            cf = ensure_baselines(campaign, st)
            if cf.get("cost"):
                from app.settings import add_cost
                add_cost(campaign, cf["cost"], kind="chform")
        except Exception as exc:  # noqa: BLE001
            log.warning("channel form skipped for %s: %s", campaign, exc)

        st.update(message="กำลังรวบรวมตัวเลขของแคมเปญ…")
        rows, pending = _build_input(campaign)
        posted = [r for r in rows if r["views"] or r["post_url"]]
        if not posted:
            st.update(status="success",
                      message="ยังไม่มีโพสต์ที่ลงงานแล้วให้วิเคราะห์",
                      finished_at=dt.datetime.now(config.TZ).isoformat())
            return {"status": "skipped"}

        st.update(message=f"กำลังวิเคราะห์ {len(posted)} โพสต์ "
                          f"(+{pending} คนยังไม่ลงงาน)…")
        from app.tiein import _claude
        today = dt.datetime.now(config.TZ).date().isoformat()
        prompt = (f"{SYSTEM_PROMPT}\n\n{FEW_SHOT}\n\n"
                  f"วันนี้คือ {today} (ใช้คำนวณอายุโพสต์)\n"
                  f"มี KOL ที่ยังไม่ลงงานอีก {pending} คน (นับใน pending_count)\n\n"
                  f"ข้อมูลรายโพสต์:\n{json.dumps(rows, ensure_ascii=False)}")
        reply, usage = _claude([{"type": "text", "text": prompt}],
                               max_tokens=ADVISOR_MAX_TOKENS, model=ADVISOR_MODEL,
                               with_usage=True)
        cost = _run_cost_usd(ADVISOR_MODEL, usage or {})
        if cost:
            try:
                from app.settings import add_cost
                add_cost(campaign, cost, kind="advisor")
            except Exception:  # noqa: BLE001 — cost tracking must not break the run
                pass
        try:
            result = json.loads(_FENCE.sub("", (reply or "").strip()))
        except (ValueError, TypeError):
            log.warning("advisor[%s]: unparseable reply (%d chars)",
                        campaign, len(reply or ""))
            st.update(status="failed",
                      message="AI ตอบมาในรูปแบบที่อ่านไม่ได้ — ลองกดใหม่อีกครั้ง",
                      finished_at=dt.datetime.now(config.TZ).isoformat())
            return {"status": "failed"}

        from app.settings import set_setting
        set_setting(f"advisor:{campaign}", json.dumps({
            "generated_at": dt.datetime.now(config.TZ).isoformat(),
            "model": ADVISOR_MODEL,
            "posted_count_input": len(posted),
            "result": result,
        }, ensure_ascii=False))

        n = len(result.get("posts") or [])
        st.update(status="success",
                  message=f"ให้คะแนนแล้ว {n} โพสต์ · {pending} คนยังไม่ลงงาน",
                  finished_at=dt.datetime.now(config.TZ).isoformat(), posts=n,
                  cost_usd=cost)
        return {"status": "success", "kols": n}
    except Exception as exc:  # noqa: BLE001
        log.exception("advisor[%s] failed", campaign)
        st.update(status="failed", message=f"วิเคราะห์ไม่สำเร็จ: {_redact(exc)}",
                  finished_at=dt.datetime.now(config.TZ).isoformat())
        return {"status": "failed", "error": _redact(exc)}


def stored(campaign: str) -> dict:
    from app.settings import get_setting
    raw = get_setting(f"advisor:{campaign}")
    if not raw:
        return {"is_set": False}
    try:
        data = json.loads(raw)
    except ValueError:
        return {"is_set": False}
    data["is_set"] = True
    return data
