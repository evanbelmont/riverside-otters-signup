# Riverside Otters Swim Club — Club Event Signup

A signup website for a **fictional** swimming club. Visitors sign up a made-up
attendee for one of two sessions. One small Python server delivers both the
web page and its data API from the same address. Data is saved in a database:
a local SQLite file by default, or PostgreSQL when hosted.

> Use fictional names only. This is a class project, not a real registration system.

## Requirements

| What | Version | Where it is set |
|---|---|---|
| Python | **3.9 or newer** (tested locally with 3.9.6) | `.python-version` asks hosts such as Render for 3.12 |
| PostgreSQL driver `psycopg[binary]` | **3.2.13** | `requirements.txt` |
| A database | Nothing to set up locally: a SQLite file is created automatically. PostgreSQL is only used if `DATABASE_URL` is set. | `db.py` |

There is **no build step**: no JavaScript bundler and no compiled assets. The
files in `public/` are served as they are.

## Run it locally (from a fresh GitHub ZIP)

1. On GitHub choose **Code → Download ZIP**, then unzip it. The folder is
   usually called `riverside-otters-signup-main`.
2. Open a terminal **in that folder** and run these commands.

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python server.py
```

**Windows (PowerShell)**

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python server.py
```

3. The terminal shows:

   ```
   Club Event Signup running at http://localhost:8000  (Ctrl+C to stop)
   Database: SQLite file .../signups.db
   ```

4. Open **http://localhost:8000** in your browser.

**To stop the server:** click the terminal and press **Ctrl+C**. Type
`deactivate` to leave the virtual environment.

**Next time**, you only need these steps: `source .venv/bin/activate` (Windows:
`.venv\Scripts\Activate.ps1`), then `python server.py`.

The download does **not** include any database. On the first start, the server
creates an empty `signups.db` file next to `server.py`. Your signups stay in that
file between restarts. To start over, stop the server and delete `signups.db`.

### Where the commands come from

| Command | Comes from |
|---|---|
| `pip install -r requirements.txt` | `requirements.txt` lists the only dependency (the PostgreSQL driver). Local SQLite mode uses only Python's standard library. |
| `python server.py` | `server.py` is the program that starts the web server (see `main()` at the bottom of the file). |
| `http://localhost:8000` | `server.py` uses port 8000 unless the `PORT` environment variable says otherwise. |

## Quick test with fictional data

1. Under **Sign up**, type `Test Swimmer`, choose **Beginner Lesson**, and press **Sign Up**.
   You should see: *Success! Test Swimmer is signed up for Beginner Lesson.*
2. Under **Saved registrations**, type `swim` in **Search attendee names** and press **Search**.
   You should see 1 registration: Test Swimmer, Beginner Lesson.
3. Search for `zzz`. You should see **No registrations found**.
4. Press **Clear**. The full list comes back.
5. Stop the server (Ctrl+C), start it again with `python server.py`, and reload the page.
   Test Swimmer is still listed.

## Settings (environment variables)

All of these are optional.

| Variable | Default | What it does |
|---|---|---|
| `PORT` | `8000` | Port to listen on. Hosting platforms such as Render set it automatically. |
| `HOST` | `127.0.0.1` locally; `0.0.0.0` when `PORT` is set | Network address to listen on. `127.0.0.1` keeps the app private to your computer. |
| `DATABASE_URL` | *(not set)* | If set, the app uses **PostgreSQL** instead of SQLite. It creates any missing tables on startup. |

About `DATABASE_URL`:

- If it is set but PostgreSQL can't be reached, the server **stops with a clear
  error**. It does **not** quietly switch to SQLite.
- The app never prints the URL, sends it to the browser, or writes it to its logs.
- Never put the real URL in this README, in code, or in Git. On a host, enter it
  in the host's environment settings. Locally, any `.env` file is ignored by Git.

## Hosting notes (e.g. Render). Not deployed yet.

A host such as Render would use:

- **Build command:** `pip install -r requirements.txt`
- **Start command:** `python server.py`
- **Environment:** add `DATABASE_URL` from a PostgreSQL database. Render sets `PORT` itself.

Use PostgreSQL when hosting. Many hosts have temporary file systems, so a SQLite
file there could be erased on every restart or redeploy.

## Features

**Signup**
- Sign up a fictional attendee for **Beginner Lesson** or **Advanced Practice**
- Blank or spaces-only names and missing sessions are rejected with clear messages
- A confirmation names the attendee and session
- The same name can't sign up twice for the same session (capitalization and
  surrounding spaces are ignored)

**Saved registrations**
- Saved in the database, so they're still there after closing and reopening the page
- Names listed A–Z, counts and remaining spots for each session
- Search by attendee name, with **Clear** to show the full list again
- **Attended** checkbox for each person, saved in the database
- **Change Session** moves someone to the other session (updates the same record)
- **Cancel** removes a signup, after a confirmation prompt

**Capacity and waitlist**
- Each session holds **5** confirmed registrations, and the server enforces this
- When a session is full, **Join Waitlist** adds the person to that session's waitlist
- When a cancellation or session change opens a spot, the earliest person waiting is
  **promoted automatically** in the same database transaction, and a message names them
- People can leave the waitlist (with a confirmation prompt)

**Design**
- Navy and aqua theme on a gentle pool-water background (the ripple animation
  stops if your device asks for reduced motion)
- Works on desktop and phone, with readable labels and keyboard-accessible controls

## How one signup travels through the code

| Step | File | What happens |
|---|---|---|
| 1. Page | `public/index.html` | The signup form: name box, two session choices, Sign Up button |
| 2. Browser check | `public/app.js` | Checks the name and session, then sends `POST /api/registrations` (a relative path, so the page and API share one address) |
| 3. Server | `server.py` | `handle_post` checks the input again, then calls `db.add_registration` |
| 4. Database | `db.py` | `add_registration` locks writes, checks duplicates and capacity, and inserts the row |
| 5. Reply | `server.py` → `public/app.js` | The server returns the saved row; the page shows the confirmation and reloads the list |

## Project files

| Part | File(s) | What it does |
|---|---|---|
| Browser | `public/index.html`, `public/style.css`, `public/app.js` | The page, its styling, and its behavior. Talks to the server with `fetch` using relative paths. |
| Server | `server.py` | Serves the page and the JSON API from one address. Re-checks every input. |
| Database | `db.py` | All database code for SQLite and PostgreSQL: creates tables, enforces duplicate and capacity rules, runs waitlist promotions, search, and counts. All queries use parameters. |
| Dependencies | `requirements.txt`, `.python-version` | Driver version and the Python version requested from hosts |
| Design | `design.md 1.md` | The original Meeting 1 design document (plain-English spec) |

### API (used by the page)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/registrations?search=` | Registrations, waitlist, and spots per session |
| `POST` | `/api/registrations` | New signup `{name, session}` |
| `PATCH` | `/api/registrations/<id>` | Change session `{session}` or attendance `{attended}` |
| `DELETE` | `/api/registrations/<id>` | Cancel a signup (promotes from the waitlist) |
| `POST` | `/api/waitlist` | Join a full session's waitlist `{name, session}` |
| `DELETE` | `/api/waitlist/<id>` | Leave the waitlist |

Only the three files in `public/` are sent to browsers. The database and the
Python files are never served.
