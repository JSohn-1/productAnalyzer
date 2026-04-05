import logging
import os

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic import BaseModel as PydanticBaseModel
from uagents import Model
from browser_use_sdk.v3 import AsyncBrowserUse

load_dotenv()

logger = logging.getLogger(__name__)

asi_client = AsyncOpenAI(
    base_url="https://api.asi1.ai/v1",
    api_key=os.getenv("ASI_API_KEY"),
)
browser_client = AsyncBrowserUse(api_key=os.getenv("BROWSER_USE_API_KEY"))

TASK_GEN_PROMPT = """\
Write a concise browser automation task to find a used or refurbished product on {platform}.

Product: {product}
Location: {location}
{price_clause}

The task must instruct the browser to:
1. Go to {start_url}
2. Search for the product
3. Filter for used or refurbished condition only
4. Filter results to listings near "{location}" only
5. Apply a max price filter if a budget was specified
6. Open the FIRST listing in the results that has a valid URL and price
7. Extract: exact title, listed price, seller location, and the direct URL of that listing page
8. Stop immediately as soon as you have extracted the data — do NOT open or check any other listings

Do NOT browse multiple listings. Return as soon as you have a valid result from the first listing.

Output ONLY the task instruction as plain text. No explanation, no JSON, no markdown.
"""


class ScrapeRequest(Model):
    product: str
    location: str
    max_price: str


class ScrapeResponse(Model):
    title: str = ""
    price: str = ""
    location: str = ""
    url: str = ""
    source: str = ""
    success: bool = False


class ScraperStatus(Model):
    phase: str
    message: str


class ScrapedListing(PydanticBaseModel):
    title: str
    price: str
    location: str
    url: str


async def scrape_site(
    platform: str,
    start_url: str,
    product: str,
    location: str,
    max_price: str,
    status: dict,
) -> dict | None:
    price_clause = f"Max price: ${max_price}" if max_price else "No price limit specified."

    status.update({"phase": "generating", "message": f"Generating task for {platform}..."})

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

    status.update({"phase": "browsing", "message": f"Browsing {platform}..."})

    try:
        result = await browser_client.run(task, schema=ScrapedListing)
        listing = result.output
        if listing:
            return {
                "title": listing.title,
                "price": listing.price,
                "location": listing.location,
                "url": listing.url,
            }
    except Exception as e:
        logger.error(f"Browser scrape failed for {platform}: {type(e).__name__}: {e}")

    return None
