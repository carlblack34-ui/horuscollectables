"""Product balances, immutable stock movements and moving weighted average cost."""
import hashlib
import json
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal

IDENTITY = ['name','product_type','category','set_name','condition','tcg','era','language','sku']
COMPONENTS = ['unit_cost','shipping_cost','grading_cost','supplies_cost']
SCALE = Decimal('0.00000001')
now = lambda: datetime.now(timezone.utc).isoformat(timespec='seconds')
def number(v): return Decimal(str(v or 0)).quantize(SCALE)
def normal(v): return ' '.join(unicodedata.normalize('NFKC',str(v or '')).casefold().split())
def identity(row):
    values=[normal(row.get(k,'')) for k in IDENTITY]
    aliases={'pack':'booster pack','etb':'elite trainer box (etb)','single':'single card','slab':'graded card'}
    values[2]=aliases.get(values[2],values[2])
    return hashlib.sha256(json.dumps(values,ensure_ascii=False).encode()).hexdigest()
def landed(row): return sum(number(row.get(k,0)) for k in COMPONENTS)

def get_product(d,pid,lock=False):
    row=d.execute('SELECT * FROM products WHERE id=?'+(' FOR UPDATE' if lock and d.pg else ''),(pid,)).fetchone()
    if not row: raise ValueError('Product not found.')
    return enrich(dict(row))
def enrich(p):
    p['book_value']=number(p['book_value'])
    p['remaining']=p['on_hand']
    p['average']=number(p['book_value']/p['on_hand']) if p['on_hand'] else Decimal(0)
    p['landed']=p['average']
    return p
def product_rows(d):
    return [enrich(dict(r)) for r in d.execute('''SELECT p.*,
      (SELECT COUNT(*) FROM stock WHERE product_id=p.id) AS purchase_count,
      COALESCE((SELECT SUM(quantity) FROM stock WHERE product_id=p.id),0) AS purchased,
      COALESCE((SELECT SUM(quantity) FROM sales WHERE product_id=p.id AND voided=0),0) AS sold,
      COALESCE((SELECT SUM(quantity) FROM adjustments WHERE product_id=p.id AND voided=0),0) AS removed,
      (SELECT unit_cost+shipping_cost+grading_cost+supplies_cost FROM stock WHERE product_id=p.id ORDER BY id DESC LIMIT 1) AS latest_cost
      FROM products p ORDER BY p.id DESC''')]
def ensure_product(d,row):
    key=identity(row)
    fields=['identity_key']+IDENTITY+['created_at']
    values=[key]+[row.get(k,'') or '' for k in IDENTITY]+[now()]
    d.execute('INSERT INTO products ('+','.join(fields)+') VALUES ('+','.join('?' for _ in fields)+') ON CONFLICT(identity_key) DO NOTHING',values)
    pid=d.execute('SELECT id FROM products WHERE identity_key=?',(key,)).fetchone()['id']
    return get_product(d,pid,True)

def move(d,pid,qty,value,kind,reference,actor,notes=''):
    """Caller holds product lock. Append a movement and update balance atomically."""
    p=get_product(d,pid)
    new_qty=p['on_hand']+qty; new_value=number(p['book_value']+number(value))
    if new_qty<0 or new_value<0: raise ValueError('Not enough stock or inventory value for this correction. Void and re-record the transaction at the current average cost.')
    if new_qty==0 and abs(new_value)>SCALE:
        raise ValueError('This correction would leave value without stock. Void and re-record at the current average cost.')
    if new_qty==0:new_value=Decimal(0)
    d.execute('UPDATE products SET on_hand=?,book_value=?,archived=0 WHERE id=?',(new_qty,str(new_value),pid))
    d.execute('''INSERT INTO stock_movements(product_id,kind,reference,quantity_delta,value_delta,
      quantity_after,value_after,username,notes,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)''',
      (pid,kind,str(reference),qty,str(number(value)),new_qty,str(new_value),actor,notes,now()))

def issue_cost(product,quantity):
    if quantity>product['on_hand']: raise ValueError('Not enough stock available for this product.')
    total=product['book_value'] if quantity==product['on_hand'] else number(product['book_value']*quantity/product['on_hand'])
    unit=total/quantity
    return str(unit),str(total)

def migrate_products(d,add,pk):
    d.execute(f'''CREATE TABLE IF NOT EXISTS products (id {pk},identity_key TEXT NOT NULL UNIQUE,
      name TEXT NOT NULL,product_type TEXT,category TEXT,set_name TEXT,condition TEXT,tcg TEXT,era TEXT,
      language TEXT,sku TEXT,on_hand INTEGER NOT NULL DEFAULT 0,book_value NUMERIC NOT NULL DEFAULT 0,
      selling_price NUMERIC NOT NULL DEFAULT 0,archived INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL)''')
    add('stock','product_id','INTEGER REFERENCES products(id)')
    for table in ['sales','adjustments']:
        add(table,'product_id','INTEGER REFERENCES products(id)')
        add(table,'cost_total','NUMERIC')
        d.execute(f'UPDATE {table} SET cost_total=cost_snapshot*quantity WHERE cost_total IS NULL')
    d.execute(f'''CREATE TABLE IF NOT EXISTS stock_movements (id {pk},product_id INTEGER NOT NULL REFERENCES products(id),
      kind TEXT NOT NULL,reference TEXT NOT NULL,quantity_delta INTEGER NOT NULL,value_delta NUMERIC NOT NULL,
      quantity_after INTEGER NOT NULL,value_after NUMERIC NOT NULL,username TEXT NOT NULL,notes TEXT,created_at TEXT NOT NULL)''')
    d.execute(f'''CREATE TABLE IF NOT EXISTS price_history (id {pk},product_id INTEGER NOT NULL REFERENCES products(id),
      price NUMERIC NOT NULL,username TEXT NOT NULL,notes TEXT,created_at TEXT NOT NULL)''')
    if not d.execute('SELECT version FROM schema_version WHERE version=5').fetchone():
        for row in d.execute('SELECT * FROM stock ORDER BY id').fetchall():
            row=dict(row); p=ensure_product(d,row)
            sold=d.execute('SELECT COALESCE(SUM(quantity),0) AS n FROM sales WHERE stock_id=? AND voided=0',(row['id'],)).fetchone()['n']
            removed=d.execute('SELECT COALESCE(SUM(quantity),0) AS n FROM adjustments WHERE stock_id=? AND voided=0',(row['id'],)).fetchone()['n']
            qty=row['quantity']-sold-removed
            if qty<0:raise ValueError(f"Legacy purchase #{row['id']} has negative stock. Correct it before upgrading.")
            d.execute('UPDATE stock SET product_id=? WHERE id=?',(p['id'],row['id']))
            for table in ['sales','adjustments']:
                d.execute(f'UPDATE {table} SET product_id=? WHERE stock_id=?',(p['id'],row['id']))
            move(d,p['id'],qty,qty*landed(row),'migration opening',row['id'],'migration','Remaining purchase stock; historical transaction costs preserved.')
        d.execute('INSERT INTO schema_version(version) VALUES (5) ON CONFLICT DO NOTHING')
    for table in ['stock','sales','adjustments','stock_movements','price_history']:
        d.execute(f'CREATE INDEX IF NOT EXISTS ix_{table}_product_id ON {table}(product_id)')
