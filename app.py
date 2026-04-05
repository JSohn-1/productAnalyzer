import os

# When Streamlit re-runs this file as a subprocess, it sets this env var.
# In that case, just boot the UI and skip agent launching.
if os.environ.get("STREAMLIT_MODE"):
    from components.base import run
    run()
else:
    import multiprocessing
    import subprocess
    import sys
    import time

    def run_agent(module: str):
        import importlib
        mod = importlib.import_module(module)
        mod.agent.run()

    def start_agents():
        agent_modules = [
            "agent.scraper_ebay",
            "agent.scraper_facebook",
            "agent.scraper_offerup",
            "agent.agents",
        ]
        for module in agent_modules:
            p = multiprocessing.Process(target=run_agent, args=(module,), daemon=True)
            p.start()
            print(f"Started {module}")

    if __name__ == "__main__":
        multiprocessing.set_start_method("spawn", force=True)

        print("Starting all agents...")
        start_agents()

        time.sleep(3)

        print("Starting Streamlit UI...")
        result = subprocess.run(
            [sys.executable, "-m", "streamlit", "run", "app.py"],
            env={**os.environ, "STREAMLIT_MODE": "1"},
            check=False,
        )
        sys.exit(result.returncode)
