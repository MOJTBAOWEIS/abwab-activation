"""SQLite storage layer for the Abwab activation tracker."""

import os
import sqlite3
from datetime import datetime

import config

# On a hosted platform point ABWAB_DB at a *persistent* volume. Most hosts give
# the app a fresh filesystem on every deploy — leaving this on the default path
# there would silently wipe the leads on the next restart.
DB_PATH = os.environ.get(
    "ABWAB_DB",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "abwab.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS shifts (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    shift_key      TEXT UNIQUE NOT NULL,      -- date|promoter_code
    date           TEXT NOT NULL,
    branch         TEXT NOT NULL,
    promoter_code  TEXT NOT NULL,
    shift          TEXT NOT NULL,             -- Morning | Evening
    start_ts       TEXT NOT NULL,
    end_ts         TEXT,
    conversations  INTEGER,
    gifts_issued   INTEGER,
    note           TEXT
);

CREATE TABLE IF NOT EXISTS leads (
    lead_id        TEXT PRIMARY KEY,
    ts             TEXT NOT NULL,
    date           TEXT NOT NULL,
    branch         TEXT NOT NULL,
    promoter_code  TEXT NOT NULL,
    shift          TEXT NOT NULL,
    grade          TEXT,
    interest       TEXT,
    customer_type  TEXT,
    outcome        TEXT NOT NULL,             -- Captured | Declined
    customer_name  TEXT,
    phone_raw      TEXT,
    phone_norm     TEXT,
    note           TEXT
);
CREATE INDEX IF NOT EXISTS idx_leads_date ON leads(date);
CREATE INDEX IF NOT EXISTS idx_leads_promoter ON leads(promoter_code);
CREATE INDEX IF NOT EXISTS idx_leads_phone ON leads(phone_norm);

CREATE TABLE IF NOT EXISTS followups (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id        TEXT NOT NULL,
    contact_ts     TEXT NOT NULL,
    sales_agent    TEXT NOT NULL,
    attempts       INTEGER NOT NULL DEFAULT 1,
    status         TEXT NOT NULL,
    purchase       INTEGER NOT NULL DEFAULT 0,
    purchase_date  TEXT,
    revenue        REAL NOT NULL DEFAULT 0,
    product        TEXT,
    notes          TEXT,
    backdated      INTEGER NOT NULL DEFAULT 0,
    logged_ts      TEXT NOT NULL,
    FOREIGN KEY (lead_id) REFERENCES leads(lead_id)
);
CREATE INDEX IF NOT EXISTS idx_fu_lead ON followups(lead_id);

CREATE TABLE IF NOT EXISTS costs (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    date      TEXT NOT NULL,
    branch    TEXT NOT NULL,
    cost_type TEXT NOT NULL,
    amount    REAL NOT NULL,
    note      TEXT
);

/* ---- editable setup: owned by the manager, not by the code ---- */

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS branches (
    code   TEXT PRIMARY KEY,
    name   TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    sort   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS promoters (
    code   TEXT PRIMARY KEY,
    name   TEXT NOT NULL,
    branch TEXT,
    pin    TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS agents (
    code   TEXT PRIMARY KEY,
    name   TEXT NOT NULL,
    pin    TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS shift_types (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time   TEXT NOT NULL,
    sort       INTEGER NOT NULL DEFAULT 0
);

/* Who is *supposed* to be on the floor, and when. The promoter is never
   blocked by this — it exists so the manager can compare the plan against
   what actually happened. */
CREATE TABLE IF NOT EXISTS roster (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    date          TEXT NOT NULL,
    promoter_code TEXT NOT NULL,
    branch        TEXT NOT NULL,
    shift_type    TEXT NOT NULL,
    note          TEXT,
    UNIQUE(date, promoter_code)
);
CREATE INDEX IF NOT EXISTS idx_roster_date ON roster(date);
"""


def connect():
    directory = os.path.dirname(DB_PATH)
    if directory:
        os.makedirs(directory, exist_ok=True)
    # timeout: if another request holds the write lock, wait rather than fail.
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # WAL lets readers carry on while one writer commits. Without it, two
    # promoters saving a lead in the same instant can collide with
    # "database is locked" — rare on a laptop, routine once the whole team
    # is on the same hosted instance.
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 15000")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


# Columns added after the first release. SQLite has no "ADD COLUMN IF NOT
# EXISTS", so each one is checked against the live table before being added.
MIGRATIONS = [
    ("leads", "note", "TEXT"),
]


def init():
    conn = connect()
    conn.executescript(SCHEMA)
    for table, column, decl in MIGRATIONS:
        have = {r["name"] for r in
                conn.execute("PRAGMA table_info(%s)" % table).fetchall()}
        if column not in have:
            conn.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, column, decl))
    conn.commit()
    conn.close()


# --- helpers ------------------------------------------------------------

def now_iso():
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def parse_ts(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    value = value.strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


# These three depend on values the manager can edit at runtime, so they live in
# settings.py. Thin wrappers keep every existing call site working; the import
# is deferred because settings.py imports this module.

def normalise_phone(raw):
    import settings
    return settings.normalise_phone(raw)


def phone_is_valid(norm):
    import settings
    return settings.phone_is_valid(norm)


def shift_of(dt):
    import settings
    return settings.shift_for(dt)


def make_lead_id(dt, promoter_code):
    """AB-YYMMDD-P07-HHMMSS — unique by construction, sorts chronologically."""
    return "AB-%s-%s-%s" % (dt.strftime("%y%m%d"), promoter_code,
                            dt.strftime("%H%M%S"))
