"""Campaign comment collection, classification and rollup.

report_posts.comments only ever held a COUNT, so the product could report how
many people commented but never what they said. This module fills that gap:

1. run_comment_refresh(campaign) — scrape the comment TEXT under every active
   KOL's post (Apify, pay-per-result), store it, then classify what is not yet
   classified.
2. summary(campaign) — the rollup the dashboard panel reads.

TAXONOMY (three axes, from references/comment-analysis.md)
  category   one of CATEGORIES — fixed, so campaigns stay comparable
  sentiment  pos/neu/neg — only on comments that touch the product, because a
             comment praising the creator is not praise for the product
  theme      one free word taken from what the comments actually say (รสชาติ,
             ราคา, หาซื้อยาก, ...) — this is where product-specific detail
             lives, as DATA rather than as a schema that changes per campaign

Cost: TikTok $0.50 / 1,000 comments, Facebook $1.40 / 1,000, both
pay-per-result — config.COMMENTS_PER_POST is a ceiling, not a bill.
Classification adds roughly $0.05 per 1,000 comments on Haiku.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
from typing import Optional

from sqlalchemy import func, select

from app import config
from app.apify_client import run_scrape_comments_fb, run_scrape_comments_tiktok
from app.db import session_scope
from app.models import ReportComment, ReportKol, ReportPost
from app.report_refresh import _redact, state_for

log = logging.getLogger("comments")

# Axis 1 — fixed across every campaign, so the donut can be compared
CATEGORIES = ("FAN", "PRODUCT", "INTENT", "ECHO", "NEG", "QUESTION", "SPAM")
# Axis 2 applies only to comments that actually touch the product. A FAN or
# QUESTION comment has no product sentiment to report, and forcing one would
# inflate whichever way it defaulted.
PRODUCT_CATEGORIES = ("PRODUCT", "INTENT", "ECHO", "NEG")
SENTIMENTS = ("pos", "neu", "neg")

# Thai labels for the UI, kept next to the codes so the two cannot drift
CATEGORY_LABELS = {
    "FAN": "แฟนคลับ (ไม่แตะสินค้า)",
    "PRODUCT": "พูดถึงสินค้า",
    "INTENT": "ตั้งใจซื้อ / ถามช่องทาง",
    "ECHO": "เล่นสโลแกนต่อ",
    "NEG": "เชิงลบ",
    "QUESTION": "คำถามทั่วไป",
    "SPAM": "สแปม / ไม่เกี่ยวข้อง",
}

# One Claude call per batch. 40 keeps the prompt small enough that Haiku holds
# the numbering reliably; a bigger batch starts dropping lines.
BATCH = 40
CLASSIFY_MAX_TOKENS = 4000
# Posts per Apify run. One run per post would multiply run overhead; one run for
# everything makes a single bad URL slower to isolate.
POSTS_PER_RUN = 20


# ---------------------------------------------------------------------------
# classification
# ---------------------------------------------------------------------------

def _classify_prompt(product_desc: str, batch: list) -> str:
    lines = "\n".join(f"{i}. {(c.text or '')[:400]}" for i, c in enumerate(batch, 1))
    return (
        f"สินค้าของแคมเปญ: {product_desc}\n\n"
        "จัดประเภทคอมเมนต์ใต้โพสต์รีวิวต่อไปนี้ ทีละอัน ตาม taxonomy:\n\n"
        "category (เลือก 1 ค่า):\n"
        "FAN = พูดถึงตัวครีเอเตอร์/ทักทาย ไม่แตะสินค้า\n"
        "PRODUCT = พูดถึงสินค้า แบรนด์ หรือการใช้งาน\n"
        "INTENT = ตั้งใจซื้อ หรือถามช่องทางซื้อ/ราคา\n"
        "ECHO = เอาสโลแกนหรือมุกของแคมเปญไปเล่นต่อ\n"
        "NEG = เชิงลบต่อสินค้า แบรนด์ ครีเอเตอร์ หรือบ่นว่าขายของ\n"
        "QUESTION = คำถามทั่วไปที่ไม่เกี่ยวกับการซื้อ\n"
        "SPAM = บอท โฆษณาแฝง ลิงก์พนัน ไม่เกี่ยวข้อง\n\n"
        "sentiment (ทิศทางต่อ 'สินค้า' เท่านั้น ไม่ใช่ต่อครีเอเตอร์):\n"
        "pos / neu / neg — ถ้า category เป็น FAN, QUESTION หรือ SPAM ให้ตอบ -\n\n"
        "theme: คำเดียวสั้น ๆ ว่าพูดถึงแง่ไหนของสินค้า (เช่น รสชาติ ราคา "
        "หาซื้อยาก แพ็กเกจ เห็นผล กลิ่น) — ถ้าไม่แตะสินค้าให้ตอบ -\n\n"
        "ข้อควรระวัง: คอมเมนต์ที่ชมครีเอเตอร์แต่ไม่พูดถึงสินค้า = FAN ไม่ใช่ PRODUCT · "
        "ภาษาไทยมีการประชดเยอะ ให้ยึดบริบทไม่ใช่ถ้อยคำ\n\n"
        "ตอบบรรทัดละ 1 คอมเมนต์ รูปแบบ: เลข|CATEGORY|sentiment|theme\n"
        "ห้ามมีข้อความอื่น ต้องตอบให้ครบทุกเลข\n\n"
        f"คอมเมนต์:\n{lines}"
    )


_LINE = re.compile(r"^\s*(\d+)\s*\|\s*([A-Z]+)\s*\|\s*([a-z-]+)\s*\|\s*(.*?)\s*$")


def _parse_classification(reply: str, size: int) -> dict:
    """1-based index -> (category, sentiment, theme). Unparseable or unknown
    values are dropped rather than guessed: an unclassified comment stays
    visible as 'ยังไม่จัดประเภท', a wrongly-classified one silently skews the
    percentages the whole panel exists to report."""
    out: dict = {}
    for raw in (reply or "").splitlines():
        m = _LINE.match(raw)
        if not m:
            continue
        n, cat, sent, theme = int(m.group(1)), m.group(2), m.group(3), m.group(4)
        if not (1 <= n <= size) or cat not in CATEGORIES:
            continue
        if cat in PRODUCT_CATEGORIES and sent in SENTIMENTS:
            sentiment = sent
        else:
            sentiment = None
        theme = theme.strip()[:64]
        if theme in {"-", "", "none", "None"}:
            theme = None
        out[n] = (cat, sentiment, theme)
    return out


def classify_pending(campaign: str, product_desc: str, st: Optional[dict] = None) -> int:
    """Classify every stored comment of the campaign that has no category yet.
    Returns how many were classified. Safe to re-run — it only ever looks at
    rows still missing a category, so an interrupted run resumes."""
    from app.tiein import _claude  # shared Claude caller (key handling, Thai errors)

    done = 0
    while True:
        with session_scope() as session:
            batch = session.scalars(
                select(ReportComment)
                .where(ReportComment.campaign == campaign,
                       ReportComment.category.is_(None))
                .limit(BATCH)).all()
            if not batch:
                return done
            payload = [(c.id, c.text) for c in batch]

        holder = [type("C", (), {"text": t})() for _, t in payload]
        try:
            reply = _claude(
                [{"type": "text", "text": _classify_prompt(product_desc, holder)}],
                max_tokens=CLASSIFY_MAX_TOKENS)
        except RuntimeError as exc:
            log.warning("comment classify failed: %s", exc)
            return done  # transient — the next run picks the same rows up
        parsed = _parse_classification(reply or "", len(payload))
        if not parsed:
            # nothing usable came back; stop rather than spin on the same rows
            log.warning("comment classify returned nothing parseable — stopping")
            return done

        now = dt.datetime.now(dt.timezone.utc)
        with session_scope() as session:
            for i, (cid, _) in enumerate(payload, 1):
                got = parsed.get(i)
                if not got:
                    continue
                row = session.get(ReportComment, cid)
                if row:
                    row.category, row.sentiment, row.theme = got
                    row.classified_at = now
                    done += 1
        if st is not None:
            st.update(message=f"จัดประเภทคอมเมนต์แล้ว {done} อัน…")
        if len(payload) < BATCH:
            return done


# ---------------------------------------------------------------------------
# scraping
# ---------------------------------------------------------------------------

def _chunks(seq: list, n: int):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def _upsert(rows: list) -> int:
    """Insert comments, skipping ones already stored.

    NOT session.merge(): merge matches on the PRIMARY KEY, and the primary key
    here is an autoincrement id, so merge cheerfully inserts a second row for a
    comment we already have and the run dies on the unique constraint the
    second time a post is scraped.

    On conflict only the volatile metrics are refreshed. `text` and the three
    classification columns are deliberately left alone: re-scraping must not
    silently invalidate a classification we already paid for, and comment edits
    are rare enough that stale text beats re-billing every classification.
    """
    if not rows:
        return 0
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    stmt = pg_insert(ReportComment).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[ReportComment.comment_id],
        set_={"likes": stmt.excluded.likes, "author": stmt.excluded.author,
              "posted_at": stmt.excluded.posted_at},
    )
    with session_scope() as session:
        session.execute(stmt)
    return len(rows)


def _store_tiktok(campaign: str, items: list, owner_of: dict) -> int:
    """clockworks/tiktok-comments-scraper output -> report_comments."""
    rows, seen = [], set()
    for it in items:
        cid = str(it.get("cid") or "")
        text = (it.get("text") or "").strip()
        if not cid or not text or cid in seen:
            continue
        vid = _video_id(str(it.get("videoWebUrl") or it.get("postUrl") or ""))
        owner = owner_of.get(vid)
        if not owner:
            continue  # a comment on a post we did not ask about
        seen.add(cid)
        rows.append({
            "campaign": campaign, "platform": "tiktok", "post_video_id": vid,
            "kol_username": owner, "comment_id": f"tt:{cid}"[:128],
            "author": str(it.get("uniqueId") or "")[:255], "text": text[:5000],
            "likes": int(it.get("diggCount") or 0),
            "posted_at": _parse_dt(it.get("createTimeISO")),
            "is_reply": bool(it.get("repliesToId")),
        })
    return _upsert(rows)


def _store_fb(campaign: str, items: list, owner_of: dict) -> int:
    """apify/facebook-comments-scraper output -> report_comments."""
    rows, seen = [], set()
    for it in items:
        text = (it.get("text") or "").strip()
        cid = str(it.get("id") or it.get("commentUrl") or "")
        if not cid or not text or cid in seen:
            continue
        vid = _video_id(str(it.get("facebookUrl") or it.get("postUrl") or ""))
        owner = owner_of.get(vid)
        if not owner:
            continue
        seen.add(cid)
        rows.append({
            "campaign": campaign, "platform": "facebook", "post_video_id": vid,
            "kol_username": owner, "comment_id": f"fb:{cid}"[:128],
            "author": str(it.get("profileName") or "")[:255], "text": text[:5000],
            "likes": int(it.get("likesCount") or 0),
            "posted_at": _parse_dt(it.get("date")),
            "is_reply": bool(it.get("threadingDepth")),
        })
    return _upsert(rows)


def _video_id(url: str) -> str:
    """The key both the post table and a comment agree on. TikTok exposes a
    numeric video id; Facebook has no equivalent, so the URL itself is the key
    (normalised, because the actor echoes it back with query strings attached)."""
    m = re.search(r"/video/(\d+)", url)
    if m:
        return m.group(1)
    return url.split("?")[0].rstrip("/")[-64:]


def _parse_dt(value) -> Optional[dt.datetime]:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# the job
# ---------------------------------------------------------------------------

def run_comment_refresh(campaign: str) -> dict:
    """Scrape + classify every active KOL's post comments. Progress in
    state_for('cm:'+campaign). Never raises."""
    st = state_for("cm:" + campaign)
    st.update(status="running", message="กำลังรวบรวมโพสต์ของแคมเปญ…",
              started_at=dt.datetime.now(config.TZ).isoformat(), finished_at=None,
              posts=0, cost_usd=None)
    try:
        tiktok, facebook, owner_of = [], [], {}
        with session_scope() as session:
            active = {k.username.lower() for k in session.scalars(select(ReportKol).where(
                ReportKol.active.is_(True), ReportKol.campaign == campaign)).all()}
            for p in session.scalars(select(ReportPost).where(
                    ReportPost.campaign == campaign)).all():
                if not p.url or p.username.lower() not in active:
                    continue
                owner_of[_video_id(p.url)] = p.username
                (tiktok if p.platform == "tiktok" else
                 facebook if p.platform == "facebook" else []).append(p.url)

        if not tiktok and not facebook:
            st.update(status="success", message="ไม่มีโพสต์ที่ดึงคอมเมนต์ได้",
                      finished_at=dt.datetime.now(config.TZ).isoformat())
            return {"status": "skipped"}

        cost, stored = 0.0, 0
        for label, urls, runner, store in (
                ("TikTok", tiktok, run_scrape_comments_tiktok, _store_tiktok),
                ("Facebook", facebook, run_scrape_comments_fb, _store_fb)):
            for i, chunk in enumerate(_chunks(urls, POSTS_PER_RUN), 1):
                st.update(message=f"ดึงคอมเมนต์ {label} ชุดที่ {i} ({len(chunk)} โพสต์)…")
                try:
                    items, meta = runner(chunk)
                except Exception as exc:  # noqa: BLE001 — keep the other chunks alive
                    log.error("comment scrape failed (%s): %s", label, _redact(exc))
                    continue
                cost += meta.get("cost_usd") or 0.0
                stored += store(campaign, items, owner_of)

        st.update(message="กำลังวิเคราะห์คอมเมนต์…")
        from app.tiein import infer_product
        classified = classify_pending(campaign, infer_product(campaign), st)

        try:
            from app.settings import add_cost
            add_cost(campaign, cost)
        except Exception:  # noqa: BLE001
            pass

        st.update(status="success",
                  message=(f"เก็บคอมเมนต์ {stored} อัน · จัดประเภทแล้ว {classified} อัน"),
                  finished_at=dt.datetime.now(config.TZ).isoformat(),
                  posts=stored, cost_usd=round(cost, 4) if cost else None)
        return {"status": "success", "stored": stored, "classified": classified}
    except Exception as exc:  # noqa: BLE001
        log.exception("comment refresh[%s] failed", campaign)
        st.update(status="failed", message=f"ดึงคอมเมนต์ไม่สำเร็จ: {_redact(exc)}",
                  finished_at=dt.datetime.now(config.TZ).isoformat())
        return {"status": "failed", "error": _redact(exc)}


# ---------------------------------------------------------------------------
# rollup for the dashboard
# ---------------------------------------------------------------------------

def summary(campaign: str, preview_limit: int = 24) -> dict:
    """Category split, product sentiment, and a preview of the comments that
    actually mention the product — each carrying whose post it came from."""
    with session_scope() as session:
        total = session.scalar(select(func.count()).select_from(ReportComment)
                               .where(ReportComment.campaign == campaign)) or 0
        rows = session.execute(
            select(ReportComment.category, func.count())
            .where(ReportComment.campaign == campaign)
            .group_by(ReportComment.category)).all()
        by_cat = {c: n for c, n in rows}
        sent_rows = session.execute(
            select(ReportComment.sentiment, func.count())
            .where(ReportComment.campaign == campaign,
                   ReportComment.category.in_(PRODUCT_CATEGORIES))
            .group_by(ReportComment.sentiment)).all()
        themes = session.execute(
            select(ReportComment.theme, func.count())
            .where(ReportComment.campaign == campaign,
                   ReportComment.theme.isnot(None))
            .group_by(ReportComment.theme)
            .order_by(func.count().desc()).limit(12)).all()
        # preview shows product-touching comments, most-liked first — those are
        # the ones a brand reads, and likes are the crowd's own ranking
        preview = session.scalars(
            select(ReportComment)
            .where(ReportComment.campaign == campaign,
                   ReportComment.category.in_(PRODUCT_CATEGORIES))
            .order_by(ReportComment.likes.desc(), ReportComment.id.desc())
            .limit(preview_limit)).all()
        platforms = session.execute(
            select(ReportComment.platform, func.count())
            .where(ReportComment.campaign == campaign)
            .group_by(ReportComment.platform)).all()

        return {
            "total": total,
            "unclassified": by_cat.get(None, 0),
            "by_platform": {p: n for p, n in platforms},
            "categories": [
                {"code": c, "label": CATEGORY_LABELS[c], "count": by_cat.get(c, 0),
                 "pct": round(100 * by_cat.get(c, 0) / total, 1) if total else 0.0}
                for c in CATEGORIES
            ],
            "product_sentiment": {
                s: n for s, n in sent_rows if s in SENTIMENTS
            },
            "themes": [{"theme": t, "count": n} for t, n in themes],
            "preview": [
                {"id": c.id, "text": c.text, "author": c.author,
                 "platform": c.platform, "kol": c.kol_username,
                 "category": c.category, "label": CATEGORY_LABELS.get(c.category or ""),
                 "sentiment": c.sentiment, "theme": c.theme, "likes": c.likes,
                 "posted_at": c.posted_at.isoformat() if c.posted_at else None}
                for c in preview
            ],
        }


def by_kol(campaign: str, per_kol: int = 6) -> list:
    """Per-KOL breakdown: totals, product sentiment split, and that KOL's
    best product comments.

    NOT read by the dashboard panel — this exists for the planned PPTX slide
    that follows each KOL's stats slide. Keeping it here means the deck side
    reads the same taxonomy and the same "product comment" definition the
    dashboard shows, instead of re-deriving them and drifting apart.
    """
    with session_scope() as session:
        totals = dict(session.execute(
            select(ReportComment.kol_username, func.count())
            .where(ReportComment.campaign == campaign)
            .group_by(ReportComment.kol_username)).all())
        sent = session.execute(
            select(ReportComment.kol_username, ReportComment.sentiment, func.count())
            .where(ReportComment.campaign == campaign,
                   ReportComment.category.in_(PRODUCT_CATEGORIES))
            .group_by(ReportComment.kol_username, ReportComment.sentiment)).all()
        rows = session.scalars(
            select(ReportComment)
            .where(ReportComment.campaign == campaign,
                   ReportComment.category.in_(PRODUCT_CATEGORIES))
            .order_by(ReportComment.likes.desc(), ReportComment.id.desc())).all()

        picked: dict = {}
        for c in rows:  # already sorted by likes, so the first N per KOL are the top N
            bucket = picked.setdefault(c.kol_username, [])
            if len(bucket) < per_kol:
                bucket.append({
                    "text": c.text, "author": c.author, "platform": c.platform,
                    "category": c.category, "sentiment": c.sentiment,
                    "theme": c.theme, "likes": c.likes,
                })

        out = []
        for kol, total in sorted(totals.items(), key=lambda kv: -kv[1]):
            s = {v: n for k, v, n in sent if k == kol and v in SENTIMENTS}
            out.append({
                "kol": kol, "total": total,
                "product_total": sum(s.values()),
                "sentiment": s,
                "comments": picked.get(kol, []),
            })
        return out
