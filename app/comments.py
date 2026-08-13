"""Campaign comment collection, classification and rollup.

report_posts.comments only ever held a COUNT, so the product could report how
many people commented but never what they said. This module fills that gap:

1. run_comment_refresh(campaign) — scrape the comment TEXT under every active
   KOL's post (Apify, pay-per-result), store it, then classify what is not yet
   classified.
2. summary(campaign) — the rollup the dashboard panel reads.

TAXONOMY (two axes)
  category   one of CATEGORIES — WHAT the comment is about (ผลลัพธ์ / กลิ่น /
             ราคา / หาซื้อ / ...). Fixed, so campaigns stay comparable.
  theme      one free word, more specific than the category (ผิวนุ่ม, ติดทน,
             โปรโมชัน) — product-specific detail as DATA rather than as a schema
             that changes per campaign

There is deliberately NO sentiment axis. It existed (pos/neu/neg on
product-related comments) and was removed in 2026-08: Thai comments carry
polarity through sarcasm, joke-complaints, particles and stretched spelling,
and the team judged the labels too unreliable to show a client. The topic
categories replace it — "what is this about" is a question the model answers
consistently, and a brand can act on ISSUE or WHERE without being told a
sentiment score. Direction still shows through the comment text itself, which
the panel and the Excel export both display verbatim.

Cost: TikTok $0.50 / 1,000 comments, Facebook $1.40 / 1,000, both
pay-per-result — config.COMMENTS_PER_POST is a ceiling, not a bill.
Classification adds roughly $0.05 per 1,000 comments on Haiku.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
from typing import Optional

from sqlalchemy import func, or_, select

from app import config
from app.apify_client import run_scrape_comments_fb, run_scrape_comments_tiktok
from app.db import session_scope
from app.models import ReportComment, ReportKol, ReportPost
from app.report_refresh import _redact, state_for

log = logging.getLogger("comments")

# The one axis — fixed across every campaign, so the donut can be compared.
# Ordered as the panel lists them: product topics first, then the two buckets
# that are not about the product.
CATEGORIES = ("EFFECT", "SENSORY", "PRICE", "WHERE", "INTENT", "QUESTION",
              "ISSUE", "OFFTOPIC", "SPAM")
# What counts as "a comment about the product" — the preview list and the
# product-comment count both use this. Everything except the two buckets that
# by definition say nothing about it.
PRODUCT_CATEGORIES = ("EFFECT", "SENSORY", "PRICE", "WHERE", "INTENT",
                      "QUESTION", "ISSUE")

# Thai labels for the UI, kept next to the codes so the two cannot drift
CATEGORY_LABELS = {
    "EFFECT": "สรรพคุณ / ผลลัพธ์",
    "SENSORY": "กลิ่น / รสชาติ / เนื้อสัมผัส",
    "PRICE": "ราคา / ความคุ้มค่า",
    "WHERE": "หาซื้อที่ไหน / ของหมด",
    "INTENT": "อยากซื้อ / จะไปซื้อ",
    "QUESTION": "ถามข้อมูลสินค้า",
    "ISSUE": "ติดปัญหา / ข้อกังวล",
    "OFFTOPIC": "ไม่เกี่ยวกับสินค้า",
    "SPAM": "สแปม",
}

# One Claude call per batch. 40 keeps the prompt small enough that Haiku holds
# the numbering reliably; a bigger batch starts dropping lines.
BATCH = 40
CLASSIFY_MAX_TOKENS = 4000
# Bump this whenever _classify_prompt changes in a way that would label comments
# differently. Every comment stores the version that labelled it, so the next
# ordinary run re-labels anything older — no separate action to remember, and
# nothing is re-labelled when the rules have not moved. Same idea as
# TIEIN_VERSION, which redoes shots produced by an older algorithm.
CLASSIFY_VERSION = "topic1"
# Posts per Apify run. One run per post would multiply run overhead; one run for
# everything makes a single bad URL slower to isolate.
POSTS_PER_RUN = 20


# ---------------------------------------------------------------------------
# classification
# ---------------------------------------------------------------------------

def _classify_prompt(product_desc: str, batch: list) -> str:
    """The classifier. One question only: what is this comment ABOUT.

    Rewritten in 2026-08 away from intent+sentiment. The rules that survived are
    the ones that teach a BOUNDARY — a joke is not a complaint, talking about the
    clip is not talking about the product, "ของที่ใช้อยู่หมด" is not "ของหมดในร้าน"
    — because those patterns hold for any product and each one was written after
    seeing the model get it wrong. What went is every rule that asked the model
    to judge direction (pos/neu/neg, "ประชด", "ต้องตำหนิจริง"): that call is the
    one Thai makes unreliable, and the topic buckets do not need it. EFFECT holds
    "ใช้ดีมาก" and "ไม่เห็นผล" alike; a reader sees which from the text.

    Examples are worded without naming a product category, because this prompt
    runs for perfume, food and household campaigns alike and a body-wash example
    would pull the others off course.
    """
    lines = "\n".join(f"{i}. {(c.text or '')[:400]}" for i, c in enumerate(batch, 1))
    return (
        f"สินค้าของแคมเปญ: {product_desc}\n\n"
        "อ่านคอมเมนต์ใต้โพสต์รีวิวต่อไปนี้ แล้วตอบว่าแต่ละอัน 'พูดถึงเรื่องอะไร' "
        "ทีละอัน\n"
        "ห้ามตัดสินว่าเป็นบวกหรือลบ — ดูแค่ว่าเนื้อหาอยู่เรื่องไหน\n\n"

        "category (เลือก 1 ค่า):\n"
        "EFFECT = สรรพคุณ ผลลัพธ์ การใช้งาน ใช้ดี/ใช้ไม่เห็นผล ติดทน เห็นผลเร็ว\n"
        "SENSORY = กลิ่น รสชาติ เนื้อสัมผัส สี ความรู้สึกตอนใช้\n"
        "PRICE = ราคา ความคุ้มค่า โปรโมชัน ส่วนลด ขนาด/ปริมาณเทียบราคา\n"
        "WHERE = หาซื้อที่ไหน ช่องทางขาย สาขา ของหมดในร้าน หาไม่เจอ\n"
        "INTENT = บอกว่าจะซื้อ อยากลอง สั่งแล้ว หรือของที่ใช้อยู่กำลังจะหมด\n"
        "QUESTION = ถามข้อมูลสินค้า (ไม่ใช่ถามที่ซื้อหรือถามราคา)\n"
        "ISSUE = ปัญหาจากตัวสินค้า (แพ้ ระคายเคือง ของเสีย ใช้ไม่ได้) "
        "หรือบ่นว่าคลิปนี้ขายของ\n"
        "OFFTOPIC = ไม่แตะสินค้าเลย — เชียร์ครีเอเตอร์ ทักทาย มุกตลก "
        "พูดถึงการตัดต่อ/เพลง/มุมกล้อง/ความยาวคลิป\n"
        "SPAM = บอท ลิงก์พนัน โฆษณาแฝง\n\n"

        "คอมเมนต์เดียวเข้าได้หลายเรื่อง → เลือก 'อันเดียว' ตามลำดับนี้ "
        "อันไหนอยู่บนกว่าให้ใช้อันนั้น:\n"
        "SPAM > ISSUE > WHERE > INTENT > PRICE > SENSORY > EFFECT > QUESTION "
        "> OFFTOPIC\n"
        "เช่น 'อยากซื้อ ขายที่ไหนคะ' → WHERE · 'อยากลอง ราคาเท่าไหร่' → INTENT\n\n"

        "แยก 'ของที่ผู้คอมเมนต์ใช้อยู่หมด' ออกจาก 'สินค้าหมดในร้าน':\n"
        "· 'ของที่ใช้อยู่หมดพอดี' / 'ขวดเก่าใช้หมดแล้ว' = ของตัวเองหมด "
        "มักเป็นสัญญาณว่ากำลังจะซื้อ → INTENT\n"
        "· 'หาซื้อไม่ได้' / 'ร้านไม่มีของ' / 'ของหมดทุกสาขา' = "
        "ปัญหาการกระจายสินค้า → WHERE\n\n"

        "OFFTOPIC ไม่ได้แปลว่า 'คอมเมนต์ไม่ดี' — แปลว่าไม่ได้พูดถึงสินค้า:\n"
        "· มุกตลก หยอกล้อ แกล้งบ่น อีโมจิเยอะ สะกดยืด ถ้าไม่แตะสินค้า = OFFTOPIC\n"
        "· เอาสโลแกนของแคมเปญไปเล่นต่อ: ถ้าประโยคนั้นพูดถึงคุณสมบัติสินค้า "
        "→ หมวดของคุณสมบัตินั้น (มักเป็น EFFECT) · ถ้าเป็นมุกเปล่า ๆ → OFFTOPIC\n"
        "· ISSUE ใช้กับ 'ปัญหาที่เกิดจากสินค้า' เท่านั้น "
        "ไม่ใช่ทุกคอมเมนต์ที่น้ำเสียงแรง\n\n"

        "คอมเมนต์ภาษาจีน พม่า อังกฤษ: จัดหมวดตามเนื้อหาปกติ ไม่ใช่ SPAM "
        "(SPAM คือบอท ลิงก์พนัน โฆษณาแฝง ไม่ใช่ 'ภาษาที่อ่านไม่ออก')\n\n"

        "theme: ขยายให้ละเอียดกว่า category หนึ่งขั้น เป็นคำสั้น ๆ "
        "ห้ามตอบคำกว้างอย่าง ทั่วไป / สินค้า / ดี / ชอบ "
        "และห้ามตอบคำเดียวกับชื่อ category\n"
        "ใช้คำเดิมให้ตรงกันทั้งชุดเพื่อให้นับรวมได้ เช่น "
        "ติดทน · เห็นผลเร็ว · ผิวนุ่ม · กลิ่นหอม · รสชาติ · เนื้อสัมผัส · "
        "คุ้มค่า · โปรโมชัน · สาขา · ของหมด · ระคายเคือง · ขายของ\n"
        "ถ้าไม่มีรายละเอียดพอ ตอบ -\n\n"

        "ตัวอย่างที่จัดถูกแล้ว ใช้เทียบ:\n"
        "\"ที่บ้านใช้ประจำเลย ใช้แล้วดีจริงค้าบ\"        → EFFECT|เห็นผล\n"
        "\"เคยใช้แล้วไม่เห็นผล\"                       → EFFECT|เห็นผล\n"
        "\"มันต้องดีน่าา\"                            → EFFECT|-\n"
        "\"กลิ่นหอมมาก ติดทนทั้งวัน\"                   → SENSORY|กลิ่นหอม\n"
        "\"ราคาเท่าไหร่คะ\"                           → PRICE|ราคา\n"
        "\"ร้านไหนใกล้ฉันมีขายบ้าง~\"                  → WHERE|สาขา\n"
        "\"หาซื้อไม่ได้เลย ร้านแถวบ้านไม่มี\"             → WHERE|ของหมด\n"
        "\"ได้เวลาเปลี่ยนมาใช้ตัวนี้แล้ว\"              → INTENT|-\n"
        "\"ของที่ใช้อยู่หมดพอดี\"                      → INTENT|-\n"
        "\"ใช้กับผิวแพ้ง่ายได้ไหม\"                    → QUESTION|ผิวแพ้ง่าย\n"
        "\"ใช้แล้วคันเลย ขึ้นผื่น\"                    → ISSUE|ระคายเคือง\n"
        "\"โอนค่าตัวมาด้วย !!\"                       → ISSUE|ขายของ\n"
        "\"มู้ดเสียงคลิปคือ ขึ้นๆลงๆ\"                  → OFFTOPIC|-\n"
        "\"อยู่กับข้าเอ็งเหมือนไก่จี๊ดริดในก้านกล้วย\"     → OFFTOPIC|-\n"
        "\"ตกใจค้าบ มากอดเค้าเลยค้าบ\"                → OFFTOPIC|-\n\n"

        "ตอบบรรทัดละ 1 คอมเมนต์ รูปแบบ: เลข|CATEGORY|theme\n"
        "ห้ามมีข้อความอื่น ต้องตอบให้ครบทุกเลข\n\n"
        f"คอมเมนต์:\n{lines}"
    )


# a theme must have at least one letter or digit — dashes, dots and stray
# punctuation are the model's way of saying "no theme", in several spellings
_THEME_WORD = re.compile(r"[^\W_]", re.UNICODE)

# `เลข|CATEGORY|theme`. The old four-field form (with a sentiment slot) is still
# accepted so a reply that slips back into the previous shape is used rather than
# thrown away — the third field is simply ignored.
_LINE = re.compile(r"^\s*(\d+)\s*\|\s*([A-Z]+)\s*\|\s*(?:[a-z-]{1,4}\s*\|\s*)?(.*?)\s*$")


def _parse_classification(reply: str, size: int) -> dict:
    """1-based index -> (category, theme). Unparseable or unknown values are
    dropped rather than guessed: an unclassified comment stays visible as
    'ยังไม่จัดประเภท', a wrongly-classified one silently skews the percentages
    the whole panel exists to report."""
    out: dict = {}
    for raw in (reply or "").splitlines():
        m = _LINE.match(raw)
        if not m:
            continue
        n, cat, theme = int(m.group(1)), m.group(2), m.group(3)
        if not (1 <= n <= size) or cat not in CATEGORIES:
            continue
        theme = theme.strip()[:64]
        # A theme has to contain an actual word. The model answers the
        # no-theme case with a dash, but not always exactly one: "---" slipped
        # past a `theme in {"-"}` check and became the second most common
        # "theme" on the panel, with 17 comments behind it.
        if not _THEME_WORD.search(theme) or theme.lower() in {"none", "null", "ไม่มี", "ทั่วไป"}:
            theme = None
        out[n] = (cat, theme)
    return out


def _needs_label():
    """Rows the next classify run will (re)do: never labelled, labelled by older
    rules, or carrying a code the current taxonomy no longer has.

    Shared with summary() on purpose. The panel reports this same count as
    "ยังไม่จัดประเภท", and if the two conditions drifted the panel would claim
    everything was labelled while the classifier still had work — or, worse,
    show a donut of zeroes with nothing explaining why. The taxonomy rewrite made
    that concrete: every comment already stored carried a code (PRODUCT, FAN,
    NEG) that no longer exists, so "has a category" stopped meaning "labelled".
    """
    return or_(ReportComment.category.is_(None),
               ReportComment.category.notin_(CATEGORIES),
               # coalesce covers rows stored before the column existed, whose
               # version is NULL and must count as "older".
               func.coalesce(ReportComment.rules_version, "") != CLASSIFY_VERSION)


def classify_pending(campaign: str, product_desc: str, st: Optional[dict] = None,
                     total: int = 0) -> int:
    """Label every comment of the campaign that needs it — see _needs_label().

    Returns how many were labelled. Safe to re-run: a row drops out of the
    queue only once it carries the current version, so an interrupted run
    resumes where it stopped rather than starting over.

    A stale row keeps its old labels until it is re-done, so the panel stays
    readable during a long re-label instead of blanking out. The numbers are a
    mix of old and new rules while that runs."""
    from app.tiein import _claude  # shared Claude caller (key handling, Thai errors)

    done = 0
    while True:
        with session_scope() as session:
            batch = session.scalars(
                select(ReportComment)
                .where(ReportComment.campaign == campaign, _needs_label())
                .limit(BATCH)).all()
            if not batch:
                return done
            payload = [(c.id, c.text) for c in batch]

        holder = [type("C", (), {"text": t})() for _, t in payload]
        try:
            reply = _claude(
                [{"type": "text", "text": _classify_prompt(product_desc, holder)}],
                max_tokens=CLASSIFY_MAX_TOKENS, model=config.COMMENT_MODEL)
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
                    row.category, row.theme = got
                    row.classified_at = now
                    row.rules_version = CLASSIFY_VERSION
                    done += 1
        if st is not None:
            st.update(message=(f"จัดประเภทคอมเมนต์แล้ว {done}"
                               + (f"/{total}" if total else "") + " อัน…"),
                      posts=done, total=total)
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
            "is_reply": _is_reply_tiktok(it),
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


def _is_reply_tiktok(it: dict) -> bool:
    """Whether a TikTok comment is a reply. The actor page documents the reply
    COUNT (`replyCommentTotal`) but not the parent-id field name, so several
    plausible spellings are checked rather than betting on one. is_reply is
    metadata only — nothing aggregates on it — so a miss costs a label, not a
    number."""
    for key in ("repliesToId", "replyToId", "parentCommentId", "replyId", "aid"):
        if it.get(key):
            return True
    return bool(it.get("replyToComment") or it.get("isReply"))


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
              posts=0, total=0, cost_usd=None)
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
            chunks = list(_chunks(urls, POSTS_PER_RUN))
            total_chunks = len(chunks)
            for i, chunk in enumerate(chunks, 1):
                # the running total matters: this job takes minutes, and without
                # it a slow chunk is indistinguishable from a stuck one
                so_far = f" · เก็บแล้ว {stored} อัน" if stored else ""
                st.update(message=(f"ดึงคอมเมนต์ {label} ชุดที่ {i}/{total_chunks} "
                                   f"({len(chunk)} โพสต์){so_far}…"))
                try:
                    items, meta = runner(chunk)
                except Exception as exc:  # noqa: BLE001 — keep the other chunks alive
                    log.error("comment scrape failed (%s): %s", label, _redact(exc))
                    continue
                cost += meta.get("cost_usd") or 0.0
                stored += store(campaign, items, owner_of)
                # no denominator during the scrape — how many comments a post
                # carries is unknown until Apify answers
                st.update(message=f"ดึงคอมเมนต์ {label} · เก็บแล้ว {stored} อัน…",
                          posts=stored, total=0)

        st.update(message="กำลังวิเคราะห์คอมเมนต์…")
        from app.tiein import infer_product
        st.update(total=stored)   # classifying HAS a denominator: what was stored
        classified = classify_pending(campaign, infer_product(campaign), st, total=stored)

        try:
            from app.settings import add_cost
            add_cost(campaign, cost, kind="comments")
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

def _not_creator():
    """Excludes a KOL's replies under their own post.

    Replies are collected, which means the creator's own answers land in the
    table. Counting those as audience voice lets the brand vote for itself: a KOL
    replying "อร่อยจริง ๆ ค่ะ" would show up as someone praising the product.
    comment-analysis.md calls these out as advertising to be kept separate.

    Matches on the author name, so it catches TikTok (where the commenter
    handle equals the roster username) but not always Facebook, whose actor
    returns a display name rather than a handle. Partial cover beats none.
    """
    return or_(ReportComment.author.is_(None),
               func.lower(ReportComment.author) != func.lower(ReportComment.kol_username))


def _post_urls(session, campaign: str) -> dict:
    """post_video_id -> the post's real URL, so a comment card can link to where
    it was written.

    Built by re-deriving the key rather than joining, because the two tables use
    different key spaces: ReportPost.video_id is a synthetic
    `{campaign}_{platform}_{md5}` string, while a comment keys on _video_id() of
    the post URL. A campaign has tens of posts, so this is one small query.
    """
    out = {}
    for url in session.scalars(
            select(ReportPost.url)
            .where(ReportPost.campaign == campaign,
                   ReportPost.url.isnot(None))).all():
        out[_video_id(url)] = url
    return out


def _item(c: ReportComment, post_url: Optional[str]) -> dict:
    return {"id": c.id, "text": c.text, "author": c.author,
            "platform": c.platform, "kol": c.kol_username,
            "post_url": post_url,
            "category": c.category, "label": CATEGORY_LABELS.get(c.category or ""),
            "theme": c.theme, "likes": c.likes,
            "posted_at": c.posted_at.isoformat() if c.posted_at else None}


def list_comments(campaign: str, category: Optional[str] = None,
                  offset: int = 0, limit: int = 20) -> dict:
    """One page of product-related comments, most-liked first, optionally
    narrowed to a single topic.

    Paged on the server rather than in the browser: a campaign's product
    comments run into the thousands, and shipping all of them so the client can
    slice twenty is the kind of thing that works fine until the campaign that
    matters most is the one that breaks it.
    """
    limit = max(1, min(limit, 100))
    where = [ReportComment.campaign == campaign,
             ReportComment.category.in_(PRODUCT_CATEGORIES),
             _not_creator()]
    # An unknown code is ignored rather than returning nothing: a stale bookmark
    # from the previous taxonomy should show all comments, not an empty page.
    if category in PRODUCT_CATEGORIES:
        where.append(ReportComment.category == category)

    with session_scope() as session:
        total = session.scalar(
            select(func.count()).select_from(ReportComment).where(*where)) or 0
        rows = session.scalars(
            select(ReportComment).where(*where)
            .order_by(ReportComment.likes.desc(), ReportComment.id.desc())
            .offset(offset).limit(limit)).all()
        urls = _post_urls(session, campaign)
        return {
            "total": total,
            "offset": offset,
            "limit": limit,
            "items": [_item(c, urls.get(c.post_video_id)) for c in rows],
        }


def summary(campaign: str) -> dict:
    """Topic split, the product-comment count and top themes. The comments
    themselves come from list_comments(), which pages them.

    `product_total` and `by_topic` exclude the creators' own replies, because
    those are what the preview list shows; the `categories` split does not, so
    `total` still matches what was collected."""
    with session_scope() as session:
        total = session.scalar(select(func.count()).select_from(ReportComment)
                               .where(ReportComment.campaign == campaign)) or 0
        rows = session.execute(
            select(ReportComment.category, func.count())
            .where(ReportComment.campaign == campaign)
            .group_by(ReportComment.category)).all()
        by_cat = {c: n for c, n in rows}
        # NOT `by_cat[None]`: after a taxonomy change every stored row still has
        # a category, just one that no longer exists, and counting only NULLs
        # would report "all classified" over a panel of zeroes.
        stale = session.scalar(
            select(func.count()).select_from(ReportComment)
            .where(ReportComment.campaign == campaign, _needs_label())) or 0
        # Counts behind the preview's filter chips. Same WHERE as
        # list_comments(), so a chip's number always matches the page it opens —
        # the previous panel counted sentiment over a different set and the two
        # could disagree.
        topic_rows = session.execute(
            select(ReportComment.category, func.count())
            .where(ReportComment.campaign == campaign,
                   ReportComment.category.in_(PRODUCT_CATEGORIES),
                   _not_creator())
            .group_by(ReportComment.category)).all()
        by_topic = {c: n for c, n in topic_rows if c}
        creator_replies = session.scalar(
            select(func.count()).select_from(ReportComment)
            .where(ReportComment.campaign == campaign,
                   func.lower(ReportComment.author)
                   == func.lower(ReportComment.kol_username))) or 0
        # Over-fetch and filter in Python: rows classified before the parser
        # learned to reject dash-only themes still hold values like "---", and
        # they should not occupy a slot on the panel.
        theme_rows = session.execute(
            select(ReportComment.theme, func.count())
            .where(ReportComment.campaign == campaign,
                   ReportComment.theme.isnot(None))
            .group_by(ReportComment.theme)
            .order_by(func.count().desc()).limit(40)).all()
        themes = [(t, n) for t, n in theme_rows
                  if t and _THEME_WORD.search(t)
                  and t.lower() not in {"none", "null", "ไม่มี", "ทั่วไป"}][:12]
        platforms = session.execute(
            select(ReportComment.platform, func.count())
            .where(ReportComment.campaign == campaign)
            .group_by(ReportComment.platform)).all()
        replies = session.scalar(
            select(func.count()).select_from(ReportComment)
            .where(ReportComment.campaign == campaign,
                   ReportComment.is_reply.is_(True))) or 0

        return {
            "total": total,
            "unclassified": stale,
            "replies": replies,
            "creator_replies": creator_replies,
            "by_platform": {p: n for p, n in platforms},
            "categories": [
                {"code": c, "label": CATEGORY_LABELS[c], "count": by_cat.get(c, 0),
                 "pct": round(100 * by_cat.get(c, 0) / total, 1) if total else 0.0}
                for c in CATEGORIES
            ],
            "product_total": sum(by_topic.values()),
            "by_topic": [
                {"code": c, "label": CATEGORY_LABELS[c], "count": by_topic.get(c, 0)}
                for c in PRODUCT_CATEGORIES
            ],
            "themes": [{"theme": t, "count": n} for t, n in themes],
        }


# ---------------------------------------------------------------------------
# Excel export
# ---------------------------------------------------------------------------

# A ceiling, not an expectation: a browser has to hold the whole thing in memory
# to build the workbook, and a campaign this size is a signal to page the export
# rather than a size to silently truncate. The API reports when it bites.
EXPORT_MAX = 50_000


def export_rows(campaign: str) -> dict:
    """EVERY stored comment of the campaign, flat, for the Excel export.

    Deliberately unfiltered — not product-only, not excluding the creators'
    replies, not excluding the unclassified. The panel filters because a reader
    can only take twenty at a time; a spreadsheet is where someone goes to see
    the whole thing and sort it themselves. The columns that drive the panel's
    filtering are included so they can redo it in Excel.
    """
    with session_scope() as session:
        total = session.scalar(select(func.count()).select_from(ReportComment)
                               .where(ReportComment.campaign == campaign)) or 0
        rows = session.scalars(
            select(ReportComment)
            .where(ReportComment.campaign == campaign)
            .order_by(ReportComment.kol_username, ReportComment.likes.desc(),
                      ReportComment.id)
            .limit(EXPORT_MAX)).all()
        urls = _post_urls(session, campaign)
        return {
            "total": total,
            "truncated": total > len(rows),
            "rows": [{
                "kol": c.kol_username,
                "platform": c.platform,
                "post_url": urls.get(c.post_video_id),
                "author": c.author,
                "text": c.text,
                "is_reply": bool(c.is_reply),
                "category": c.category,
                "label": CATEGORY_LABELS.get(c.category or ""),
                "theme": c.theme,
                "likes": c.likes,
                "posted_at": c.posted_at.isoformat() if c.posted_at else None,
            } for c in rows],
        }


def by_kol(campaign: str, per_kol: int = 6) -> list:
    """Per-KOL breakdown: totals, the topic split, and that KOL's best product
    comments.

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
        topics = session.execute(
            select(ReportComment.kol_username, ReportComment.category, func.count())
            .where(ReportComment.campaign == campaign,
                   ReportComment.category.in_(PRODUCT_CATEGORIES),
                   _not_creator())
            .group_by(ReportComment.kol_username, ReportComment.category)).all()
        rows = session.scalars(
            select(ReportComment)
            .where(ReportComment.campaign == campaign,
                   ReportComment.category.in_(PRODUCT_CATEGORIES),
                   _not_creator())
            .order_by(ReportComment.likes.desc(), ReportComment.id.desc())).all()

        picked: dict = {}
        for c in rows:  # already sorted by likes, so the first N per KOL are the top N
            bucket = picked.setdefault(c.kol_username, [])
            if len(bucket) < per_kol:
                bucket.append({
                    "text": c.text, "author": c.author, "platform": c.platform,
                    "category": c.category, "theme": c.theme, "likes": c.likes,
                })

        out = []
        for kol, total in sorted(totals.items(), key=lambda kv: -kv[1]):
            split = {v: n for k, v, n in topics if k == kol and v}
            out.append({
                "kol": kol, "total": total,
                "product_total": sum(split.values()),
                "topics": split,
                "comments": picked.get(kol, []),
            })
        return out
