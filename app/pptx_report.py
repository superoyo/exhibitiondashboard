"""Generate a per-campaign PowerPoint report (the "📥 PowerPoint" button).

Deck structure mirrors the agency's manual reports (e.g. P2026-027 PAO):
  1. cover  — "Influencer Report / Campaign : <name>"
  2. group divider slides (only when the roster has >1 big group)
  3. one slide per post — KOL name, link, post date, screenshot, KPI (blank),
     platform-appropriate stat rows; a KOL's platforms appear consecutively
  4. closing "Thank You" slide

Stats the scraper can't fetch are left blank (per the team's convention), and
the KPI value is always blank for the team to fill in.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import io
import logging
from typing import Optional

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Emu, Inches, Pt
from sqlalchemy import select

from app import config
from app.db import session_scope
from app.models import Campaign, ImageCache, ReportKol, ReportPost
from app.report_refresh import kol_links

log = logging.getLogger("pptx_report")

NAVY = RGBColor(0x1E, 0x27, 0x61)
INK = RGBColor(0x0F, 0x17, 0x2A)
MUTED = RGBColor(0x64, 0x74, 0x8B)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
LINK_BLUE = RGBColor(0x25, 0x63, 0xEB)
BOX_BG = RGBColor(0xF1, 0xF5, 0xF9)

PLAT_LABEL = {"tiktok": "TikTok", "facebook": "Facebook", "instagram": "Instagram",
              "youtube": "YouTube", "x": "X (Twitter)", "line": "LINE",
              "website": "Website", "other": "Link"}
PLAT_ORDER = {"tiktok": 0, "facebook": 1, "instagram": 2, "youtube": 3,
              "x": 4, "line": 5, "website": 6, "other": 7}


def _fmt(n) -> str:
    return f"{int(n):,}" if n else ""


def _stat_rows(platform: str, p: Optional[ReportPost]) -> list:
    """(label, value-or-blank) rows per platform — blanks where the scraper has
    no data, matching the team's manual report conventions."""
    v = (lambda x: _fmt(x)) if p else (lambda x: "")
    if platform == "facebook":
        eng = (p.likes + p.comments + p.shares) if p else 0
        return [("Reach", ""), ("View", v(p.views if p else 0)),
                ("Engagement", _fmt(eng) if p else ""),
                ("Reactions", v(p.likes if p else 0)),
                ("Comments", v(p.comments if p else 0)),
                ("Shares", v(p.shares if p else 0))]
    if platform == "instagram":
        return [("View", v(p.views if p else 0)), ("Like", v(p.likes if p else 0)),
                ("Comments", v(p.comments if p else 0)), ("Shares", "")]
    if platform == "youtube":
        return [("View", v(p.views if p else 0)), ("Like", v(p.likes if p else 0)),
                ("Comments", v(p.comments if p else 0))]
    if platform == "x":
        return [("View", v(p.views if p else 0)), ("Like", v(p.likes if p else 0)),
                ("Comments", v(p.comments if p else 0)),
                ("Reposts", v(p.shares if p else 0))]
    # tiktok / default
    return [("Impression", ""), ("View", v(p.views if p else 0)), ("Reach", ""),
            ("Like", v(p.likes if p else 0)), ("Comment", v(p.comments if p else 0)),
            ("Share", v(p.shares if p else 0)), ("Save", v(p.saves if p else 0))]


def _image_bytes(session, url: Optional[str]) -> Optional[bytes]:
    """Post screenshot bytes — from the image cache, else one quick fetch."""
    if not url:
        return None
    h = hashlib.sha256(url.encode("utf-8")).hexdigest()[:40]
    row = session.get(ImageCache, h)
    if row and row.data:
        return row.data
    try:
        import httpx
        r = httpx.get(url, timeout=8, follow_redirects=True, headers={
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/125.0.0.0 Safari/537.36"),
            "Referer": "https://www.tiktok.com/"})
        ct = (r.headers.get("content-type") or "").lower()
        if r.status_code == 200 and r.content and ct.startswith("image/"):
            return r.content
    except Exception:  # noqa: BLE001 — slide falls back to a placeholder box
        pass
    return None


def _txt(slide, x, y, w, h, text, size, *, bold=False, color=INK,
         align=PP_ALIGN.LEFT, link=None, wrap=True):
    box = slide.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.word_wrap = wrap
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    para = tf.paragraphs[0]
    para.alignment = align
    run = para.add_run()
    run.text = text
    f = run.font
    f.size = Pt(size)
    f.bold = bold
    f.color.rgb = color
    f.name = "Arial"
    if link:
        try:
            run.hyperlink.address = link
        except Exception:  # noqa: BLE001 — malformed URLs just render as text
            pass
    return box


def _fill(slide, color):
    bg = slide.background
    bg.fill.solid()
    bg.fill.fore_color.rgb = color


SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)


def build_pptx(campaign_key: str) -> tuple[io.BytesIO, str]:
    """Build the deck; returns (file bytes, download filename)."""
    with session_scope() as session:
        camp = session.get(Campaign, campaign_key)
        camp_name = camp.name if camp else campaign_key
        kols = session.scalars(
            select(ReportKol)
            .where(ReportKol.active.is_(True), ReportKol.campaign == campaign_key)
            .order_by(ReportKol.content_group, ReportKol.subgroup, ReportKol.username)
        ).all()
        posts_by = {}
        for p in session.scalars(select(ReportPost).where(
                ReportPost.campaign == campaign_key)).all():
            key = (p.username.lower(), p.platform or "tiktok")
            if key not in posts_by or p.views > posts_by[key].views:
                posts_by[key] = p

        prs = Presentation()
        prs.slide_width = SLIDE_W
        prs.slide_height = SLIDE_H
        blank = prs.slide_layouts[6]

        # ---- 1. cover -------------------------------------------------------
        s = prs.slides.add_slide(blank)
        _fill(s, NAVY)
        _txt(s, Inches(0.9), Inches(2.5), Inches(11.5), Inches(1.2),
             "Influencer Report", 48, bold=True, color=WHITE)
        _txt(s, Inches(0.9), Inches(3.8), Inches(11.5), Inches(0.8),
             f"Campaign : {camp_name}", 24, color=WHITE)
        _txt(s, Inches(0.9), Inches(6.4), Inches(11.5), Inches(0.5),
             f"Far East Fame Line · {dt.datetime.now(config.TZ).strftime('%d %b %Y')}",
             14, color=RGBColor(0xCA, 0xDC, 0xFC))

        # ---- 2-3. group dividers + per-post slides ---------------------------
        groups: dict[str, list[ReportKol]] = {}
        for k in kols:
            groups.setdefault(k.content_group or "KOL", []).append(k)
        show_dividers = len(groups) > 1

        for gname, gkols in groups.items():
            if show_dividers:
                s = prs.slides.add_slide(blank)
                _fill(s, NAVY)
                _txt(s, Inches(0.9), Inches(3.0), Inches(11.5), Inches(1.1),
                     gname, 40, bold=True, color=WHITE)
                _txt(s, Inches(0.9), Inches(4.2), Inches(11.5), Inches(0.6),
                     f"{len(gkols)} KOLs", 20, color=RGBColor(0xCA, 0xDC, 0xFC))

            for k in gkols:
                links = kol_links(k) or [{"platform": "tiktok", "url": k.url or "",
                                          "handle": k.username.lower()}]
                links = sorted(links, key=lambda l: PLAT_ORDER.get(l["platform"], 9))
                for ln in links:
                    plat = ln["platform"]
                    p = posts_by.get((k.username.lower(), plat))
                    s = prs.slides.add_slide(blank)
                    _fill(s, WHITE)

                    # left: post screenshot (or placeholder)
                    img = _image_bytes(session, (p.cover_url if p else None))
                    box_x, box_y = Inches(0.7), Inches(0.9)
                    box_w, box_h = Inches(3.4), Inches(6.0)
                    if img:
                        try:
                            from PIL import Image as _Img
                            iw, ih = _Img.open(io.BytesIO(img)).size
                            scale = min(box_w / iw, box_h / ih)
                            w, hh = Emu(int(iw * scale)), Emu(int(ih * scale))
                            s.shapes.add_picture(
                                io.BytesIO(img),
                                box_x + Emu(int((box_w - w) / 2)),
                                box_y + Emu(int((box_h - hh) / 2)), w, hh)
                        except Exception:  # noqa: BLE001
                            img = None
                    if not img:
                        ph = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, box_x, box_y, box_w, box_h)
                        ph.fill.solid()
                        ph.fill.fore_color.rgb = BOX_BG
                        ph.line.fill.background()
                        tf = ph.text_frame
                        tf.text = "ตัวอย่างคอนเทนต์"
                        tf.paragraphs[0].runs[0].font.size = Pt(12)
                        tf.paragraphs[0].runs[0].font.color.rgb = MUTED

                    # right: KOL + platform + link + date
                    rx = Inches(4.6)
                    rw = Inches(8.0)
                    _txt(s, rx, Inches(0.7), rw, Inches(0.6),
                         k.display or k.username, 28, bold=True)
                    _txt(s, rx, Inches(1.35), rw, Inches(0.4),
                         PLAT_LABEL.get(plat, plat), 16, bold=True, color=NAVY)
                    if ln.get("url"):
                        _txt(s, rx, Inches(1.85), rw, Inches(0.7),
                             f"Link : {ln['url']}", 11, color=LINK_BLUE,
                             link=ln["url"])
                    posted = (p.posted_at.strftime("%d %b %Y")
                              if p and p.posted_at else "")
                    _txt(s, rx, Inches(2.6), rw, Inches(0.4),
                         f"Post Date : {posted}", 13, color=MUTED)

                    # KPI (blank, for the team to fill) + stat rows
                    y = Inches(3.2)
                    rows = [("KPI", "")] + _stat_rows(plat, p)
                    for label, val in rows:
                        _txt(s, rx, y, Inches(2.6), Inches(0.38), label, 14,
                             color=MUTED)
                        _txt(s, rx + Inches(2.8), y, Inches(3.4), Inches(0.38),
                             val, 16, bold=True, align=PP_ALIGN.RIGHT)
                        y += Inches(0.46)

        # ---- 4. thank you ----------------------------------------------------
        s = prs.slides.add_slide(blank)
        _fill(s, NAVY)
        _txt(s, Inches(0.9), Inches(3.1), Inches(11.5), Inches(1.3),
             "Thank You", 54, bold=True, color=WHITE)

        buf = io.BytesIO()
        prs.save(buf)
        buf.seek(0)
        fname = f"{camp_name} - Influencer Report.pptx"
        return buf, fname
