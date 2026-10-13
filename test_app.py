import os
import shutil
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from pathlib import Path
from app import create_app
from db import Database, migrate
from werkzeug.security import generate_password_hash

class PortalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=os.environ.get('HORUS_TEST_TEMP')); self.path=str(Path(self.tmp.name)/'test.db')
        self.app=create_app({'TESTING':True,'SECRET_KEY':'test-secret','DATABASE_URL':self.path})
        with Database(self.path) as d: d.execute('INSERT INTO users(username,password_hash) VALUES (?,?)',('owner',generate_password_hash('long-test-password')))
        self.client=self.app.test_client()
        with self.client.session_transaction() as s: s.update(user='owner',csrf='token')
    def tearDown(self): self.tmp.cleanup()
    def post(self,url,**data):
        if url.startswith('/stock/') and not url.endswith('/archive'):
            data={'tcg':'Pokémon','era':'Sun & Moon','set_name':'Sun & Moon','language':'English',**data}
        return self.client.post(url,data={'csrf':'token',**data})
    def stock(self,quantity='5'):
        return self.post('/stock/add',name='Pikachu',product_type='singles',category='Single',quantity=quantity,unit_cost='10',shipping_cost='2',grading_cost='0',supplies_cost='1')
    def sale(self,**overrides):
        data=dict(stock_id='1',quantity='2',sale_price='50',fees='5',shipping_paid='3',sale_date='2026-10-14'); data.update(overrides)
        return self.post('/sales/add',**data)
    def scalar(self,sql):
        with Database(self.path) as d: return d.execute(sql).fetchone()[0]
    def test_auth_csrf_and_templates(self):
        anon=self.app.test_client()
        for url in ['/','/stock','/sales','/reports','/export/stock','/adjustments']:
            self.assertEqual(anon.get(url).status_code,302)
            self.assertEqual(self.client.get(url).status_code,200)
        self.assertEqual(self.client.post('/stock/add').status_code,400)
        for url in ['/stock/add','/sales/add','/adjustments/add','/password','/login']:
            self.assertEqual(self.client.get(url).status_code,200)
    def test_financial_snapshots_and_no_double_count(self):
        self.stock(); self.sale()
        self.post('/adjustments/add',stock_id='1',quantity='1',kind='giveaway',expense='2',notes='Show prize',adjustment_date='2026-10-14')
        response=self.client.get('/').get_data(as_text=True)
        self.assertIn('$26.00',response) # remaining two units
        self.assertIn('$1.00',response) # 50 - 5 - 3 - 26 - 15
        self.post('/stock/1/edit',name='Pikachu',product_type='singles',quantity='5',unit_cost='99',shipping_cost='0',grading_cost='0',supplies_cost='0')
        self.assertEqual(self.scalar('SELECT cost_snapshot FROM sales'),13)
        self.assertEqual(self.scalar('SELECT cost_snapshot FROM adjustments'),13)
        self.assertEqual(self.client.get('/sales/1/edit').status_code,200)
        self.assertEqual(self.client.get('/adjustments/1/edit').status_code,200)
    def test_validation_edit_void(self):
        self.stock('3')
        for bad in ['-1','0','4','nan']:
            self.sale(quantity=bad)
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM sales'),0)
        self.sale(sale_price='NaN'); self.sale(sale_price='0.001')
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM sales'),0)
        self.sale()
        self.post('/sales/1/edit',stock_id='1',quantity='3',sale_price='60',fees='0',shipping_paid='0')
        self.assertEqual(self.scalar('SELECT quantity FROM sales'),3)
        self.post('/adjustments/add',stock_id='1',quantity='1',kind='write-off',notes='damaged')
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM adjustments'),0)
        self.post('/stock/1/edit',name='X',product_type='sealed',quantity='2')
        self.assertEqual(self.scalar('SELECT quantity FROM stock'),3)
        self.post('/sales/1/void'); self.post('/sales/1/void')
        self.sale(quantity='3')
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM sales WHERE voided=0'),1)
    def test_login_lockout_and_password_hash(self):
        c=self.app.test_client(); c.get('/login')
        with c.session_transaction() as s: token=s['csrf']
        for _ in range(5): c.post('/login',data=dict(csrf=token,username='owner',password='wrong'))
        self.assertGreater(self.scalar('SELECT locked_until FROM users'),0)
        self.assertEqual(c.post('/login',data=dict(csrf=token,username='owner',password='long-test-password')).status_code,200)
        self.assertNotIn('long-test-password',self.scalar('SELECT password_hash FROM users'))
    def test_concurrent_last_unit(self):
        self.stock('1'); results=[]
        def sell():
            c=self.app.test_client()
            with c.session_transaction() as s: s.update(user='owner',csrf='token')
            results.append(c.post('/sales/add',data=dict(csrf='token',stock_id='1',quantity='1',sale_price='20')).status_code)
        threads=[threading.Thread(target=sell) for _ in range(2)]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertEqual(sorted(results),[200,302]); self.assertEqual(self.scalar('SELECT COUNT(*) FROM sales'),1)
    def test_original_migration_idempotent(self):
        source=Path(__file__).parent/'originals'/'whatnot_stock.db'
        if not source.exists(): self.skipTest('Original upload is excluded from code-only upgrade archives.')
        copy=Path(self.tmp.name)/'legacy.db'; shutil.copy2(source,copy)
        with closing(sqlite3.connect(copy)) as c:
            before={t:c.execute(f'SELECT * FROM {t} ORDER BY id').fetchall() for t in ['stock','sales']}
            columns={t:[r[1] for r in c.execute(f'PRAGMA table_info({t})')] for t in before}
        migrate(str(copy)); migrate(str(copy))
        with closing(sqlite3.connect(copy)) as c:
            for t in before:
                self.assertEqual(before[t],c.execute('SELECT '+','.join(columns[t])+f' FROM {t} ORDER BY id').fetchall())

    def test_catalogue_hierarchy_persistence_and_validation(self):
        from catalog import load
        with Database(self.path) as d:
            data=load(d)
        self.assertIn('Sun & Moon',data['Pokémon']['Sun & Moon'])
        self.assertIn('Guardians Rising',data['Pokémon']['Sun & Moon'])
        self.assertEqual(self.client.get('/catalogue').status_code,200)
        self.post('/catalogue',game='My TCG',era='First era',set_name='Base expansion')
        result=self.post('/stock/add',name='Custom booster',product_type='sealed',category='Booster Box',quantity='1',tcg='My TCG',era='First era',set_name='Base expansion')
        self.assertEqual(result.status_code,302)
        self.assertEqual(self.scalar('SELECT tcg FROM stock'),'My TCG')
        migrate(self.path)
        with Database(self.path) as d:self.assertIn('Base expansion',load(d)['My TCG']['First era'])
        bad=self.post('/stock/add',name='Invalid',product_type='sealed',quantity='1',tcg='Pokémon',era='Sun & Moon',set_name='Evolving Skies')
        self.assertEqual(bad.status_code,200)
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM stock'),1)
        # Stored product classification is not reclassified on subsequent startup.
        with Database(self.path) as d:d.execute("UPDATE stock SET product_type='sealed',category='Single'")
        migrate(self.path)
        self.assertEqual(self.scalar('SELECT product_type FROM stock'),'sealed')

    def test_app_shell_inventory_cards_and_sale_shortcut(self):
        self.stock()
        inventory=self.client.get('/stock').get_data(as_text=True)
        self.assertIn('stock-card',inventory)
        self.assertIn('/sales/add?stock_id=1',inventory)
        self.assertIn('sidebar',inventory)
        sale=self.client.get('/sales/add?stock_id=1').get_data(as_text=True)
        self.assertIn('value="1" selected',sale)
        purchase=self.client.get('/stock/add').get_data(as_text=True)
        self.assertIn('data-panel="3"',purchase)
        self.assertIn('app-builder.js',purchase)
        self.assertIn('era-tiles',purchase)
        self.assertIn('product-tiles',purchase)

    def test_naruto_pony_upgrade_preserves_stock_and_custom_catalogue(self):
        from catalog import load
        self.stock()
        self.post('/catalogue',game='Naruto',era='Custom regional releases',set_name='My existing import')
        with Database(self.path) as d:
            d.execute("DELETE FROM catalogue WHERE game IN ('Naruto','My Little Pony') AND era != 'Custom regional releases'")
            d.execute('DELETE FROM schema_version WHERE version=4')
        migrate(self.path); migrate(self.path)
        with Database(self.path) as d:
            data=load(d)
            self.assertIn('Heaven Scroll Series 1',data['Naruto']['Kayou · Smriti · Heaven / Jin Scroll'])
            self.assertIn('The Path to Hokage',data['Naruto']['Bandai CCG · Naruto'])
            self.assertIn('Moon Edition Series 3',data['My Little Pony']['Kayou · Friendship Eternal · Moon Edition'])
            self.assertIn('Premiere',data['My Little Pony']['Enterplay · Collectible Card Game'])
            self.assertIn('Fantasy Wonderland',data['My Little Pony']['Kayou · Trading Card Game'])
            self.assertIn('My existing import',data['Naruto']['Custom regional releases'])
            self.assertEqual(d.execute('SELECT COUNT(*) AS n FROM stock').fetchone()['n'],1)
            self.assertEqual(d.execute("SELECT COUNT(*) AS n FROM catalogue WHERE game='Naruto' AND set_name='The Path to Hokage'").fetchone()['n'],1)
        result=self.post('/stock/add',name='Moon Series 3 booster box',product_type='sealed',category='Booster Box',quantity='1',tcg='My Little Pony',era='Kayou · Friendship Eternal · Moon Edition',set_name='Moon Edition Series 3')
        self.assertEqual(result.status_code,302)
        html=self.client.get('/stock/add').get_data(as_text=True)
        self.assertIn('data-game="Naruto"',html)
        self.assertIn('data-game="My Little Pony"',html)

if __name__=='__main__': unittest.main(verbosity=2)
