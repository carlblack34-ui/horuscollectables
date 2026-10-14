import unittest
import threading
from decimal import Decimal
import test_app as support
from db import Database,migrate
from inventory_service import get_product

class StockManagementTests(unittest.TestCase):
    setUp=support.PortalTests.setUp
    tearDown=support.PortalTests.tearDown
    post=support.PortalTests.post
    scalar=support.PortalTests.scalar

    def buy(self,qty,cost,**changes):
        data=dict(name='Nightmare Night · Booster Pack',product_type='sealed',category='Booster Pack',quantity=str(qty),unit_cost=str(cost),shipping_cost='0',grading_cost='0',supplies_cost='0',purchase_date='2026-10-14',condition='Sealed')
        data.update(changes)
        return self.post('/stock/add',**data)
    def sell(self,qty,**changes):
        data=dict(product_id='1',quantity=str(qty),sale_price='100',fees='0',shipping_paid='0',sale_date='2026-10-14')
        data.update(changes);return self.post('/sales/add',**data)
    def product(self,pid=1):
        with Database(self.path) as d:return get_product(d,pid)

    def test_repeat_purchases_one_card_weighted_cost_and_history(self):
        self.buy(20,8,source='Supplier A');self.buy(10,9,source='Supplier B')
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM products'),1)
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM stock'),2)
        p=self.product();self.assertEqual(p['on_hand'],30);self.assertEqual(p['book_value'],250)
        self.assertEqual(p['average'],Decimal('8.33333333'))
        html=self.client.get('/stock').get_data(as_text=True)
        self.assertEqual(html.count('<article class="stock-card">'),1)
        self.assertIn('$8.33',html);self.assertIn('$250.00',html)
        history=self.client.get('/products/1').get_data(as_text=True)
        self.assertIn('Supplier A',history);self.assertIn('Supplier B',history)
        self.assertEqual(self.client.get('/stock/add?product_id=1').status_code,200)
        self.assertEqual(self.client.get('/export/purchases').status_code,200)

    def test_restock_uses_remaining_stock_not_all_time_purchases(self):
        self.buy(20,8);self.sell(10);self.buy(10,9)
        p=self.product();self.assertEqual(p['on_hand'],20);self.assertEqual(p['average'],Decimal('8.5'))
        self.assertEqual(self.scalar('SELECT cost_total FROM sales WHERE id=1'),80)
        self.sell(3)
        self.assertEqual(self.scalar('SELECT cost_total FROM sales WHERE id=2'),25.5)
        self.assertEqual(self.product()['book_value'],Decimal('144.5'))

    def test_selling_across_receipts_and_full_depletion(self):
        self.buy(20,8);self.buy(10,9)
        self.assertEqual(self.sell(25).status_code,302)
        self.assertEqual(self.product()['on_hand'],5)
        self.assertEqual(self.sell(5).status_code,302)
        self.assertEqual(self.product()['on_hand'],0);self.assertEqual(self.product()['book_value'],0)
        total=self.scalar('SELECT SUM(cost_total) FROM sales')
        self.assertAlmostEqual(float(total),250,places=7)
        self.assertEqual(self.sell(1).status_code,200)
        self.buy(3,12);self.assertEqual(self.product()['average'],12)

    def test_void_restores_recorded_cost_once_after_restock(self):
        self.buy(10,8);self.sell(5);self.buy(10,10)
        self.assertEqual(self.product()['book_value'],140)
        self.post('/sales/1/void');self.post('/sales/1/void')
        p=self.product();self.assertEqual(p['on_hand'],20);self.assertEqual(p['book_value'],180);self.assertEqual(p['average'],9)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM stock_movements WHERE kind='sales void reversal'"),1)

    def test_adjustment_is_counted_once_and_void_restores_value(self):
        self.buy(20,8);self.buy(10,9)
        self.post('/adjustments/add',product_id='1',quantity='3',kind='giveaway',expense='2',notes='Prize')
        self.assertEqual(self.product()['on_hand'],27);self.assertEqual(self.product()['book_value'],225)
        self.assertEqual(self.scalar('SELECT cost_total FROM adjustments'),25)
        self.post('/adjustments/1/void');self.assertEqual(self.product()['book_value'],250)

    def test_invalid_sale_edit_rolls_back_balance_and_movement_history(self):
        self.buy(10,8);self.sell(2)
        count=self.scalar('SELECT COUNT(*) FROM stock_movements')
        response=self.post('/sales/1/edit',product_id='1',quantity='20',sale_price='200')
        self.assertEqual(response.status_code,200)
        self.assertEqual(self.product()['on_hand'],8);self.assertEqual(self.product()['book_value'],64)
        self.assertEqual(self.scalar('SELECT quantity FROM sales'),2)
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM stock_movements'),count)
        self.post('/sales/1/edit',product_id='1',quantity='3',sale_price='200')
        self.assertEqual(self.product()['on_hand'],7);self.assertEqual(self.scalar('SELECT cost_total FROM sales'),24)

    def test_purchase_correction_before_sales_and_lock_after_sales(self):
        self.buy(10,8)
        response=self.post('/stock/1/edit',name='Nightmare Night · Booster Pack',product_type='sealed',category='Booster Pack',condition='Sealed',quantity='12',unit_cost='9',shipping_cost='0',grading_cost='0',supplies_cost='0')
        self.assertEqual(response.status_code,302);self.assertEqual(self.product()['on_hand'],12);self.assertEqual(self.product()['book_value'],108)
        self.sell(2)
        response=self.post('/stock/1/edit',name='Nightmare Night · Booster Pack',product_type='sealed',category='Booster Pack',condition='Sealed',quantity='12',unit_cost='99',shipping_cost='0',grading_cost='0',supplies_cost='0')
        self.assertEqual(response.status_code,200);self.assertEqual(self.product()['book_value'],90)
        self.assertEqual(self.scalar('SELECT unit_cost FROM stock'),9)

    def test_selling_price_history_is_persistent_and_not_cost(self):
        self.buy(10,8)
        self.post('/products/1/price',selling_price='12',notes='Launch')
        self.post('/products/1/price',selling_price='14',notes='New show')
        self.post('/products/1/price',selling_price='14')
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM price_history'),2)
        self.assertEqual(self.product()['selling_price'],14);self.assertEqual(self.product()['average'],8)
        self.post('/products/1/price',selling_price='NaN')
        self.assertEqual(self.product()['selling_price'],14)

    def test_product_variants_not_merged_and_case_spacing_normalised(self):
        self.buy(10,8);self.buy(10,9,name='  NIGHTMARE Night · Booster Pack  ')
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM products'),1)
        self.buy(1,10,language='Japanese');self.buy(1,11,condition='Damaged packaging')
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM products'),3)

    def test_existing_duplicate_migration_preserves_previous_profit(self):
        with Database(self.path) as d:
            for qty,cost in [(20,8),(10,9)]:
                d.execute("INSERT INTO stock(name,category,quantity,unit_cost,created_at) VALUES (?,?,?,?,?)",('Legacy pack','Booster Pack',qty,cost,'2026-10-01'))
            d.execute("INSERT INTO sales(stock_id,sale_date,quantity,sale_price,cost_snapshot,cost_total,created_at) VALUES (1,?,5,100,8,40,?)",('2026-10-02','2026-10-02'))
            d.execute('DELETE FROM schema_version WHERE version=5')
        migrate(self.path);migrate(self.path)
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM products'),1)
        self.assertEqual(self.product()['on_hand'],25);self.assertEqual(self.product()['book_value'],210)
        self.assertEqual(self.scalar('SELECT cost_snapshot FROM sales'),8)
        self.assertEqual(self.scalar('SELECT cost_total FROM sales'),40)
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM stock_movements'),2)

    def test_two_logins_concurrent_receipts_share_one_balance(self):
        results=[]
        def receipt(cost):
            c=self.app.test_client()
            with c.session_transaction() as s:s.update(user='owner',csrf='token')
            results.append(c.post('/stock/add',data=dict(csrf='token',name='Concurrent pack',product_type='sealed',category='Booster Pack',quantity='10',unit_cost=str(cost),tcg='Pokémon',era='Sun & Moon',set_name='Sun & Moon',language='English')).status_code)
        threads=[threading.Thread(target=receipt,args=(cost,)) for cost in [8,9]]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertEqual(results,[302,302]);self.assertEqual(self.scalar('SELECT COUNT(*) FROM products'),1)
        self.assertEqual(self.product()['on_hand'],20);self.assertEqual(self.product()['book_value'],170)

    def test_move_sale_to_another_product_and_void(self):
        self.buy(10,8);self.buy(5,20,name='Different product');self.sell(2)
        result=self.post('/sales/1/edit',product_id='2',quantity='3',sale_price='100')
        self.assertEqual(result.status_code,302)
        self.assertEqual(self.product(1)['on_hand'],10);self.assertEqual(self.product(1)['book_value'],80)
        self.assertEqual(self.product(2)['on_hand'],2);self.assertEqual(self.product(2)['book_value'],40)
        self.assertEqual(self.scalar('SELECT cost_total FROM sales'),60)
        self.post('/sales/1/void');self.assertEqual(self.product(2)['book_value'],100)

    def test_restock_identity_change_rolls_back_new_product(self):
        self.buy(10,8)
        response=self.buy(10,9,product_id='1',name='Changed name')
        self.assertEqual(response.status_code,200)
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM products'),1)
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM stock'),1)

    def test_pool_and_movement_ledger_reconcile(self):
        self.buy(20,8);self.sell(3);self.buy(10,9);self.sell(7)
        self.post('/adjustments/add',product_id='1',quantity='2',kind='write-off',expense='0',notes='Damaged')
        self.post('/sales/1/void')
        with Database(self.path) as d:
            p=get_product(d,1)
            rows=d.execute('SELECT * FROM stock_movements WHERE product_id=1 ORDER BY id').fetchall()
            self.assertEqual(sum(r['quantity_delta'] for r in rows),p['on_hand'])
            self.assertAlmostEqual(sum(float(r['value_delta']) for r in rows),float(p['book_value']),places=7)
            self.assertEqual(rows[-1]['quantity_after'],p['on_hand'])

if __name__=='__main__':unittest.main(verbosity=2)
