"""SQLite 스키마와 연결 (기획서 §4 DB 스키마 + 운영에 필요한 컬럼 최소 추가)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS channels (
  channel_id TEXT PRIMARY KEY,
  title TEXT, handle TEXT, country TEXT, category TEXT,
  "group" TEXT,                      -- 내 채널 그룹(시드 JSON의 키) 또는 규칙 매핑 결과
  source TEXT,                       -- seed / chart / snowball
  added_at TEXT, active INTEGER DEFAULT 1,
  uploads_playlist TEXT, thumb TEXT, published_at TEXT,
  last_stats_at TEXT,                -- channels.list 로 마지막 갱신한 날짜
  last_videos_at TEXT                -- 최근 영상 목록을 마지막으로 수집한 날짜
);
CREATE TABLE IF NOT EXISTS channel_daily (
  channel_id TEXT, date TEXT, subs INTEGER, views INTEGER, videos INTEGER,
  PRIMARY KEY (channel_id, date)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS videos (
  video_id TEXT PRIMARY KEY, channel_id TEXT, title TEXT, published_at TEXT,
  duration_s INTEGER, is_short INTEGER, category_id TEXT, tags TEXT,
  thumb TEXT, lang TEXT,
  views INTEGER, likes INTEGER, comments INTEGER, stats_at TEXT   -- 최신 통계(빠른 조회용)
);
CREATE TABLE IF NOT EXISTS video_daily (
  video_id TEXT, date TEXT, views INTEGER, likes INTEGER, comments INTEGER,
  PRIMARY KEY (video_id, date)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS chart_daily (
  date TEXT, category_id TEXT, format TEXT, rank INTEGER, video_id TEXT,
  PRIMARY KEY (date, category_id, format, rank)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS ai_teardown (
  video_id TEXT PRIMARY KEY, model TEXT, created_at TEXT, json TEXT
);
CREATE TABLE IF NOT EXISTS quota_log (
  date TEXT, job TEXT, endpoint TEXT, units INTEGER, calls INTEGER,
  PRIMARY KEY (date, job, endpoint)
);
CREATE INDEX IF NOT EXISTS idx_videos_channel ON videos(channel_id, published_at);
CREATE INDEX IF NOT EXISTS idx_chart_video ON chart_daily(video_id);
CREATE INDEX IF NOT EXISTS idx_video_daily_date ON video_daily(date);
"""


def connect(path: Path | str) -> sqlite3.Connection:
    p = Path(path)
    if str(p) != ":memory:":
        p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(p))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=DELETE")
    con.executescript(SCHEMA)
    return con
