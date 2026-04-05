import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from uagents import Agent, Context
from agent.scraper_base import ScrapeRequest, ScrapeResponse, ScraperStatus, scrape_site

PLATFORM = "FaceBook Marketplace"
START_URL = "https://www.facebook.com/marketplace"

agent = Agent(
    name="scraper-facebook",
    seed=os.getenv("AGENT_SEED", "scraper-facebook-default-seed"),
    port=8003,
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
    if "_error" in result:
        error_msg = result["_error"]
        _status["message"] = error_msg
        return ScrapeResponse(source=PLATFORM, success=False, error_message=error_msg)
    _status = {"phase": "done", "message": "Done"}
    return ScrapeResponse(**result, source=PLATFORM, success=True)


if __name__ == "__main__":
    print(f"Facebook scraper agent address: {agent.address}")
    agent.run()
