"""Private browser operating profiles on a persistent SQLite volume."""
import os
import sqlite3
from contextlib import closing
from pathlib import Path

RATE_FIELDS = ("fuel_cost_per_mile", "target_hourly_wage", "chemical_cost_per_lb")


def database_path():
    explicit = os.environ.get("SCRAPRADAR_DB_PATH")
    mount = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
    if explicit:
        return Path(explicit)
    if mount:
        return Path(mount) / "scrapradar.db"
    if os.environ.get("RAILWAY_ENVIRONMENT_ID"):
        raise RuntimeError("Persistent profile storage is not configured")
    return Path(__file__).resolve().parent / "data" / "scrapradar.db"


def _connect():
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10)
    conn.execute("PRAGMA busy_timeout = 10000")
    conn.execute("""CREATE TABLE IF NOT EXISTS user_profiles (
        user_id TEXT PRIMARY KEY,
        fuel_cost_per_mile REAL CHECK(fuel_cost_per_mile >= 0),
        target_hourly_wage REAL CHECK(target_hourly_wage >= 0),
        chemical_cost_per_lb REAL CHECK(chemical_cost_per_lb >= 0),
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.commit()
    return conn


def init_db():
    with closing(_connect()):
        pass


def save_user_profile(owner_key, profile):
    # owner_key is derived from a private bearer credential, never a posted user_id.
    with closing(_connect()) as conn, conn:
        values = tuple(profile.get(name) for name in RATE_FIELDS)
        if all(value is None for value in values):
            conn.execute("DELETE FROM user_profiles WHERE user_id = ?", (owner_key,))
        else:
            conn.execute("""INSERT INTO user_profiles
                (user_id, fuel_cost_per_mile, target_hourly_wage, chemical_cost_per_lb, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET
                    fuel_cost_per_mile = excluded.fuel_cost_per_mile,
                    target_hourly_wage = excluded.target_hourly_wage,
                    chemical_cost_per_lb = excluded.chemical_cost_per_lb,
                    updated_at = CURRENT_TIMESTAMP""", (owner_key, *values))
    return get_user_profile(owner_key)


def get_user_profile(owner_key):
    with closing(_connect()) as conn:
        row = conn.execute("""SELECT fuel_cost_per_mile, target_hourly_wage,
            chemical_cost_per_lb, updated_at FROM user_profiles WHERE user_id = ?""",
            (owner_key,)).fetchone()
    if row is None:
        return None
    return dict(zip((*RATE_FIELDS, "updated_at"), row))
