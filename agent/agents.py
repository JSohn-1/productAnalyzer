import json
import os
from datetime import datetime
from typing import List
from uuid import uuid4

from dotenv import load_dotenv
from openai import OpenAI
from uagents import Agent, Context, Model, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    EndSessionContent,
    TextContent,
    chat_protocol_spec,
)

load_dotenv()

client = OpenAI(
    base_url='https://api.asi1.ai/v1',
    api_key=os.getenv("ASI_API_KEY"),
)

agent = Agent(
    name="sustainable-product-finder",
    seed=os.getenv("AGENT_SEED", "sustainable-product-finder-default-seed"),
    port=8001,
    mailbox=True,
    publish_agent_details=True,
)


# --- Models ---

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


class SearchResponse(Model):
    results: List[ProductResult]
    summary: str


# --- Core search logic ---

SYSTEM_PROMPT = """
You are a sustainable product sourcing assistant. Given a user request, generate realistic search results
from Craigslist, Facebook Marketplace, and local business directories.

Return ONLY valid JSON (no markdown code fences, no explanation) with this exact structure:
{
  "summary": "2-3 sentence assistant message summarizing what you found and the best pick",
  "results": [
    {
      "title": "product name and condition",
      "price": "$XXX",
      "location": "city or distance description",
      "source": "Craigslist | Facebook Marketplace | Local Business",
      "carbon_saved": "XXkg CO2 saved vs buying new",
      "is_local_business": false,
      "repair_suggestion": false,
      "repair_text": "",
      "url": "https://..."
    }
  ]
}

Rules:
- Include 2-3 used/refurbished product results
- Add 1 final entry with repair_suggestion: true (title like "Got a broken X?", no price/source needed, fill repair_text)
- Local business entries: set is_local_business: true, include store name + distance in location, leave url empty
- carbon_saved: realistic estimates — used electronics save 50-150kg CO2 vs new; leave empty for repair/local entries
- Stay within the user's stated budget where possible; flag if slightly over
- url field: for Craigslist use a real craigslist.org search URL for the product (e.g. https://sfbay.craigslist.org/search/sss?query=4k+monitor), for Facebook Marketplace use https://www.facebook.com/marketplace/search/?query=4k+monitor, for repair entries use https://www.ifixit.com/Search?query=monitor — replace spaces with + and match the product
"""


def call_asi_one(query: str) -> SearchResponse:
    r = client.chat.completions.create(
        model="asi1",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ],
        max_tokens=1024,
    )

    raw = r.choices[0].message.content.strip()

    # Strip markdown code fences if the model adds them
    if raw.startswith("```"):
        raw = raw[raw.index("\n") + 1:]
        raw = raw[:raw.rfind("```")]

    data = json.loads(raw)
    results = [ProductResult(**item) for item in data["results"]]
    return SearchResponse(results=results, summary=data["summary"])


# --- REST endpoint (called by Streamlit UI) ---

@agent.on_rest_post("/search", SearchRequest, SearchResponse)
async def handle_rest_search(ctx: Context, req: SearchRequest) -> SearchResponse:
    ctx.logger.info(f"REST /search: {req.query}")
    try:
        return call_asi_one(req.query)
    except Exception:
        ctx.logger.exception("Error in /search")
        return SearchResponse(results=[], summary="Something went wrong. Please try again.")


# --- Chat protocol (for Agentverse / DeltaV compatibility) ---

protocol = Protocol(spec=chat_protocol_spec)


@protocol.on_message(ChatMessage)
async def handle_message(ctx: Context, sender: str, msg: ChatMessage):
    await ctx.send(
        sender,
        ChatAcknowledgement(timestamp=datetime.now(), acknowledged_msg_id=msg.msg_id),
    )

    text = "".join(item.text for item in msg.content if isinstance(item, TextContent))

    try:
        result = call_asi_one(text)
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
