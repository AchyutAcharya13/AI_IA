"""Flask backend: serves the frontend and streams the agent trace via Server-Sent Events."""
import os, json
from flask import Flask, Response, request, jsonify, send_from_directory
from . import tools
from .agent import run_agent, MODEL, LOG_DIR, friendly_error
from .baseline import rule_based_agent

ROOT = tools.BASE
app = Flask(__name__, static_folder=None)


KEY_CHECK = {"ok": None, "msg": ""}   # filled by run.py's startup check


def key_status():
    key, _ = tools.get_key()
    prob = tools.key_problem(key)
    if prob in ("missing", "placeholder"):
        return prob
    if KEY_CHECK["ok"] is False:          # only Google's own answer blocks a run, never a format guess
        return "invalid"
    return "set"


def key_message():
    key, src = tools.get_key()
    prob = tools.key_problem(key)
    if prob == "missing":
        return "No Gemini API key found. Add GEMINI_API_KEY=your_key to the .env file in the project folder, then restart the server."
    if prob == "placeholder":
        return "The .env file still has the placeholder key. Replace paste_your_key_here with your real key, then restart the server."
    msg = KEY_CHECK["msg"]
    if prob:
        msg += f" Note: {prob}"
    return msg


@app.after_request
def cors(resp):
    # lets the page work even when index.html is opened directly or served by another dev server
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
    return resp


@app.get("/")
def index():
    return send_from_directory(os.path.join(ROOT, "frontend"), "index.html")


@app.get("/exports/<path:name>")
def exports(name):
    return send_from_directory(tools.EXPORTS, name, as_attachment=True)


@app.get("/api/status")
def status():
    key, src = tools.get_key()
    return jsonify(model=MODEL, key=key_status(), key_hint=tools.mask(key) if key else "", key_source=src,
                   key_message=key_message() if key_status() != "set" else "",
                   tools=[d["name"] for d in tools.DECLARATIONS])


@app.post("/api/run")
def run():
    goal = (request.get_json(silent=True) or {}).get("goal", "").strip()
    if not goal:
        return jsonify(error="Type a goal first."), 400
    if key_status() != "set":
        return jsonify(error=key_message()), 400

    def stream():
        try:
            for ev in run_agent(goal):
                yield f"data: {json.dumps(ev)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'text': friendly_error(e)})}\n\n"
        yield "data: {\"type\": \"done\"}\n\n"

    return Response(stream(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/baseline")
def baseline():
    goal = (request.get_json(silent=True) or {}).get("goal", "")
    return jsonify(rule_based_agent(goal))


@app.get("/api/memory")
def memory():
    return jsonify(tools.get_memory())


@app.delete("/api/memory")
def clear_memory():
    if os.path.exists(tools.MEMORY_FILE):
        os.remove(tools.MEMORY_FILE)
    return jsonify(ok=True)


@app.get("/api/logs")
def logs():
    p = os.path.join(LOG_DIR, "agent_trace.log")
    return Response(open(p, encoding="utf-8").read() if os.path.exists(p) else "", mimetype="text/plain")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
