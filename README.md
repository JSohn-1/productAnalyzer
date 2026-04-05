# Sustainable Products Finder

A web application that helps users find sustainable, used products by scraping real listings from platforms like eBay. Built with ASI:One AI orchestration, Browser Use automation, and Streamlit UI.

## Features

- **AI-Powered Search**: Uses ASI:One to generate intelligent browser automation tasks
- **Live Scraping**: Browser Use SDK executes real-time web scraping
- **Sustainability Focus**: Prioritizes used/refurbished items and calculates carbon savings
- **Multi-Platform**: Currently supports eBay, Offerup, and Facebook Marketplace
- **Concurrent Processing**: Spawns up to 3 scraping threads simultaneously for performance
- **Beautiful UI**: Glass-morphism design with responsive layout

## Prerequisites

- Python 3.8 or higher
- API Keys:
  - ASI:One API key (get from [asi1.ai](https://asi1.ai))
  - Browser Use API key (get from [browser-use.com](https://browser-use.com))

## Environment Setup

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd productAnalyzer
   ```

2. **Create and activate virtual environment**:
   ```bash
   python -m venv .venv
   # On Windows:
   .venv\Scripts\activate
   # On macOS/Linux:
   source .venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**:
   - Copy the `.env` file and update with your API keys:
   ```bash
   cp .env .env.local
   ```
   - Edit `.env.local` with your actual keys:
   ```
   ASI_API_KEY=your_asi_api_key_here
   BROWSER_USE_API_KEY=your_browser_use_key_here
   AGENT_SEED=your_agent_seed_here
   ```

## Running the Application

### Option 1: Using the run script (Recommended)

The included `run.sh` script handles starting both the agent backend and Streamlit frontend:

```bash
chmod +x run.sh  # Make executable (Linux/macOS)
./run.sh
```

### Option 2: Manual startup

1. **Start the agent backend** (in one terminal):
   ```bash
   python agent/agents.py
   ```
   The agent will start on `http://localhost:8001`

2. **Start the Streamlit frontend** (in another terminal):
   ```bash
   streamlit run app.py
   ```
   The web app will be available at `http://localhost:8501`

## Usage

1. Open the Streamlit app in your browser
2. Enter a product you're looking for (e.g., "4K monitor")
3. Optionally specify location and max price
4. Click "Find Sustainable Listings"
5. View the results with carbon savings estimates and repair suggestions

## Architecture

- **Agent (`agent/agents.py`)**: uAgents-based orchestrator using ASI:One for task generation and Browser Use for execution
- **Frontend (`app.py`, `components/base.py`)**: Streamlit web interface with real-time status updates
- **Styling (`style.css`)**: Custom CSS for glass-morphism design
- **Concurrency**: Async scraping with semaphore limiting to 3 concurrent operations

## API Endpoints

- `POST /search` - Main search endpoint (accepts `{"query": "string"}`)
- `GET /status` - Agent status and platform progress

## Development

- The agent supports both REST API and uAgents chat protocol
- Easily add new platforms by extending the `PLATFORMS` list and creating platform-specific prompts
- CSS styling can be customized in `style.css`
