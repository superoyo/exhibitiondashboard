"""Read a team member's promotion-page quota sheet and count it.

The Promotion Page Package page (/promotion-packages) is a read-only overview:
clients pre-buy posting quotas on Facebook promotion pages, each teammate tracks
their deals in their OWN spreadsheet, and this module turns such a workbook into
"which page, how many posts bought, how many used, which links". We never write
to the files, and money columns are ignored by decision (2026-11-17) — counts
and links only.

Nobody on the team lays the sheet out the same way, so nothing here is keyed to
cell positions. Each worksheet is read by its HEADER WORDS. Four real layouts
shaped this (and are reproduced in scripts/verify-promo.py):

  A  one sheet per page; "No. Post" = "Sale Here 7"; one "Link Post" cell
     holding FB+IG+X; a "Used" tick column on some sheets only; single-cell
     section rows ("SALZ", "Complimentary VDO*5 Post").
  B  every page on one sheet; slot label in "Influencer" ("Event Pass 1
     Post"); the link sits in whichever "Post 1".."Post 13" column matches the
     slot; extra platforms in "Post all platform".
  C  page name in a vertically merged "Name" cell; slot label "Post 1/6" (the
     6 is the quota, and the sheet may list fewer rows than that); a STATUS
     dropdown ("Post", "Wait idea").
  D  one sheet per page; slot label is a bare number under "Post"; "Status" =
     "Published"; a summary box above the table that is NOT trusted — it was
     stale in the real file, which is the reason to count the rows instead.

A slot is "used" when the team says so (Used tick, or a status such as Post /
Published) or when a post link is present; "reserved" when it names a brand or
job but is not used; "free" otherwise.
"""
from __future__ import annotations

import datetime as dt
import io
import re
from typing import Any, Optional

MAX_HEADER_SCAN = 40
MAX_TEXT = 300

_URL = re.compile(r"https?://[^\s<>\"']+", re.I)

# Header vocabulary → the role a column plays. Order matters only for `slot`,
# resolved separately below.
_H_LINK = re.compile(r"^(link\s*post|link|ลิงก์.*|post\s*\d+)$", re.I)
_H_EXTRA = re.compile(r"all\s*platform", re.I)
_H_SLOT_STRONG = re.compile(r"^no\.?\s*post$", re.I)
_H_SLOT_INFLU = re.compile(r"^influencer$", re.I)
_H_SLOT_BARE = re.compile(r"^post$", re.I)
_H_PAGE = re.compile(r"^(name|page|เพจ)$", re.I)
_H_ACCOUNT = re.compile(r"^(account|brand|แบรนด์)$", re.I)
_H_CAMPAIGN = re.compile(r"^(campaign|product|งาน|สินค้า)$", re.I)
_H_BUYER = re.compile(r"^(influ\s*buyer|buyer|ผู้ดูแล)$", re.I)
_H_DATE = re.compile(r"^(post\s*date|วันที่ลง.*|วันลง.*)$", re.I)
_H_EXPIRY = re.compile(r"(หมดอายุ|หมดเขต|expire|expiry)", re.I)
_H_STATUS = re.compile(r"^(status|สถานะ)$", re.I)
_H_USED = re.compile(r"^(used|ใช้แล้ว)$", re.I)
_H_NOTE = re.compile(r"^(note|notes|remark|remarks|conditions?|หมายเหตุ)$", re.I)
_HEADER_WORDS = (_H_LINK, _H_EXTRA, _H_SLOT_STRONG, _H_SLOT_INFLU, _H_SLOT_BARE,
                 _H_PAGE, _H_ACCOUNT, _H_CAMPAIGN, _H_BUYER, _H_DATE, _H_EXPIRY,
                 _H_STATUS, _H_USED, _H_NOTE)

_USED_STATUS = {"post", "posted", "publish", "published", "done", "complete",
                "completed", "used", "ลงแล้ว", "โพสต์แล้ว", "โพสแล้ว", "เรียบร้อย"}
_TRUTHY = {"true", "yes", "y", "1", "x", "✓", "✔", "☑", "used", "ใช้แล้ว"}

# Notes about payment are out of scope with the money columns.
_MONEY_NOTE = re.compile(r"(จ่าย|ยอด|บูส|boost|budget|invoice|\bpo\b|บาท|ราคา)", re.I)

_LABEL_OF_N = re.compile(r"^post\s*(\d+)\s*/\s*(\d+)$", re.I)
_LABEL_NAMED = re.compile(r"^(.*?)[\s#]*(\d+)(?:\s*post)?$", re.I)


def _text(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (dt.datetime, dt.date)):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return re.sub(r"[​﻿]", "", str(v)).strip()


def _norm(v: Any) -> str:
    return re.sub(r"\s+", " ", _text(v)).strip().lower()


def platform_of(url: str) -> str:
    host = re.sub(r"^https?://(www\.|m\.|web\.)?", "", url.lower()).split("/")[0]
    if "facebook.com" in host or host in ("fb.com", "fb.watch", "fb.me"):
        return "facebook"
    if "instagram.com" in host:
        return "instagram"
    if host in ("x.com", "twitter.com", "t.co"):
        return "x"
    if "tiktok.com" in host:
        return "tiktok"
    if "youtube.com" in host or host == "youtu.be":
        return "youtube"
    if "line.me" in host:
        return "line"
    return "website"


def _links_in(cells: list) -> list[str]:
    """Every post URL in the given (value, hyperlink) cells, in order, unique.

    A cell's hyperlink target and its visible text are usually the same URL
    give or take a trailing "#" or "/", so those are compared loosely."""
    out: list[str] = []
    seen: set[str] = set()
    for value, hyper in cells:
        found = _URL.findall(_text(value))
        if hyper and re.match(r"https?://", hyper, re.I):
            found.insert(0, hyper)
        for u in found:
            u = u.rstrip(".,;)")
            key = u.rstrip("#?/").lower()
            if key not in seen:
                seen.add(key)
                out.append(u)
    return out


def _date_of(v: Any) -> tuple[str, Optional[str]]:
    """(text as written, ISO date when the cell is a real date)."""
    if isinstance(v, dt.datetime):
        return v.strftime("%Y-%m-%d"), v.date().isoformat()
    if isinstance(v, dt.date):
        return v.isoformat(), v.isoformat()
    return _text(v)[:MAX_TEXT], None


class _Sheet:
    """Cell values + hyperlinks of one worksheet, 0-indexed."""

    def __init__(self, ws, ws_formulas=None):
        self.title = (ws.title or "").strip()
        self.rows: list[list[Any]] = []
        self.links: dict[tuple[int, int], str] = {}
        for r, row in enumerate(ws.iter_rows()):
            vals = []
            for c, cell in enumerate(row):
                vals.append(cell.value)
                target = getattr(getattr(cell, "hyperlink", None), "target", None)
                if target:
                    self.links[(r, c)] = target
            self.rows.append(vals)
        # =HYPERLINK("url","text") keeps its URL only in the formula text.
        if ws_formulas is not None:
            for r, row in enumerate(ws_formulas.iter_rows()):
                for c, cell in enumerate(row):
                    v = cell.value
                    if isinstance(v, str) and v.startswith("=") and "HYPERLINK" in v.upper():
                        m = _URL.search(v)
                        if m and (r, c) not in self.links:
                            self.links[(r, c)] = m.group(0).rstrip('",)')
        # Top-left value of every merged block, for the vertically merged page
        # name column. Kept apart from `rows` so a merged cell is not mistaken
        # for a value typed on each row.
        self.merged: dict[tuple[int, int], Any] = {}
        for rng in ws.merged_cells.ranges:
            top = self.get(rng.min_row - 1, rng.min_col - 1)
            for r in range(rng.min_row - 1, rng.max_row):
                for c in range(rng.min_col - 1, rng.max_col):
                    self.merged[(r, c)] = top

    def get(self, r: int, c: Optional[int]) -> Any:
        if c is None or r >= len(self.rows) or c >= len(self.rows[r]):
            return None
        return self.rows[r][c]

    def filled(self, r: int, c: Optional[int]) -> Any:
        v = self.get(r, c)
        if v in (None, "") and c is not None:
            return self.merged.get((r, c))
        return v

    def cell(self, r: int, c: int) -> tuple[Any, Optional[str]]:
        return self.get(r, c), self.links.get((r, c))


def _find_header(sheet: _Sheet) -> Optional[int]:
    best, best_score = None, 0
    for r in range(min(MAX_HEADER_SCAN, len(sheet.rows))):
        cells = [_norm(v) for v in sheet.rows[r]]
        if not any(_H_LINK.match(c) for c in cells if c):
            continue
        score = sum(1 for c in cells if c and any(p.search(c) for p in _HEADER_WORDS))
        if score > best_score:
            best, best_score = r, score
    return best if best_score >= 2 else None


def _columns(sheet: _Sheet, header: int) -> dict:
    cols: dict[str, Any] = {"link": [], "extra": [], "note": []}
    single = {"page": _H_PAGE, "account": _H_ACCOUNT, "campaign": _H_CAMPAIGN,
              "buyer": _H_BUYER, "date": _H_DATE, "expiry": _H_EXPIRY,
              "status": _H_STATUS, "used": _H_USED}
    slot_rank: dict[int, int] = {}
    for c, raw in enumerate(sheet.rows[header]):
        h = _norm(raw)
        if not h:
            continue
        if _H_EXTRA.search(h):
            cols["extra"].append(c)
        elif _H_SLOT_STRONG.match(h):
            slot_rank.setdefault(0, c)
        elif _H_SLOT_INFLU.match(h):
            slot_rank.setdefault(1, c)
        elif _H_SLOT_BARE.match(h):
            slot_rank.setdefault(2, c)
        elif _H_LINK.match(h):
            cols["link"].append(c)
        elif _H_NOTE.match(h):
            cols["note"].append(c)
        else:
            for key, pat in single.items():
                if key not in cols and pat.search(h):
                    cols[key] = c
                    break
    if slot_rank:
        cols["slot"] = slot_rank[min(slot_rank)]
    return cols


def _parse_label(raw: Any) -> Optional[tuple[str, int, Optional[int]]]:
    """(page named in the label, slot number, quota hint) or None."""
    if isinstance(raw, bool) or raw is None:
        return None
    if isinstance(raw, (int, float)):
        return ("", int(raw), None) if float(raw).is_integer() and 0 < raw < 1000 else None
    s = re.sub(r"\s+", " ", _text(raw))
    if not s:
        return None
    m = _LABEL_OF_N.match(s)
    if m:
        return "", int(m.group(1)), int(m.group(2))
    if s.isdigit():
        return "", int(s), None
    m = _LABEL_NAMED.match(s)
    if m and m.group(1).strip():
        return m.group(1).strip(" -:#"), int(m.group(2)), None
    return None


def _used_flag(v: Any) -> Optional[bool]:
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return v
    return _norm(v) in _TRUTHY


def _parse_sheet(sheet: _Sheet, index: int, packs: dict, warnings: list) -> None:
    header = _find_header(sheet)
    if header is None:
        return
    cols = _columns(sheet, header)
    if "slot" not in cols:
        warnings.append(f"ชีต \"{sheet.title}\" มีคอลัมน์ลิงก์แต่ไม่พบคอลัมน์ลำดับโพสต์ — ข้ามชีตนี้")
        return
    has_date_col = "date" in cols
    known = {cols[k] for k in ("slot", "page") if k in cols}
    section = ""

    for r in range(header + 1, len(sheet.rows)):
        label = _parse_label(sheet.get(r, cols["slot"]))
        if label is None:
            # A lone text cell is a section banner ("SALZ", "Complimentary VDO").
            texts = {_text(v) for c, v in enumerate(sheet.rows[r])
                     if c not in known and _text(v)}
            if len(texts) == 1:
                t = next(iter(texts))
                if 2 <= len(t) <= 60 and not t.replace(".", "").isdigit() and not _URL.search(t):
                    section = t
            continue

        page_in_label, number, quota_hint = label
        page = (_text(sheet.filled(r, cols.get("page"))) or page_in_label
                or sheet.title or "ไม่ระบุเพจ")
        page = re.sub(r"\s+", " ", page)[:120]
        key = page.lower()
        if key not in packs:
            packs[key] = {"page": page, "expiry": "", "quota_hint": 0, "slots": []}
        pack = packs[key]
        if quota_hint:
            pack["quota_hint"] = max(pack["quota_hint"], quota_hint)

        main = _links_in([sheet.cell(r, c) for c in cols["link"]])
        # "Post all platform" repeats the main post in another URL form; take
        # from it only the platforms the main link column did not give.
        have = {platform_of(u) for u in main}
        links = main + [u for u in _links_in([sheet.cell(r, c) for c in cols["extra"]])
                        if platform_of(u) not in have]
        account = _text(sheet.get(r, cols.get("account")))[:MAX_TEXT]
        campaign = re.sub(r"\s*\n\s*", " · ", _text(sheet.get(r, cols.get("campaign"))))[:MAX_TEXT]
        buyer = _text(sheet.get(r, cols.get("buyer")))[:80]
        date_text, date_iso = _date_of(sheet.get(r, cols.get("date")))

        # Without a Post Date column, the expiry column doubles as one: the
        # block's first row carries the pack's expiry, later rows a post date.
        exp_text, exp_iso = _date_of(sheet.get(r, cols.get("expiry")))
        if exp_text:
            if not pack["slots"] or has_date_col:
                pack["expiry"] = pack["expiry"] or (exp_iso or exp_text)
            elif not has_date_col:
                date_text, date_iso = exp_text, exp_iso

        status_text = _text(sheet.get(r, cols.get("status")))[:60]
        ticked = _used_flag(sheet.get(r, cols.get("used")))
        said_used = bool(ticked) or status_text.lower() in _USED_STATUS
        if said_used or main:
            status = "used"
        elif account or campaign or buyer or date_text or status_text:
            status = "reserved"
        else:
            status = "free"

        notes = [re.sub(r"\s*\n\s*", " · ", _text(sheet.get(r, c))) for c in cols["note"]]
        note = " · ".join(n for n in notes if n and not _MONEY_NOTE.search(n))[:MAX_TEXT]

        pack["slots"].append({
            "n": number,
            "status": status,
            "status_text": "" if status_text.lower() in _USED_STATUS else status_text,
            "account": account,
            "campaign": campaign,
            "buyer": buyer,
            "date": date_text,
            "date_iso": date_iso,
            "links": [{"platform": platform_of(u), "url": u} for u in links],
            "note": note,
            "section": section,
            "_sheet": sheet.title,
            "_pos": (index, r),
        })


def parse_workbook(data: bytes) -> dict:
    """xlsx bytes → {"packs": [...], "warnings": [...]}. Raises ValueError when
    the file is not a workbook or holds no quota table at all."""
    from openpyxl import load_workbook

    try:
        wb = load_workbook(io.BytesIO(data), data_only=True)
        wb_formulas = load_workbook(io.BytesIO(data), data_only=False)
    except Exception as exc:  # noqa: BLE001 — not an xlsx / corrupt
        raise ValueError("ไฟล์นี้เปิดเป็นตารางไม่ได้ (ต้องเป็น Google Sheet หรือ Excel)") from exc

    packs: dict[str, dict] = {}
    warnings: list[str] = []
    for index, ws in enumerate(wb.worksheets):
        if ws.sheet_state != "visible":
            continue
        formulas = wb_formulas[ws.title] if ws.title in wb_formulas.sheetnames else None
        _parse_sheet(_Sheet(ws, formulas), index, packs, warnings)

    if not packs:
        raise ValueError(
            "ไม่พบตารางโควต้าในไฟล์นี้ — ต้องมีหัวคอลัมน์ลำดับโพสต์ (เช่น No. Post) "
            "และคอลัมน์ลิงก์ (เช่น Link Post)")

    sheet_rows: dict[str, int] = {}
    for pack in packs.values():
        for s in pack["slots"]:
            sheet_rows[s["_sheet"]] = sheet_rows.get(s["_sheet"], 0) + 1

    out = []
    for pack in packs.values():
        # The same slot can show up on a second sheet (a production timeline
        # beside the status table). The sheet listing most of this page's slots
        # is the tracker — on a tie, the sheet with more slots overall — and
        # another sheet only adds slots the tracker lacks.
        per_sheet: dict[str, int] = {}
        for s in pack["slots"]:
            per_sheet[s["_sheet"]] = per_sheet.get(s["_sheet"], 0) + 1
        main_sheet = max(per_sheet, key=lambda k: (per_sheet[k], sheet_rows[k]))
        taken = {s["n"] for s in pack["slots"] if s["_sheet"] == main_sheet}
        slots = [s for s in pack["slots"]
                 if s["_sheet"] == main_sheet or s["n"] not in taken]
        first = min(s["_pos"] for s in slots if s["_sheet"] == main_sheet)
        for s in slots:
            s.pop("_sheet", None)
            s.pop("_pos", None)
        # "Post 1/6" promises six even when the sheet lists four so far.
        seen = {s["n"] for s in slots}
        n = 1
        while len(slots) < pack["quota_hint"]:
            while n in seen:
                n += 1
            seen.add(n)
            slots.append({"n": n, "status": "free", "status_text": "", "account": "",
                          "campaign": "", "buyer": "", "date": "", "date_iso": None,
                          "links": [], "note": "", "section": ""})
        counts = {"used": 0, "reserved": 0, "free": 0}
        for s in slots:
            counts[s["status"]] += 1
        out.append((first, {"page": pack["page"], "expiry": pack["expiry"],
                            "quota": len(slots), **counts, "slots": slots}))
    out.sort(key=lambda item: item[0])
    return {"packs": [p for _, p in out], "warnings": warnings}


def totals(data: Optional[dict]) -> dict:
    packs = (data or {}).get("packs") or []
    t = {"pack_count": len(packs), "quota": 0, "used": 0, "reserved": 0, "free": 0}
    for p in packs:
        for k in ("quota", "used", "reserved", "free"):
            t[k] += int(p.get(k) or 0)
    return t
