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
    if not rows:
        print('No lesson table or no columns returned')
    else:
        print('lesson table columns:')
        for r in rows:
            # r format: (cid, name, type, notnull, dflt_value, pk)
            print('-', r[1], r[2])
    cur.close()
    con.close()

if __name__ == '__main__':
    main()
