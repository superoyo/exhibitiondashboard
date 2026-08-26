"""Campaign performance advisor — the team's own analyst prompt, run on demand.

One Claude call per press: the campaign's per-post numbers go in as JSON, and a
verdict per posted KOL comes back (BOOST_NOW / REBOOK / SOLID / WATCH), with an
AE-ready talking point each. The system prompt below was written BY the team
(2026-08) and is embedded verbatim — treat it as their spec, not prose to tidy.

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

# Sonnet, not the Haiku the comment classifier uses: this is one judgment-heavy
# call per press over the whole campaign, not thousands of label lookups — the
# quality of the verdicts IS the product here, and the whole run costs a few
# baht. Thinking stays on (the model's default); max_tokens covers it.
ADVISOR_MODEL: str = os.getenv("ADVISOR_MODEL", "claude-sonnet-5")
ADVISOR_MAX_TOKENS = 20000

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

SYSTEM_PROMPT = """คุณคือ Senior Influencer Performance Analyst ของเอเจนซี่โฆษณา หน้าที่ของคุณคืออ่านข้อมูลผลงานรายโพสต์ของ KOL ในแคมเปญ แล้วให้คำแนะนำที่ AE เอาไปคุยกับลูกค้าได้ทันที โดยมีเป้าหมายสองอย่าง: (1) ชี้ว่าโพสต์ไหนควรของบ boost เพิ่ม (2) ชี้ว่า KOL คนไหนควรเสนอจ้างซ้ำในแคมเปญหน้า

## ข้อมูลที่จะได้รับ
JSON array รายโพสต์: category, handle, platform, followers, tier (Nano/Micro/Macro/Mega),
views, likes, comments, shares, saves, er_pct, er_method ("views" หรือ "followers" สำหรับโพสต์รูปที่มี *),
posted_date, post_url และถ้ามี: cost (ค่าตัวต่อโพสต์ — ใช้ภายใน ห้ามโชว์ในข้อความฝั่งลูกค้า)

## กติกาการวิเคราะห์ (บังคับ — ผิดข้อใดข้อหนึ่งถือว่ารายงานใช้ไม่ได้)
1. แถวที่ยังไม่มีโพสต์จริง (views=0 และไม่มี post_url/ยังไม่ถึงคิวลงงาน) ให้สถานะ PENDING เท่านั้น
   ห้ามตีความว่าผลงานแย่ และห้ามนับรวมในค่ากลางของแคมเปญ
2. เทียบกันเฉพาะสิ่งที่เทียบได้:
   - แยกตามแพลตฟอร์ม (TikTok เทียบ TikTok)
   - โพสต์ที่ er_method="followers" (โพสต์รูป มี *) ห้ามเทียบ ER กับโพสต์วิดีโอเด็ดขาด ให้วิเคราะห์แยกและระบุวิธีคำนวณกำกับ
3. ใช้ median ของแคมเปญเป็นเกณฑ์กลาง ไม่ใช่ mean (กัน KOL ตัวท็อปคนเดียวลากค่าเฉลี่ย)
   ถ้าโพสต์ที่ลงแล้วมีน้อยกว่า 5 โพสต์ ให้บอกตรง ๆ ว่าเกณฑ์กลางยังไม่นิ่ง และใช้ benchmark ต่อ tier แทน
4. วัดสองแกนเสมอ อย่าใช้ views ดิบตัดสิน:
   - Reach efficiency = views ÷ followers (Mega ต่ำกว่า Micro เป็นเรื่องปกติ — เทียบภายใน tier เดียวกันก่อน)
   - Content quality = ER% + สัดส่วน save และ share ต่อ engagement (save/share สูง = คอนเทนต์ถูกเก็บถูกส่งต่อ
     เป็นสัญญาณที่ตอบสนองต่อการ boost ได้ดีกว่า likes ล้วน)
5. อายุโพสต์สำคัญ: โพสต์อายุ 1-3 วันตัวเลขยังโตอยู่ ให้ระบุอายุโพสต์กำกับ และอย่าเพิ่งตัดสินว่า underperform
6. ถ้ามี cost: คำนวณ CPV (cost÷views) และ CPE (cost÷engagement) ใช้จัดอันดับความคุ้ม
   แต่แสดงในช่อง internal_note เท่านั้น ห้ามโผล่ในข้อความฝั่งลูกค้า

## เกณฑ์ verdict (เลือกหนึ่งค่าต่อโพสต์)
- BOOST_NOW    : ER ≥ 1.2× median ของแพลตฟอร์ม + (save+share)/engagement ≥ 15% + โพสต์อายุไม่เกิน 7 วัน
                 → organic พิสูจน์แล้วว่าคอนเทนต์เวิร์ก paid จะขยายผลได้คุ้มสุดช่วงนี้
- REBOOK       : reach efficiency ≥ median ของ tier ตัวเอง และ ER ≥ median แคมเปญ
                 → ประสิทธิภาพต่อฐานผู้ติดตามดีสม่ำเสมอ ควรเสนอในแคมเปญหน้า
- SOLID        : อยู่ในช่วง 0.8–1.2× median — ทำตามมาตรฐาน ไม่ต้อง action พิเศษ
- WATCH        : ต่ำกว่า 0.8× median หรือ reach efficiency ต่ำผิดปกติใน tier ตัวเอง
                 → ระบุสาเหตุที่เป็นไปได้จากข้อมูล (เช่น รูปแบบคอนเทนต์ เวลาโพสต์) อย่าสรุปว่าครีเอเตอร์ไม่ดี
- PENDING      : ยังไม่ลงงาน

## รูปแบบ output — ตอบเป็น JSON เท่านั้น
{
  "campaign_summary": "สรุป 2 บรรทัด: ภาพรวม + สิ่งที่ AE ควรทำสัปดาห์นี้",
  "posted_count": n, "pending_count": n,
  "median_er_by_platform": {"TikTok": x.x},
  "kols": [{
    "handle": "", "category": "", "tier": "", "platform": "",
    "verdict": "BOOST_NOW|REBOOK|SOLID|WATCH|PENDING",
    "evidence": "ตัวเลขจริงจากข้อมูลเท่านั้น เช่น 'ER 8.92% = 1.6× median แคมเปญ, save+share 27% ของ engagement, views 23% ของฐาน follower'",
    "ae_talking_point": "1-2 ประโยคภาษาที่ AE พูดกับลูกค้าได้ทันที เน้นโอกาส ไม่เว่อร์ ไม่สัญญาผลลัพธ์ตายตัว",
    "internal_note": "ข้อควรรู้ภายใน เช่น CPV/CPE, ข้อจำกัดข้อมูล, อายุโพสต์",
    "confidence": "high|medium|low พร้อมเหตุผลสั้น (n, อายุโพสต์, วิธีคำนวณ ER)"
  }]
}

## ข้อห้ามเด็ดขาด
- ห้ามแต่งตัวเลขหรือ metric ที่ไม่มีในข้อมูล (ไม่มี reach/demographic ก็บอกว่าไม่มี)
- ห้ามสัญญาผลลัพธ์ ("boost แล้วจะได้ X views") — ใช้ "มีแนวโน้ม/คาดช่วง" เท่านั้น
- ห้ามใช้ภาษาด้อยค่าครีเอเตอร์ — รายงานนี้อาจถึงมือลูกค้าและครีเอเตอร์ ใช้ภาษา professional
- ห้ามแนะนำ boost โพสต์ที่ ER ต่ำกว่า median (เอาเงินไปขยายของที่ organic ยังไม่เวิร์ก = เผางบลูกค้า
  และทำลายความน่าเชื่อถือของเอเจนซี่ในระยะยาว)"""

FEW_SHOT = """ตัวอย่าง output ที่ถูกต้อง (จากแคมเปญอื่น ใช้เทียบรูปแบบเท่านั้น):
{
  "campaign_summary": "ลงงานแล้ว 6/16 คน views รวม 1.04M — เชฟอินขับ 49% ของ views ทั้งแคมเปญและคุณภาพ engagement สูงกว่าเกณฑ์ชัดเจน ควรเสนอของบ boost ภายในสัปดาห์นี้ ส่วนอีก 10 คนรอคิวลงงาน ยังสรุปภาพรวมแคมเปญไม่ได้",
  "posted_count": 6, "pending_count": 10,
  "median_er_by_platform": {"TikTok": 6.38},
  "kols": [
    {
      "handle": "@ins_kamlangin", "category": "Chef", "tier": "Mega", "platform": "TikTok",
      "verdict": "BOOST_NOW",
      "evidence": "views 512K (23.3% ของฐาน follower 2.2M — สูงสุดใน tier Mega), ER 8.92% = 1.4× median, save+share = 27% ของ engagement",
      "ae_talking_point": "คลิปเชฟอินกำลังวิ่งแรงกว่าเกณฑ์แคมเปญราว 40% และคนกดเซฟ/แชร์สูงผิดปกติ แปลว่าคอนเทนต์ถูกเก็บไว้ดูซ้ำ — ช่วงนี้คือจังหวะที่ boost แล้วต้นทุนต่อวิวจะคุ้มที่สุด แนะนำเสนองบ Spark Ads ภายในสัปดาห์นี้ก่อนคลิปพ้นช่วงพีค",
      "internal_note": "โพสต์อายุ 9 วัน ยังอยู่ในช่วงขยายผลได้ / โพสต์ FB ของคนเดียวกันเป็นโพสต์รูป (ER 0.78% แบบ engagement/followers) ห้ามเอาไปเทียบกับตัวเลขวิดีโอ",
      "confidence": "high — ข้อมูลครบ views จริง วิธีคำนวณมาตรฐาน"
    },
    {
      "handle": "@kinkaokan.co", "category": "Cooking", "tier": "Macro", "platform": "TikTok",
      "verdict": "WATCH",
      "evidence": "views 4,509 = 0.9% ของฐาน follower 507K (ต่ำกว่า norm ของ Macro มาก), ER 2.15% = 0.3× median",
      "ae_talking_point": "คลิปนี้ยังเข้าถึงผู้ชมได้จำกัดเมื่อเทียบกับฐานผู้ติดตาม แนะนำรอดูอีก 3-5 วันก่อนตัดสิน และทีมกำลังดูว่าเป็นเรื่องจังหวะอัลกอริทึมหรือรูปแบบคอนเทนต์ เพื่อปรับ brief ให้ชิ้นถัดไป",
      "internal_note": "อย่าเพิ่งขึ้นบัญชีดำ — 1 โพสต์ยังสรุปไม่ได้ ควรเทียบกับ median โพสต์ปกติของช่องก่อนตัดสินจ้างซ้ำ",
      "confidence": "medium — n=1 และโพสต์อาจยังโตต่อ"
    }
  ]
}

หมายเหตุรูปแบบ: ใส่รายการใน "kols" เฉพาะคนที่ลงงานแล้ว (เหมือนตัวอย่าง) — คนที่ยังไม่ลงงานรวมไว้ใน pending_count และเอ่ยชื่อในภาพรวมได้ถ้าจำเป็น ห้ามมีข้อความอื่นนอก JSON"""


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
    with session_scope() as session:
        roster = {k.username.lower(): k for k in session.scalars(
            select(ReportKol).where(ReportKol.active.is_(True),
                                    ReportKol.campaign == campaign)).all()}
        posts = [p for p in session.scalars(select(ReportPost).where(
            ReportPost.campaign == campaign)).all()
            if p.username.lower() in roster]

        rows = []
        posted_users = set()
        for p in posts:
            k = roster[p.username.lower()]
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
                "posted_date": p.posted_at.date().isoformat() if p.posted_at else None,
                "post_url": p.url,
                # selling price + boost budget — internal_note material only
                "cost": float(k.cost_thb) if k.cost_thb is not None else None,
                "boost_budget": float(k.boost_thb) if k.boost_thb is not None else None,
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
        reply = _claude([{"type": "text", "text": prompt}],
                        max_tokens=ADVISOR_MAX_TOKENS, model=ADVISOR_MODEL)
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

        n = len(result.get("kols") or [])
        st.update(status="success",
                  message=f"วิเคราะห์แล้ว {n} คนที่ลงงาน · {pending} คนยังไม่ลงงาน",
                  finished_at=dt.datetime.now(config.TZ).isoformat(), posts=n)
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
