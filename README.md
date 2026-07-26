# Truth or Dare (Web Version)

A Flask web app version of the desktop game, built for **one shared
screen or device passed around the group** -- the server keeps a single
shared game in memory rather than separate games per visitor.

## Project layout

| File / folder       | Purpose                                                        |
|----------------------|------------------------------------------------------------------|
| `game_logic.py`      | `Player`, `PromptManager`, `Game` -- all game rules, no web code. |
| `app.py`             | Flask routes / JSON API + the single shared `Game` instance.     |
| `templates/index.html` | Page shell the front end renders into.                        |
| `templates/error.html` | Shown if a prompt file is missing/invalid at startup.          |
| `static/style.css`   | Dark-mode-first styling, mobile responsive.                      |
| `static/script.js`   | Fetches state, renders screens, wires up all buttons/shortcuts.  |
| `prompts/*.txt`      | Your four prompt lists -- **edit these before deploying**.       |
| `requirements.txt`   | `Flask` + `gunicorn`.                                             |
| `Procfile`           | Tells Render/Heroku-style hosts how to start the app.             |
| `render.yaml`        | Optional one-click Render Blueprint config.                       |

## Run it locally

```bash
pip install -r requirements.txt
python app.py
```

Then open `http://localhost:5000`.

## Edit your prompts

Put one prompt per line, UTF-8 encoded, in:

```
prompts/normal_truth.txt
prompts/spicy_truth.txt
prompts/normal_dare.txt
prompts/spicy_dare.txt
```

Sample prompts are included so you can test immediately -- replace them
with your own before deploying for real. If a file is missing or empty
when the app starts, you'll get a clear on-screen error telling you
which one.

## Deploy to Render

1. Push this project to a GitHub repo (make sure `prompts/*.txt` are
   committed with your real content).
2. In the Render dashboard: **New + > Web Service**, connect the repo.
   - Render will auto-detect the `Procfile`. If asked manually, set:
     - **Build Command:** `pip install -r requirements.txt`
     - **Start Command:** `gunicorn app:app`
3. Deploy. Render gives you a public URL -- open it on the shared
   device and you're playing.

Alternatively, use **New + > Blueprint** and point it at this repo;
Render will read `render.yaml` and set everything up automatically.

### A note on Render's free tier

Free web services on Render spin down after a period of inactivity and
take a few seconds to wake back up on the next request. That's fine
for a party game (the group is actively using it), but expect a short
delay if the page has been idle a while.

## How the game works here

- **Setup**: add players (2+ required), remove any, shuffle order.
- **Category buttons**: current player picks Normal/Spicy Truth or Dare
  (also selectable with keys `1`-`4`).
- **Completed** (`Enter`): prompt is removed for good; turn passes to
  the next player.
- **Skip** (`S`, 3 per player for the whole game): the prompt goes back
  into its pool with extra weight (more likely to reappear later), and
  a **new prompt from that same category** is drawn immediately -- no
  category re-pick, same player, same turn.
- **Double Skip** (`D`, unlimited): the current prompt is gone for
  good, and the player is immediately given **two more prompts from
  that same category**, back to back, both of which must be resolved
  before the turn passes on.
- **Impossible checkbox**: disables Skip only, so Completed or Double
  Skip are the only ways forward for a prompt that's genuinely not
  doable.
- Empty categories disable their button automatically; once every
  category is exhausted, the Game Over screen appears.
- **Save Game** downloads a JSON snapshot of everything (players,
  stats, remaining/weighted prompt pools, whose turn it is). **Load
  Game** restores from that file.
- **Stats** and **Dark Mode** are available any time from the top bar.

## Why a single shared game instead of per-visitor sessions

Since everyone plays by passing around the same screen, the app keeps
one game in server memory rather than juggling cookies/sessions per
visitor. That keeps the code simple, but it does mean:

- Only one game is "live" on the server at a time.
- If the hosting dyno restarts (e.g., Render free tier spinning down),
  in-progress state is lost -- use **Save Game** before a long break if
  that matters to you.

If you'd ever want everyone joining from their own phone as *separate*
players in a synced multiplayer session instead, that's a different
architecture (real-time sync via WebSockets/Socket.IO) -- just ask and
it can be built that way instead.
