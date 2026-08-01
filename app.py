"""Telkom SA Digital Assistant — web chatbot.

Run locally:

    python -m venv .venv
    .venv\\Scripts\\activate
    pip install -r requirements.txt
    python app.py

Then open http://127.0.0.1:5000
"""

from __future__ import annotations

import os
from pathlib import Path

from flask import Flask, jsonify, render_template, request, url_for

from chatbot.flow import engine


def create_app() -> Flask:
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config["JSON_SORT_KEYS"] = False

    @app.context_processor
    def inject_static_url():
        def static_url(filename: str) -> str:
            """Cache-busted static URL: a `?v=<mtime>` query string so
            browsers pick up new CSS/JS immediately after a deploy instead
            of serving a stale copy for the full nginx `expires` window."""
            path = Path(app.static_folder) / filename
            try:
                version = int(path.stat().st_mtime)
            except OSError:
                version = 0
            return f"{url_for('static', filename=filename)}?v={version}"

        return dict(static_url=static_url)

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/healthz")
    def healthz():
        return jsonify(status="ok")

    @app.post("/api/start")
    def api_start():
        data = request.get_json(silent=True) or {}
        session_id = str(data.get("session_id") or "anonymous")
        return jsonify(messages=engine.start(session_id))

    @app.post("/api/reset")
    def api_reset():
        data = request.get_json(silent=True) or {}
        session_id = str(data.get("session_id") or "anonymous")
        return jsonify(messages=engine.reset(session_id))

    @app.post("/api/message")
    def api_message():
        data = request.get_json(silent=True) or {}
        session_id = str(data.get("session_id") or "anonymous")
        text = str(data.get("text") or "")[:1000]
        return jsonify(messages=engine.handle_text(session_id, text))

    @app.post("/api/action")
    def api_action():
        data = request.get_json(silent=True) or {}
        session_id = str(data.get("session_id") or "anonymous")
        action = str(data.get("action") or "")
        name = str(data.get("name") or "")
        value = str(data.get("value") or "")[:500]
        return jsonify(messages=engine.handle_action(session_id, action, value, name))

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=port, debug=True)
