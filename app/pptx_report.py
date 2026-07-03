"""Generate a per-campaign PowerPoint report (the "📥 PowerPoint" button).

Built ON TOP of the agency's own deck design: app/assets/report_template.pptx
is the real P2026-027 PAO file with its slides stripped out but every layout,
master, background art and embedded font kept. Slides are recreated at the
exact coordinates measured from the original, so the output matches the format
the team already uses:

  1. cover  — "Influencer Report / Campaign : <name>"   (layout 1 artwork)
  2. group divider slides when the roster has >1 big group (layout 1)
  3. one slide per post (layout 2): KOL name, avatar, post date, screenshot,
     link at the bottom, and the KPI/stat table (KPI value left blank; stats
     the scraper can't fetch left blank). A KOL's platforms are consecutive.
  4. closing "Thank You" slide (layout 1)
"""
from __future__ import annotations

import hashlib
import io
import logging
import pathlib
from typing import Optional

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Emu, Pt
from sqlalchemy import select

from app.db import session_scope
from app.models import Campaign, ImageCache, ReportKol, ReportPost
from app.report_refresh import kol_links

log = logging.getLogger("pptx_report")

TEMPLATE = pathlib.Path(__file__).resolve().parent / "assets" / "report_template.pptx"
FONT = "Leelawadee"

WHITE = RGBColor(0xFF, 0xFF, 0xFF)
BLACK = RGBColor(0x00, 0x00, 0x00)
TEAL = RGBColor(0x0D, 0x9B, 0xB3)     # KPI header cell (from the original deck)
CELL_GRAY = RGBColor(0xE0, 0xE6, 0xEC)

PLAT_LABEL = {"tiktok": "TikTok", "facebook": "Facebook", "instagram": "Instagram",
              "youtube": "YouTube", "x": "X (Twitter)", "line": "LINE",
              "website": "Website", "other": "Link"}
PLAT_ORDER = {"tiktok": 0, "facebook": 1, "instagram": 2, "youtube": 3,
              "x": 4, "line": 5, "website": 6, "other": 7}


def _fmt(n) -> str:
    return f"{int(n):,}" if n else ""


def _stat_rows(platform: str, p: Optional[ReportPost]) -> list:
    """(label, value) rows exactly as the team lays them out per platform —
    blank where the scraper has no data."""
    if platform == "facebook":
        eng = (p.likes + p.comments + p.shares) if p else 0
        return [("Reach", ""), ("View", _fmt(p.views) if p else ""),
                ("Engagement", _fmt(eng) if p else ""),
                ("Reactions", _fmt(p.likes) if p else ""),
                ("Comments", _fmt(p.comments) if p else ""),
                ("Shares", _fmt(p.shares) if p else "")]
    if platform == "instagram":
        return [("View", _fmt(p.views) if p else ""), ("Like", _fmt(p.likes) if p else ""),
                ("Comments", _fmt(p.comments) if p else ""), ("Shares", "")]
    if platform == "youtube":
        return [("View", _fmt(p.views) if p else ""), ("Like", _fmt(p.likes) if p else ""),
                ("Comments", _fmt(p.comments) if p else "")]
    if platform == "x":
        return [("View", _fmt(p.views) if p else ""), ("Like", _fmt(p.likes) if p else ""),
                ("Comments", _fmt(p.comments) if p else ""),
                ("Reposts", _fmt(p.shares) if p else "")]
    return [("Impression", ""), ("View", _fmt(p.views) if p else ""), ("Reach", ""),
            ("Like", _fmt(p.likes) if p else ""), ("Comment", _fmt(p.comments) if p else ""),
            ("Share", _fmt(p.shares) if p else ""), ("Save", _fmt(p.saves) if p else "")]


def _image_bytes(session, url: Optional[str]) -> Optional[bytes]:
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
    except Exception:  # noqa: BLE001 — slide simply omits the picture
        pass
    return None


def _circle_png(img: bytes) -> Optional[io.BytesIO]:
    """Center-crop to a circle (the original deck uses round avatars)."""
    try:
        from PIL import Image, ImageDraw
        im = Image.open(io.BytesIO(img)).convert("RGBA")
        side = min(im.size)
        im = im.crop(((im.width - side) // 2, (im.height - side) // 2,
                      (im.width + side) // 2, (im.height + side) // 2))
        mask = Image.new("L", (side, side), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, side, side), fill=255)
        im.putalpha(mask)
        out = io.BytesIO()
        im.save(out, "PNG")
        out.seek(0)
        return out
    except Exception:  # noqa: BLE001
        return None


def _layout(prs, n: int):
    for lay in prs.slide_layouts:
        if str(lay.part.partname).endswith(f"slideLayout{n}.xml"):
            return lay
    return prs.slide_layouts[0]


def _add(prs, layout):
    s = prs.slides.add_slide(layout)
    for shp in list(s.shapes):  # drop cloned layout placeholders (empty boxes)
        if shp.is_placeholder:
            shp._element.getparent().remove(shp._element)
    return s


def _txt(slide, x, y, w, h, text, size, *, bold=False, color=BLACK, link=None):
    box = slide.shapes.add_textbox(Emu(x), Emu(y), Emu(w), Emu(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    run = tf.paragraphs[0].add_run()
    run.text = text
    f = run.font
    f.size = Pt(size)
    f.bold = bold
    f.color.rgb = color
    f.name = FONT
    if link:
        try:
            run.hyperlink.address = link
        except Exception:  # noqa: BLE001
            pass
    return box


def _fit_picture(slide, img: bytes, bx, by, bw, bh):
    """Place the screenshot inside the original deck's picture box, keeping
    aspect and centering (their screenshots are portrait phone captures)."""
    try:
        from PIL import Image
        iw, ih = Image.open(io.BytesIO(img)).size
        scale = min(bw / iw, bh / ih)
        w, h = int(iw * scale), int(ih * scale)
        slide.shapes.add_picture(io.BytesIO(img), Emu(bx + (bw - w) // 2),
                                 Emu(by + (bh - h) // 2), Emu(w), Emu(h))
    except Exception:  # noqa: BLE001
        pass


def _stat_table(slide, rows: list):
    """KPI + stat table at the original deck's position/format: teal KPI header
    cell, gray blank KPI value, bold labels, 0.5" rows."""
    n = len(rows) + 1
    x, y, w = 7360297, 1686539, 3883100
    row_h = 457200
    gf = slide.shapes.add_table(n, 2, Emu(x), Emu(y), Emu(w), Emu(row_h * n))
    tbl = gf.table
    tbl.first_row = False
    tbl.horz_banding = False
    tbl.columns[0].width = Emu(w // 2)
    tbl.columns[1].width = Emu(w - w // 2)
    for i in range(n):
        tbl.rows[i].height = Emu(row_h)

    def set_cell(cell, text, *, bold, fill, color=BLACK, size=14):
        cell.fill.solid()
        cell.fill.fore_color.rgb = fill
        tf = cell.text_frame
        tf.word_wrap = False
        run = tf.paragraphs[0].add_run()
        run.text = text
        f = run.font
        f.size = Pt(size)
        f.bold = bold
        f.color.rgb = color
        f.name = FONT

    set_cell(tbl.cell(0, 0), "KPI", bold=True, fill=TEAL, color=WHITE, size=16)
    set_cell(tbl.cell(0, 1), "", bold=False, fill=CELL_GRAY)
    for i, (label, val) in enumerate(rows, start=1):
        set_cell(tbl.cell(i, 0), label, bold=True, fill=WHITE)
        set_cell(tbl.cell(i, 1), val, bold=False, fill=WHITE)


def build_pptx(campaign_key: str) -> tuple[io.BytesIO, str]:
    """Build the deck from the agency template; returns (bytes, filename)."""
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

        prs = Presentation(str(TEMPLATE))
        lay_dark = _layout(prs, 1)   # cover / divider / thank-you artwork
        lay_stat = _layout(prs, 2)   # per-post artwork

        # ---- 1. cover (positions measured from the original slide 1) --------
        s = _add(prs, lay_dark)
        _txt(s, 4410075, 2383644, 7124700, 1397781,
             "Influencer Report", 44, color=WHITE)
        _txt(s, 4410075, 3781425, 7124700, 640812,
             f"Campaign : {camp_name}", 18, color=WHITE)

        # ---- 2-3. dividers + per-post slides --------------------------------
        groups: dict[str, list[ReportKol]] = {}
        for k in kols:
            groups.setdefault(k.content_group or "KOL", []).append(k)
        show_dividers = len(groups) > 1

        for gname, gkols in groups.items():
            if show_dividers:  # original slide 9 geometry
                s = _add(prs, lay_dark)
                _txt(s, 4914900, 2469369, 5981700, 1397781, gname, 44, color=WHITE)
                _txt(s, 4914900, 3867150, 5981700, 640812,
                     f"{len(gkols)} KOLs", 18, color=WHITE)

            for k in gkols:
                links = kol_links(k) or [{"platform": "tiktok", "url": k.url or "",
                                          "handle": k.username.lower()}]
                links = sorted(links, key=lambda l: PLAT_ORDER.get(l["platform"], 9))
                avatar = _image_bytes(session, k.avatar_url)
                avatar_png = _circle_png(avatar) if avatar else None
                for ln in links:
                    plat = ln["platform"]
                    p = posts_by.get((k.username.lower(), plat))
                    s = _add(prs, lay_stat)

                    # geometry measured from the original slide 2
                    if avatar_png:
                        avatar_png.seek(0)
                        s.shapes.add_picture(avatar_png, Emu(187587), Emu(160544),
                                             Emu(879810), Emu(879810))
                    name = k.display or k.username
                    _txt(s, 1067397, 161170, 5789644, 662150, name, 20)
                    posted = (p.posted_at.strftime("%d %b %Y")
                              if p and p.posted_at else "")
                    _txt(s, 1067397, 519577, 5681886, 536575,
                         f"{PLAT_LABEL.get(plat, plat)} · Post Date: {posted}", 11)

                    shot = _image_bytes(session, (p.cover_url if p else None))
                    if shot:
                        _fit_picture(s, shot, 908482, 1349012, 2628527, 4569755)

                    _stat_table(s, _stat_rows(plat, p))

                    if ln.get("url"):
                        _txt(s, 187587, 6277800, 10372464, 580200,
                             f"Link : {ln['url']}", 12, link=ln["url"])

        # ---- 4. thank you (original slide 16 geometry) -----------------------
        s = _add(prs, lay_dark)
        _txt(s, 5972175, 2621769, 4219575, 1397781, "Thank You", 44, color=WHITE)

        buf = io.BytesIO()
        prs.save(buf)
        buf.seek(0)
        return buf, f"{camp_name} - Influencer Report.pptx"
