from .dbconnect import connect
import logging
import sqlite3

def getUsers():
    with connect() as connection:
        cursor = connection.execute("SELECT factorID, username FROM lottery")
        return cursor.fetchall()

def showUsers():
    users = getUsers()
    for counter, user in enumerate(users, start=1):
        print(counter, user["username"])

def deletefactor(invoice):
    try:
        deleted = connect().execute("DELETE FROM lottery WHERE factorID = ?", (invoice))
        connect().commit()

        if deleted.rowcount == 0:
            logging.warning(f"invoice {invoice} Not Found")
            return False

        logging.info(f"invoice {invoice} deleted!")
        return True

    except sqlite3.Error:
        logging.exception("Faild to delete Invoice")
        return False

    finally:
        if connect():
            connect().close()

def createUser(invoiceID, username, firstname, lastname, phone, prize, played_at):
    try:
        created = connect().execute("""
        INSERT INTO lottery (
                factorID, 
                username, 
                firstname, 
                lastname, 
                phone, 
                lottery_check, 
                prize, 
                played_at) VALUES (?, ?, ?, ?, ?, 0, ?, ?)
        """, (invoiceID, username, firstname, lastname, phone, prize, played_at))
        connect().commit()
        logging.info(f"user: sort {firstname} {lastname} created on sqlite file\n prize: {prize}, player at {played_at}")
        return True

    except sqlite3.Error as ERROR:
        logging.exception(f"!User Create Faild! Error: {ERROR}")
        return False

    finally:
        if connect():
            connect().close()

def editUser(invoiceID, username, firstname, lastname, phone, lottery_check, prize, played_at):
    try:
        connect().execute("""
            UPDATE lottery SET (
                factorID = ?, 
                username = ?,   
                firstname = ?, 
                lastname = ?, 
                phone = ?, 
                lottery_check = ?, 
                prize = ?, 
                played_at = ?
            ) WHERE factorID = ?
        """, (invoiceID, username, firstname, lastname, phone, lottery_check, prize, played_at, invoiceID))
        connect().commit()
        logging.info(f"Update: Invoice {invoiceID} edited!")
        return True

    except sqlite3.Error as ERROR:
        logging.exception(f"Edit user Faild! ERROR: {ERROR}")
        return False

    finally:
        if connect():
            connect().close()