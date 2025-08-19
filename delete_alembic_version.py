import sqlite3
import os

# Assuming your database file is named 'app.db' in the project root
# Adjust this path if your database file is located elsewhere
DB_FILE = 'app.db'

if not os.path.exists(DB_FILE):
    print(f"Database file '{DB_FILE}' not found. Skipping table deletion.")
else:
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS alembic_version;")
        conn.commit()
        conn.close()
        print("Table 'alembic_version' deleted successfully (if it existed).")
    except sqlite3.Error as e:
        print(f"Error deleting table: {e}")