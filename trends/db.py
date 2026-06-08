from __future__ import annotations

import json
from pathlib import Path

import duckdb
from loguru import logger

from scraper.adapter import TrendRecord


def init_db(db_path: Path) -> duckdb.DuckDBPyConnection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trends (
            trend_id VARCHAR PRIMARY KEY,
            label VARCHAR,
            category VARCHAR,
            primary_hashtag VARCHAR,
            related_hashtags VARCHAR,
            topic_label VARCHAR,
            state VARCHAR,
            first_seen VARCHAR,
            last_seen VARCHAR,
            weeks_active INTEGER,
            weeks_missing INTEGER,
            current_rank INTEGER,
            rank_history VARCHAR,
            engagement_history VARCHAR,
            velocity_pct DOUBLE,
            momentum_score DOUBLE,
            predicted_peak VARCHAR,
            crossover_categories VARCHAR,
            top_creators VARCHAR,
            top_sounds VARCHAR,
            sample_videos VARCHAR
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS weekly_snapshots (
            week VARCHAR,
            category VARCHAR,
            trend_id VARCHAR,
            snapshot_json VARCHAR,
            PRIMARY KEY (week, category, trend_id)
        )
    """)
    logger.info(f"Initialized DuckDB at {db_path}")
    return conn


def upsert_trend(conn: duckdb.DuckDBPyConnection, trend: TrendRecord) -> None:
    conn.execute("""
        INSERT OR REPLACE INTO trends VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
    """, [
        trend.trend_id,
        trend.label,
        trend.category,
        trend.primary_hashtag,
        json.dumps(trend.related_hashtags),
        trend.topic_label,
        trend.state,
        trend.first_seen,
        trend.last_seen,
        trend.weeks_active,
        trend.weeks_missing,
        trend.current_rank,
        json.dumps(trend.rank_history),
        json.dumps(trend.engagement_history),
        trend.velocity_pct,
        trend.momentum_score,
        trend.predicted_peak,
        json.dumps(trend.crossover_categories),
        json.dumps(trend.top_creators),
        json.dumps(trend.top_sounds),
        json.dumps(trend.sample_videos),
    ])


def _row_to_trend(row: tuple) -> TrendRecord:
    return TrendRecord(
        trend_id=row[0],
        label=row[1],
        category=row[2],
        primary_hashtag=row[3],
        related_hashtags=json.loads(row[4] or "[]"),
        topic_label=row[5],
        state=row[6],
        first_seen=row[7],
        last_seen=row[8],
        weeks_active=row[9],
        weeks_missing=row[10],
        current_rank=row[11],
        rank_history=json.loads(row[12] or "[]"),
        engagement_history=json.loads(row[13] or "[]"),
        velocity_pct=row[14],
        momentum_score=row[15],
        predicted_peak=row[16],
        crossover_categories=json.loads(row[17] or "[]"),
        top_creators=json.loads(row[18] or "[]"),
        top_sounds=json.loads(row[19] or "[]"),
        sample_videos=json.loads(row[20] or "[]"),
    )


def get_active_trends(conn: duckdb.DuckDBPyConnection, category: str) -> list[TrendRecord]:
    rows = conn.execute(
        "SELECT * FROM trends WHERE category = ? AND state != 'ARCHIVED'",
        [category],
    ).fetchall()
    return [_row_to_trend(r) for r in rows]


def get_all_trends(conn: duckdb.DuckDBPyConnection, category: str) -> list[TrendRecord]:
    rows = conn.execute(
        "SELECT * FROM trends WHERE category = ?",
        [category],
    ).fetchall()
    return [_row_to_trend(r) for r in rows]


def save_weekly_snapshot(
    conn: duckdb.DuckDBPyConnection,
    week: str,
    trends: list[TrendRecord],
) -> None:
    for trend in trends:
        conn.execute("""
            INSERT OR REPLACE INTO weekly_snapshots (week, category, trend_id, snapshot_json)
            VALUES (?, ?, ?, ?)
        """, [week, trend.category, trend.trend_id, trend.model_dump_json()])
    logger.info(f"Saved {len(trends)} trend snapshots for week {week}")


def get_weekly_snapshot(
    conn: duckdb.DuckDBPyConnection,
    week: str,
    category: str,
) -> list[TrendRecord]:
    rows = conn.execute(
        "SELECT snapshot_json FROM weekly_snapshots WHERE week = ? AND category = ?",
        [week, category],
    ).fetchall()
    trends = []
    for (snapshot_json,) in rows:
        try:
            trends.append(TrendRecord.model_validate_json(snapshot_json))
        except Exception as e:
            logger.warning(f"Could not deserialize snapshot: {e}")
    return trends
