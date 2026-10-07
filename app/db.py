import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path("data/pf.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    unit TEXT NOT NULL DEFAULT 'шт',
    ref_qty REAL NOT NULL DEFAULT 0,
    tol_abs REAL NOT NULL DEFAULT 0,
    tol_pct REAL NOT NULL DEFAULT 0,
    track_stock INTEGER NOT NULL DEFAULT 1,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stock_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(id),
    event_type TEXT NOT NULL,
    qty REAL NOT NULL,
    batch_id TEXT,
    occurred_at TEXT NOT NULL,
    note TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_product_time
    ON stock_events(product_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_events_batch
    ON stock_events(batch_id);

CREATE TABLE IF NOT EXISTS ref_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(id),
    old_qty REAL NOT NULL,
    new_qty REAL NOT NULL,
    changed_at TEXT NOT NULL,
    note TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    generated_at TEXT NOT NULL,
    period_from TEXT NOT NULL,
    period_to TEXT NOT NULL,
    acknowledged INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS report_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id),
    ref_qty REAL NOT NULL,
    fact_qty REAL,
    diff REAL,
    tolerance REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    intake_sum REAL NOT NULL DEFAULT 0,
    consumption REAL,
    beginning_qty REAL
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('admin','line')),
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS weekly_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_start TEXT NOT NULL UNIQUE,
    week_end TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    is_final INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS weekly_report_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER NOT NULL REFERENCES weekly_reports(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id),
    name_snapshot TEXT NOT NULL,
    unit_snapshot TEXT NOT NULL,
    beginning REAL,
    intake REAL NOT NULL DEFAULT 0,
    writeoff REAL NOT NULL DEFAULT 0,
    ending REAL,
    consumption REAL,
    prev_consumption REAL,
    trend_diff REAL,
    trend_pct REAL
);
CREATE INDEX IF NOT EXISTS idx_wri_report ON weekly_report_items(report_id);
CREATE INDEX IF NOT EXISTS idx_wri_product ON weekly_report_items(product_id);

CREATE TABLE IF NOT EXISTS tech_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    note TEXT,
    method TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tech_card_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id INTEGER NOT NULL REFERENCES tech_cards(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id),
    qty_per_portion REAL NOT NULL,
    unit TEXT,
    variant TEXT
);
CREATE INDEX IF NOT EXISTS idx_tci_card ON tech_card_items(card_id);
"""


@contextmanager
def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)