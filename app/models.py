"""SQLAlchemy ORM models — time-series schema (see brief section 8).

Note: the brief's logical column "group" is stored as `content_group`
because GROUP is a reserved SQL word; the JSON/API layer still exposes it
as "group".
"""
from __future__ import annotations

import datetime as dt
from typing import List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Kol(Base):
    __tablename__ = "kols"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    display: Mapped[str] = mapped_column(String(255), nullable=False)
    content_group: Mapped[str] = mapped_column("content_group", String(64), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    posts: Mapped[List["Post"]] = relationship(back_populates="kol")
    dailies: Mapped[List["KolDaily"]] = relationship(back_populates="kol")


class ReportKol(Base):
    """Roster of KOLs for a static campaign report (e.g. PAO Super Perfume).

    Editable via the /kols admin page. Independent of the live `kols` table —
    the report's metrics are a snapshot; this table just stores the roster
    (who was in the campaign) so names/groups can be curated.
    """
    __tablename__ = "report_kols"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    display: Mapped[str] = mapped_column(String(255), nullable=False)
    content_group: Mapped[str] = mapped_column("content_group", String(64), nullable=False)
    subgroup: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    campaign: Mapped[str] = mapped_column(String(32), nullable=False, default="pao", index=True)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # JSON list of {"platform","url","handle"} — all channels this KOL posted on.
    # Falls back to `url` (single link) when null, for pre-multiplatform data.
    links_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    followers: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    __table_args__ = (UniqueConstraint("campaign", "username", name="uq_report_kols_campaign_username"),)


class ReportPost(Base):
    """Latest scraped posts for the report roster (refreshed via the Refresh
    Data button). Holds the trailing-window snapshot per video, replaced on
    each refresh for the refreshed usernames."""
    __tablename__ = "report_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign: Mapped[str] = mapped_column(String(32), nullable=False, default="pao", index=True)
    username: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(16), nullable=False, default="tiktok", index=True)
    video_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cover_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    caption: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    posted_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    views: Mapped[int] = mapped_column(BigInteger, default=0)
    likes: Mapped[int] = mapped_column(BigInteger, default=0)
    comments: Mapped[int] = mapped_column(BigInteger, default=0)
    shares: Mapped[int] = mapped_column(BigInteger, default=0)
    saves: Mapped[int] = mapped_column(BigInteger, default=0)
    scraped_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Campaign(Base):
    """Metadata for a report campaign — makes campaigns dynamic (created from
    the /kols/home UI, not by editing code). The `campaign` string column in
    report_kols/report_posts references this table's `key` (soft-linked; no FK
    so pre-existing data survives without a metadata row)."""
    __tablename__ = "campaigns"

    key: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # random unguessable token for the client view-only link (/v/<token>)
    view_token: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    emoji: Mapped[str] = mapped_column(String(8), nullable=False, default="📊")
    subtitle: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    groups_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    subgroups_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ImageCache(Base):
    """Cached bytes of remote images (TikTok avatars/covers). TikTok's CDN URLs
    are signed + expire after a few days, so pictures vanish once the link dies.
    We fetch each image once (while its URL is still valid) and serve our own
    copy forever from /api/img."""
    __tablename__ = "image_cache"

    hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    content_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AppSetting(Base):
    """Tiny key/value store for runtime-editable settings (e.g. apify_token),
    so an expired Apify key can be swapped from the web UI without a redeploy."""
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ScrapeRun(Base):
    """One row per scrape attempt — audit + idempotency anchor."""
    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_date: Mapped[dt.date] = mapped_column(Date, nullable=False, index=True)
    apify_run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)  # running/success/failed
    posts_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[Optional[float]] = mapped_column(Numeric(10, 4), nullable=True)
    started_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class Post(Base):
    """One row per TikTok video. Metrics live in post_metrics (time-series)."""
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kol_id: Mapped[int] = mapped_column(ForeignKey("kols.id"), nullable=False, index=True)
    video_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    posted_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    is_slideshow: Mapped[bool] = mapped_column(Boolean, default=False)
    first_seen: Mapped[dt.date] = mapped_column(Date, nullable=False)
    last_scraped: Mapped[dt.date] = mapped_column(Date, nullable=False)

    kol: Mapped["Kol"] = relationship(back_populates="posts")
    metrics: Mapped[List["PostMetric"]] = relationship(back_populates="post")


class PostMetric(Base):
    """Metric snapshot of a post at a given scrape_date."""
    __tablename__ = "post_metrics"
    __table_args__ = (UniqueConstraint("post_id", "scrape_date", name="uq_post_metric_day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), nullable=False, index=True)
    scrape_date: Mapped[dt.date] = mapped_column(Date, nullable=False, index=True)
    views: Mapped[int] = mapped_column(BigInteger, default=0)
    likes: Mapped[int] = mapped_column(BigInteger, default=0)
    comments: Mapped[int] = mapped_column(BigInteger, default=0)
    shares: Mapped[int] = mapped_column(BigInteger, default=0)
    saves: Mapped[int] = mapped_column(BigInteger, default=0)

    post: Mapped["Post"] = relationship(back_populates="metrics")


class KolDaily(Base):
    """Per-KOL per-day rollup of the trailing 7-day window — fast trend reads."""
    __tablename__ = "kol_daily"
    __table_args__ = (UniqueConstraint("kol_id", "scrape_date", name="uq_kol_daily_day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kol_id: Mapped[int] = mapped_column(ForeignKey("kols.id"), nullable=False, index=True)
    scrape_date: Mapped[dt.date] = mapped_column(Date, nullable=False, index=True)
    followers: Mapped[int] = mapped_column(BigInteger, default=0)
    posts_7d: Mapped[int] = mapped_column(Integer, default=0)
    views_7d: Mapped[int] = mapped_column(BigInteger, default=0)
    likes_7d: Mapped[int] = mapped_column(BigInteger, default=0)
    comments_7d: Mapped[int] = mapped_column(BigInteger, default=0)
    shares_7d: Mapped[int] = mapped_column(BigInteger, default=0)
    saves_7d: Mapped[int] = mapped_column(BigInteger, default=0)
    engagement_rate: Mapped[Optional[float]] = mapped_column(Numeric(8, 5), nullable=True)

    kol: Mapped["Kol"] = relationship(back_populates="dailies")
