"""AI product tie-in shots for the PPTX post previews.

Two capabilities:
1. infer_product(campaign) — Claude reads the campaign name, post captions and
   a few cover images and summarises WHAT the campaign's product is. Stored in
   app_settings (product:<campaign>) and reused.
2. run_tiein(campaign)   — background job: re-scrape the campaign's TikTok
   posts WITH video download (Apify), sample ~8 frames per video (bundled
   ffmpeg), let Claude pick the frame that best shows the product being
   held/used, and cache that frame; the PPTX then uses it as the post preview.

Requires ANTHROPIC_API_KEY (Railway env). Model via TIEIN_MODEL
(default claude-haiku-4-5 — cheap vision).
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

MODEL = os.getenv("TIEIN_MODEL", "claude-haiku-4-5-20251001")
MAX_VIDEOS_PER_RUN = 40
FRAMES_PER_VIDEO = 12
# bump when the sampling/selection algorithm improves — posts whose stored
# shot came from an older version are automatically redone on the next run
TIEIN_VERSION = "tiein4"
VIDEO_BATCH = 6  # one 16-url actor run dropped 13/16 videos; small chunks stick


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


def _claude(content: list, max_tokens: int = 300) -> Optional[str]:
    from app.settings import get_anthropic_key
    key = get_anthropic_key()
    if not key:
        raise RuntimeError("ยังไม่ได้ตั้งค่า Claude API key — ใส่ได้ที่เมนู Apify Token (หน้า Home)")
    r = httpx.post(
        "https://api.anthropic.com/v1/messages",
        timeout=90,
        headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json={"model": MODEL, "max_tokens": max_tokens,
              "messages": [{"role": "user", "content": content}]},
    )
    if r.status_code != 200:
        raise RuntimeError(_api_error_thai(r))
    data = r.json()
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
    desc = _claude(content, max_tokens=300) or name
    set_setting(f"product:{campaign_key}", desc)
    return desc


# ---------------------------------------------------------------------------
# 2) frame extraction + selection
# ---------------------------------------------------------------------------

def _extract_frames(video_path: str) -> list:
    """Frames covering the WHOLE clip: decode one frame every 3s (up to 60 =
    3 minutes), then thin evenly down to FRAMES_PER_VIDEO. No duration parsing
    — earlier versions that guessed the length could silently fall back to
    sampling only the first seconds and miss mid/late tie-in scenes."""
    import imageio_ffmpeg
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    outdir = tempfile.mkdtemp(prefix="tiein_")
    pattern = os.path.join(outdir, "f_%03d.jpg")
    subprocess.run(
        [exe, "-y", "-i", video_path, "-vf", "fps=1/3,scale=480:-2",
         "-frames:v", "60", "-q:v", "4", pattern],
        capture_output=True, timeout=300,
    )
    frames = []
    for f in sorted(glob.glob(os.path.join(outdir, "f_*.jpg"))):
        try:
            with open(f, "rb") as fh:
                frames.append(fh.read())
            os.unlink(f)
        except OSError:
            pass
    try:
        os.rmdir(outdir)
    except OSError:
        pass
    if len(frames) > FRAMES_PER_VIDEO:  # keep first + last, spread the rest
        step = (len(frames) - 1) / (FRAMES_PER_VIDEO - 1)
        frames = [frames[round(i * step)] for i in range(FRAMES_PER_VIDEO)]
    return frames


def _pick_frame(product_desc: str, frames: list,
                ref_img: Optional[bytes] = None) -> Optional[int]:
    """Ask Claude which frame best shows the product (1-based; None if none)."""
    if not frames:
        return None
    content: list = [{"type": "text", "text":
        f"สินค้าของแคมเปญ: {product_desc}\n\n"
        f"ต่อไปนี้คือเฟรมจากวิดีโอรีวิว {len(frames)} เฟรม สุ่มกระจายตลอดทั้งคลิป "
        "(แต่ละภาพมีเลขเฟรมกำกับไว้ก่อนหน้า) "
        "เลือกเฟรมเดียวที่เป็น tie-in shot ที่ดีที่สุด ตามลำดับความสำคัญ:\n"
        "1) เห็น 'ตัวแพ็คเกจสินค้า' (ขวด/ถุง/กล่อง พร้อมฉลาก) ชัดเจน และมีคนถือ/หยิบจับ\n"
        "2) เห็นตัวแพ็คเกจสินค้าชัดเจนในเฟรม (แม้ไม่มีคนถือ)\n"
        "3) เห็นแพ็คเกจสินค้าเพียงบางส่วน\n"
        "ข้อควรระวัง: ฉากที่กำลัง 'ใช้งาน' โดยไม่เห็นแพ็คเกจ (เช่น ถูพื้น เทของ "
        "โดยไม่เห็นขวด/ถุงสินค้า) ถือว่าด้อยกว่าเฟรมที่เห็นแพ็คเกจเสมอ\n"
        "ตอบเป็นตัวเลขเฟรมเท่านั้น (เช่น 3) — ตอบ 0 เฉพาะกรณีไม่มีเฟรมไหนเห็นแพ็คเกจสินค้าเลย"}]
    if ref_img:
        content.append({"type": "text",
                        "text": "ภาพอ้างอิง: pack shot จริงของสินค้า — เลือกเฟรมที่เห็นสินค้าตรงกับภาพนี้:"})
        content.append(_img_block(_shrink(ref_img)))
    for k, f in enumerate(frames, 1):  # label every image so the index is exact
        content.append({"type": "text", "text": f"เฟรมที่ {k}:"})
        content.append(_img_block(f))
    ans = _claude(content, max_tokens=10) or "0"
    try:
        n = int("".join(ch for ch in ans if ch.isdigit()) or "0")
    except ValueError:
        n = 0
    if 1 <= n <= len(frames):
        return n - 1
    return None


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
        # download in SMALL batches — one big 16-url run returned only 3
        # videos; short runs let the actor finish every download
        items, kv_videos, cost = [], {}, 0.0
        dbg: list = []  # per-batch evidence, surfaced via the status endpoint
        for b in range(0, len(urls), VIDEO_BATCH):
            chunk = urls[b:b + VIDEO_BATCH]
            st.update(message=(f"สินค้า: {product[:80]} · กำลังดึงวิดีโอ… "
                               f"({min(b + len(chunk), len(urls))}/{len(urls)})"))
            try:
                ch_items, meta = run_scrape_posts_with_video(chunk)
                items += ch_items
                cost += meta.get("cost_usd") or 0.0
                kv_id = meta.get("kv_store_id") or ""
                st.update(message=(f"สินค้า: {product[:80]} · รอไฟล์วิดีโออัพโหลด… "
                                   f"({min(b + len(chunk), len(urls))}/{len(urls)})"))
                import time as _time
                t0 = _time.monotonic()
                _wait_videos(kv_id, token, expect=len(chunk))
                kv_map, kv_raw = _kv_video_urls(kv_id, token)
                kv_videos.update(kv_map)
                dbg.append({
                    "run": meta.get("apify_run_id"), "kv": kv_id,
                    "urls": len(chunk), "items": len(ch_items),
                    "items_with_mediaUrls": sum(1 for it in ch_items
                                                if it.get("mediaUrls")),
                    "waited_s": round(_time.monotonic() - t0),
                    "kv_keys_total": len(kv_raw), "kv_ids_matched": len(kv_map),
                    "kv_key_sample": kv_raw[:8],
                })
            except Exception as exc:  # noqa: BLE001 — keep other batches alive
                log.error("tiein[%s] video batch failed: %s", campaign, _redact(exc))
                dbg.append({"urls": len(chunk), "error": _redact(exc)})
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
