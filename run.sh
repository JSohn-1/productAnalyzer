#!/bin/bash
set -e

# Start the agent backend in the background
python agent/agents.py &
AGENT_PID=$!

# Give the agent a moment to start
sleep 2

# Start Streamlit (foreground)
streamlit run app.py

# When Streamlit exits, kill the agent
kill $AGENT_PID 2>/dev/null
