import sqlite3

DB_PATH = 'D:/focus grok gemini/app.db'

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

try:
    cursor.execute('SELECT id, name, type, balance FROM account')
    accounts = cursor.fetchall()
    if accounts:
        print('Accounts found in app.db:')
        for account in accounts:
            print(f'  ID: {account[0]}, Name: {account[1]}, Type: {account[2]}, Balance: {account[3]}')
    else:
        print('No accounts found in app.db.')
except sqlite3.OperationalError as e:
    print(f'Error accessing database: {e}')
finally:
    conn.close()