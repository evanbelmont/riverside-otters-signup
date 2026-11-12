"""Database layer: everything that touches the SQLite file lives here."""

import os
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path

# SIGNUP_DB lets tests use a separate copy so real records are never touched.
DB_PATH = Path(
    os.environ.get("SIGNUP_DB") or Path(__file__).resolve().parent / "signups.db"
)
SESSIONS = ("Beginner Lesson", "Advanced Practice")
CAPACITY = 5  # confirmed spots per session


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


def name_key(name):
    """'  MIA lopez ' and 'Mia Lopez' both become 'mia lopez'."""
    return name.strip().casefold()


def connect():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def write_transaction():
    """One all-or-nothing change.

    BEGIN IMMEDIATE locks the database for writing *before* we count spots,
    so nobody can slip in between "a spot opened" and "the waitlist got it".
    """
    conn = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def init_db():
    """Create tables on first run, and upgrade older databases in place.

    Upgrading only ADDS tables/columns; existing rows are never deleted.
    """
    with write_transaction() as conn:
        conn.execute(
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
            """
        )
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(registrations)")}
        if "attended" not in columns:
            conn.execute(
                "ALTER TABLE registrations ADD COLUMN"
                " attended INTEGER NOT NULL DEFAULT 0 CHECK (attended IN (0, 1))"
            )

        # Waitlist is its own table, separate from confirmed registrations.
        # AUTOINCREMENT ids only ever go up, so a smaller id = joined earlier.
        conn.execute(
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
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS waitlist_by_session_order ON waitlist (session, id)"
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
    row = conn.execute(
        "SELECT id, name, name_key, session, attended FROM registrations WHERE id = ?",
        (registration_id,),
    ).fetchone()
    if row is None:
        raise NotFoundError()
    return row


def _count(conn, session):
    return conn.execute(
        "SELECT COUNT(*) FROM registrations WHERE session = ?", (session,)
    ).fetchone()[0]


def _waiting(conn, session):
    return conn.execute(
        "SELECT COUNT(*) FROM waitlist WHERE session = ?", (session,)
    ).fetchone()[0]


def _is_duplicate(conn, key, session, exclude_id=None):
    row = conn.execute(
        "SELECT 1 FROM registrations WHERE name_key = ? AND session = ? AND id IS NOT ?",
        (key, session, exclude_id),
    ).fetchone()
    return row is not None


def _is_waitlisted(conn, key, session):
    row = conn.execute(
        "SELECT 1 FROM waitlist WHERE name_key = ? AND session = ?", (key, session)
    ).fetchone()
    return row is not None


def _position(conn, entry_id, session):
    return conn.execute(
        "SELECT COUNT(*) FROM waitlist WHERE session = ? AND id <= ?", (session, entry_id)
    ).fetchone()[0]


def _promote(conn, session):
    """Fill open spots in `session` from its waitlist, earliest first.

    Runs inside the same transaction as the cancel/move that opened the spot.
    Returns the people who were promoted.
    """
    promoted = []
    while _count(conn, session) < CAPACITY:
        first = conn.execute(
            "SELECT id, name, name_key FROM waitlist WHERE session = ? ORDER BY id LIMIT 1",
            (session,),
        ).fetchone()
        if first is None:
            break
        conn.execute("DELETE FROM waitlist WHERE id = ?", (first["id"],))
        try:
            cursor = conn.execute(
                "INSERT INTO registrations (name, name_key, session, attended)"
                " VALUES (?, ?, ?, 0)",
                (first["name"], first["name_key"], session),
            )
        except sqlite3.IntegrityError:
            # Already registered for this session somehow: just drop the
            # stale waitlist entry and offer the spot to the next person.
            continue
        promoted.append({"id": cursor.lastrowid, "name": first["name"], "session": session})
    return promoted


# ---------- registrations ----------

def add_registration(name, session):
    """Save one signup as a new row. Blocks duplicates and full sessions."""
    name = name.strip()
    key = name_key(name)
    with write_transaction() as conn:
        if _is_duplicate(conn, key, session):
            raise DuplicateSignupError()
        # ">=" keeps sessions that are already over 5 as they are, but lets
        # nobody else in. If anyone is waiting, they get the next spot first.
        if _count(conn, session) >= CAPACITY or _waiting(conn, session) > 0:
            raise SessionFullError()
        try:
            cursor = conn.execute(
                "INSERT INTO registrations (name, name_key, session) VALUES (?, ?, ?)",
                (name, key, session),
            )
        except sqlite3.IntegrityError as error:
            raise DuplicateSignupError() from error
        return _row_to_dict(_get(conn, cursor.lastrowid))


def change_session(registration_id, new_session):
    """Move an existing row to another session (UPDATE, not a new row).

    The spot it leaves behind goes to that session's waitlist in the same
    transaction. Returns (old_session, updated_registration, promoted).
    """
    with write_transaction() as conn:
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
        except sqlite3.IntegrityError as error:
            raise DuplicateSignupError() from error
        # Someone moving into a session no longer needs to wait for it.
        conn.execute(
            "DELETE FROM waitlist WHERE name_key = ? AND session = ?",
            (row["name_key"], new_session),
        )
        promoted = _promote(conn, old_session)
        return old_session, _row_to_dict(_get(conn, registration_id)), promoted


def set_attended(registration_id, attended):
    with write_transaction() as conn:
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
    with write_transaction() as conn:
        row = _get(conn, registration_id)
        conn.execute("DELETE FROM registrations WHERE id = ?", (registration_id,))
        promoted = _promote(conn, row["session"])
        return _row_to_dict(row), promoted


def list_registrations(search=""):
    """Return saved signups sorted by name A-Z.

    A search term keeps only names that contain it (ignoring capitalization).
    """
    search = name_key(search)
    query = "SELECT id, name, session, attended FROM registrations"
    params = ()
    if search:
        query += " WHERE instr(name_key, ?) > 0"
        params = (search,)
    query += " ORDER BY name_key, session, id"

    with closing(connect()) as conn:
        rows = conn.execute(query, params).fetchall()
    return [_row_to_dict(row) for row in rows]


# ---------- waitlist ----------

def join_waitlist(name, session):
    """Add someone to the end of a full session's waitlist.

    Returns the new entry including its position (1 = next in line).
    """
    name = name.strip()
    key = name_key(name)
    with write_transaction() as conn:
        if _is_duplicate(conn, key, session):
            raise DuplicateSignupError()
        if _is_waitlisted(conn, key, session):
            raise AlreadyWaitlistedError()
        if _count(conn, session) < CAPACITY and _waiting(conn, session) == 0:
            raise SessionNotFullError()
        try:
            cursor = conn.execute(
                "INSERT INTO waitlist (name, name_key, session) VALUES (?, ?, ?)",
                (name, key, session),
            )
        except sqlite3.IntegrityError as error:
            raise AlreadyWaitlistedError() from error
        entry_id = cursor.lastrowid
        return {
            "id": entry_id,
            "name": name,
            "session": session,
            "position": _position(conn, entry_id, session),
        }


def leave_waitlist(entry_id):
    """Remove one waitlist entry. Everyone behind them moves up one place."""
    with write_transaction() as conn:
        row = conn.execute(
            "SELECT id, name, session FROM waitlist WHERE id = ?", (entry_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError()
        conn.execute("DELETE FROM waitlist WHERE id = ?", (entry_id,))
        return {"id": row["id"], "name": row["name"], "session": row["session"]}


def list_waitlist():
    """Everyone waiting, in joining order, with their place in their session."""
    with closing(connect()) as conn:
        rows = conn.execute(
            """
            SELECT id, name, session,
                   ROW_NUMBER() OVER (PARTITION BY session ORDER BY id) AS position
            FROM waitlist
            ORDER BY session, id
            """
        ).fetchall()
    return [dict(row) for row in rows]


def session_summary():
    """Registered count, spots left, full/not full, and waiting per session."""
    with closing(connect()) as conn:
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
