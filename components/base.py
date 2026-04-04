import streamlit as st
import httpx

AGENT_URL = "http://localhost:8001/search"

st.set_page_config(page_title="Sustainable Products", layout="wide")


def load_css():
    try:
        with open("style.css", "r") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except Exception:
        st.warning("Could not load style.css")


def search_products(query: str):
    try:
        response = httpx.post(AGENT_URL, json={"query": query}, timeout=30.0)
        response.raise_for_status()
        return response.json()
    except httpx.ConnectError:
        return None
    except Exception as e:
        st.error(f"Agent error: {e}")
        return None


def render_results(results):
    for item in results:
        url = item.get("url", "")
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
            st.markdown(f'''
                <div class="glass" style="margin-bottom: 20px;">
                    {badge}
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

    col_chat, col_dash = st.columns([1, 1], gap="large")

    with col_chat:
        st.markdown("### ASI:One Chat")

        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        prompt = st.chat_input("E.g., I need a 4k monitor. Budget is $200. Used preferred.")
        if prompt:
            st.session_state.messages.append({"role": "user", "content": prompt})
            st.session_state.workflow_status = "searching"
            st.session_state.pending_query = prompt
            st.rerun()

    with col_dash:
        st.markdown("### Orchestrator Dashboard")

        if st.session_state.workflow_status == "idle":
            st.info("Awaiting Intent. Ask me to find something sustainable!")

        elif st.session_state.workflow_status == "searching":
            with st.status("Querying ASI:One Agent...", expanded=True) as status:
                st.write("**Parsing Intent:** Sending request to agent...")
                data = search_products(st.session_state.pending_query)

                if data is None:
                    status.update(
                        label="Could not reach agent — is `python agent/agents.py` running?",
                        state="error",
                    )
                    st.session_state.workflow_status = "idle"
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": "Could not connect to the agent. Please start it with `python agent/agents.py` and try again.",
                    })
                else:
                    st.write("**Evaluating Results:** Ranking by carbon saved, locality, and price...")
                    status.update(label="Results ready!", state="complete", expanded=False)
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
                st.rerun()
