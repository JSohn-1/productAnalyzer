import streamlit as st
import httpx
import threading
import time
import subprocess
import atexit
import sys
import os

AGENT_URL = "http://localhost:8001/search"
PARTIAL_URL = "http://localhost:8001/partial"

# Start the agent backend automatically (runs once when this module is imported)
_agent_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agent", "agents.py")
_agent_proc = subprocess.Popen([sys.executable, _agent_path])
atexit.register(_agent_proc.terminate)
time.sleep(2)

st.set_page_config(page_title="Sustainable Products", layout="wide")


def load_css():
    try:
        with open("style.css", "r") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except Exception:
        st.warning("Could not load style.css")


STATUS_URL = "http://localhost:8001/status"


def search_products(query: str):
    try:
        response = httpx.post(AGENT_URL, json={"query": query}, timeout=300.0)
        response.raise_for_status()
        return response.json()
    except httpx.ConnectError:
        return None
    except Exception as e:
        st.error(f"Agent error: {e}")
        return None


def get_status() -> dict | None:
    try:
        response = httpx.get(STATUS_URL, timeout=3.0)
        response.raise_for_status()
        return response.json()
    except Exception:
        return None


def get_partial() -> list:
    try:
        response = httpx.get(PARTIAL_URL, timeout=3.0)
        response.raise_for_status()
        return response.json().get("results", [])
    except Exception:
        return []


def search_in_background(query: str, container: dict):
    container["result"] = search_products(query)
    container["done"] = True


def render_results(results):
    for item in results:
        url = item.get("url", "")
        img_url = item.get("image_url", "")
        if item.get("repair_suggestion"):
            st.markdown(f'''
                <div class="glass">
                    <div class="repair-banner">Repair-First Suggestion</div>
                    <div class="product-title">{item["title"]}</div>
                    <div class="product-detail">{item.get("repair_text", "Before buying a replacement, check if your current item can be repaired. Extend its lifespan and save 100% of the carbon cost.")}</div>
                    <div style="margin-top: 15px;">
                        <a href="{url or "https://www.ifixit.com"}" target="_blank" style="color: #58a6ff; font-weight: 500;">View iFixit Repair Guides ➔</a>
                    </div>
                </div>
            ''', unsafe_allow_html=True)
        elif item.get("is_local_business"):
            st.markdown(f'''
                <div class="glass" style="margin-bottom: 20px;">
                    <div class="carbon-badge" style="background: linear-gradient(135deg, #1f6feb 0%, #388bfd 100%);">🏢 Local SMB Supported</div>
                    <div class="product-title">{item["title"]}</div>
                    <div class="product-detail">Location: {item["location"]}</div>
                    <div class="product-detail">Source: {item["source"]}</div>
                    <div class="price">{item["price"]}</div>
                    <a class="pay-button" style="background-color: #1f6feb; box-shadow: 0 4px 15px rgba(31, 111, 235, 0.3); text-decoration: none; display: inline-block;">Call Store & Reserve</a>
                </div>
            ''', unsafe_allow_html=True)
        else:
            carbon = item.get("carbon_saved", "")
            badge = f'<div class="carbon-badge">Carbon Saved: {carbon}</div>' if carbon else ""
            link = f'href="{url}" target="_blank"' if url else ""
            img_tag = f'<div class="product-image"><img src="{img_url}" style="width: 100%; height: auto; max-height: 250px; object-fit: cover; border-radius: 8px; display: block;"></div>' if img_url else ""
            st.markdown(f'''
                <div class="glass" style="margin-bottom: 20px;">
                    {badge}
                    {img_tag}
                    <div class="product-title">{item["title"]}</div>
                    <div class="product-detail">Location: {item["location"]}</div>
                    <div class="product-detail">Source: {item["source"]}</div>
                    <div class="price">{item["price"]}</div>
                    <a class="pay-button" {link} style="text-decoration: none; display: inline-block;">View Listing ➔</a>
                </div>
            ''', unsafe_allow_html=True)


def run():
    load_css()
    st.title("Sustainable Products Finder")
    st.markdown("<div class='subtitle'>ASI:One Intelligent Orchestrator</div>", unsafe_allow_html=True)

    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "workflow_status" not in st.session_state:
        st.session_state.workflow_status = "idle"
    if "search_results" not in st.session_state:
        st.session_state.search_results = None
    if "pending_query" not in st.session_state:
        st.session_state.pending_query = None
    if "search_task" not in st.session_state:
        st.session_state.search_task = None

    col_chat, col_dash = st.columns([1, 1], gap="large")

    with col_chat:
        st.markdown("### ASI:One Chat")

        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"].replace("$", "&#36;"))

        with st.form("search_form", clear_on_submit=False):
            product = st.text_input("Product", placeholder="e.g. 4K monitor, bicycle, sofa")
            col_loc, col_price = st.columns(2)
            with col_loc:
                location = st.text_input("Location", placeholder="e.g. San Francisco, CA")
            with col_price:
                max_price = st.text_input("Max Price ($)", placeholder="e.g. 200")
            submitted = st.form_submit_button("Find Sustainable Listings", use_container_width=True)

        if submitted and product.strip():
            parts = [f"I'm looking for a used {product.strip()}"]
            if max_price.strip():
                parts.append(f"with a budget of ${max_price.strip()}")
            if location.strip():
                parts.append(f"near {location.strip()}")
            query = " ".join(parts) + "."

            st.session_state.messages.append({"role": "user", "content": query})
            st.session_state.workflow_status = "searching"
            st.session_state.pending_query = query
            st.rerun()

    with col_dash:
        st.markdown("### Orchestrator Dashboard")

        if st.session_state.workflow_status == "idle":
            st.info("Awaiting Intent. Ask me to find something sustainable!")

        elif st.session_state.workflow_status == "searching":
            with st.status("Searching live listings via Browser Use...", expanded=True) as status:
                st.write("**Generating search tasks** with ASI:One...")
                st.write("**Scraping** eBay, OfferUp, and Facebook Marketplace in parallel (this takes ~1-2 min)...")
                phase_placeholder = st.empty()
                platforms_placeholder = st.empty()

                if st.session_state.search_task is None:
                    st.session_state.result_container = {"result": None, "done": False}
                    t = threading.Thread(
                        target=search_in_background,
                        args=(st.session_state.pending_query, st.session_state.result_container),
                        daemon=True,
                    )
                    t.start()
                    st.session_state.search_task = t

                result_container = st.session_state.result_container
                partial_placeholder = st.empty()

                while not result_container["done"]:
                    s = get_status()
                    if s:
                        phase_placeholder.markdown(f"**{s['message']}**")
                        rows = []
                        for p in s.get("platforms_started", []):
                            if p in s.get("platforms_done", []):
                                rows.append(f"✅ **{p}** — done")
                            elif p in s.get("platforms_failed", []):
                                error = next(
                                    (e.split(": ", 1)[1] for e in s.get("platform_errors", []) if e.startswith(f"{p}:")),
                                    "failed",
                                )
                                rows.append(f"❌ **{p}** — {error}")
                            else:
                                rows.append(f"🔍 **{p}** — browsing...")
                        if rows:
                            platforms_placeholder.markdown("  \n".join(rows))
                    else:
                        phase_placeholder.markdown("*Connecting to orchestrator...*")

                    partial = get_partial()
                    if partial:
                        html = ""
                        for item in partial:
                            url = item.get("url", "")
                            link_attr = f'href="{url}" target="_blank"' if url else ""
                            img_url = item.get("image_url", "")
                            img_tag = f'<div class="product-image"><img src="{img_url}" style="width: 100%; height: auto; max-height: 250px; object-fit: cover; border-radius: 8px; display: block;"></div>' if img_url else ""

                            html += f'''
                                <div class="glass" style="margin-bottom:12px;">
                                    {img_tag}
                                    <div class="product-title">{item["title"]}</div>
                                    <div class="product-detail">{item["source"]} · {item["location"]}</div>
                                    <div class="price">{item["price"]}</div>
                                    <a class="pay-button" {link_attr} style="text-decoration:none;display:inline-block;">View Listing ➔</a>
                                </div>
                            '''
                        partial_placeholder.markdown(html, unsafe_allow_html=True)

                    time.sleep(1)

                st.session_state.search_task.join()
                data = result_container["result"]
                st.session_state.search_task = None

                if data is None:
                    status.update(
                        label="Could not reach agent — please restart the app.",
                        state="error",
                    )
                    st.session_state.workflow_status = "idle"
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": "Could not connect to the agent. Please restart the app and try again.",
                    })
                else:
                    status.update(label="Live listings found!", state="complete", expanded=False)
                    st.session_state.search_results = data.get("results", [])
                    st.session_state.workflow_status = "found"
                    summary = data.get("summary", "Here are the best sustainable options I found.")
                    st.session_state.messages.append({"role": "assistant", "content": summary})

            st.rerun()

        elif st.session_state.workflow_status == "found":
            if st.session_state.search_results:
                render_results(st.session_state.search_results)

        if st.session_state.workflow_status != "idle":
            if st.button("Reset Protocol"):
                st.session_state.messages = []
                st.session_state.workflow_status = "idle"
                st.session_state.search_results = None
                st.session_state.pending_query = None
                st.session_state.search_task = None
                st.rerun()
