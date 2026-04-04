import streamlit as st
import time

# --- Setup Page Config ---
st.set_page_config(page_title="Sustainable Products", layout="wide")

# --- Load Custom CSS ---
def load_css():
    try:
        with open("style.css", "r") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except Exception as e:
        st.warning("Could not load style.css")

def run():
    load_css()
    # --- Page Header ---
    st.title("Sustainable Products Finder")
    st.markdown("<div class='subtitle'>ASI:One Intelligent Orchestrator</div>", unsafe_allow_html=True)

    # --- State Management ---
    if "messages" not in st.session_state:
        st.session_state.messages = []
        
    if "workflow_status" not in st.session_state:
        st.session_state.workflow_status = "idle" # States: idle, searching, found
        
    if "show_typing" not in st.session_state:
        st.session_state.show_typing = False

    # --- Layout: Main Columns ---
    col_chat, col_dash = st.columns([1, 1], gap="large")

    # --- LEFT COLUMN: Chat Interface (ASI:One) ---
    with col_chat:
        st.markdown("### ASI:One Chat")
        
        # Render messages
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                
        # Input Area
        prompt = st.chat_input("E.g., I need a 4k monitor. Budget is $200. Used preferred.")
        if prompt:
            st.session_state.messages.append({"role": "user", "content": prompt})
            st.session_state.workflow_status = "searching"
            st.session_state.show_typing = True
            st.rerun()

    # --- RIGHT COLUMN: Orchestrator Dashboard ---
    with col_dash:
        st.markdown("### Orchestrator Dashboard")
        
        if st.session_state.workflow_status == "idle":
            st.info("Awaiting Intent. Ask me to find something sustainable!")
            
        elif st.session_state.workflow_status == "searching":
            with st.status("Executing Browser Use Protocol...", expanded=True) as status:
                time.sleep(0.5)
                st.write("**Parsing Intent:** Product - 4K Monitor, Max Price - $200, Sustainability - High Priority")
                time.sleep(1.2)
                st.write("**Initializing Browser Use:** Launching headless browser session...")
                time.sleep(1.5)
                st.write("**Navigating & Scraping:** Searching Craigslist, Facebook Marketplace, and querying local directories for Small Business IT shops...")
                time.sleep(2.0)
                st.write("**Evaluating Items:** Ranking scraped results by Carbon Saved, Local Economic Impact, and Price.")
                time.sleep(1.0)
                status.update(label="Items Located. Finalizing Discovery Phase...", state="complete", expanded=False)
            
            # Move to found state
            st.session_state.workflow_status = "found"
            st.rerun()
            
        elif st.session_state.workflow_status == "found":
            # Render the result cards
            st.markdown('''
                <div class="glass" style="margin-bottom: 20px;">
                    <div class="carbon-badge" style="background: linear-gradient(135deg, #1f6feb 0%, #388bfd 100%);">🏢 Local SMB Supported</div>
                    <div class="product-title">Dell UltraSharp 27" 4K (Open Box)</div>
                    <div class="product-detail">Location: "Bob's Main Street Electronics" (2.5 miles away)</div>
                    <div class="product-detail">Source: Local Business Directory (Found via Browser Use)</div>
                    <div class="price">$205</div>
                    <button class="pay-button" style="background-color: #1f6feb; box-shadow: 0 4px 15px rgba(31, 111, 235, 0.3);">Call Store & Reserve</button>
                </div>

                <div class="glass" style="margin-bottom: 20px;">
                    <div class="carbon-badge">Carbon Saved: 85kg CO2</div>
                    <div class="product-title">Dell UltraSharp 27" 4K (Used / Refurbished)</div>
                    <div class="product-detail">Location: 5 miles away (Low shipping carbon footprint)</div>
                    <div class="product-detail">Source: Craigslist (Found via Browser Use)</div>
                    <div class="price">$195</div>
                    <button class="pay-button">Navigate to Listing & Autobuy</button>
                </div>
                
                <div class="glass">
                    <div class="repair-banner">Repair-First Suggestion</div>
                    <div class="product-title">Got a broken monitor?</div>
                    <div class="product-detail">Before buying a replacement, check if you can fix your current setup. Extend lifespan, save 100% Carbon.</div>
                    <div style="margin-top: 15px;">
                        <a href="#" style="color: #58a6ff; font-weight: 500;">View iFixit Repair Guides for Displays ➔</a>
                    </div>
                </div>
            ''', unsafe_allow_html=True)
            
            # Add assistant response simulating finding it (if we haven't already appended it)
            if st.session_state.show_typing:
                st.session_state.show_typing = False
                found_msg = "I found two great options for you! \n\n1. **Bob's Main Street Electronics** has an open-box model slightly over your budget at **$205**, but buying here supports a local small business.\n2. A used listing on Craigslist for **$195** that saves **85kg of CO2**.\n\nI can either automatically reserve the SMB option for you, or navigate to the Craigslist listing to autobuy. 🌱"
                st.session_state.messages.append({"role": "assistant", "content": found_msg})
                st.rerun()

        # Reset button for demo purposes
        if st.session_state.workflow_status != "idle":
            if st.button("Reset Protocol"):
                st.session_state.messages = []
                st.session_state.workflow_status = "idle"
                st.session_state.show_typing = False
                st.rerun()
