from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from loguru import logger

DEBUG_DIR = Path(__file__).parent.parent.parent / "data" / "debug"


async def fetch_trending_playwright() -> list[dict]:
    from playwright.async_api import async_playwright

    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    debug_path = DEBUG_DIR / f"{date_str}-playwright-raw.json"

    intercepted: list[dict] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            },
        )
        page = await context.new_page()

        async def handle_response(response):
            url = response.url
            if "/api/recommend/item_list/" in url or "/api/discover/" in url:
                try:
                    body = await response.json()
                    items = (
                        body.get("itemList", [])
                        or body.get("item_list", [])
                        or body.get("data", {}).get("videos", [])
                        or []
                    )
                    if items:
                        logger.info(f"Playwright intercepted {len(items)} items from {url}")
                        intercepted.extend(items)
                except Exception as e:
                    logger.debug(f"Could not parse intercepted response from {url}: {e}")

        page.on("response", handle_response)

        logger.info("Playwright navigating to TikTok trending page")
        try:
            await page.goto(
                "https://www.tiktok.com/discover/trending-videos-this-week",
                wait_until="domcontentloaded",
                timeout=30000,
            )
        except Exception as e:
            logger.warning(f"Navigation error (non-fatal): {e}")

        import asyncio
        await asyncio.sleep(15)

        await browser.close()

    debug_payload = {"intercepted_count": len(intercepted), "items": intercepted}
    try:
        debug_path.write_text(json.dumps(debug_payload, default=str, indent=2), encoding="utf-8")
        logger.info(f"Saved playwright debug payload to {debug_path}")
    except Exception as e:
        logger.warning(f"Could not save debug payload: {e}")

    return intercepted
