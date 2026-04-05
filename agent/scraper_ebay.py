import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from uagents import Agent, Context
from agent.scraper_base import ScrapeRequest, ScrapeResponse, ScraperStatus, scrape_site

PLATFORM = "eBay"
START_URL = "https://www.ebay.com"

agent = Agent(
    name="scraper-ebay",
    seed=os.getenv("AGENT_SEED", "scraper-ebay-default-seed"),
    port=8002,
)

_status: dict = {"phase": "idle", "message": "Idle"}


@agent.on_rest_get("/status", ScraperStatus)
async def handle_status(_ctx: Context) -> ScraperStatus:
    return ScraperStatus(**_status)


@agent.on_rest_post("/scrape", ScrapeRequest, ScrapeResponse)
async def handle_scrape(_ctx: Context, req: ScrapeRequest) -> ScrapeResponse:
    global _status
    _status = {"phase": "starting", "message": f"Starting {PLATFORM} scrape..."}
    result = await scrape_site(PLATFORM, START_URL, req.product, req.location, req.max_price, _status)
    if result:
        _status = {"phase": "done", "message": "Done"}
        return ScrapeResponse(**result, source=PLATFORM, success=True)
    _status = {"phase": "failed", "message": f"{PLATFORM} scrape failed"}
    return ScrapeResponse(source=PLATFORM, success=False)


if __name__ == "__main__":
    print(f"eBay scraper agent address: {agent.address}")
    agent.run()
