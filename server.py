"""Local server: serves the page in public/ and a small JSON API.

Run:  python3 server.py   then open http://localhost:8000

API
  GET    /api/registrations?search=...   registrations, waitlist, spots per session
  POST   /api/registrations              {"name", "session"}   new signup
  PATCH  /api/registrations/<id>         {"session"} or {"attended"}
  DELETE /api/registrations/<id>         cancel a signup
  POST   /api/waitlist                   {"name", "session"}   join a full session's waitlist
  DELETE /api/waitlist/<id>              leave the waitlist
"""

import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import db

HOST = "127.0.0.1"
PORT = int(os.environ.get("SIGNUP_PORT", "8000"))  # tests use another port
PUBLIC_DIR = Path(__file__).resolve().parent / "public"

# Only these files are served, so the database and Python files stay private.
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
}

REGISTRATIONS_PATH = "/api/registrations"
WAITLIST_PATH = "/api/waitlist"
ITEM_PATH = re.compile(r"^/api/(registrations|waitlist)/(\d+)$")

NAME_ERROR = "Please enter an attendee name."
SESSION_ERROR = "Please choose a session."
INVALID_REQUEST = "Invalid request."
NOT_FOUND = "That registration no longer exists. The list has been refreshed."
WAITLIST_NOT_FOUND = "That waitlist entry no longer exists. The list has been refreshed."
MAX_NAME_LENGTH = 100
MAX_BODY_BYTES = 10_000


def signup_full_message(session):
    return f"{session} is full ({db.CAPACITY} spots). You can press Join Waitlist instead."


def move_full_message(session):
    return f"{session} is full ({db.CAPACITY} spots). Please choose another session."


def duplicate_message(name, session):
    return f"{name} is already signed up for {session}."


def promotion_messages(promoted):
    return [
        f"{p['name']} was automatically promoted from the waitlist "
        f"and is now registered for {p['session']}."
        for p in promoted
    ]


class Handler(BaseHTTPRequestHandler):
    # ----- list + static files -----

    def do_GET(self):
        url = urlsplit(self.path)
        if url.path == REGISTRATIONS_PATH:
            search = parse_qs(url.query).get("search", [""])[0]
            self.send_json(
                200,
                {
                    "registrations": db.list_registrations(search),
                    "waitlist": db.list_waitlist(),
                    "counts": db.session_summary(),
                },
            )
        elif url.path in STATIC_FILES:
            filename, content_type = STATIC_FILES[url.path]
            self.send_body(200, (PUBLIC_DIR / filename).read_bytes(), content_type)
        else:
            self.send_error_json(404, "Not found.")

    # ----- new signup / join waitlist -----

    def do_POST(self):
        path = urlsplit(self.path).path
        if path not in (REGISTRATIONS_PATH, WAITLIST_PATH):
            self.send_error_json(404, "Not found.")
            return
        data = self.read_json()
        if data is None:
            self.send_error_json(400, INVALID_REQUEST)
            return

        name, session, errors = self.check_name_and_session(data)
        if errors:
            self.send_json(400, {"errors": errors})
            return

        if path == REGISTRATIONS_PATH:
            self.create_registration(name, session)
        else:
            self.create_waitlist_entry(name, session)

    def create_registration(self, name, session):
        try:
            record = db.add_registration(name, session)
        except db.DuplicateSignupError:
            self.send_error_json(409, duplicate_message(name, session))
            return
        except db.SessionFullError:
            self.send_json(409, {"errors": [signup_full_message(session)], "full": True})
            return
        self.send_json(201, {"registration": record})

    def create_waitlist_entry(self, name, session):
        try:
            entry = db.join_waitlist(name, session)
        except db.DuplicateSignupError:
            self.send_error_json(409, f"{name} is already registered for {session}.")
            return
        except db.AlreadyWaitlistedError:
            self.send_error_json(409, f"{name} is already on the waitlist for {session}.")
            return
        except db.SessionNotFullError:
            self.send_error_json(
                409, f"{session} still has open spots. Please press Sign Up instead."
            )
            return
        message = f"{entry['name']} is #{entry['position']} on the waitlist for {session}."
        self.send_json(201, {"entry": entry, "message": message})

    # ----- change session / mark attendance -----

    def do_PATCH(self):
        kind, item_id = self.item()
        if kind != "registrations":
            self.send_error_json(404, "Not found.")
            return
        data = self.read_json()
        if data is None or len(data) != 1:
            self.send_error_json(400, INVALID_REQUEST)
            return

        promoted = []
        try:
            if "session" in data:
                new_session = data["session"]
                if new_session not in db.SESSIONS:
                    self.send_error_json(400, SESSION_ERROR)
                    return
                old_session, record, promoted = db.change_session(item_id, new_session)
                if old_session == new_session:
                    message = f"{record['name']} is already in {new_session}."
                else:
                    message = f"{record['name']} moved from {old_session} to {new_session}."
            elif "attended" in data and isinstance(data["attended"], bool):
                record = db.set_attended(item_id, data["attended"])
                status = "attended" if record["attended"] else "not attended"
                message = f"{record['name']} ({record['session']}) marked as {status}."
            else:
                self.send_error_json(400, INVALID_REQUEST)
                return
        except db.NotFoundError:
            self.send_error_json(404, NOT_FOUND)
            return
        except db.DuplicateSignupError:
            self.send_error_json(409, self.duplicate_for(item_id, data["session"]))
            return
        except db.SessionFullError:
            self.send_error_json(409, move_full_message(data["session"]))
            return
        self.send_json(
            200,
            {
                "registration": record,
                "message": message,
                "promoted": promoted,
                "promotions": promotion_messages(promoted),
            },
        )

    # ----- cancel signup / leave waitlist -----

    def do_DELETE(self):
        kind, item_id = self.item()
        if kind == "registrations":
            try:
                record, promoted = db.delete_registration(item_id)
            except db.NotFoundError:
                self.send_error_json(404, NOT_FOUND)
                return
            self.send_json(
                200,
                {
                    "registration": record,
                    "message": f"Cancelled {record['name']}'s signup for {record['session']}.",
                    "promoted": promoted,
                    "promotions": promotion_messages(promoted),
                },
            )
        elif kind == "waitlist":
            try:
                entry = db.leave_waitlist(item_id)
            except db.NotFoundError:
                self.send_error_json(404, WAITLIST_NOT_FOUND)
                return
            self.send_json(
                200,
                {
                    "entry": entry,
                    "message": f"{entry['name']} left the waitlist for {entry['session']}.",
                },
            )
        else:
            self.send_error_json(404, "Not found.")

    # ----- helpers -----

    def check_name_and_session(self, data):
        """Check the input again on the server; never trust the browser alone."""
        name = data.get("name")
        name = name.strip() if isinstance(name, str) else ""
        session = data.get("session")
        errors = []
        if not name:
            errors.append(NAME_ERROR)
        elif len(name) > MAX_NAME_LENGTH:
            errors.append(f"Please use {MAX_NAME_LENGTH} characters or fewer for the name.")
        if session not in db.SESSIONS:
            errors.append(SESSION_ERROR)
        return name, session, errors

    def item(self):
        match = ITEM_PATH.match(urlsplit(self.path).path)
        if not match:
            return None, None
        return match.group(1), int(match.group(2))

    def duplicate_for(self, registration_id, session):
        """Duplicate message for a session change, using the saved name."""
        for reg in db.list_registrations():
            if reg["id"] == registration_id:
                return duplicate_message(reg["name"], session)
        return NOT_FOUND

    def read_json(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return None
        if length <= 0 or length > MAX_BODY_BYTES:
            return None
        try:
            data = json.loads(self.rfile.read(length))
        except (ValueError, UnicodeDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def send_error_json(self, status, message):
        self.send_json(status, {"errors": [message]})

    def send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_body(status, body, "application/json; charset=utf-8")

    def send_body(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def main():
    db.init_db()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Club Event Signup running at http://localhost:{PORT}  (Ctrl+C to stop)", flush=True)
    print(f"Database: {db.DB_PATH}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
