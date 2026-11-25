import sqlite3
import logging

DATABASE = "lottery.db"

def connect():
    try:
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row

        logging.info("Datatbase Connected Successfully")

        return conn

    except sqlite3.Error:
        logging.exception("Database connection faild")
        raise