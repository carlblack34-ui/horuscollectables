import csv
import io
import os
import secrets
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
import click
from flask import Flask, abort, flash, redirect, render_template, request, session, url_for, Response, g, has_request_context
from werkzeug.security import check_password_hash, generate_password_hash
from db import Database, migrate
from pokemon_sets import POKEMON_SETS, CATEGORY_OPTIONS, CONDITION_OPTIONS
from catalog import load as load_catalogue, PRODUCTS, GAME_PRODUCTS
from inventory_service import product_rows, get_product, ensure_product, identity, landed, number, move, issue_cost, COMPONENTS
from user_management import require_admin,create_user as add_user,change_user,password_valid,lock_accounts

TYPES = ['sealed', 'singles', 'graded', 'accessories']
NOW = lambda: datetime.now(timezone.utc).isoformat(timespec='seconds')

def create_app(config=None):
    app = Flask(__name__)
    secret = os.environ.get('SECRET_KEY')
    if not secret:
        if os.environ.get('APP_ENV') == 'production':
            raise RuntimeError('Set SECRET_KEY in Railway Variables before starting.')
        p = Path(__file__).parent / '.local-secret'
        if not p.exists():
            p.write_text(secrets.token_hex(32))
        secret = p.read_text().strip()
    app.config.update(SECRET_KEY=secret, DATABASE_URL=os.environ.get('DATABASE_URL'),
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=os.environ.get('APP_ENV') == 'production',
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8), MAX_CONTENT_LENGTH=1024*1024)
    if config: app.config.update(config)
    database = lambda: Database(app.config['DATABASE_URL'])
    migrate(app.config['DATABASE_URL'])
    # One-time owner promotion requested for this Horus installation.
    # Never creates an account, changes a password, or re-enables disabled users.
    with database() as d:
        lock_accounts(d)
        d.execute('CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY,value TEXT NOT NULL)')
        done=d.execute('SELECT value FROM app_settings WHERE key=?',('owner_admin_bootstrap_carl_v1',)).fetchone()
        owner=d.execute('SELECT role,disabled FROM users WHERE username=?',('carl',)).fetchone()
        if not done and owner and not owner['disabled']:
            if owner['role']!='admin':
                d.execute("UPDATE users SET role='admin',auth_version=auth_version+1 WHERE username=?",('carl',))
                d.execute('INSERT INTO audit(username,action,details,created_at) VALUES (?,?,?,?)',('deployment','owner admin enabled','carl',NOW()))
            d.execute('INSERT INTO app_settings(key,value) VALUES (?,?)',('owner_admin_bootstrap_carl_v1','complete'))
    app.jinja_env.filters['money'] = lambda v: f'${Decimal(str(v or 0)):,.2f}'

    def audit(d, action, details):
        actor=session.get('user','CLI') if has_request_context() else 'CLI'
        d.execute('INSERT INTO audit(username,action,details,created_at) VALUES (?,?,?,?)', (actor, action, details, NOW()))
    def amount(key):
        try: v = Decimal(request.form.get(key, '0') or '0')
        except InvalidOperation: raise ValueError(f'{key}: enter a valid amount.')
        if not v.is_finite() or v < 0 or v > Decimal('100000000') or v.as_tuple().exponent < -2:
            raise ValueError(f'{key}: use a non-negative amount with at most two decimal places.')
        return str(v)
    def integer(key):
        try: v = int(request.form.get(key, ''))
        except ValueError: raise ValueError(f'{key}: enter a whole number.')
        if not 1 <= v <= 1000000: raise ValueError(f'{key}: must be between 1 and 1,000,000.')
        return v
    def text(key, required=False):
        v = request.form.get(key,'').strip()
        if (required and not v) or len(v)>2000: raise ValueError(f'{key}: required, maximum 2,000 characters.')
        return v
    def day(key):
        v = request.form.get(key) or date.today().isoformat()
        try: date.fromisoformat(v)
        except ValueError: raise ValueError(f'{key}: use a valid date.')
        return v
    def lock(d, sid):
        r = d.execute('SELECT id FROM stock WHERE id=?'+(' FOR UPDATE' if d.pg else ''),(sid,)).fetchone()
        if not r: abort(404)

    @app.before_request
    def protect():
        session.setdefault('csrf',secrets.token_hex(32))
        if request.method == 'POST' and not secrets.compare_digest(session['csrf'], request.form.get('csrf','')):
            abort(400, 'Form expired. Reload the page and try again.')
        if request.endpoint not in ('login','static','health'):
            if not session.get('user'): return redirect(url_for('login'))
            with database() as d:
                user=d.execute('SELECT * FROM users WHERE username=?',(session['user'],)).fetchone()
                if not user or user['disabled'] or user['auth_version']!=session.get('auth_version',0):
                    session.clear(); return redirect(url_for('login'))
                g.is_admin=user['role']=='admin'
                if user['must_change_password'] and request.endpoint not in ['password','logout']:
                    return redirect(url_for('password'))

    @app.after_request
    def headers(response):
        response.headers.update({'X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY',
          'Content-Security-Policy':"default-src 'self'; style-src 'self'; form-action 'self'; frame-ancestors 'none'",
          'Referrer-Policy':'same-origin','Cache-Control':'no-store'})
        if app.config['SESSION_COOKIE_SECURE']: response.headers['Strict-Transport-Security']='max-age=31536000'
        return response

    @app.route('/health')
    def health():
        with database() as d: d.execute('SELECT 1')
        return {'status':'ok'}

    @app.route('/login', methods=['GET','POST'])
    def login():
        if request.method=='POST':
            username = request.form.get('username','').strip()
            with database() as d:
                u = d.execute('SELECT * FROM users WHERE username=?',(username,)).fetchone()
                valid = check_password_hash(u['password_hash'] if u else generate_password_hash('dummy-password'), request.form.get('password',''))
                if u and not u['disabled'] and time.time()>=float(u['locked_until']) and valid:
                    d.execute('UPDATE users SET failures=0,locked_until=0 WHERE username=?',(username,))
                    session.clear(); session.update(user=username,csrf=secrets.token_hex(32),auth_version=u['auth_version']); session.permanent=True
                    audit(d,'login',username)
                    return redirect(url_for('password' if u['must_change_password'] else 'dashboard'))
                if u:
                    failures = u['failures']+1
                    d.execute('UPDATE users SET failures=?,locked_until=? WHERE username=?',(failures, time.time()+900 if failures>=5 else u['locked_until'], username))
            flash('Unable to sign in. Check your details or try again in 15 minutes.','error')
        return render_template('login.html')

    @app.post('/logout')
    def logout():
        session.clear(); return redirect(url_for('login'))

    @app.route('/password',methods=['GET','POST'])
    def password():
        if request.method=='POST':
            with database() as d:
                lock_accounts(d)
                u=d.execute('SELECT * FROM users WHERE username=?'+(' FOR UPDATE' if d.pg else ''),(session['user'],)).fetchone()
                if not u or u['disabled'] or u['auth_version']!=session.get('auth_version',0):
                    session.clear();return redirect(url_for('login'))
                new=request.form.get('new_password','')
                try:
                    password_valid(new)
                    if not check_password_hash(u['password_hash'],request.form.get('current_password','')):raise ValueError('Current password does not match.')
                    if new!=request.form.get('confirm_password'):raise ValueError('New password confirmation must match.')
                    if check_password_hash(u['password_hash'],new):raise ValueError('Choose a different password.')
                    d.execute('UPDATE users SET password_hash=?,auth_version=auth_version+1,must_change_password=0 WHERE username=?',(generate_password_hash(new),session['user']))
                    session['auth_version']=u['auth_version']+1
                    session['csrf']=secrets.token_hex(32)
                    audit(d,'password changed',session['user']); flash('Password updated. Other sessions have been signed out.')
                    return redirect(url_for('dashboard'))
                except ValueError as e:flash(str(e),'error')
        return render_template('password.html')

    @app.route('/admin/users',methods=['GET','POST'])
    def admin_users():
        if not g.is_admin:abort(403)
        with database() as d:
            if request.method=='POST':
                try:
                    require_admin(d,session['user'],session.get('auth_version',0))
                    password=request.form.get('password','')
                    if password!=request.form.get('confirm_password'):raise ValueError('Password confirmation must match.')
                    username=add_user(d,text('username',True),password,text('role'),temporary=True)
                    audit(d,'user created',username+'; role='+text('role'))
                    flash('User created. They must change the temporary password on first sign-in.')
                    return redirect(url_for('admin_users'))
                except PermissionError:abort(403)
                except ValueError as e:flash(str(e),'error')
            users=[dict(r) for r in d.execute('SELECT username,role,disabled,must_change_password,failures,locked_until,created_at FROM users ORDER BY username')]
        return render_template('admin_users.html',users=users)

    @app.post('/admin/users/action')
    def admin_user_action():
        if not g.is_admin:abort(403)
        with database() as d:
            try:
                require_admin(d,session['user'],session.get('auth_version',0))
                target=text('username',True);action=text('action');role=text('role')
                password=request.form.get('password','')
                if action=='reset' and password!=request.form.get('confirm_password'):raise ValueError('Password confirmation must match.')
                change_user(d,session['user'],target,action,role,password)
                audit(d,'user '+action,target+('; role='+role if action=='role' else ''))
                flash('Temporary password set; existing sessions revoked.' if action=='reset' else 'User updated.')
            except PermissionError:abort(403)
            except ValueError as e:flash(str(e),'error')
        return redirect(url_for('admin_users'))

    def ledger(d):
        sales=[dict(r) for r in d.execute('SELECT sa.*,p.name FROM sales sa JOIN products p ON p.id=sa.product_id ORDER BY sale_date DESC,sa.id DESC')]
        adjustments=[dict(r) for r in d.execute('SELECT a.*,p.name FROM adjustments a JOIN products p ON p.id=a.product_id ORDER BY adjustment_date DESC,a.id DESC')]
        start=request.args.get('start',''); end=request.args.get('end','')
        for v in (start,end):
            if v:
                try: date.fromisoformat(v)
                except ValueError: abort(400,'Invalid report date')
        if start and end and start>end: abort(400,'Start date must precede end date')
        sales=[r for r in sales if (not start or r['sale_date']>=start) and (not end or r['sale_date']<=end)]
        adjustments=[r for r in adjustments if (not start or r['adjustment_date']>=start) and (not end or r['adjustment_date']<=end)]
        for r in sales:
            r['net']=Decimal(str(r['sale_price']))-Decimal(str(r['fees']))-Decimal(str(r['shipping_paid']))
            r['cost']=Decimal(str(r['cost_total'])); r['profit']=r['net']-r['cost']
        for r in adjustments: r['loss']=Decimal(str(r['cost_total']))+Decimal(str(r['expense']))
        return sales,adjustments

    @app.route('/reports')
    @app.route('/')
    def dashboard():
        with database() as d:
            stocks=product_rows(d); sales,adjustments=ledger(d)
        active=[r for r in sales if not r['voided']]; losses=[r for r in adjustments if not r['voided']]
        total=lambda key: sum((r[key] if isinstance(r[key],Decimal) else Decimal(str(r[key]))) for r in active)
        gross=total('sale_price'); net=total('net'); costs=total('cost'); loss=sum(r['loss'] for r in losses)
        groups={}
        for r in active:
            key=(r['category_snapshot'] or 'Uncategorised',r['show_name'] or 'No show')
            if key not in groups: groups[key]={'gross':Decimal(0),'profit':Decimal(0),'qty':0}
            groups[key]['gross']+=Decimal(str(r['sale_price'])); groups[key]['profit']+=r['profit']; groups[key]['qty']+=r['quantity']
        return render_template('dashboard.html' if request.path=='/reports' else 'overview.html', stocks=stocks,sales=active,groups=groups,gross=gross,net=net,costs=costs,loss=loss,profit=net-costs-loss,
          value=sum(r['book_value'] for r in stocks),units=sum(r['on_hand'] for r in stocks),margin=(net-costs-loss)/net*100 if net else 0)

    @app.route('/stock')
    def stock():
        with database() as d:
            rows=product_rows(d); games=list(load_catalogue(d))
        q=request.args.get('q','').lower(); kind=request.args.get('type',''); game=request.args.get('tcg','')
        rows=[r for r in rows if q in (r['name']+' '+r['sku']+' '+(r['set_name'] or '')+' '+r['tcg']+' '+r['era']).lower() and (not kind or r['product_type']==kind) and (not game or r['tcg']==game)]
        return render_template('product_inventory.html',rows=rows,types=TYPES,games=games)

    @app.route('/stock/add',methods=['GET','POST'])
    @app.route('/stock/<int:rid>/edit',methods=['GET','POST'])
    def stock_form(rid=None):
        with database() as d:
            old=d.execute('SELECT * FROM stock WHERE id=?'+(' FOR UPDATE' if d.pg and request.method=='POST' else ''),(rid,)).fetchone() if rid else None
            if rid and not old: abort(404)
            prefill={}
            if not rid and request.args.get('product_id'):
                try:
                    product=get_product(d,int(request.args['product_id']))
                    prefill=dict(product)
                    for key in ['id','quantity','unit_cost','shipping_cost','grading_cost','supplies_cost']:prefill.pop(key,None)
                    prefill['product_id']=product['id']
                except (ValueError,TypeError):abort(404)
            if request.method=='POST':
                d.execute('SAVEPOINT purchase_save')
                try:
                    fields=['name','category','set_name','condition','quantity','unit_cost','shipping_cost','grading_cost','supplies_cost','source','purchase_date','notes','product_type','sku']
                    values=[text('name',True),text('category'),text('set_name'),text('condition'),integer('quantity'),amount('unit_cost'),amount('shipping_cost'),amount('grading_cost'),amount('supplies_cost'),text('source'),day('purchase_date'),text('notes'),text('product_type'),text('sku')]
                    if values[-2] not in TYPES: raise ValueError('Choose a valid product type.')
                    catalogue=load_catalogue(d)
                    game=text('tcg'); era=text('era'); set_name=text('set_name')
                    legacy=old and (game,era,set_name)==(old['tcg'],old['era'],old['set_name'] or '')
                    if not legacy and (game not in catalogue or era not in catalogue[game] or set_name not in catalogue[game][era]):
                        raise ValueError('Choose a game, era and set from the catalogue. Add missing options using Manage catalogue.')
                    fields+=['tcg','era','language']; values += [game,era,text('language') or 'English']
                    receipt=dict(zip(fields,values))
                    if rid:
                        p=get_product(d,old['product_id'],True);lock(d,rid)
                        if identity(receipt)!=p['identity_key']:raise ValueError('This purchase belongs to an existing product. Keep its product details unchanged; add a new product for a different variation.')
                        changed=values[4]!=old['quantity'] or any(number(receipt[k])!=number(old[k]) for k in COMPONENTS)
                        used=any(d.execute(f'SELECT id FROM {t} WHERE product_id=? LIMIT 1',(p['id'],)).fetchone() for t in ['sales','adjustments'])
                        if changed and used:raise ValueError('Purchase quantities and costs are locked after this product has sales or write-offs. Add new purchases separately; past sale costs remain unchanged.')
                        if changed:move(d,p['id'],values[4]-old['quantity'],values[4]*landed(receipt)-old['quantity']*landed(dict(old)),'purchase correction',rid,session['user'])
                        d.execute('UPDATE stock SET '+','.join(f'{f}=?' for f in fields)+' WHERE id=?',values+[rid])
                    else:
                        p=ensure_product(d,receipt)
                        selected=request.form.get('product_id')
                        if selected and str(p['id'])!=selected:raise ValueError('Product details changed. Open Add stock to create a different product, or keep this product’s details when restocking.')
                        fields+=['product_id'];values+=[p['id']]
                        added=d.execute('INSERT INTO stock ('+','.join(fields)+',created_at) VALUES ('+','.join('?' for _ in range(len(fields)+1))+') RETURNING id',values+[NOW()]).fetchone()['id']
                        move(d,p['id'],receipt['quantity'],receipt['quantity']*landed(receipt),'purchase',added,session['user'],receipt['source'])
                    audit(d,'purchase edited' if rid else 'purchase added',str(rid or added)); flash('Purchase saved. Stock and weighted average cost updated.')
                    return redirect(url_for('stock'))
                except ValueError as e:
                    d.execute('ROLLBACK TO SAVEPOINT purchase_save');flash(str(e),'error')
            catalogue=load_catalogue(d)
        return render_template('purchase.html',row=request.form if request.method=='POST' else dict(old) if old else prefill,types=TYPES,sets=POKEMON_SETS,categories=CATEGORY_OPTIONS,conditions=CONDITION_OPTIONS,catalogue=catalogue,products=PRODUCTS,game_products=GAME_PRODUCTS)

    @app.route('/products/<int:pid>')
    def product_detail(pid):
        with database() as d:
            try:p=get_product(d,pid)
            except ValueError:abort(404)
            purchases=[dict(r) for r in d.execute('SELECT * FROM stock WHERE product_id=? ORDER BY purchase_date DESC,id DESC',(pid,))]
            for r in purchases:r['landed']=landed(r);r['total']=r['quantity']*r['landed']
            movements=[dict(r) for r in d.execute('SELECT * FROM stock_movements WHERE product_id=? ORDER BY id DESC',(pid,))]
            prices=[dict(r) for r in d.execute('SELECT * FROM price_history WHERE product_id=? ORDER BY id DESC',(pid,))]
            sales=[dict(r) for r in d.execute('SELECT * FROM sales WHERE product_id=? ORDER BY id DESC',(pid,))]
        return render_template('product_detail.html',product=p,purchases=purchases,movements=movements,prices=prices,sales=sales)

    @app.post('/products/<int:pid>/price')
    def product_price(pid):
        with database() as d:
            try:
                p=get_product(d,pid,True);price=amount('selling_price');notes=text('notes')
                if number(price)!=number(p['selling_price']):
                    d.execute('UPDATE products SET selling_price=? WHERE id=?',(price,pid))
                    d.execute('INSERT INTO price_history(product_id,price,username,notes,created_at) VALUES (?,?,?,?,?)',(pid,price,session['user'],notes,NOW()))
                    audit(d,'selling price changed',f'Product {pid}: {p["selling_price"]} → {price}')
                flash('Selling price saved.')
            except ValueError as e:flash(str(e),'error')
        return redirect(url_for('product_detail',pid=pid))

    @app.route('/catalogue',methods=['GET','POST'])
    def catalogue():
        with database() as d:
            if request.method=='POST':
                try:
                    game=text('game',True); era=text('era'); name=text('set_name')
                    if name and not era: raise ValueError('An era / series is required when adding a set.')
                    d.execute('INSERT INTO catalogue(game,era,set_name) VALUES (?,?,?) ON CONFLICT DO NOTHING',(game,era,name))
                    audit(d,'catalogue added',f'{game} / {era} / {name}'); flash('Catalogue option saved. It is now available in stock dropdowns.')
                    return redirect('/catalogue')
                except ValueError as e: flash(str(e),'error')
            data=load_catalogue(d)
        return render_template('catalogue.html',catalogue=data)

    @app.post('/stock/<int:rid>/archive')
    def archive(rid):
        with database() as d:
            source=d.execute('SELECT product_id FROM stock WHERE id=?',(rid,)).fetchone()
            if not source:abort(404)
            p=get_product(d,source['product_id'],True)
            if p['on_hand']:abort(400,'Only empty products can be archived.')
            d.execute('UPDATE products SET archived=1 WHERE id=?',(p['id'],))
            audit(d,'product archived',str(p['id']))
        return redirect(url_for('stock'))

    @app.route('/sales')
    @app.route('/adjustments')
    def transactions():
        with database() as d: sales,adjustments=ledger(d)
        return render_template('transactions.html',rows=adjustments if request.path=='/adjustments' else sales,adjustment=request.path=='/adjustments')

    @app.route('/sales/add',methods=['GET','POST'])
    @app.route('/sales/<int:rid>/edit',methods=['GET','POST'])
    @app.route('/adjustments/add',methods=['GET','POST'])
    @app.route('/adjustments/<int:rid>/edit',methods=['GET','POST'])
    def transaction_form(rid=None):
        adjustment=request.path.startswith('/adjustments'); table='adjustments' if adjustment else 'sales'
        with database() as d:
            old=d.execute(f'SELECT * FROM {table} WHERE id=?'+(' FOR UPDATE' if d.pg and request.method=='POST' else ''),(rid,)).fetchone() if rid else None
            if rid and (not old or old['voided']): abort(404)
            if request.method=='POST':
                d.execute('SAVEPOINT transaction_save')
                try:
                    qty=integer('quantity')
                    if request.form.get('product_id'):pid=integer('product_id')
                    else:
                        source=d.execute('SELECT product_id FROM stock WHERE id=?',(integer('stock_id'),)).fetchone()
                        if not source:raise ValueError('Product not found.')
                        pid=source['product_id']
                    for product_id in sorted(set([pid]+([old['product_id']] if old else []))):get_product(d,product_id,True)
                    if old:move(d,old['product_id'],old['quantity'],old['cost_total'],table+' edit reversal',rid,session['user'])
                    p=get_product(d,pid)
                    if qty>p['on_hand'] or p['archived']:raise ValueError('Not enough available stock for this product.')
                    if old and pid==old['product_id']:
                        cost=str(old['cost_snapshot']);total=str(number(Decimal(str(old['cost_total']))*qty/old['quantity']))
                    else:cost,total=issue_cost(p,qty)
                    sid=d.execute('SELECT id FROM stock WHERE product_id=? ORDER BY id LIMIT 1',(pid,)).fetchone()['id']
                    if adjustment:
                        kind=text('kind')
                        if kind not in ['giveaway','write-off']: raise ValueError('Choose giveaway or write-off.')
                        fields=['stock_id','quantity','kind','adjustment_date','expense','notes','cost_snapshot','cost_total','product_id']
                        values=[sid,qty,kind,day('adjustment_date'),amount('expense'),text('notes',True),cost,total,pid]
                    else:
                        fields=['stock_id','quantity','sale_date','show_name','buyer','sale_price','fees','shipping_paid','notes','cost_snapshot','category_snapshot','cost_total','product_id']
                        values=[sid,qty,day('sale_date'),text('show_name'),text('buyer'),amount('sale_price'),amount('fees'),amount('shipping_paid'),text('notes'),cost,old['category_snapshot'] if old and pid==old['product_id'] else p['category'],total,pid]
                    if rid:d.execute(f'UPDATE {table} SET '+','.join(f'{f}=?' for f in fields)+' WHERE id=?',values+[rid])
                    else:rid=d.execute(f'INSERT INTO {table} ('+','.join(fields)+',created_at) VALUES ('+','.join('?' for _ in range(len(fields)+1))+') RETURNING id',values+[NOW()]).fetchone()['id']
                    move(d,pid,-qty,-Decimal(total),table+' recorded',rid,session['user'])
                    audit(d,table+' saved',str(rid));flash('Transaction saved at its recorded average cost.')
                    return redirect('/'+table)
                except ValueError as e:
                    d.execute('ROLLBACK TO SAVEPOINT transaction_save');flash(str(e),'error')
            stocks=product_rows(d)
            initial={'product_id':request.args.get('product_id','')}
            if not initial['product_id'] and request.args.get('stock_id'):
                source=d.execute('SELECT product_id FROM stock WHERE id=?',(request.args['stock_id'],)).fetchone()
                if source:initial['product_id']=source['product_id']
        return render_template('product_transaction.html',row=request.form if request.method=='POST' else dict(old) if old else initial,stocks=stocks,adjustment=adjustment)

    @app.post('/<table>/<int:rid>/void')
    def void(table,rid):
        if table not in ['sales','adjustments']: abort(404)
        with database() as d:
            old=d.execute(f'SELECT * FROM {table} WHERE id=?'+(' FOR UPDATE' if d.pg else ''),(rid,)).fetchone()
            if not old: abort(404)
            get_product(d,old['product_id'],True)
            if not old['voided']:
                move(d,old['product_id'],old['quantity'],old['cost_total'],table+' void reversal',rid,session['user'])
                d.execute(f'UPDATE {table} SET voided=1 WHERE id=?',(rid,))
                audit(d,table+' voided',str(rid))
            flash('Voided; units and their recorded cost returned to inventory.')
        return redirect('/'+table)

    @app.route('/export/<table>')
    def export(table):
        if table not in ['stock','purchases','sales','adjustments','audit','stock_movements','price_history']: abort(404)
        if table=='audit' and not g.is_admin:abort(403)
        with database() as d:
            rows=product_rows(d) if table=='stock' else [dict(r) for r in d.execute(f'SELECT * FROM {"stock" if table=="purchases" else table} ORDER BY id')]
        out=io.StringIO(); w=csv.writer(out)
        def safe(v):
            v=str(v if v is not None else '')
            return "'"+v if v.startswith(('=','+','-','@','\t','\r')) else v
        if rows:
            w.writerow(rows[0].keys())
            for r in rows: w.writerow([safe(v) for v in r.values()])
        return Response(out.getvalue().encode('utf-8-sig'),mimetype='text/csv',headers={'Content-Disposition':f'attachment; filename=horus_{table}.csv'})

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    def error(e): return render_template('error.html',message=e.description),e.code

    @app.cli.command('create-user')
    @click.argument('username')
    @click.option('--admin',is_flag=True,help='Create or promote a trusted administrator.')
    @click.password_option(confirmation_prompt=True)
    def create_user(username,password,admin):
        try:password_valid(password)
        except ValueError as e:raise click.ClickException(str(e))
        with database() as d:
            lock_accounts(d)
            old=d.execute('SELECT * FROM users WHERE username=?',(username.strip(),)).fetchone()
            if old:
                d.execute('UPDATE users SET password_hash=?,role=?,disabled=0,auth_version=auth_version+1,must_change_password=0,failures=0,locked_until=0 WHERE username=?',(generate_password_hash(password),'admin' if admin else old['role'],username.strip()))
            else:
                try:username=add_user(d,username,password,'admin' if admin else 'staff',temporary=False)
                except ValueError as e:raise click.ClickException(str(e))
            audit(d,'CLI user created / reset',username)
        click.echo('User created / password reset.')

    @app.cli.command('promote-admin')
    @click.argument('username')
    def promote_admin(username):
        with database() as d:
            lock_accounts(d)
            if not d.execute('SELECT username FROM users WHERE username=?',(username,)).fetchone():raise click.ClickException('User not found. Create the account first.')
            d.execute("UPDATE users SET role='admin',disabled=0,auth_version=auth_version+1 WHERE username=?",(username,))
            audit(d,'CLI admin promoted',username)
        click.echo('Administrator enabled. Sign in again to use user management.')
    return app

if __name__=='__main__': create_app().run(host='127.0.0.1',debug=False)
