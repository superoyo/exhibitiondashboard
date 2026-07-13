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
TIEIN_VERSION = "tiein2"


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

def _video_duration(exe: str, video_path: str) -> float:
    """Clip length in seconds, parsed from ffmpeg's banner (no ffprobe bundled)."""
    import re as _re
    try:
        r = subprocess.run([exe, "-i", video_path], capture_output=True, timeout=60)
        m = _re.search(rb"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", r.stderr or b"")
        if m:
            return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    except Exception:  # noqa: BLE001
        pass
    return 0.0


def _extract_frames(video_path: str) -> list:
    """FRAMES_PER_VIDEO jpegs spread EVENLY across the WHOLE clip. v1 sampled
    only seconds 2-26 (fps=1/3) and missed tie-in scenes that appear mid/late
    video — most clips came back with no usable shot."""
    import imageio_ffmpeg
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    outdir = tempfile.mkdtemp(prefix="tiein_")
    pattern = os.path.join(outdir, "f_%02d.jpg")
    dur = _video_duration(exe, video_path)
    if dur > 8:  # skip 1s head/tail, spread the samples over what's left
        fps = FRAMES_PER_VIDEO / max(dur - 2.0, 1.0)
        cmd = [exe, "-y", "-ss", "1", "-i", video_path,
               "-vf", f"fps={fps:.6f},scale=480:-2",
               "-frames:v", str(FRAMES_PER_VIDEO), "-q:v", "4", pattern]
    else:  # very short clip — just grab a couple of frames per second
        cmd = [exe, "-y", "-i", video_path, "-vf", "fps=2,scale=480:-2",
               "-frames:v", str(FRAMES_PER_VIDEO), "-q:v", "4", pattern]
    subprocess.run(cmd, capture_output=True, timeout=180)
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
        f"ต่อไปนี้คือเฟรมจากวิดีโอรีวิว {len(frames)} เฟรม สุ่มกระจายตลอดทั้งคลิป (เรียงตามเวลา 1-{len(frames)}) "
        "เลือกเฟรมเดียวที่เป็น tie-in shot ที่ดีที่สุด ตามลำดับความสำคัญ:\n"
        "1) ผู้รีวิวกำลังถือ/หยิบจับ/ใช้งานสินค้า และเห็นแพ็คเกจสินค้าชัดเจน\n"
        "2) เห็นแพ็คเกจ/ฉลากสินค้าชัดเจนเต็มเฟรม (แม้ไม่มีคนถือ)\n"
        "3) เห็นสินค้าบางส่วนในฉาก\n"
        "ตอบเป็นตัวเลขเฟรมเท่านั้น (เช่น 3) — ตอบ 0 เฉพาะกรณีไม่มีเฟรมไหนเห็นสินค้าเลยจริงๆ"}]
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

        st.update(message="กำลังวิเคราะห์สินค้าของแคมเปญ…")
        product = infer_product(campaign)
        st.update(message=f"สินค้า: {product[:120]} · กำลังดึงวิดีโอ…")

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
            if not frames:  # download/ffmpeg hiccup — retry on the next run
                continue
            try:
                idx = _pick_frame(product, frames)
            except RuntimeError as exc:
                log.warning("frame pick failed: %s", exc)
                continue  # transient API error — retry on the next run
            if idx is None:
                # Claude examined the clip and found no product frame — store
                # the versioned hash WITHOUT an image so the next run doesn't
                # pay Apify again; the PPTX falls back to the post cover.
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
        st.update(status="success",
                  message=f"สินค้า: {product[:120]} · ได้ tie-in shot {done}/{len(targets)} คลิป",
                  finished_at=dt.datetime.now(config.TZ).isoformat(),
                  posts=done, cost_usd=round(cost, 4) if cost else None)
        return {"status": "success", "done": done}
    except Exception as exc:  # noqa: BLE001
        log.exception("tiein[%s] failed", campaign)
        st.update(status="failed", message=f"หา tie-in shot ไม่สำเร็จ: {_redact(exc)}",
                  finished_at=dt.datetime.now(config.TZ).isoformat())
        return {"status": "failed", "error": _redact(exc)}
