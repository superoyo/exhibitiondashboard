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

from sqlalchemy import func, or_, select

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
# Bump this whenever _classify_prompt changes in a way that would label comments
# differently. Every comment stores the version that labelled it, so the next
# ordinary run re-labels anything older — no separate action to remember, and
# nothing is re-labelled when the rules have not moved. Same idea as
# TIEIN_VERSION, which redoes shots produced by an older algorithm.
CLASSIFY_VERSION = "rules2"
# Posts per Apify run. One run per post would multiply run overhead; one run for
# everything makes a single bad URL slower to isolate.
POSTS_PER_RUN = 20


# ---------------------------------------------------------------------------
# classification
# ---------------------------------------------------------------------------

def _classify_prompt(product_desc: str, batch: list) -> str:
    """The classifier. Ported by hand from references/comment-analysis.md — the
    skill file is an agent-context artifact and nothing in the app reads it.

    The example block is the load-bearing part. The examples that teach a
    BOUNDARY (a joke is not a complaint; talking about the clip is not talking
    about the product) are kept verbatim because those patterns hold for any
    product. The ones that touch the product are worded without naming a
    product category, because this prompt runs for perfume, food and household
    campaigns alike and a body-wash example would pull the others off course.
    """
    lines = "\n".join(f"{i}. {(c.text or '')[:400]}" for i, c in enumerate(batch, 1))
    return (
        f"สินค้าของแคมเปญ: {product_desc}\n\n"
        "จัดประเภทคอมเมนต์ใต้โพสต์รีวิวต่อไปนี้ ทีละอัน ตาม taxonomy:\n\n"
        "category (เลือก 1 ค่า):\n"
        "FAN = พูดถึงตัวครีเอเตอร์/ทักทาย/มุกตลก ไม่แตะสินค้า\n"
        "PRODUCT = พูดถึงสินค้า แบรนด์ หรือการใช้งาน\n"
        "INTENT = ตั้งใจซื้อ หรือถามช่องทางซื้อ/ราคา\n"
        "ECHO = เอาสโลแกนหรือมุกของแคมเปญไปเล่นต่อ\n"
        "NEG = เชิงลบต่อสินค้า แบรนด์ ครีเอเตอร์ หรือบ่นว่าขายของ\n"
        "QUESTION = คำถามทั่วไปที่ไม่เกี่ยวกับการซื้อ\n"
        "SPAM = บอท โฆษณาแฝง ลิงก์พนัน ไม่เกี่ยวข้อง\n\n"

        "กติกาเมื่อคอมเมนต์เข้าได้หลายหมวด — เลือกเจตนาเด่นสุด 'อันเดียว' "
        "ห้ามตอบหลายหมวด:\n"
        "· แตะสินค้า + บอกว่าจะซื้อ / ถามที่ซื้อ / ถามราคา → INTENT (ไม่ใช่ PRODUCT)\n"
        "· แตะสินค้า + บ่น ตำหนิ บอกว่าไม่เวิร์ก → NEG (ไม่ใช่ PRODUCT)\n"
        "· เล่นมุกหรือสโลแกนของแคมเปญ + แตะสินค้า → ECHO\n"
        "· คอมเมนต์ยาวหลายเจตนา → เลือกเจตนาที่เด่นที่สุด\n\n"

        "NEG ต้องมีการ 'ตำหนิ' จริง ไม่ใช่แค่ 'น้ำเสียงแรง':\n"
        "· มุกตลก หยอกล้อ แกล้งบ่น อีโมจิเยอะ สะกดยืด = FAN "
        "ถ้าไม่ได้ตำหนิสินค้า/แบรนด์/ครีเอเตอร์\n"
        "· พูดถึงการตัดต่อ เสียง เพลง มุมกล้อง ความยาวคลิป = FAN "
        "(พูดถึงคลิป ไม่ใช่สินค้า)\n"
        "· ประชด: 'ดีย์มากค่า' ในบริบทกำลังบ่น = NEG · ในบริบทชม = PRODUCT "
        "→ ยึดบริบททั้งประโยค ไม่ยึดคำเดี่ยว\n\n"

        "sentiment (ทิศทางต่อ 'สินค้า' เท่านั้น ไม่ใช่ต่อครีเอเตอร์):\n"
        "pos / neu / neg — ถ้า category เป็น FAN, QUESTION หรือ SPAM ให้ตอบ -\n"
        "neg ต้องมีการตำหนิ/ไม่พอใจสินค้าจริง · การเล่าสถานะเฉย ๆ = neu\n\n"

        "แยก 'ของที่ผู้คอมเมนต์ใช้อยู่หมด' ออกจาก 'สินค้าหมดในร้าน' "
        "— คำว่า 'หมด' ไม่ได้แปลว่าเชิงลบ:\n"
        "· 'ของที่ใช้อยู่หมดพอดี' / 'ขวดเก่าใช้หมดแล้ว' = ของตัวเองหมด "
        "ไม่ใช่การตำหนิ → sentiment neu และ theme ต้องไม่ใช่ หาซื้อยาก "
        "(มักเป็นสัญญาณว่ากำลังจะซื้อ)\n"
        "· 'หาซื้อไม่ได้' / 'ร้านไม่มีของ' / 'ของหมดทุกสาขา' = "
        "ปัญหาการกระจายสินค้าจริง → NEG|neg|หาซื้อยาก\n\n"

        "theme: ต้องเป็น 'แง่มุมของสินค้า' ที่เจาะจง "
        "ห้ามตอบคำกว้างอย่าง ทั่วไป / สินค้า / ดี / ชอบ\n"
        "ใช้คำเดิมให้ตรงกันทั้งชุดเพื่อให้นับรวมได้ ถ้าเข้ากรณีนี้ให้ใช้คำนี้: "
        "รสชาติ · กลิ่น · เนื้อสัมผัส · เห็นผล · ราคา · หาซื้อยาก · แพ็กเกจ · "
        "ปริมาณ · ระคายเคือง · ขายของ\n"
        "ถ้าไม่เข้าเลย ตั้งคำใหม่สั้น ๆ ได้ แต่ต้องเจาะจง · ไม่แตะสินค้าให้ตอบ -\n\n"

        "คอมเมนต์ภาษาจีน พม่า อังกฤษ: จัดหมวดตามเนื้อหาปกติ ไม่ใช่ SPAM "
        "(SPAM คือบอท ลิงก์พนัน โฆษณาแฝง ไม่ใช่ 'ภาษาที่อ่านไม่ออก')\n\n"

        "ตัวอย่างที่จัดถูกแล้ว ใช้เทียบ:\n"
        "\"ที่บ้านใช้ประจำเลย ใช้แล้วดีจริงค้าบ\"        → PRODUCT|pos|เห็นผล\n"
        "\"ได้เวลาเปลี่ยนมาใช้ตัวนี้แล้ว\"              → INTENT|pos|-\n"
        "\"ร้านไหนใกล้ฉันมีขายบ้าง~\"                  → INTENT|neu|หาซื้อยาก\n"
        "\"มันต้องดีน่าา\"                            → ECHO|pos|-\n"
        "\"ของที่ใช้อยู่หมดพอดี\"                      → PRODUCT|neu|-\n"
        "\"หาซื้อไม่ได้เลย ร้านแถวบ้านไม่มี\"             → NEG|neg|หาซื้อยาก\n"
        "\"เคยใช้แล้วไม่เห็นผล\"                       → NEG|neg|เห็นผล\n"
        "\"โอนค่าตัวมาด้วย !!\"                       → NEG|neg|ขายของ\n"
        "\"มู้ดเสียงคลิปคือ ขึ้นๆลงๆ\"                  → FAN|-|-\n"
        "\"อยู่กับข้าเอ็งเหมือนไก่จี๊ดริดในก้านกล้วย\"     → FAN|-|-\n"
        "\"ตกใจค้าบ มากอดเค้าเลยค้าบ\"                → FAN|-|-\n\n"

        "ตอบบรรทัดละ 1 คอมเมนต์ รูปแบบ: เลข|CATEGORY|sentiment|theme\n"
        "ห้ามมีข้อความอื่น ต้องตอบให้ครบทุกเลข\n\n"
        f"คอมเมนต์:\n{lines}"
    )


# a theme must have at least one letter or digit — dashes, dots and stray
# punctuation are the model's way of saying "no theme", in several spellings
_THEME_WORD = re.compile(r"[^\W_]", re.UNICODE)

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
        # A theme has to contain an actual word. The model answers the
        # no-theme case with a dash, but not always exactly one: "---" slipped
        # past a `theme in {"-"}` check and became the second most common
        # "theme" on the panel, with 17 comments behind it.
        if not _THEME_WORD.search(theme) or theme.lower() in {"none", "null", "ไม่มี", "ทั่วไป"}:
            theme = None
        out[n] = (cat, sentiment, theme)
    return out


def classify_pending(campaign: str, product_desc: str, st: Optional[dict] = None,
                     total: int = 0) -> int:
    """Label every comment of the campaign that needs it — never labelled, or
    labelled by an older version of the rules.

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
                .where(ReportComment.campaign == campaign,
                       # never labelled, or labelled by older rules. coalesce
                       # covers rows stored before the column existed, whose
                       # version is NULL and must count as "older".
                       or_(ReportComment.category.is_(None),
                           func.coalesce(ReportComment.rules_version, "")
                           != CLASSIFY_VERSION))
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
                    row.category, row.sentiment, row.theme = got
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

def _not_creator():
    """Excludes a KOL's replies under their own post.

    Replies are collected, which means the creator's own answers land in the
    table. Counting those as product sentiment lets the brand vote for itself:
    a KOL replying "อร่อยจริง ๆ ค่ะ" would register as audience praise.
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
            "sentiment": c.sentiment, "theme": c.theme, "likes": c.likes,
            "posted_at": c.posted_at.isoformat() if c.posted_at else None}


def list_comments(campaign: str, sentiment: Optional[str] = None,
                  offset: int = 0, limit: int = 20) -> dict:
    """One page of product-related comments, newest-liked first.

    Paged on the server rather than in the browser: a campaign's product
    comments run into the thousands, and shipping all of them so the client can
    slice twenty is the kind of thing that works fine until the campaign that
    matters most is the one that breaks it.
    """
    limit = max(1, min(limit, 100))
    where = [ReportComment.campaign == campaign,
             ReportComment.category.in_(PRODUCT_CATEGORIES),
             _not_creator()]
    if sentiment in SENTIMENTS:
        where.append(ReportComment.sentiment == sentiment)

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
    """Category split, product sentiment and top themes. The comments
    themselves come from list_comments(), which pages them.

    Product sentiment excludes the creators' own replies; the category split
    does not, so `total` still matches what was collected."""
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
                   ReportComment.category.in_(PRODUCT_CATEGORIES),
                   _not_creator())
            .group_by(ReportComment.sentiment)).all()
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
            "unclassified": by_cat.get(None, 0),
            "replies": replies,
            "creator_replies": creator_replies,
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
                   ReportComment.category.in_(PRODUCT_CATEGORIES),
                   _not_creator())
            .group_by(ReportComment.kol_username, ReportComment.sentiment)).all()
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
