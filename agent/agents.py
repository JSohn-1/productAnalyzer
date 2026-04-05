import asyncio
import json
import logging
import os
import re
from datetime import datetime
from typing import List
from uuid import uuid4

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel as PydanticBaseModel
from openai import AsyncOpenAI
from uagents import Agent, Context, Model, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    EndSessionContent,
    TextContent,
    chat_protocol_spec,
)
from browser_use_sdk.v3 import AsyncBrowserUse

load_dotenv()

logger = logging.getLogger(__name__)

asi_client = AsyncOpenAI(
    base_url="https://api.asi1.ai/v1",
    api_key=os.getenv("ASI_API_KEY"),
)

# Browser Use — actually opens a browser and visits real websites
browser_client = AsyncBrowserUse(api_key=os.getenv("BROWSER_USE_API_KEY"))

agent = Agent(
    name="sustainable-product-finder",
    seed=os.getenv("AGENT_SEED", "sustainable-product-finder-default-seed"),
    port=8001,
    mailbox=True,
    publish_agent_details=True,
)


# --- uagents Models ---

class SearchRequest(Model):
    query: str


class ProductResult(Model):
    title: str
    price: str
    location: str
    source: str
    carbon_saved: str
    is_local_business: bool
    repair_suggestion: bool
    repair_text: str = ""
    url: str = ""
    image_url: str = ""


class SearchResponse(Model):
    results: List[ProductResult]
    summary: str


class StatusResponse(Model):
    phase: str
    message: str
    platforms_started: List[str]
    platforms_done: List[str]
    platforms_failed: List[str]
    platform_errors: List[str]


class RawListing(Model):
    title: str
    price: str
    location: str
    url: str
    image_url: str
    source: str


class PartialResultsResponse(Model):
    results: List[RawListing]


# Global orchestrator status — polled by the UI
_orch_status: dict = {
    "phase": "idle",
    "message": "Idle",
    "platforms_started": [],
    "platforms_done": [],
    "platforms_failed": [],
    "platform_errors": [],
}

# Partial results — populated as each scraper finishes
_partial_results: list = []


# --- Pydantic schemas for Browser Use structured output ---

class ScrapedListing(PydanticBaseModel):
    title: str
    price: str
    location: str
    url: str
    image_url: str


# --- Prompts ---

TASK_GEN_PROMPT = """\
Write a concise browser automation task to find a used or refurbished product on {platform}.

The task must instruct the browser to:
Go to {start_url}.
Type "{product}" in the search bar and submit.
Click the filter labeled "Used" or "Refurbished".
Set location filter to "{location}".
Set max price to {price_clause}.

Wait until results are visible.
Click the FIRST result in the list without inspecting others.

On the listing page:
Extract:
- title (exact text)
- price (numeric)
- seller location (text)
- first image URL (src)
- page URL

Return immediately after extraction.
Do not scroll, do not open additional listings, do not re-check results.
Do NOT browse multiple listings. Return as soon as you have a valid result from the first listing.

Output ONLY the task instruction as plain text. No explanation, no JSON, no markdown.
"""

SCORE_PROMPT = """\
You are a sustainability scoring assistant. Given real scraped used/secondhand product listings and the user's original request, enrich the data with sustainability metadata.

User request: {query}

Scraped listings (JSON):
{listings}

Return ONLY valid JSON (no markdown, no explanation):
{{
  "summary": "2-3 sentence summary of the findings and the best pick",
  "results": [
    {{
      "title": "...",
      "price": "...",
      "location": "...",
      "source": "eBay",
      "url": "...",
      "image_url": "...",
      "carbon_saved": "XXkg CO2 saved vs buying new",
      "is_local_business": false,
      "repair_suggestion": false,
      "repair_text": ""
    }},
    {{
      "title": "Got a broken [product type]?",
      "price": "",
      "location": "",
      "source": "",
      "url": "https://www.ifixit.com/Search?query=[product+keywords]",
      "carbon_saved": "",
      "is_local_business": false,
      "repair_suggestion": true,
      "repair_text": "Before replacing it, check if your current one can be repaired. Repairing saves 100% of the manufacturing carbon cost."
    }}
  ]
}}

Rules:
- Preserve title, price, location, and url exactly as scraped
- Estimate carbon_saved: used electronics typically save 50-150kg CO2 vs buying new
- Add exactly 1 repair_suggestion entry at the end with a real iFixit search URL
"""

FALLBACK_PROMPT = """\
Live product scraping failed. Generate 3 realistic placeholder listings for this request and return valid JSON.

User request: {query}

Return ONLY valid JSON (no markdown):
{{
  "summary": "...",
  "results": [
    {{
      "title": "...", "price": "$...", "location": "...",
      "source": "eBay",
      "url": "https://www.ebay.com/sch/i.html?_nkw=QUERY&LH_ItemCondition=3000&_udhi=PRICE",
      "carbon_saved": "XXkg CO2 saved vs buying new",
      "is_local_business": false, "repair_suggestion": false, "repair_text": ""
    }}
  ]
}}
Include 3 results (one per platform) + 1 repair_suggestion at the end.
Use real filtered search URLs: eBay with LH_ItemCondition=3000, Craigslist with max_price, Facebook with condition=used.
"""


PLATFORMS = [
    ("eBay", "https://www.ebay.com"),
    ("Facebook Marketplace", "https://www.facebook.com/marketplace"),
    ("OfferUp", "https://offerup.com/"),
]


async def scrape_site(platform: str, start_url: str, product: str, location: str, max_price: str) -> dict | None:
    global _orch_status, _partial_results
    price_clause = f"Max price: ${max_price}" if max_price else "No price limit specified."

    # Step 1: ASI:One generates the browser task
    r = await asi_client.chat.completions.create(
        model="asi1",
        messages=[{"role": "user", "content": TASK_GEN_PROMPT.format(
            platform=platform,
            start_url=start_url,
            product=product,
            location=location,
            price_clause=price_clause,
        )}],
        max_tokens=300,
    )
    task = r.choices[0].message.content.strip()
    logger.info(f"[{platform}] Browser task: {task}")

    # Step 2: Browser Use executes the task and returns structured output
    try:
        result = await browser_client.run(task, schema=ScrapedListing)
        listing = result.output
        if listing:
            _orch_status["platforms_done"].append(platform)
            result = {
                "title": listing.title,
                "price": listing.price,
                "location": listing.location,
                "url": listing.url,
                "image_url": listing.image_url,
                "source": platform,
            }
            _partial_results.append(result)
            return result
        _orch_status["platforms_failed"].append(platform)
        _orch_status["platform_errors"].append(f"{platform}: page could not load.")
    except Exception as e:
        logger.error(f"Browser scrape failed for {platform}: {type(e).__name__}: {e}")
        _orch_status["platforms_failed"].append(platform)
        _orch_status["platform_errors"].append(f"{platform}: {type(e).__name__}")
    return None


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw[raw.index("\n") + 1:]
        raw = raw[:raw.rfind("```")]
    return json.loads(raw)


async def scrape_and_score(query: str) -> SearchResponse:
    global _orch_status, _partial_results
    _partial_results = []

    price_match = re.search(r'\$(\d+)', query) or re.search(r'budget of \$?(\d+)', query)
    max_price = price_match.group(1) if price_match else ""

    location_match = re.search(r'near (.+?)(?:\.|$)', query)
    location = location_match.group(1).strip() if location_match else "United States"

    product_match = re.search(r'looking for a used (.+?)(?:\s+with|\s+near|\.|$)', query)
    product = product_match.group(1).strip() if product_match else query

    platform_names = [p for p, _ in PLATFORMS]
    _orch_status = {
        "phase": "scraping",
        "message": "Dispatching browser agents...",
        "platforms_started": platform_names,
        "platforms_done": [],
        "platforms_failed": [],
        "platform_errors": [],
    }

    # Scrape all platforms concurrently — one browser session each
    tasks = [
        asyncio.create_task(scrape_site(platform, start_url, product, location, max_price))
        for platform, start_url in PLATFORMS
    ]
    results = await asyncio.gather(*tasks)
    listings = [r for r in results if r is not None]

    if not listings:
        logger.warning("All scrapes failed — using fallback AI generation")
        _orch_status["phase"] = "fallback"
        _orch_status["message"] = "Live scraping failed — generating AI listings..."
        r = await asi_client.chat.completions.create(
            model="asi1",
            messages=[{"role": "user", "content": FALLBACK_PROMPT.format(query=query)}],
            max_tokens=1024,
        )
        data = _parse_json(r.choices[0].message.content)
    else:
        _orch_status["phase"] = "scoring"
        _orch_status["message"] = "Scoring results by carbon saved, locality, and price..."
        r = await asi_client.chat.completions.create(
            model="asi1",
            messages=[{"role": "user", "content": SCORE_PROMPT.format(
                query=query,
                listings=json.dumps(listings, indent=2),
            )}],
            max_tokens=1024,
        )
        data = _parse_json(r.choices[0].message.content)

    _orch_status["phase"] = "done"
    _orch_status["message"] = "Done"
    return SearchResponse(
        results=[ProductResult(**item) for item in data["results"]],
        summary=data["summary"],
    )


# --- REST endpoints ---

@agent.on_rest_get("/status", StatusResponse)
async def handle_status(_ctx: Context) -> StatusResponse:
    return StatusResponse(**_orch_status)


@agent.on_rest_get("/partial", PartialResultsResponse)
async def handle_partial(_ctx: Context) -> PartialResultsResponse:
    return PartialResultsResponse(results=[RawListing(**r) for r in _partial_results])


@agent.on_rest_post("/search", SearchRequest, SearchResponse)
async def handle_rest_search(ctx: Context, req: SearchRequest) -> SearchResponse:
    ctx.logger.info(f"REST /search: {req.query}")
    try:
        return await scrape_and_score(req.query)
    except Exception:
        ctx.logger.exception("Error in /search")
        return SearchResponse(results=[], summary="Something went wrong. Please try again.")


# --- Chat protocol ---

protocol = Protocol(spec=chat_protocol_spec)


@protocol.on_message(ChatMessage)
async def handle_message(ctx: Context, sender: str, msg: ChatMessage):
    await ctx.send(
        sender,
        ChatAcknowledgement(timestamp=datetime.now(), acknowledged_msg_id=msg.msg_id),
    )

    text = "".join(item.text for item in msg.content if isinstance(item, TextContent))

    try:
        result = await scrape_and_score(text)
        lines = [result.summary, ""]
        for r in result.results:
            if r.repair_suggestion:
                lines.append(f"- **Repair first:** {r.title} — {r.repair_text}")
            else:
                label = "🏢 Local SMB" if r.is_local_business else r.source
                lines.append(f"- **{r.title}** ({r.price}) — {label} · {r.location}")
        response_text = "\n".join(lines)
    except Exception:
        ctx.logger.exception("Error in chat handler")
        response_text = "Sorry, I couldn't process that request."

    await ctx.send(sender, ChatMessage(
        timestamp=datetime.utcnow(),
        msg_id=uuid4(),
        content=[
            TextContent(type="text", text=response_text),
            EndSessionContent(type="end-session"),
        ],
    ))


@protocol.on_message(ChatAcknowledgement)
async def handle_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    pass


agent.include(protocol, publish_manifest=True)

if __name__ == "__main__":
    print(f"Agent address: {agent.address}")
    agent.run()
