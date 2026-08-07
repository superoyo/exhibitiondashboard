"""AI product tie-in shots for the PPTX post previews.

Two capabilities:
1. infer_product(campaign) — Claude reads the campaign name, post captions and
   a few cover images and summarises WHAT the campaign's product is. Stored in
   app_settings (product:<campaign>) and reused.
2. run_tiein(campaign)   — background job: re-scrape the campaign's TikTok
   posts WITH video download (Apify), sample a frame every 2s (bundled ffmpeg),
   let Claude pick the frame that best shows the product being held/used, and
   cache that frame; the PPTX then uses it as the post preview.

Cost shape of the pick, since it is the whole design: one call per clip, every
frame in it, each frame shrunk to PICK_MAX_SIDE. Image tokens dominate the bill
and scale with frame COUNT x AREA, so FRAMES_PER_VIDEO and PICK_MAX_SIDE move
the number far more than the model tier does — which is why the coverage went up
and the model stayed cheap. A two-stage variant (cheap model shortlists,
expensive one decides between the survivors at full size) was measured at
roughly 7x the per-clip cost and deliberately not kept; TIEIN_MODEL covers the
case where one campaign is worth paying for.

Frames are DECODED at source resolution but SENT shrunk: the winning frame goes
into ImageCache for the PPTX slide, so decoding small would soften every slide
to save tokens that shrinking already saves.

Requires ANTHROPIC_API_KEY (Railway env). Model via TIEIN_MODEL — overridable
from Railway Variables with no deploy.
"""
from __future__ import annotations

import base64
import datetime as dt
import glob
import hashlib
import logging
import os
import subprocess
import tempfile
from typing import Optional

import httpx
from sqlalchemy import select

from app import config
from app.apify_client import run_scrape_posts_with_video
from app.db import session_scope
from app.models import Campaign, ImageCache, ReportKol, ReportPost
from app.report_refresh import _redact, state_for

log = logging.getLogger("tiein")

# Cheap vision. The accuracy lever here is frame COVERAGE, not model tier: at
# $1/M input, doubling the frames costs cents, while a frame that was never
# sampled cannot be picked by any model. Set TIEIN_MODEL=claude-sonnet-5 (~3x)
# or claude-opus-5 (~7x per clip) when a campaign needs a sharper pick.
MODEL = os.getenv("TIEIN_MODEL", "claude-haiku-4-5")
# What gets STORED and ends up on the PPTX slide, capped by WIDTH (720 -> 720x1280
# on a 9:16 clip). A slide preview is a couple of inches wide, so more than this
# only inflated the deck and the ImageCache rows.
DECODE_MAX_WIDTH = 720
# What the model SEES — smaller than what is stored, and capped by the LONG edge
# rather than the width. Sending frames at DECODE_MAX_WIDTH would roughly double
# the image tokens. NOTE the old ffmpeg `scale=480:-2` capped the WIDTH, so on
# 9:16 clips it sent 480x853 — a 640 cap here would have SHRUNK what the model
# sees, not grown it. 896 -> 504x896, a little sharper than before.
PICK_MAX_SIDE = 896
# Haiku 4.5 does not think, so this budget is nearly free here — it exists for
# the TIEIN_MODEL override: on Sonnet 5 / Opus 5 thinking is ON BY DEFAULT and
# max_tokens caps thinking PLUS the reply, so the old value of 10 would spend
# the budget on thinking and return an empty string, which this code reads as
# "no product in this clip" — for every single clip.
PICK_MAX_TOKENS = 2048
MAX_VIDEOS_PER_RUN = 40
FRAMES_PER_VIDEO = 24
# bump when the sampling/selection algorithm improves — posts whose stored
# shot came from an older version are automatically redone on the next run
TIEIN_VERSION = "tiein5"
# the actor only ever finishes downloading the FIRST video of a run — so each
# clip gets its own single-url run, several in flight at once
VIDEO_WORKERS = 5


def packshot_hash(campaign: str) -> str:
    """ImageCache key of the campaign's uploaded product pack shot."""
    return hashlib.sha256(f"packshot:{campaign}".encode()).hexdigest()[:40]


def get_packshot(campaign: str) -> Optional[bytes]:
    with session_scope() as session:
        row = session.get(ImageCache, packshot_hash(campaign))
        return row.data if row and row.data else None


# ---------------------------------------------------------------------------
# Claude Messages API (plain httpx — no SDK dependency)
# ---------------------------------------------------------------------------

def _api_error_thai(r) -> str:
    """Translate a Claude API error response into an actionable Thai message
    (shown in the UI — the team must know HOW to fix it, not just that it broke)."""
    txt = (r.text or "")[:400]
    low = txt.lower()
    if "credit balance is too low" in low or "billing" in low:
        return ("เครดิต Claude AI หมด — เข้า console.anthropic.com → Billing → "
                "Add credits แล้วใช้งานต่อได้ทันที (ไม่ต้องเปลี่ยน key)")
    if r.status_code == 401:
        return ("ANTHROPIC_API_KEY ไม่ถูกต้องหรือถูกยกเลิก — สร้าง key ใหม่ที่ "
                "console.anthropic.com → API Keys แล้วแก้ค่าใน Railway Variables")
    if r.status_code == 429:
        return "Claude API ติด rate limit ชั่วคราว — รอสักครู่แล้วลองใหม่"
    return f"Claude API HTTP {r.status_code}: {txt[:150]}"


def _claude(content: list, max_tokens: int = 1500) -> Optional[str]:
    from app.settings import get_anthropic_key
    key = get_anthropic_key()
    if not key:
        raise RuntimeError("ยังไม่ได้ตั้งค่า Claude API key — ใส่ได้ที่เมนู Apify Token (หน้า Home)")
    r = httpx.post(
        "https://api.anthropic.com/v1/messages",
        # two dozen frames per call, and a TIEIN_MODEL override puts a thinking
        # model behind it — the old 90s was tuned for 12 frames on Haiku
        timeout=240,
        headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json={"model": MODEL, "max_tokens": max_tokens,
              "messages": [{"role": "user", "content": content}]},
    )
    if r.status_code != 200:
        raise RuntimeError(_api_error_thai(r))
    data = r.json()
    # thinking blocks are type "thinking", so they never reach the parsed text
    parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
    return "".join(parts).strip()


_AI_STATUS_CACHE: dict = {"t": 0.0, "data": None}


def ai_status(force: bool = False) -> dict:
    """Live key/credit check for the settings page: a 1-token ping (costs a
    fraction of a satang), cached 5 minutes so page loads don't spam the API."""
    import time as _time
    if (not force and _AI_STATUS_CACHE["data"]
            and _time.time() - _AI_STATUS_CACHE["t"] < 300):
        return _AI_STATUS_CACHE["data"]
    from app.settings import get_anthropic_key
    key = get_anthropic_key()
    if not key:
        out = {"ok": False, "state": "no_key",
               "message": "ยังไม่ได้ตั้ง Claude API key — วาง key ในช่องด้านล่างแล้วกดบันทึกได้เลย"}
    else:
        try:
            r = httpx.post(
                "https://api.anthropic.com/v1/messages", timeout=20,
                headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                         "content-type": "application/json"},
                # No `thinking` key on purpose: omitting it is the only form
                # valid on every model TIEIN_MODEL may name. Haiku 4.5 predates
                # the adaptive/disabled config and can reject it outright, and
                # breaking this ping would break the whole credit-check page.
                json={"model": MODEL, "max_tokens": 1,
                      "messages": [{"role": "user", "content": "hi"}]},
            )
            if r.status_code == 200:
                out = {"ok": True, "state": "ok",
                       "message": "พร้อมใช้งาน — key และเครดิตปกติ"}
            else:
                low = (r.text or "").lower()
                state = ("no_credit" if ("credit balance is too low" in low
                                         or "billing" in low)
                         else "invalid_key" if r.status_code == 401 else "error")
                out = {"ok": False, "state": state, "message": _api_error_thai(r)}
        except Exception as exc:  # noqa: BLE001
            out = {"ok": False, "state": "error",
                   "message": f"เชื่อมต่อ Claude API ไม่ได้: {exc}"}
    _AI_STATUS_CACHE.update(t=_time.time(), data=out)
    return out


def _img_block(jpeg: bytes) -> dict:
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                        "data": base64.b64encode(jpeg).decode()}}


def _shrink(img: bytes, max_side: int = 512) -> bytes:
    try:
        import io

        from PIL import Image
        im = Image.open(io.BytesIO(img)).convert("RGB")
        im.thumbnail((max_side, max_side))
        out = io.BytesIO()
        im.save(out, "JPEG", quality=75)
        return out.getvalue()
    except Exception:  # noqa: BLE001
        return img


# ---------------------------------------------------------------------------
# 1) what is this campaign's product?
# ---------------------------------------------------------------------------

def infer_product(campaign_key: str, force: bool = False,
                  ref_img: Optional[bytes] = None) -> str:
    """Summarise the campaign's product from its name, captions and covers
    (plus the uploaded pack shot when there is one). Cached in app_settings
    so it's inferred once per campaign."""
    from app.settings import get_setting, set_setting
    cached = get_setting(f"product:{campaign_key}")
    if cached and not force:
        return cached

    with session_scope() as session:
        camp = session.get(Campaign, campaign_key)
        name = camp.name if camp else campaign_key
        posts = session.scalars(select(ReportPost).where(
            ReportPost.campaign == campaign_key)).all()
        captions = [p.caption for p in posts if p.caption][:12]
        covers = []
        from app.pptx_report import _image_bytes
        for p in posts:
            if len(covers) >= 4:
                break
            img = _image_bytes(session, p.cover_url)
            if img:
                covers.append(_shrink(img))

    content: list = [{"type": "text", "text":
        f"แคมเปญการตลาดชื่อ: \"{name}\"\n\n"
        "Caption จากโพสต์ของ influencer ในแคมเปญนี้:\n"
        + "\n---\n".join((c or "")[:300] for c in captions)
        + "\n\nจากชื่อแคมเปญ caption และภาพตัวอย่างที่แนบมา "
          "สรุปว่า 'สินค้า/บริการ' ของแคมเปญนี้คืออะไร "
          "ตอบภาษาไทย 1-2 ประโยค ระบุลักษณะภายนอกของสินค้า "
          "(รูปทรง สี แพ็คเกจ) ให้ชัดที่สุดเท่าที่เห็น"}]
    if ref_img:
        content.append({"type": "text",
                        "text": "ภาพ pack shot สินค้าอย่างเป็นทางการของแคมเปญ (เชื่อภาพนี้เป็นหลัก):"})
        content.append(_img_block(_shrink(ref_img)))
    content += [_img_block(c) for c in covers]
    # 300 was enough when nothing was thinking; on Opus 5 the budget covers
    # thinking too, and a truncated reply here poisons every later frame pick
    desc = _claude(content, max_tokens=1500) or name
    set_setting(f"product:{campaign_key}", desc)
    return desc


# ---------------------------------------------------------------------------
# 2) frame extraction + selection
# ---------------------------------------------------------------------------

def _not_black(path: str) -> bool:
    """Drop black/near-black frames (intros, fades, decode glitches) so they
    can never end up as the slide preview."""
    try:
        from PIL import Image
        with Image.open(path) as im:
            small = im.convert("L")
            small.thumbnail((32, 32))
            pix = list(small.getdata())
        return (sum(pix) / max(len(pix), 1)) > 10
    except Exception:  # noqa: BLE001
        return True


def _extract_frames(video_path: str) -> list:
    """Frames covering the WHOLE clip: decode one frame every 2s (up to 90 =
    3 minutes), drop the black ones, then thin evenly down to FRAMES_PER_VIDEO.
    No duration parsing — earlier versions that guessed the length could
    silently fall back to sampling only the first seconds and miss mid/late
    tie-in scenes.

    Two things the frame rate and size are doing:
      - every 2s, not every 3s: a product that is only on screen for a beat
        can fall between samples entirely, and no model can pick a frame that
        was never decoded.
      - DECODE_MAX_WIDTH instead of 480: the winning frame is what the PPTX
        slide shows, so it is decoded at slide quality and only shrunk on the
        way to the model. Costs no extra tokens. Only the frames that survive
        thinning are read into memory, so a 3-minute clip costs a couple of MB
        rather than 90 frames at once.
    """
    import imageio_ffmpeg
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    outdir = tempfile.mkdtemp(prefix="tiein_")
    pattern = os.path.join(outdir, "f_%03d.jpg")
    subprocess.run(
        # min(w,iw) never upscales — an already-small clip keeps its own size
        # instead of being blown up into interpolated pixels. The escaped comma
        # is required: a bare one would read as a filter separator.
        [exe, "-y", "-i", video_path,
         "-vf", rf"fps=1/2,scale=min({DECODE_MAX_WIDTH}\,iw):-2",
         # q4 is the project's long-standing value and stays: measured against
         # both a noisy and a flat test source, q3 buys ~10% more bytes for
         # nothing a slide preview can show. Frame BYTES track picture content
         # far more than this flag (13KB flat vs 51KB noisy at the same q).
         "-frames:v", "90", "-q:v", "4", pattern],
        capture_output=True, timeout=300,
    )
    paths = sorted(glob.glob(os.path.join(outdir, "f_*.jpg")))
    kept = [p for p in paths if _not_black(p)] or paths[:1]
    if len(kept) > FRAMES_PER_VIDEO:  # keep first + last, spread the rest
        step = (len(kept) - 1) / (FRAMES_PER_VIDEO - 1)
        kept = [kept[round(i * step)] for i in range(FRAMES_PER_VIDEO)]
    frames = []
    for p in kept:
        try:
            with open(p, "rb") as fh:
                frames.append(fh.read())
        except OSError:
            pass
    for p in paths:  # every decoded frame, kept or thinned away
        try:
            os.unlink(p)
        except OSError:
            pass
    try:
        os.rmdir(outdir)
    except OSError:
        pass
    return frames


_CRITERIA = (
    "เกณฑ์ของ tie-in shot ที่ดี เรียงตามลำดับความสำคัญ:\n"
    "1) เห็น 'ตัวแพ็คเกจสินค้า' (ขวด/ถุง/กล่อง พร้อมฉลาก) ชัดเจน และมีคนถือ/หยิบจับ\n"
    "2) เห็นตัวแพ็คเกจสินค้าชัดเจนในเฟรม (แม้ไม่มีคนถือ)\n"
    "3) เห็นแพ็คเกจสินค้าเพียงบางส่วน\n"
    "ข้อควรระวัง: ฉากที่กำลัง 'ใช้งาน' โดยไม่เห็นแพ็คเกจ (เช่น ถูพื้น เทของ "
    "โดยไม่เห็นขวด/ถุงสินค้า) ถือว่าด้อยกว่าเฟรมที่เห็นแพ็คเกจเสมอ"
)


def _frame_numbers(text: str, hi: int) -> list:
    """1-based frame numbers in a model reply, de-duped, in the order given.
    0 ("no product anywhere") and anything out of range fall out here."""
    import re as _re
    out = []
    for tok in _re.findall(r"\d+", text or ""):
        n = int(tok)
        if 1 <= n <= hi and n not in out:
            out.append(n)
    return out


def _frame_blocks(frames: list, numbers: list, shrink_to: Optional[int]) -> list:
    """Label every image so the number the model answers with is unambiguous."""
    content: list = []
    for n, f in zip(numbers, frames):
        content.append({"type": "text", "text": f"เฟรมที่ {n}:"})
        content.append(_img_block(_shrink(f, shrink_to) if shrink_to else f))
    return content


def _ref_blocks(ref_img: bytes) -> list:
    return [{"type": "text",
             "text": "ภาพอ้างอิง: pack shot จริงของสินค้า — เลือกเฟรมที่เห็นสินค้าตรงกับภาพนี้:"},
            _img_block(_shrink(ref_img))]


def _pick_frame(product_desc: str, frames: list,
                ref_img: Optional[bytes] = None) -> Optional[int]:
    """Which frame is the tie-in shot (0-based index into `frames`; None when
    the clip never shows the package, or the reply can't be trusted).

    One call, every frame, each shrunk to PICK_MAX_SIDE. Frame numbers in the
    prompt are 1-based so the reply maps back cleanly."""
    if not frames:
        return None
    numbers = list(range(1, len(frames) + 1))
    content: list = [{"type": "text", "text":
        f"สินค้าของแคมเปญ: {product_desc}\n\n"
        f"ต่อไปนี้คือเฟรมจากวิดีโอรีวิว {len(frames)} เฟรม สุ่มกระจายตลอดทั้งคลิป "
        "(แต่ละภาพมีเลขเฟรมกำกับไว้ก่อนหน้า)\n"
        f"{_CRITERIA}\n\n"
        "เลือกเฟรมเดียวที่เป็น tie-in shot ที่ดีที่สุด ดูให้ละเอียดว่าเฟรมไหนเห็น "
        "ฉลาก/แพ็คเกจชัดกว่ากันจริง\n"
        "ตอบเป็นเลขเฟรมเดียวเท่านั้น (เช่น 13) — "
        "ตอบ 0 เฉพาะกรณีไม่มีเฟรมไหนเห็นแพ็คเกจสินค้าเลย"}]
    if ref_img:
        content += _ref_blocks(ref_img)
    content += _frame_blocks(frames, numbers, shrink_to=PICK_MAX_SIDE)

    ans = _claude(content, max_tokens=PICK_MAX_TOKENS)
    # a number outside the range is a hallucination, not a pick — _frame_numbers
    # drops those along with the "0" that means "no product anywhere"
    got = _frame_numbers(ans or "", len(frames))
    if not got:
        return None
    return got[0] - 1


def _kv_video_urls(kv_store_id: str, token: str):
    """(video-id -> download URL, raw key names) for the scrape run's
    key-value store. The clockworks actor saves downloaded videos THERE — the
    dataset items usually come back with mediaUrls=[] (which is why no clip
    ever produced a frame before this lookup existed). Raw key names are kept
    for the debug readout — the naming scheme is undocumented."""
    import re as _re
    out: dict = {}
    raw: list = []
    if not kv_store_id:
        return out, raw
    base = "https://api.apify.com/v2"
    start_key = None
    try:
        for _ in range(20):  # paginate defensively; 1000 keys per page
            params = {"token": token, "limit": 1000}
            if start_key:
                params["exclusiveStartKey"] = start_key
            r = httpx.get(f"{base}/key-value-stores/{kv_store_id}/keys",
                          params=params, timeout=30)
            if r.status_code != 200:
                break
            data = (r.json() or {}).get("data") or {}
            for it in data.get("items") or []:
                key = str(it.get("key") or "")
                raw.append(f"{key} ({it.get('size') or 0}b)")
                m = _re.search(r"(\d{15,})", key)  # tiktok ids are long digit runs
                if m:
                    out[m.group(1)] = f"{base}/key-value-stores/{kv_store_id}/records/{key}"
            if not data.get("isTruncated"):
                break
            start_key = data.get("nextExclusiveStartKey")
    except Exception:  # noqa: BLE001 — fall back to whatever was collected
        pass
    return out, raw


def _wait_videos(kv_store_id: str, token: str, expect: int,
                 timeout_s: float = 300.0) -> int:
    """The clockworks actor marks its run SUCCEEDED and then keeps uploading
    the downloaded videos through a separate queue (VIDEO_DOWNLOAD_REQUEST_
    QUEUE_ID in the store) — listing the store right away sees only the
    bookkeeping files. Poll until `expect` id-keyed videos exist, or the count
    has been stable for ~90s, or timeout. Returns the final count."""
    import time as _time
    deadline = _time.monotonic() + timeout_s
    last, stable = -1, 0
    while True:
        got, _ = _kv_video_urls(kv_store_id, token)
        n = len(got)
        if n >= expect:
            return n
        if n == last:
            stable += 1
            if stable >= 9:  # no new upload for ~90s — that's all we're getting
                return n
        else:
            last, stable = n, 0
        if _time.monotonic() > deadline:
            return n
        _time.sleep(10)


def _download(url: str, token: str) -> Optional[str]:
    """Stream an Apify-stored video to a temp file; returns the path."""
    u = url + ("&" if "?" in url else "?") + "token=" + token
    try:
        tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        with httpx.stream("GET", u, timeout=180, follow_redirects=True) as r:
            if r.status_code != 200:
                tmp.close()
                os.unlink(tmp.name)
                return None
            for chunk in r.iter_bytes(1 << 20):
                tmp.write(chunk)
        tmp.close()
        return tmp.name
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# the background job
# ---------------------------------------------------------------------------

def run_tiein(campaign: str) -> dict:
    """Find product tie-in frames for the campaign's TikTok posts. Progress in
    state_for('ti:'+campaign). Never raises."""
    st = state_for("ti:" + campaign)
    st.update(status="running", message="กำลังตรวจว่ามีคลิปใหม่ให้หา tie-in ไหม…",
              started_at=dt.datetime.now(config.TZ).isoformat(), finished_at=None,
              posts=0, cost_usd=None)
    try:
        # find targets FIRST — when everything is already processed (the common
        # case now that PPTX triggers this every time) we exit without spending
        # a single Apify or Claude call. A post is "done" only when its stored
        # shot came from the CURRENT algorithm version; older shots are redone.
        def _shot_hash(tid: str) -> str:
            return hashlib.sha256(
                f"{TIEIN_VERSION}:{campaign}:{tid}".encode()).hexdigest()[:40]

        with session_scope() as session:
            active = {k.username.lower() for k in session.scalars(select(ReportKol).where(
                ReportKol.active.is_(True), ReportKol.campaign == campaign)).all()}
            posts = [p for p in session.scalars(select(ReportPost).where(
                ReportPost.campaign == campaign,
                ReportPost.platform == "tiktok")).all()
                if p.url and p.username.lower() in active]
            targets = {}
            for p in posts:
                if len(targets) >= MAX_VIDEOS_PER_RUN:
                    break
                import re as _re
                m = _re.search(r"/video/(\d+)", p.url or "")
                if m and p.tiein_hash != _shot_hash(m.group(1)):
                    targets[m.group(1)] = p.id
        if not targets:
            st.update(status="success",
                      message="ไม่มีคลิป TikTok ใหม่ให้หา tie-in (ทุกคลิปมี shot แล้ว)",
                      finished_at=dt.datetime.now(config.TZ).isoformat())
            return {"status": "skipped"}

        ref_img = get_packshot(campaign)  # uploaded product pack shot (optional)
        st.update(message="กำลังวิเคราะห์สินค้าของแคมเปญ…"
                          + (" (มีภาพ pack shot อ้างอิง)" if ref_img else ""))
        product = infer_product(campaign, ref_img=ref_img)
        st.update(message=f"สินค้า: {product[:120]} · กำลังดึงวิดีโอ…")

        urls = []
        with session_scope() as session:
            for pid in targets.values():
                p = session.get(ReportPost, pid)
                if p and p.url:
                    urls.append(p.url)

        from app.settings import get_apify_token
        token = get_apify_token()
        # ONE url per actor run, several runs concurrently — the actor's video
        # downloader reliably finishes only the FIRST queued video before the
        # run ends (observed 1/6, 1/6, 1/4 across batch sizes), so every clip
        # must be the first of its own run. Parallelism keeps wall-clock sane.
        items, kv_videos, cost = [], {}, 0.0
        dbg: list = []  # per-run evidence, surfaced via the status endpoint

        def _one_video(u):
            ch_items, meta = run_scrape_posts_with_video([u], timeout_s=300)
            kv_id = meta.get("kv_store_id") or ""
            _wait_videos(kv_id, token, expect=1, timeout_s=150)
            kv_map, kv_raw = _kv_video_urls(kv_id, token)
            return ch_items, meta, kv_map, kv_raw

        from concurrent.futures import ThreadPoolExecutor, as_completed
        got = 0
        with ThreadPoolExecutor(max_workers=VIDEO_WORKERS) as pool:
            futs = {pool.submit(_one_video, u): u for u in urls}
            for fut in as_completed(futs):
                got += 1
                st.update(message=(f"สินค้า: {product[:80]} · ดึงวิดีโอแล้ว "
                                   f"{got}/{len(urls)}"))
                try:
                    ch_items, meta, kv_map, kv_raw = fut.result()
                    items += ch_items
                    cost += meta.get("cost_usd") or 0.0
                    kv_videos.update(kv_map)
                    dbg.append({
                        "run": meta.get("apify_run_id"),
                        "items": len(ch_items),
                        "media": sum(1 for it in ch_items if it.get("mediaUrls")),
                        "kv_ids_matched": len(kv_map),
                    })
                except Exception as exc:  # noqa: BLE001 — keep the rest alive
                    log.error("tiein[%s] video run failed for %s: %s",
                              campaign, futs[fut], _redact(exc))
                    dbg.append({"url": futs[fut][:80], "error": _redact(exc)})
        st["debug"] = dbg
        log.info("tiein[%s]: %d items, %d videos in KV store · %s", campaign,
                 len(items), len(kv_videos), dbg)
        done = no_product = errs = have_video = 0
        for i, it in enumerate(items):
            tid = str(it.get("id") or "")
            post_id = targets.get(tid)
            media = it.get("mediaUrls") or []
            if not post_id:  # actor returned an item we didn't ask about
                continue
            video_url = str(media[0]) if media else kv_videos.get(tid)
            if not video_url:  # no downloaded video came back for this clip
                errs += 1
                continue
            have_video += 1
            st.update(message=f"กำลังหา tie-in shot… ({i + 1}/{len(items)})")
            path = _download(video_url, token)
            if not path:
                errs += 1
                continue
            try:
                frames = _extract_frames(path)
            finally:
                try:
                    os.unlink(path)
                except OSError:
                    pass
            if not frames:  # download/ffmpeg hiccup — retry on the next run
                errs += 1
                continue
            try:
                idx = _pick_frame(product, frames, ref_img=ref_img)
            except RuntimeError as exc:
                log.warning("frame pick failed: %s", exc)
                errs += 1
                continue  # transient API error — retry on the next run
            log.info("tiein[%s] clip %s: %d frames, pick=%s",
                     campaign, tid, len(frames), idx)
            if idx is None:
                # Claude examined the clip and found no product frame — store
                # the versioned hash WITHOUT an image so the next run doesn't
                # pay Apify again; the PPTX falls back to the post cover.
                no_product += 1
                with session_scope() as session:
                    p = session.get(ReportPost, post_id)
                    if p:
                        p.tiein_hash = _shot_hash(tid)
                continue
            h = _shot_hash(tid)
            with session_scope() as session:
                session.merge(ImageCache(hash=h, content_type="image/jpeg",
                                         data=frames[idx]))
                p = session.get(ReportPost, post_id)
                if p:
                    p.tiein_hash = h
            done += 1

        try:
            from app.settings import add_cost
            add_cost(campaign, cost)
        except Exception:  # noqa: BLE001
            pass
        summary = (f"ได้ tie-in shot {done}/{len(targets)} คลิป "
                   f"(Apify ส่งวิดีโอมา {have_video}/{len(targets)})")
        if no_product:
            summary += f" · ไม่พบสินค้าในคลิป {no_product}"
        if errs:
            summary += f" · ดึงไม่สำเร็จ {errs} (จะลองใหม่รอบหน้า)"
        st.update(status="success",
                  message=f"สินค้า: {product[:120]} · {summary}",
                  finished_at=dt.datetime.now(config.TZ).isoformat(),
                  posts=done, cost_usd=round(cost, 4) if cost else None)
        return {"status": "success", "done": done}
    except Exception as exc:  # noqa: BLE001
        log.exception("tiein[%s] failed", campaign)
        st.update(status="failed", message=f"หา tie-in shot ไม่สำเร็จ: {_redact(exc)}",
                  finished_at=dt.datetime.now(config.TZ).isoformat())
        return {"status": "failed", "error": _redact(exc)}
