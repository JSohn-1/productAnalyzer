import asyncio
import json
import logging
import os
import re
from datetime import datetime
from typing import List, Optional, Union
from uuid import uuid4

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel as PydanticBaseModel
from openai import AsyncOpenAI
from uagents import Agent, Context, Model, Protocol
# from uagents_core.contrib.protocols.chat import (
#     ChatAcknowledgement,
#     ChatMessage,
#     EndSessionContent,
#     TextContent,
#     chat_protocol_spec,
# )
from browser_use_sdk.v3 import AsyncBrowserUse

load_dotenv()

logger = logging.getLogger(__name__)

asi_client = AsyncOpenAI(
    base_url="https://api.asi1.ai/v1",
    api_key=os.getenv("ASI_API_KEY"),
)

# Browser Use — actually opens a browser and visits real websites
browser_client = AsyncBrowserUse(api_key=os.getenv("BROWSERUSE_API_KEY"))

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
    sustainability_score: float = 0.0
    price_score: float = 0.0
    locality_score: float = 0.0
    final_score: float = 0.0


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

- Preserve title, price, location, and url exactly as scraped
- image_url MUST be a direct URL. If missing or malformed, use a high-quality placeholder: https://source.unsplash.com/400x300/?product
- Estimate carbon_saved: used electronics typically save 50-150kg CO2 vs buying new
- Add exactly 1 repair_suggestion entry at the end with a real iFixit search URL
- NO markdown formatting (like ![...](...)) in JSON values.
"""

FALLBACK_PROMPT = """\
Live product scraping failed. Generate 3 realistic placeholder listings for this request and return valid JSON.

User request: {query}

Return ONLY valid JSON (no markdown, no backticks):
{{
  "summary": "AI generated placeholder listings because live scraping is currently unavailable.",
  "results": [
    {{
      "title": "...", "price": "$...", "location": "...",
      "source": "eBay",
      "url": "https://www.ebay.com/sch/i.html?_nkw=QUERY&LH_ItemCondition=3000",
      "image_url": "https://images.unsplash.com/photo-1550745165-9bc0b2527233?auto=format&fit=crop&q=80&w=400",
      "carbon_saved": "XXkg CO2 saved vs buying new",
      "is_local_business": false, "repair_suggestion": false, "repair_text": ""
    }}
  ]
}}

Rules:
- Include 3 results (one per platform) + 1 repair_suggestion at the end.
- image_url MUST be a direct link to a high-quality product photo (use Unsplash search-by-keyword structure: https://source.unsplash.com/400x300/?PRODUCT_KEYWORD).
- NEVER use markdown syntax (like ![...](...)) in any field.
"""


PLATFORMS = [
    ("eBay", "https://www.ebay.com"),
    ("Facebook Marketplace", "https://www.facebook.com/marketplace"),
    ("OfferUp", "https://offerup.com/"),
]


async def scrape_site(platform: str, start_url: str, product: str, location: str, max_price: str) -> Optional[dict]:
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
    cleaned = raw.strip()

    # Handle fenced code blocks from LLM responses (```json ... ``` or ``` ... ```).
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, count=1, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned, count=1)
        cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Some responses include extra prose before/after JSON.
        # Fall back to parsing the first JSON object present.
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _clean_url(url: str) -> str:
    if not url:
        return ""
    # Strip markdown syntax ![...](url) or [...](url)
    match = re.search(r'\]\((https?://[^\)]+)\)', url)
    if match:
        return match.group(1).strip()
    # Strip backticks
    return url.replace("`", "").strip()


def _extract_number(raw: str) -> Optional[float]:
    if not raw:
        return None
    match = re.search(r"[-+]?\d[\d,]*(?:\.\d+)?", raw)
    if not match:
        return None
    return float(match.group(0).replace(",", ""))


def _compute_weighted_scores(
    results: list[dict], 
    sustainability_weight: float = 0.5, 
    price_weight: float = 0.3,
    locality_weight: float = 0.2
) -> list[dict]:
    scored_candidates: list[dict] = []
    repair_entries: list[dict] = []

    for item in results:
        if item.get("repair_suggestion"):
            item["sustainability_score"] = 0.0
            item["price_score"] = 0.0
            item["locality_score"] = 0.0
            item["final_score"] = 0.0
            repair_entries.append(item)
            continue
        scored_candidates.append(item)

    if not scored_candidates:
        return repair_entries

    carbon_values = [_extract_number(i.get("carbon_saved", "")) for i in scored_candidates]
    price_values = [_extract_number(i.get("price", "")) for i in scored_candidates]

    known_carbon = [v for v in carbon_values if v is not None]
    known_prices = [v for v in price_values if v is not None]

    carbon_min = min(known_carbon) if known_carbon else 0.0
    carbon_max = max(known_carbon) if known_carbon else 0.0
    price_min = min(known_prices) if known_prices else 0.0
    price_max = max(known_prices) if known_prices else 0.0

    for item, carbon, price in zip(scored_candidates, carbon_values, price_values):
        # 1. Sustainability Score (Carbon)
        if carbon is None or carbon_max == carbon_min:
            sustainability_score = 1.0 if carbon is not None else 0.0
        else:
            sustainability_score = (carbon - carbon_min) / (carbon_max - carbon_min)

        # 2. Price Score (Inverse - cheaper is better)
        if price is None or price_max == price_min:
            price_score = 1.0 if price is not None else 0.0
        else:
            price_score = (price_max - price) / (price_max - price_min)

        # 3. Locality Score (Binary bonus for now)
        locality_score = 1.0 if item.get("is_local_business") else 0.0

        # Weighted Final Score
        final_score = (
            (sustainability_weight * sustainability_score) + 
            (price_weight * price_score) + 
            (locality_weight * locality_score)
        )

        item["sustainability_score"] = round(sustainability_score, 2)
        item["price_score"] = round(price_score, 2)
        item["locality_score"] = round(locality_score, 2)
        item["final_score"] = round(final_score, 2)

    scored_candidates.sort(
        key=lambda i: (i.get("final_score", 0.0), i.get("sustainability_score", 0.0), i.get("price_score", 0.0)),
        reverse=True,
    )
    return scored_candidates + repair_entries


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

    for item in data.get("results", []):
        item["image_url"] = _clean_url(item.get("image_url", ""))
        
    data["results"] = _compute_weighted_scores(data.get("results", []))

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


# --- Chat protocol (Stubbed due to mission dependency) ---
# protocol = Protocol(spec=chat_protocol_spec)
# ... chat handlers ...
# agent.include(protocol, publish_manifest=True)

if __name__ == "__main__":
    print(f"Agent address: {agent.address}")
    agent.run()
