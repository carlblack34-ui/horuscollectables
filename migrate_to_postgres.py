"""Copy a SQLite database into an EMPTY PostgreSQL database. Never overwrites data."""
import argparse
import os
import sqlite3
from contextlib import closing
from db import Database, migrate

def transfer(source, target):
    if not target.startswith(('postgres://','postgresql://')):
        raise ValueError('Target must be PostgreSQL.')
    # Upgrade a COPY first; keep the original backup untouched.
    migrate(source)
    migrate(target)
    tables=['stock','sales','adjustments','users','audit']
    counts={}
    with closing(sqlite3.connect(source)) as src, Database(target) as dst:
        src.row_factory=sqlite3.Row
        for table in tables:
            if dst.execute(f'SELECT COUNT(*) AS n FROM {table}').fetchone()['n']:
                raise ValueError('Target is not empty. No records copied.')
        for table in tables:
            rows=src.execute(f'SELECT * FROM {table}').fetchall()
            for row in rows:
                columns=list(row.keys())
                dst.execute(f'INSERT INTO {table} ('+','.join(columns)+') VALUES ('+','.join('?' for _ in columns)+')',tuple(row))
            counts[table]=len(rows)
            if dst.execute(f'SELECT COUNT(*) AS n FROM {table}').fetchone()['n']!=len(rows):
                raise ValueError('Verification failed; transaction rolled back.')
            if table!='users':
                dst.execute(f"SELECT setval(pg_get_serial_sequence('{table}','id'), COALESCE((SELECT MAX(id) FROM {table}),1), EXISTS(SELECT 1 FROM {table}))")
        for row in src.execute('SELECT game,era,set_name FROM catalogue'):
            dst.execute('INSERT INTO catalogue(game,era,set_name) VALUES (?,?,?) ON CONFLICT DO NOTHING',tuple(row))
    return counts

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('sqlite_copy'); args=parser.parse_args()
    url=os.environ.get('DATABASE_URL','')
    print(transfer(args.sqlite_copy,url))
