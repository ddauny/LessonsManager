import sqlite3
import os

DB = os.path.join(os.path.dirname(__file__), '..', 'ripetizioni.db')

def main():
    if not os.path.exists(DB):
        print('Database not found at', DB)
        return
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("PRAGMA table_info('lesson')")
    rows = cur.fetchall()
    cols = [r[1] for r in rows]
    if 'payment_method' in cols:
        print('payment_method already present')
    else:
        print('Adding payment_method column')
        cur.execute("ALTER TABLE lesson ADD COLUMN payment_method VARCHAR(64)")
        con.commit()
        print('Done')
    cur.close()
    con.close()

if __name__ == '__main__':
    main()
