# Riverside Otters Swim Club — Club Event Signup

A small signup website for a **fictional** swimming club. Visitors sign up a
made-up attendee for one of two sessions, and everything is saved in a local
SQLite database. It runs entirely on your own computer using only Python 3,
with nothing to install.

> Use fictional names only. This is a class project, not a real registration system.

## Features

**Signup**
- Sign up a fictional attendee for **Beginner Lesson** or **Advanced Practice**
- Blank or spaces-only names and missing sessions are rejected with clear messages
- A confirmation names the attendee and session, for example
  "Success! Mia Lopez is signed up for Beginner Lesson."
- The same name can't sign up twice for the same session (capitalization and
  surrounding spaces are ignored)

**Saved registrations**
- Saved in SQLite, so they're still there after closing and reopening the page
- Names are listed A–Z
- Counts and remaining spots for each session
- Search by attendee name, with **Clear** to show the full list again
- **Attended** checkbox for each person (saved in the database)
- **Change Session** moves someone to the other session (updates the same record)
- **Cancel** removes a signup, after a confirmation prompt

**Capacity and waitlist**
- Each session holds **5** confirmed registrations, and the server enforces this
- When a session is full, **Join Waitlist** adds the person to that session's waitlist
  ("Mia Lopez is #2 on the waitlist for Beginner Lesson.")
- When a cancellation or session change opens a spot, the earliest person waiting is
  **promoted automatically**, and a message names them
- Promotions happen in the same database transaction as the change that opened the
  spot, so nobody can take the spot ahead of the waitlist
- People can leave the waitlist (with a confirmation prompt)

**Design**
- Navy and aqua theme on a gentle pool-water background
  (the ripple animation stops if your device asks for reduced motion)
- Works on desktop and phone, with readable labels and keyboard-accessible controls

## Run it locally

You need **Python 3** (version 3.9 or newer). Nothing else to install.

```bash
cd riverside-otters-signup
python3 server.py
```

Then open **http://localhost:8000** in your browser. Press `Ctrl+C` in the
terminal to stop the server.

The database file `signups.db` is created automatically the first time the
server starts. It is **not** included in this repository (see `.gitignore`),
so each copy of the project starts with an empty list.

## Project files

| Part | File(s) | What it does |
|---|---|---|
| Browser | `public/index.html`, `public/style.css`, `public/app.js` | The page: form, lists, waitlist, and messages. Talks to the server with `fetch`. No localStorage. |
| Server | `server.py` | Serves the page and a small JSON API. Re-checks every input before saving. |
| Database | `db.py` | All SQLite code: creates tables, and handles saving, duplicate and capacity rules, waitlist promotions, search, and counts. |
| Design | `design.md 1.md` | The original Meeting 1 design document (plain-English spec). |

### API (used by the page)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/registrations?search=` | Registrations, waitlist, and spots per session |
| `POST` | `/api/registrations` | New signup `{name, session}` |
| `PATCH` | `/api/registrations/<id>` | Change session `{session}` or attendance `{attended}` |
| `DELETE` | `/api/registrations/<id>` | Cancel a signup (promotes from the waitlist) |
| `POST` | `/api/waitlist` | Join a full session's waitlist `{name, session}` |
| `DELETE` | `/api/waitlist/<id>` | Leave the waitlist |

## Notes

- The server only listens on `127.0.0.1` (your own computer).
- Only the three files in `public/` are served to the browser; the database and
  Python files are never sent.
- To start over with an empty list, stop the server and delete `signups.db`.
