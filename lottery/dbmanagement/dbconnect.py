import logging
import sqlite3

log = logging.getLogger("a1.dbconnect")
_database_path = None


def configure(path):
    """Backend calls this once with the real (user_data_dir) database path."""
    global _database_path
    _database_path = str(path)


def connect():
    if _database_path is None:
        raise RuntimeError("dbmanagement.dbconnect.configure() was not called")
    try:
        conn = sqlite3.connect(_database_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error:
        log.exception("Database connection failed")
        raise
