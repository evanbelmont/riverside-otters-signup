"""Database layer: everything that touches the database lives here.

Two backends, chosen once at startup:

  * DATABASE_URL not set  ->  SQLite file (the local default, no setup needed)
  * DATABASE_URL set      ->  PostgreSQL (for hosting, for example on Render)

If DATABASE_URL is set but PostgreSQL can't be used, DatabaseUnavailableError
is raised. The app never silently switches to SQLite in that case.

The connection URL contains a password, so it is never printed: error
messages pass through _redact() first.

All queries are written once with "?" placeholders and real parameters
(never pasted-in values). For PostgreSQL the "?" becomes "%s".
"""

import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
BACKEND = "postgresql" if DATABASE_URL else "sqlite"

# SIGNUP_DB lets tests point SQLite at a separate file.
SQLITE_PATH = Path(
    os.environ.get("SIGNUP_DB") or Path(__file__).resolve().parent / "signups.db"
)

SESSIONS = ("Beginner Lesson", "Advanced Practice")
CAPACITY = 5  # confirmed spots per session

_SCHEMA_LOCK_ID = 727274  # any fixed number; stops two servers creating tables at once


class DuplicateSignupError(Exception):
    """The same name is already registered for that session."""


class SessionFullError(Exception):
    """The session has no free spot (or people are already waiting for one)."""


class NotFoundError(Exception):
    """No row has that id (for example, it was already cancelled)."""


class AlreadyWaitlistedError(Exception):
    """The same name is already on that session's waitlist."""


class SessionNotFullError(Exception):
    """The session still has spots, so there is nothing to wait for."""


class DatabaseUnavailableError(Exception):
    """The configured database can't be used. The message is safe to log."""


def describe_backend():
    """Which database is in use, without revealing the connection URL."""
    if BACKEND == "postgresql":
        return "PostgreSQL (connection details from DATABASE_URL, hidden)"
    return f"SQLite file {SQLITE_PATH}"


def name_key(name):
    """'  MIA lopez ' and 'Mia Lopez' both become 'mia lopez'."""
    return name.strip().casefold()


# ---------- keeping the connection URL secret ----------

def _redact(text):
    """Remove the URL and its parts (user, password, host, options...) from text."""
    hidden = {DATABASE_URL}
    try:
        parts = urlsplit(DATABASE_URL)
        pieces = [parts.netloc, parts.username, parts.password, parts.hostname,
                  parts.path.lstrip("/"), parts.query]
        # Options such as ?host=/path/to/socket or ?sslrootcert=... are hidden too.
        pieces += [value for _, value in parse_qsl(parts.query)]
    except ValueError:
        pieces = []
    for piece in pieces:
        if piece:
            hidden.update({piece, unquote(piece)})
    for secret in sorted(hidden, key=len, reverse=True):
        if secret and len(secret) >= 4:
            text = text.replace(secret, "[hidden]")
    return re.sub(r"\b\d{1,3}(\.\d{1,3}){3}\b", "[hidden]", text)  # IP addresses


def safe_error_text(error):
    """A one-line description of an unexpected error that is safe to log."""
    return _redact(f"{type(error).__name__}: {error}".strip())


# ---------- connections ----------

class _Connection:
    """The same small interface for SQLite and PostgreSQL connections."""

    def __init__(self, raw, postgres):
        self.raw = raw
        self.postgres = postgres

    def execute(self, sql, params=()):
        if self.postgres:
            sql = sql.replace("?", "%s")
        return self.raw.execute(sql, params)

    def one(self, sql, params=()):
        return self.execute(sql, params).fetchone()

    def all(self, sql, params=()):
        return self.execute(sql, params).fetchall()

    def insert(self, sql, params):
        """Run an INSERT and return the new row's id."""
        if self.postgres:
            return self.one(sql + " RETURNING id", params)["id"]
        return self.execute(sql, params).lastrowid


def _postgres_driver():
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError:
        raise DatabaseUnavailableError(
            "DATABASE_URL is set, but the PostgreSQL driver (psycopg) is not installed. "
            "Run: pip install -r requirements.txt"
        ) from None
    return psycopg, dict_row


def _integrity_errors():
    errors = [sqlite3.IntegrityError]
    if BACKEND == "postgresql":
        psycopg, _ = _postgres_driver()
        errors.append(psycopg.IntegrityError)
    return tuple(errors)


def _open():
    if BACKEND == "sqlite":
        raw = sqlite3.connect(SQLITE_PATH, timeout=10, isolation_level=None)
        raw.row_factory = sqlite3.Row
        return _Connection(raw, postgres=False)

    psycopg, dict_row = _postgres_driver()
    try:
        raw = psycopg.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=10)
    except psycopg.Error as error:
        # "from None" keeps the original message (which may echo the URL)
        # out of tracebacks.
        raise DatabaseUnavailableError(
            "Could not connect to PostgreSQL using DATABASE_URL: "
            + _redact(str(error).strip() or type(error).__name__)
        ) from None
    return _Connection(raw, postgres=True)


@contextmanager
def _reading():
    conn = _open()
    try:
        yield conn
    finally:
        conn.raw.close()  # PostgreSQL: closing also ends the read-only transaction


@contextmanager
def _transaction(lock_tables=True):
    """One all-or-nothing change.

    Only one writer at a time may count spots and change rows, so nobody can
    slip in between "a spot opened" and "the waitlist got it":
      * SQLite:     BEGIN IMMEDIATE takes the database's write lock.
      * PostgreSQL: LOCK TABLE ... SHARE ROW EXCLUSIVE does the same for our
                    two tables (readers are not blocked).
    """
    conn = _open()
    try:
        if conn.postgres:
            # psycopg opens the transaction automatically with the first statement.
            if lock_tables:
                conn.execute("LOCK TABLE registrations, waitlist IN SHARE ROW EXCLUSIVE MODE")
        else:
            conn.execute("BEGIN IMMEDIATE")
        yield conn
        if conn.postgres:
            conn.raw.commit()
        else:
            conn.execute("COMMIT")
    except BaseException:
        if conn.postgres:
            conn.raw.rollback()
        elif conn.raw.in_transaction:
            conn.raw.execute("ROLLBACK")
        raise
    finally:
        conn.raw.close()


# ---------- creating tables ----------

_SQLITE_TABLES = [
    """
    CREATE TABLE IF NOT EXISTS registrations (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        name       TEXT NOT NULL,
        name_key   TEXT NOT NULL,
        session    TEXT NOT NULL
                   CHECK (session IN ('Beginner Lesson', 'Advanced Practice')),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        attended   INTEGER NOT NULL DEFAULT 0 CHECK (attended IN (0, 1)),
        UNIQUE (name_key, session)
    )
    """,
    # Waitlist is its own table. AUTOINCREMENT ids only ever go up,
    # so a smaller id means the person joined earlier.
    """
    CREATE TABLE IF NOT EXISTS waitlist (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        name      TEXT NOT NULL,
        name_key  TEXT NOT NULL,
        session   TEXT NOT NULL
                  CHECK (session IN ('Beginner Lesson', 'Advanced Practice')),
        joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (name_key, session)
    )
    """,
    "CREATE INDEX IF NOT EXISTS waitlist_by_session_order ON waitlist (session, id)",
]

_POSTGRES_TABLES = [
    """
    CREATE TABLE IF NOT EXISTS registrations (
        id         BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
        name       TEXT NOT NULL,
        name_key   TEXT NOT NULL,
        session    TEXT NOT NULL
                   CHECK (session IN ('Beginner Lesson', 'Advanced Practice')),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        attended   INTEGER NOT NULL DEFAULT 0 CHECK (attended IN (0, 1)),
        UNIQUE (name_key, session)
    )
    """,
    # Identity ids come from a sequence and only ever go up; writers take
    # turns (see _transaction), so a smaller id means the person joined earlier.
    """
    CREATE TABLE IF NOT EXISTS waitlist (
        id        BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
        name      TEXT NOT NULL,
        name_key  TEXT NOT NULL,
        session   TEXT NOT NULL
                  CHECK (session IN ('Beginner Lesson', 'Advanced Practice')),
        joined_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE (name_key, session)
    )
    """,
    "CREATE INDEX IF NOT EXISTS waitlist_by_session_order ON waitlist (session, id)",
]


def init_db():
    """Create any missing tables. Safe to run on every start.

    It only ADDS what is missing; existing tables and rows are left alone.
    """
    with _transaction(lock_tables=False) as conn:
        if conn.postgres:
            # Two servers starting together won't both try to create tables.
            conn.execute(f"SELECT pg_advisory_xact_lock({_SCHEMA_LOCK_ID})")
            for statement in _POSTGRES_TABLES:
                conn.execute(statement)
        else:
            for statement in _SQLITE_TABLES:
                conn.execute(statement)
            # Upgrade older local databases made before attendance existed.
            columns = {row["name"] for row in conn.all("PRAGMA table_info(registrations)")}
            if "attended" not in columns:
                conn.execute(
                    "ALTER TABLE registrations ADD COLUMN"
                    " attended INTEGER NOT NULL DEFAULT 0 CHECK (attended IN (0, 1))"
                )


# ---------- helpers used inside a transaction ----------

def _row_to_dict(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "session": row["session"],
        "attended": bool(row["attended"]),
    }


def _get(conn, registration_id):
    row = conn.one(
        "SELECT id, name, name_key, session, attended FROM registrations WHERE id = ?",
        (registration_id,),
    )
    if row is None:
        raise NotFoundError()
    return row


def _count(conn, session):
    return conn.one(
        "SELECT COUNT(*) AS n FROM registrations WHERE session = ?", (session,)
    )["n"]


def _waiting(conn, session):
    return conn.one("SELECT COUNT(*) AS n FROM waitlist WHERE session = ?", (session,))["n"]


def _is_duplicate(conn, key, session, exclude_id=None):
    sql = "SELECT 1 AS found FROM registrations WHERE name_key = ? AND session = ?"
    params = [key, session]
    if exclude_id is not None:
        sql += " AND id <> ?"
        params.append(exclude_id)
    return conn.one(sql, tuple(params)) is not None


def _is_waitlisted(conn, key, session):
    return conn.one(
        "SELECT 1 AS found FROM waitlist WHERE name_key = ? AND session = ?", (key, session)
    ) is not None


def _position(conn, entry_id, session):
    return conn.one(
        "SELECT COUNT(*) AS n FROM waitlist WHERE session = ? AND id <= ?", (session, entry_id)
    )["n"]


def _promote(conn, session):
    """Fill open spots in `session` from its waitlist, earliest first.

    Runs inside the same transaction as the cancel/move that opened the spot.
    Returns the people who were promoted.
    """
    promoted = []
    while _count(conn, session) < CAPACITY:
        first = conn.one(
            "SELECT id, name, name_key FROM waitlist WHERE session = ? ORDER BY id LIMIT 1",
            (session,),
        )
        if first is None:
            break
        conn.execute("DELETE FROM waitlist WHERE id = ?", (first["id"],))
        if _is_duplicate(conn, first["name_key"], session):
            continue  # already registered somehow: drop the stale entry, ask the next person
        new_id = conn.insert(
            "INSERT INTO registrations (name, name_key, session, attended) VALUES (?, ?, ?, 0)",
            (first["name"], first["name_key"], session),
        )
        promoted.append({"id": new_id, "name": first["name"], "session": session})
    return promoted


# ---------- registrations ----------

def add_registration(name, session):
    """Save one signup as a new row. Blocks duplicates and full sessions."""
    name = name.strip()
    key = name_key(name)
    with _transaction() as conn:
        if _is_duplicate(conn, key, session):
            raise DuplicateSignupError()
        # ">=" keeps sessions that are already over 5 as they are, but lets
        # nobody else in. If anyone is waiting, they get the next spot first.
        if _count(conn, session) >= CAPACITY or _waiting(conn, session) > 0:
            raise SessionFullError()
        try:
            new_id = conn.insert(
                "INSERT INTO registrations (name, name_key, session) VALUES (?, ?, ?)",
                (name, key, session),
            )
        except _integrity_errors() as error:  # backup for the UNIQUE rule
            raise DuplicateSignupError() from error
        return _row_to_dict(_get(conn, new_id))


def change_session(registration_id, new_session):
    """Move an existing row to another session (UPDATE, not a new row).

    The spot it leaves behind goes to that session's waitlist in the same
    transaction. Returns (old_session, updated_registration, promoted).
    """
    with _transaction() as conn:
        row = _get(conn, registration_id)
        old_session = row["session"]
        if old_session == new_session:
            return old_session, _row_to_dict(row), []
        if _is_duplicate(conn, row["name_key"], new_session, exclude_id=registration_id):
            raise DuplicateSignupError()
        if _count(conn, new_session) >= CAPACITY or _waiting(conn, new_session) > 0:
            raise SessionFullError()
        try:
            conn.execute(
                "UPDATE registrations SET session = ? WHERE id = ?",
                (new_session, registration_id),
            )
        except _integrity_errors() as error:
            raise DuplicateSignupError() from error
        # Someone moving into a session no longer needs to wait for it.
        conn.execute(
            "DELETE FROM waitlist WHERE name_key = ? AND session = ?",
            (row["name_key"], new_session),
        )
        promoted = _promote(conn, old_session)
        return old_session, _row_to_dict(_get(conn, registration_id)), promoted


def set_attended(registration_id, attended):
    with _transaction() as conn:
        _get(conn, registration_id)  # raises NotFoundError if missing
        conn.execute(
            "UPDATE registrations SET attended = ? WHERE id = ?",
            (1 if attended else 0, registration_id),
        )
        return _row_to_dict(_get(conn, registration_id))


def delete_registration(registration_id):
    """Cancel a signup and promote from the waitlist in the same transaction.

    Returns (deleted_registration, promoted).
    """
    with _transaction() as conn:
        row = _get(conn, registration_id)
        conn.execute("DELETE FROM registrations WHERE id = ?", (registration_id,))
        promoted = _promote(conn, row["session"])
        return _row_to_dict(row), promoted


def _like_pattern(text):
    """'50%_off' -> '%50\\%\\_off%' so % and _ are matched literally."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def list_registrations(search=""):
    """Return saved signups sorted by name A-Z.

    A search term keeps only names that contain it (ignoring capitalization).
    """
    search = name_key(search)
    with _reading() as conn:
        # COLLATE "C" makes PostgreSQL sort exactly like SQLite (plain A-Z).
        order = ' ORDER BY name_key COLLATE "C", session, id' if conn.postgres \
            else " ORDER BY name_key, session, id"
        sql = "SELECT id, name, session, attended FROM registrations"
        params = ()
        if search:
            sql += " WHERE name_key LIKE ? ESCAPE '\\'"
            params = (_like_pattern(search),)
        rows = conn.all(sql + order, params)
    return [_row_to_dict(row) for row in rows]


# ---------- waitlist ----------

def join_waitlist(name, session):
    """Add someone to the end of a full session's waitlist.

    Returns the new entry including its position (1 = next in line).
    """
    name = name.strip()
    key = name_key(name)
    with _transaction() as conn:
        if _is_duplicate(conn, key, session):
            raise DuplicateSignupError()
        if _is_waitlisted(conn, key, session):
            raise AlreadyWaitlistedError()
        if _count(conn, session) < CAPACITY and _waiting(conn, session) == 0:
            raise SessionNotFullError()
        try:
            entry_id = conn.insert(
                "INSERT INTO waitlist (name, name_key, session) VALUES (?, ?, ?)",
                (name, key, session),
            )
        except _integrity_errors() as error:
            raise AlreadyWaitlistedError() from error
        return {
            "id": entry_id,
            "name": name,
            "session": session,
            "position": _position(conn, entry_id, session),
        }


def leave_waitlist(entry_id):
    """Remove one waitlist entry. Everyone behind them moves up one place."""
    with _transaction() as conn:
        row = conn.one("SELECT id, name, session FROM waitlist WHERE id = ?", (entry_id,))
        if row is None:
            raise NotFoundError()
        conn.execute("DELETE FROM waitlist WHERE id = ?", (entry_id,))
        return {"id": row["id"], "name": row["name"], "session": row["session"]}


def list_waitlist():
    """Everyone waiting, in joining order, with their place in their session."""
    with _reading() as conn:
        rows = conn.all(
            """
            SELECT id, name, session,
                   ROW_NUMBER() OVER (PARTITION BY session ORDER BY id) AS position
            FROM waitlist
            ORDER BY session, id
            """
        )
    return [
        {"id": r["id"], "name": r["name"], "session": r["session"], "position": r["position"]}
        for r in rows
    ]


def session_summary():
    """Registered count, spots left, full/not full, and waiting per session."""
    with _reading() as conn:
        data = {s: (_count(conn, s), _waiting(conn, s)) for s in SESSIONS}
    sessions = [
        {
            "session": session,
            "registered": registered,
            "remaining": max(0, CAPACITY - registered),
            "full": registered >= CAPACITY,
            "waiting": waiting,
        }
        for session, (registered, waiting) in data.items()
    ]
    total = sum(registered for registered, _ in data.values())
    return {"capacity": CAPACITY, "total": total, "sessions": sessions}
