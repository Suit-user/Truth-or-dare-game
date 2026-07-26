"""Flask web app for Truth or Dare.

Designed for ONE shared screen/device passed around the group -- the
server holds a single shared game in memory rather than separate games
per visitor/session.

Run locally:
    pip install -r requirements.txt
    python app.py
    -> open http://localhost:5000

Deploy to Render: see README.md.
"""

import os
from pathlib import Path
from typing import Optional

from flask import Flask, jsonify, render_template, request, send_file, Response
import io
import json

from game_logic import Game, PromptManager, CATEGORY_ORDER

BASE_DIR = Path(__file__).resolve().parent

# Bundled prompt files -- edit these before deploying.
PROMPT_FILES = {
    "Normal Truth": str(BASE_DIR / "prompts" / "normal_truth.txt"),
    "Spicy Truth": str(BASE_DIR / "prompts" / "spicy_truth.txt"),
    "Normal Dare": str(BASE_DIR / "prompts" / "normal_dare.txt"),
    "Spicy Dare": str(BASE_DIR / "prompts" / "spicy_dare.txt"),
}

app = Flask(__name__)

# ---------------------------------------------------------------------
# Single shared game state
# ---------------------------------------------------------------------
# LOAD_ERROR is set once at startup if a prompt file is missing/invalid,
# so every request can report the same clear message instead of crashing.
LOAD_ERROR: Optional[str] = None
game: Optional[Game] = None


def _fresh_game() -> Game:
    """Build a brand new Game with prompt pools reloaded straight from disk."""
    return Game(PromptManager(PROMPT_FILES))


def _init_game() -> None:
    """Attempt to load prompts and create the initial shared Game."""
    global game, LOAD_ERROR
    try:
        game = _fresh_game()
    except (FileNotFoundError, UnicodeDecodeError) as exc:
        LOAD_ERROR = str(exc)
        game = None


_init_game()


def _state_response(extra_error: Optional[str] = None):
    """Build the standard JSON response: current state plus an optional error message."""
    if LOAD_ERROR:
        return jsonify(error=LOAD_ERROR, screen="load_error"), 500
    payload = game.state_for_client()
    payload["error"] = extra_error
    return jsonify(payload)


# ---------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------
@app.route("/")
def index():
    if LOAD_ERROR:
        return render_template("error.html", error=LOAD_ERROR), 500
    return render_template("index.html")


# ---------------------------------------------------------------------
# API: state
# ---------------------------------------------------------------------
@app.route("/api/state", methods=["GET"])
def api_state():
    return _state_response()


# ---------------------------------------------------------------------
# API: setup (players)
# ---------------------------------------------------------------------
@app.route("/api/players", methods=["POST"])
def api_add_player():
    if LOAD_ERROR:
        return _state_response()
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", ""))
    try:
        game.add_player(name)
    except ValueError as exc:
        return _state_response(extra_error=str(exc))
    return _state_response()


@app.route("/api/players/<int:index>", methods=["DELETE"])
def api_remove_player(index: int):
    if LOAD_ERROR:
        return _state_response()
    game.remove_player(index)
    return _state_response()


@app.route("/api/shuffle", methods=["POST"])
def api_shuffle():
    if LOAD_ERROR:
        return _state_response()
    game.shuffle_players()
    return _state_response()


@app.route("/api/start", methods=["POST"])
def api_start():
    if LOAD_ERROR:
        return _state_response()
    try:
        game.start_game()
    except ValueError as exc:
        return _state_response(extra_error=str(exc))
    return _state_response()


# ---------------------------------------------------------------------
# API: turn actions
# ---------------------------------------------------------------------
@app.route("/api/category", methods=["POST"])
def api_choose_category():
    if LOAD_ERROR:
        return _state_response()
    data = request.get_json(silent=True) or {}
    category = data.get("category")
    if category not in CATEGORY_ORDER:
        return _state_response(extra_error="Unknown category.")
    prompt = game.choose_category(category)
    if prompt is None:
        return _state_response(extra_error=f"No prompts remain in {category}.")
    return _state_response()


@app.route("/api/complete", methods=["POST"])
def api_complete():
    if LOAD_ERROR:
        return _state_response()
    game.complete_current()
    return _state_response()


@app.route("/api/skip", methods=["POST"])
def api_skip():
    if LOAD_ERROR:
        return _state_response()
    ok = game.skip_current()
    if not ok:
        return _state_response(extra_error="No skips remaining for this player.")
    return _state_response()


@app.route("/api/double_skip", methods=["POST"])
def api_double_skip():
    if LOAD_ERROR:
        return _state_response()
    game.double_skip_current()
    return _state_response()


# ---------------------------------------------------------------------
# API: reset / save / load
# ---------------------------------------------------------------------
@app.route("/api/reset", methods=["POST"])
def api_reset():
    global game, LOAD_ERROR
    try:
        game = _fresh_game()
        LOAD_ERROR = None
    except (FileNotFoundError, UnicodeDecodeError) as exc:
        LOAD_ERROR = str(exc)
        game = None
    return _state_response()


@app.route("/api/save", methods=["GET"])
def api_save():
    if LOAD_ERROR:
        return _state_response()
    data = json.dumps(game.to_dict(), indent=2).encode("utf-8")
    return send_file(
        io.BytesIO(data),
        mimetype="application/json",
        as_attachment=True,
        download_name="tod_save.json",
    )


@app.route("/api/load", methods=["POST"])
def api_load():
    global game, LOAD_ERROR
    uploaded = request.files.get("file")
    if uploaded is None:
        return _state_response(extra_error="No file uploaded.")
    try:
        data = json.loads(uploaded.read().decode("utf-8"))
        game = Game.from_dict(data)
        LOAD_ERROR = None
    except (json.JSONDecodeError, KeyError, UnicodeDecodeError) as exc:
        return _state_response(extra_error=f"Could not load save file: {exc}")
    return _state_response()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
