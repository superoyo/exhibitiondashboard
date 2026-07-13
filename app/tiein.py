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
FRAMES_PER_VIDEO = 8


# ---------------------------------------------------------------------------
# Claude Messages API (plain httpx — no SDK dependency)
# ---------------------------------------------------------------------------

def _claude(content: list, max_tokens: int = 300) -> Optional[str]:
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise RuntimeError("ยังไม่ได้ตั้งค่า ANTHROPIC_API_KEY ใน Railway Variables")
    r = httpx.post(
        "https://api.anthropic.com/v1/messages",
        timeout=90,
        headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json={"model": MODEL, "max_tokens": max_tokens,
              "messages": [{"role": "user", "content": content}]},
    )
    if r.status_code != 200:
        raise RuntimeError(f"Claude API HTTP {r.status_code}: {r.text[:200]}")
    data = r.json()
    parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
    return "".join(parts).strip()


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

def infer_product(campaign_key: str, force: bool = False) -> str:
    """Summarise the campaign's product from its name, captions and covers.
    Cached in app_settings so it's inferred once per campaign."""
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
    content += [_img_block(c) for c in covers]
    desc = _claude(content, max_tokens=300) or name
    set_setting(f"product:{campaign_key}", desc)
    return desc


# ---------------------------------------------------------------------------
# 2) frame extraction + selection
# ---------------------------------------------------------------------------

def _extract_frames(video_path: str) -> list:
    """~FRAMES_PER_VIDEO jpeg frames sampled every 3s (skipping the intro)."""
    import imageio_ffmpeg
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    outdir = tempfile.mkdtemp(prefix="tiein_")
    pattern = os.path.join(outdir, "f_%02d.jpg")
    subprocess.run(
        [exe, "-y", "-ss", "2", "-i", video_path,
         "-vf", "fps=1/3,scale=480:-2", "-frames:v", str(FRAMES_PER_VIDEO),
         "-q:v", "4", pattern],
        capture_output=True, timeout=180,
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
    return frames


def _pick_frame(product_desc: str, frames: list) -> Optional[int]:
    """Ask Claude which frame best shows the product (1-based; None if none)."""
    if not frames:
        return None
    content: list = [{"type": "text", "text":
        f"สินค้าของแคมเปญ: {product_desc}\n\n"
        f"ต่อไปนี้คือเฟรมจากวิดีโอรีวิว {len(frames)} เฟรม (เรียงตามลำดับ 1-{len(frames)}) "
        "เลือกเฟรมเดียวที่เห็น 'ตัวสินค้า' ชัดที่สุด — โดยเฉพาะช็อตที่ผู้รีวิวถือ/หยิบจับ/ใช้งานสินค้า (tie-in shot)\n"
        "ตอบเป็นตัวเลขเฟรมเท่านั้น (เช่น 3) หรือตอบ 0 ถ้าไม่มีเฟรมไหนเห็นสินค้าเลย"}]
    content += [_img_block(f) for f in frames]
    ans = _claude(content, max_tokens=10) or "0"
    try:
        n = int("".join(ch for ch in ans if ch.isdigit()) or "0")
    except ValueError:
        n = 0
    if 1 <= n <= len(frames):
        return n - 1
    return None


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
    st.update(status="running", message="กำลังวิเคราะห์สินค้าของแคมเปญ…",
              started_at=dt.datetime.now(config.TZ).isoformat(), finished_at=None,
              posts=0, cost_usd=None)
    try:
        product = infer_product(campaign)
        st.update(message=f"สินค้า: {product[:120]} · กำลังดึงวิดีโอ…")

        with session_scope() as session:
            active = {k.username.lower() for k in session.scalars(select(ReportKol).where(
                ReportKol.active.is_(True), ReportKol.campaign == campaign)).all()}
            posts = [p for p in session.scalars(select(ReportPost).where(
                ReportPost.campaign == campaign,
                ReportPost.platform == "tiktok")).all()
                if p.url and not p.tiein_hash and p.username.lower() in active]
            targets = {}
            for p in posts[:MAX_VIDEOS_PER_RUN]:
                import re as _re
                m = _re.search(r"/video/(\d+)", p.url or "")
                if m:
                    targets[m.group(1)] = p.id
        if not targets:
            st.update(status="success",
                      message=f"สินค้า: {product[:120]} · ไม่มีคลิป TikTok ใหม่ให้หา tie-in",
                      finished_at=dt.datetime.now(config.TZ).isoformat())
            return {"status": "skipped"}

        urls = []
        with session_scope() as session:
            for pid in targets.values():
                p = session.get(ReportPost, pid)
                if p and p.url:
                    urls.append(p.url)
        items, meta = run_scrape_posts_with_video(urls)
        cost = meta.get("cost_usd") or 0.0

        from app.settings import get_apify_token
        token = get_apify_token()
        done = 0
        for i, it in enumerate(items):
            tid = str(it.get("id") or "")
            post_id = targets.get(tid)
            media = it.get("mediaUrls") or []
            if not post_id or not media:
                continue
            st.update(message=f"กำลังหา tie-in shot… ({i + 1}/{len(items)})")
            path = _download(str(media[0]), token)
            if not path:
                continue
            try:
                frames = _extract_frames(path)
            finally:
                try:
                    os.unlink(path)
                except OSError:
                    pass
            idx = None
            try:
                idx = _pick_frame(product, frames)
            except RuntimeError as exc:
                log.warning("frame pick failed: %s", exc)
            if idx is None:
                continue
            h = hashlib.sha256(f"tiein:{campaign}:{tid}".encode()).hexdigest()[:40]
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
        st.update(status="success",
                  message=(f"สินค้า: {product[:120]} · ได้ tie-in shot {done}/{len(targets)} คลิป — "
                           "กด PowerPoint เพื่อใช้รูปชุดใหม่"),
                  finished_at=dt.datetime.now(config.TZ).isoformat(),
                  posts=done, cost_usd=round(cost, 4) if cost else None)
        return {"status": "success", "done": done}
    except Exception as exc:  # noqa: BLE001
        log.exception("tiein[%s] failed", campaign)
        st.update(status="failed", message=f"หา tie-in shot ไม่สำเร็จ: {_redact(exc)}",
                  finished_at=dt.datetime.now(config.TZ).isoformat())
        return {"status": "failed", "error": _redact(exc)}
