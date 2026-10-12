# TripWise – Agentic AI Trip Planner & Budget Optimizer
IA II Activity 1: LLM agent (Google Gemini, ReAct-style) with tools, memory, observable traces, web frontend and Flask backend.

## Architecture
Browser (frontend/index.html) --POST /api/run--> Flask (backend/app.py) --> Gemini ReAct loop (backend/agent.py)
 -> tools (backend/tools.py): web_search, calculator, read_document, check_budget, save_memory, create_calendar_file
 -> events streamed back via Server-Sent Events (goal / thought / action / observation / final)

Memory: short-term = message context; long-term = data/memory.json.
Logs: logs/agent_trace.log (created on first run).
Baseline: backend/baseline.py (rule-based classical agent) for the Part C comparison.

## Setup
    pip install -r requirements.txt
    # free key: https://aistudio.google.com/apikey
    # put the key in the .env file (project root):  GEMINI_API_KEY=your_key
    python run.py
    open http://127.0.0.1:5000   (in the browser; do not double-click index.html)

Optional: set GEMINI_MODEL=gemini-2.5-flash-lite if you hit rate limits.

## Demo
1. Click the "Rs 25000" chip, then Run agent (watch the live trace).
2. Click the "Rs 15000" chip: the agent should detect OVER BUDGET and re-plan.
3. Click "Run rule-based agent" for the classical comparison.
4. "View raw log" shows logs/agent_trace.log (submit this as your interaction log).

## Troubleshooting
- "Agent server not running": start it with `python run.py` from the tripwise folder and keep that window open.
- "No Gemini key": edit `.env`, set `GEMINI_API_KEY=your_key`, restart the server.
- "Rate limit": wait a minute, or set `GEMINI_MODEL=gemini-2.5-flash-lite` in `.env`.
