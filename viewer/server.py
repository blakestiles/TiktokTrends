from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jinja2
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from scraper.adapter import TrendRecord
from trends.db import get_active_trends, get_all_trends, get_weekly_snapshot, init_db

ROOT = Path(__file__).parent.parent
DB_PATH = ROOT / "data" / "trends.duckdb"
TEMPLATES_DIR = Path(__file__).parent / "templates"
RUNS_DIR = ROOT / "runs"
ACTIVE_DIR = ROOT / "data" / "active"

app = FastAPI(title="TikTok Trend Tracker")
_jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=jinja2.select_autoescape(["html"]),
    cache_size=0,
)
templates = Jinja2Templates(env=_jinja_env)

CATEGORIES = ["games", "card_games", "games_marketing"]


def _get_conn():
    return init_db(DB_PATH)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, category: str = "games"):
    conn = _get_conn()
    trends = get_active_trends(conn, category)
    conn.close()

    trends_sorted = sorted(trends, key=lambda t: t.current_rank)

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "trends": trends_sorted,
            "categories": CATEGORIES,
            "selected_category": category,
        },
    )


@app.get("/trends", response_class=HTMLResponse)
async def trends_partial(request: Request, category: str = "games"):
    conn = _get_conn()
    trends = get_active_trends(conn, category)
    conn.close()
    trends_sorted = sorted(trends, key=lambda t: t.current_rank)

    return templates.TemplateResponse(
        request,
        "partials/trend_rows.html",
        {
            "trends": trends_sorted,
            "selected_category": category,
        },
    )


@app.get("/trend/{trend_id}", response_class=HTMLResponse)
async def trend_detail(request: Request, trend_id: str):
    conn = _get_conn()
    for cat in CATEGORIES:
        all_trends = get_all_trends(conn, cat)
        for t in all_trends:
            if t.trend_id == trend_id:
                conn.close()
                return templates.TemplateResponse(
                    request,
                    "detail.html",
                    {"trend": t, "categories": CATEGORIES},
                )
    conn.close()
    return HTMLResponse("<p>Trend not found.</p>", status_code=404)


@app.get("/api/trends")
async def api_trends(category: str = "games"):
    active_path = ACTIVE_DIR / f"{category}.json"
    if active_path.exists():
        data = json.loads(active_path.read_text(encoding="utf-8"))
        return JSONResponse(content=data)
    return JSONResponse(content=[])


@app.get("/api/report/latest")
async def api_latest_report():
    report_files = sorted(RUNS_DIR.glob("*-report.json"))
    if not report_files:
        return JSONResponse(content={})
    latest = report_files[-1]
    data = json.loads(latest.read_text(encoding="utf-8"))
    return JSONResponse(content=data)


@app.get("/api/sparkline/{trend_id}")
async def api_sparkline(trend_id: str):
    conn = _get_conn()
    for cat in CATEGORIES:
        all_trends = get_all_trends(conn, cat)
        for t in all_trends:
            if t.trend_id == trend_id:
                conn.close()
                return JSONResponse(content={
                    "engagement_history": t.engagement_history,
                    "rank_history": t.rank_history,
                    "weeks_active": t.weeks_active,
                })
    conn.close()
    return JSONResponse(content={}, status_code=404)
