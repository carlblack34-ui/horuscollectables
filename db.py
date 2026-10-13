"""Small database adapter. SQLite locally, psycopg on Railway."""
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).parent

class Database:
    def __init__(self, url=None):
        self.url = url or os.environ.get('DATABASE_URL', str(ROOT / 'whatnot_stock.db'))
        self.pg = self.url.startswith(('postgres://', 'postgresql://'))
    def __enter__(self):
        if self.pg:
            import psycopg
            from psycopg.rows import dict_row
            self.conn = psycopg.connect(self.url, row_factory=dict_row)
        else:
            self.conn = sqlite3.connect(self.url.removeprefix('sqlite:///'), timeout=30)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute('PRAGMA foreign_keys=ON')
            self.conn.execute('BEGIN IMMEDIATE')
        return self
    def execute(self, sql, args=()):
        return self.conn.execute(sql.replace('?', '%s') if self.pg else sql, args)
    def __exit__(self, kind, value, tb):
        try:
            self.conn.rollback() if kind else self.conn.commit()
        finally:
            self.conn.close()

def migrate(url=None):
    with Database(url) as d:
        if d.pg:
            d.execute('SELECT pg_advisory_xact_lock(7241014)')
        pk = 'SERIAL PRIMARY KEY' if d.pg else 'INTEGER PRIMARY KEY AUTOINCREMENT'
        d.execute(f'''CREATE TABLE IF NOT EXISTS stock (id {pk}, name TEXT NOT NULL,
          category TEXT, set_name TEXT, condition TEXT, quantity INTEGER NOT NULL DEFAULT 1,
          unit_cost NUMERIC NOT NULL DEFAULT 0, shipping_cost NUMERIC NOT NULL DEFAULT 0,
          grading_cost NUMERIC NOT NULL DEFAULT 0, supplies_cost NUMERIC NOT NULL DEFAULT 0,
          source TEXT, purchase_date TEXT, notes TEXT, created_at TEXT NOT NULL)''')
        d.execute(f'''CREATE TABLE IF NOT EXISTS sales (id {pk}, stock_id INTEGER NOT NULL REFERENCES stock(id),
          sale_date TEXT NOT NULL, show_name TEXT, buyer TEXT, quantity INTEGER NOT NULL DEFAULT 1,
          sale_price NUMERIC NOT NULL DEFAULT 0, fees NUMERIC NOT NULL DEFAULT 0,
          shipping_paid NUMERIC NOT NULL DEFAULT 0, notes TEXT, created_at TEXT NOT NULL)''')
        def add(table, name, definition):
            columns = [r['column_name'] for r in d.execute('SELECT column_name FROM information_schema.columns WHERE table_name=?', (table,))] if d.pg else [r['name'] for r in d.execute(f'PRAGMA table_info({table})')]
            if name not in columns:
                d.execute(f'ALTER TABLE {table} ADD COLUMN {name} {definition}')
        d.execute('CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)')
        first = not d.execute('SELECT version FROM schema_version WHERE version=1').fetchone()
        add('stock', 'product_type', "TEXT NOT NULL DEFAULT 'sealed'")
        add('stock', 'sku', "TEXT NOT NULL DEFAULT ''")
        add('stock', 'archived', 'INTEGER NOT NULL DEFAULT 0')
        add('stock', 'tcg', "TEXT NOT NULL DEFAULT ''")
        add('stock', 'era', "TEXT NOT NULL DEFAULT ''")
        add('stock', 'language', "TEXT NOT NULL DEFAULT 'English'")
        d.execute(f'''CREATE TABLE IF NOT EXISTS catalogue (id {pk}, game TEXT NOT NULL,
          era TEXT NOT NULL DEFAULT '', set_name TEXT NOT NULL DEFAULT '', UNIQUE(game,era,set_name))''')
        from catalog import seed, pokemon_catalog
        if not d.execute('SELECT version FROM schema_version WHERE version=2').fetchone():
            seed(d)
            for era,sets in pokemon_catalog().items():
                for name in sets:
                    d.execute("UPDATE stock SET tcg='Pokémon',era=? WHERE set_name=? AND tcg=''",(era,name))
            d.execute('INSERT INTO schema_version(version) VALUES (2) ON CONFLICT DO NOTHING')
        if not d.execute('SELECT version FROM schema_version WHERE version=3').fetchone():
            from catalog import seed_other
            seed_other(d)
            d.execute('INSERT INTO schema_version(version) VALUES (3) ON CONFLICT DO NOTHING')
        if not d.execute('SELECT version FROM schema_version WHERE version=4').fetchone():
            from anime_pony_catalog import seed as seed_anime_pony
            seed_anime_pony(d)
            d.execute('INSERT INTO schema_version(version) VALUES (4) ON CONFLICT DO NOTHING')
        add('sales', 'cost_snapshot', 'NUMERIC')
        add('sales', 'category_snapshot', 'TEXT')
        add('sales', 'voided', 'INTEGER NOT NULL DEFAULT 0')
        if first:
            d.execute("UPDATE stock SET product_type='singles' WHERE category IN ('Single','Bulk') AND product_type='sealed'")
            d.execute("UPDATE stock SET product_type='graded' WHERE category='Slab' AND product_type='sealed'")
        d.execute('''UPDATE sales SET cost_snapshot=(SELECT unit_cost+shipping_cost+grading_cost+supplies_cost FROM stock WHERE stock.id=sales.stock_id), category_snapshot=(SELECT category FROM stock WHERE stock.id=sales.stock_id) WHERE cost_snapshot IS NULL''')
        d.execute(f'''CREATE TABLE IF NOT EXISTS adjustments (id {pk}, stock_id INTEGER NOT NULL REFERENCES stock(id),
          kind TEXT NOT NULL, quantity INTEGER NOT NULL, adjustment_date TEXT NOT NULL,
          cost_snapshot NUMERIC NOT NULL, expense NUMERIC NOT NULL DEFAULT 0,
          notes TEXT, created_at TEXT NOT NULL, voided INTEGER NOT NULL DEFAULT 0)''')
        d.execute('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password_hash TEXT NOT NULL,
          failures INTEGER NOT NULL DEFAULT 0, locked_until NUMERIC NOT NULL DEFAULT 0)''')
        d.execute(f'''CREATE TABLE IF NOT EXISTS audit (id {pk}, username TEXT NOT NULL,
          action TEXT NOT NULL, details TEXT NOT NULL, created_at TEXT NOT NULL)''')
        d.execute('CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)')
        d.execute('INSERT INTO schema_version(version) VALUES (1) ON CONFLICT DO NOTHING')
