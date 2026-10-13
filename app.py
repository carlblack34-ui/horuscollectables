import csv
import io
import os
import secrets
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
import click
from flask import Flask, abort, flash, redirect, render_template, request, session, url_for, Response
from werkzeug.security import check_password_hash, generate_password_hash
from db import Database, migrate
from pokemon_sets import POKEMON_SETS, CATEGORY_OPTIONS, CONDITION_OPTIONS
from catalog import load as load_catalogue, PRODUCTS, GAME_PRODUCTS

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
    app.jinja_env.filters['money'] = lambda v: f'${Decimal(str(v or 0)):,.2f}'

    def audit(d, action, details):
        d.execute('INSERT INTO audit(username,action,details,created_at) VALUES (?,?,?,?)', (session.get('user','CLI'), action, details, NOW()))
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
    def stock_rows(d):
        return [dict(r) for r in d.execute('''SELECT s.*,
          COALESCE((SELECT SUM(quantity) FROM sales WHERE stock_id=s.id AND voided=0),0) AS sold,
          COALESCE((SELECT SUM(quantity) FROM adjustments WHERE stock_id=s.id AND voided=0),0) AS removed
          FROM stock s ORDER BY id DESC''')]
    def enrich(rows):
        for r in rows:
            r['remaining'] = r['quantity']-r['sold']-r['removed']
            r['landed'] = sum(Decimal(str(r[k])) for k in ['unit_cost','shipping_cost','grading_cost','supplies_cost'])
        return rows
    def lock(d, sid):
        r = d.execute('SELECT id FROM stock WHERE id=?'+(' FOR UPDATE' if d.pg else ''),(sid,)).fetchone()
        if not r: abort(404)
    def remaining(d, sid, exclude=None, adjustment=False):
        r = next(r for r in enrich(stock_rows(d)) if r['id']==sid)
        if exclude:
            table = 'adjustments' if adjustment else 'sales'
            old = d.execute(f'SELECT * FROM {table} WHERE id=?',(exclude,)).fetchone()
            if old and old['stock_id']==sid and not old['voided']: r['remaining'] += old['quantity']
        return r

    @app.before_request
    def protect():
        session.setdefault('csrf',secrets.token_hex(32))
        if request.method == 'POST' and not secrets.compare_digest(session['csrf'], request.form.get('csrf','')):
            abort(400, 'Form expired. Reload the page and try again.')
        if request.endpoint not in ('login','static','health'):
            if not session.get('user'): return redirect(url_for('login'))
            with database() as d:
                if not d.execute('SELECT username FROM users WHERE username=?',(session['user'],)).fetchone():
                    session.clear(); return redirect(url_for('login'))

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
                if u and time.time()>=float(u['locked_until']) and valid:
                    d.execute('UPDATE users SET failures=0,locked_until=0 WHERE username=?',(username,))
                    session.clear(); session.update(user=username, csrf=secrets.token_hex(32)); session.permanent=True
                    audit(d,'login',username)
                    return redirect(url_for('dashboard'))
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
                u=d.execute('SELECT * FROM users WHERE username=?',(session['user'],)).fetchone()
                new=request.form.get('new_password','')
                if not check_password_hash(u['password_hash'],request.form.get('current_password','')) or len(new)<12:
                    flash('Current password must match; new password needs at least 12 characters.','error')
                else:
                    d.execute('UPDATE users SET password_hash=? WHERE username=?',(generate_password_hash(new),session['user']))
                    audit(d,'password changed',session['user']); flash('Password updated.')
                    return redirect(url_for('dashboard'))
        return render_template('password.html')

    def ledger(d):
        sales=[dict(r) for r in d.execute('SELECT sa.*,s.name FROM sales sa JOIN stock s ON s.id=sa.stock_id ORDER BY sale_date DESC,sa.id DESC')]
        adjustments=[dict(r) for r in d.execute('SELECT a.*,s.name FROM adjustments a JOIN stock s ON s.id=a.stock_id ORDER BY adjustment_date DESC,a.id DESC')]
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
            r['cost']=Decimal(str(r['cost_snapshot']))*r['quantity']; r['profit']=r['net']-r['cost']
        for r in adjustments: r['loss']=Decimal(str(r['cost_snapshot']))*r['quantity']+Decimal(str(r['expense']))
        return sales,adjustments

    @app.route('/')
    @app.route('/reports')
    def dashboard():
        with database() as d:
            stocks=enrich(stock_rows(d)); sales,adjustments=ledger(d)
        active=[r for r in sales if not r['voided']]; losses=[r for r in adjustments if not r['voided']]
        total=lambda key: sum((r[key] if isinstance(r[key],Decimal) else Decimal(str(r[key]))) for r in active)
        gross=total('sale_price'); net=total('net'); costs=total('cost'); loss=sum(r['loss'] for r in losses)
        groups={}
        for r in active:
            key=(r['category_snapshot'] or 'Uncategorised',r['show_name'] or 'No show')
            if key not in groups: groups[key]={'gross':Decimal(0),'profit':Decimal(0),'qty':0}
            groups[key]['gross']+=Decimal(str(r['sale_price'])); groups[key]['profit']+=r['profit']; groups[key]['qty']+=r['quantity']
        return render_template('dashboard.html' if request.path=='/reports' else 'overview.html', stocks=stocks,sales=active,groups=groups,gross=gross,net=net,costs=costs,loss=loss,profit=net-costs-loss,
          value=sum(r['remaining']*r['landed'] for r in stocks),units=sum(r['remaining'] for r in stocks),margin=(net-costs-loss)/net*100 if net else 0)

    @app.route('/stock')
    def stock():
        with database() as d:
            rows=enrich(stock_rows(d)); games=list(load_catalogue(d))
        q=request.args.get('q','').lower(); kind=request.args.get('type',''); game=request.args.get('tcg','')
        rows=[r for r in rows if q in (r['name']+' '+r['sku']+' '+(r['set_name'] or '')+' '+r['tcg']+' '+r['era']).lower() and (not kind or r['product_type']==kind) and (not game or r['tcg']==game)]
        return render_template('inventory.html',rows=rows,types=TYPES,games=games)

    @app.route('/stock/add',methods=['GET','POST'])
    @app.route('/stock/<int:rid>/edit',methods=['GET','POST'])
    def stock_form(rid=None):
        with database() as d:
            old=d.execute('SELECT * FROM stock WHERE id=?',(rid,)).fetchone() if rid else None
            if rid and not old: abort(404)
            if request.method=='POST':
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
                    if rid:
                        lock(d,rid); r=remaining(d,rid)
                        if values[4]<r['sold']+r['removed']: raise ValueError('Purchased quantity cannot be lower than units already sold or removed.')
                        d.execute('UPDATE stock SET '+','.join(f'{f}=?' for f in fields)+' WHERE id=?',values+[rid])
                    else:
                        d.execute('INSERT INTO stock ('+','.join(fields)+',created_at) VALUES ('+','.join('?' for _ in range(len(fields)+1))+')',values+[NOW()])
                    audit(d,'stock edited' if rid else 'purchase added',str(rid or values[0])); flash('Stock saved. Historical transaction costs are unchanged.')
                    return redirect(url_for('stock'))
                except ValueError as e: flash(str(e),'error')
            catalogue=load_catalogue(d)
        return render_template('purchase.html',row=request.form if request.method=='POST' else dict(old) if old else {},types=TYPES,sets=POKEMON_SETS,categories=CATEGORY_OPTIONS,conditions=CONDITION_OPTIONS,catalogue=catalogue,products=PRODUCTS,game_products=GAME_PRODUCTS)

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
            lock(d,rid); r=remaining(d,rid)
            if r['remaining']: abort(400,'Only empty lots can be archived.')
            d.execute('UPDATE stock SET archived=1 WHERE id=?',(rid,)); audit(d,'stock archived',str(rid))
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
                try:
                    sid=integer('stock_id'); qty=integer('quantity')
                    for stock_id in sorted(set([sid]+([old['stock_id']] if old else []))): lock(d,stock_id)
                    r=remaining(d,sid,rid,adjustment)
                    if qty>r['remaining'] or r['archived']: raise ValueError('Not enough available stock in this lot.')
                    cost=str(old['cost_snapshot']) if old and sid==old['stock_id'] else str(r['landed'])
                    if adjustment:
                        kind=text('kind')
                        if kind not in ['giveaway','write-off']: raise ValueError('Choose giveaway or write-off.')
                        fields=['stock_id','quantity','kind','adjustment_date','expense','notes','cost_snapshot']
                        values=[sid,qty,kind,day('adjustment_date'),amount('expense'),text('notes',True),cost]
                    else:
                        fields=['stock_id','quantity','sale_date','show_name','buyer','sale_price','fees','shipping_paid','notes','cost_snapshot','category_snapshot']
                        values=[sid,qty,day('sale_date'),text('show_name'),text('buyer'),amount('sale_price'),amount('fees'),amount('shipping_paid'),text('notes'),cost, old['category_snapshot'] if old and sid==old['stock_id'] else r['category']]
                    if rid: d.execute(f'UPDATE {table} SET '+','.join(f'{f}=?' for f in fields)+' WHERE id=?',values+[rid])
                    else: d.execute(f'INSERT INTO {table} ('+','.join(fields)+',created_at) VALUES ('+','.join('?' for _ in range(len(fields)+1))+')',values+[NOW()])
                    audit(d,table+' saved',str(rid or sid)); flash('Transaction saved.')
                    return redirect('/'+table)
                except ValueError as e: flash(str(e),'error')
            stocks=enrich(stock_rows(d))
        return render_template('transaction_form.html',row=request.form if request.method=='POST' else dict(old) if old else {'stock_id':request.args.get('stock_id','')},stocks=stocks,adjustment=adjustment)

    @app.post('/<table>/<int:rid>/void')
    def void(table,rid):
        if table not in ['sales','adjustments']: abort(404)
        with database() as d:
            old=d.execute(f'SELECT * FROM {table} WHERE id=?'+(' FOR UPDATE' if d.pg else ''),(rid,)).fetchone()
            if not old: abort(404)
            lock(d,old['stock_id'])
            d.execute(f'UPDATE {table} SET voided=1 WHERE id=?',(rid,))
            d.execute('UPDATE stock SET archived=0 WHERE id=?',(old['stock_id'],))
            audit(d,table+' voided',str(rid)); flash('Voided; units returned to inventory.')
        return redirect('/'+table)

    @app.route('/export/<table>')
    def export(table):
        if table not in ['stock','sales','adjustments','audit']: abort(404)
        with database() as d:
            rows=enrich(stock_rows(d)) if table=='stock' else [dict(r) for r in d.execute(f'SELECT * FROM {table} ORDER BY '+('id' if table!='users' else 'username'))]
        out=io.StringIO(); w=csv.writer(out)
        def safe(v):
            v=str(v if v is not None else '')
            return "'"+v if v.startswith(('=','+','-','@','\t','\r')) else v
        if rows:
            w.writerow(rows[0].keys())
            for r in rows: w.writerow([safe(v) for v in r.values()])
        return Response(out.getvalue().encode('utf-8-sig'),mimetype='text/csv',headers={'Content-Disposition':f'attachment; filename=horus_{table}.csv'})

    @app.errorhandler(400)
    @app.errorhandler(404)
    def error(e): return render_template('error.html',message=e.description),e.code

    @app.cli.command('create-user')
    @click.argument('username')
    @click.password_option(confirmation_prompt=True)
    def create_user(username,password):
        if not username.strip() or len(password)<12: raise click.ClickException('Username required; password needs at least 12 characters.')
        with database() as d:
            d.execute('INSERT INTO users(username,password_hash) VALUES (?,?) ON CONFLICT(username) DO UPDATE SET password_hash=excluded.password_hash,failures=0,locked_until=0',(username.strip(),generate_password_hash(password)))
        click.echo('User created / password reset.')
    return app

if __name__=='__main__': create_app().run(host='127.0.0.1',debug=False)
