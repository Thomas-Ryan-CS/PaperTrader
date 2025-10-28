from datetime import datetime
from decimal import Decimal
import random
from flask import Flask, render_template, request, redirect, url_for, session, abort
from models import db, User, Ticker, Account, Order, Position, Trade

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev-insecure-key'  # demo only
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///paper.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# create tables on first request
@app.before_request
def ensure_db():
    with app.app_context():
        db.create_all()

def current_user():
    username = session.get('username')
    if not username:
        return None
    return User.query.filter_by(username=username).first()

def login_required(fn):
    def wrapper(*args, **kwargs):
        if not current_user():
            return redirect(url_for('login'))
        return fn(*args, **kwargs)
    wrapper.__name__ = fn.__name__
    return wrapper

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        if not username:
            return render_template('login.html', error='Enter a username')
        user = User.query.filter_by(username=username).first()
        if not user:
            user = User(username=username)
            db.session.add(user)
            db.session.commit()
            acct = Account(user_id=user.id, cash=Decimal('100000.00'))
            db.session.add(acct)
            db.session.commit()
        session['username'] = user.username
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def dashboard():
    # seed demo tickers
    if Ticker.query.count() == 0:
        for sym in ['AAPL', 'MSFT', 'GOOG', 'TSLA']:
            price = Decimal(random.randrange(80, 250))
            db.session.add(Ticker(symbol=sym, price=price))
        db.session.commit()

    user = current_user()
    positions = Position.query.filter_by(user_id=user.id).join(Ticker).all()
    tickers = Ticker.query.order_by(Ticker.symbol).all()
    return render_template('dashboard.html', tickers=tickers, positions=positions)

@app.route('/prices')
@login_required
def prices_partial():
    # random walk prices each poll
    for t in Ticker.query.all():
        drift = Decimal(random.randrange(-50, 51)) / Decimal('100')  # -0.50..+0.50
        t.price = max(Decimal('1.00'), (t.price + drift).quantize(Decimal('0.01')))
    db.session.commit()
    tickers = Ticker.query.order_by(Ticker.symbol).all()
    return render_template('_prices.html', tickers=tickers)

@app.route('/positions')
@login_required
def positions_partial():
    user = current_user()
    positions = Position.query.filter_by(user_id=user.id).join(Ticker).all()
    return render_template('_positions.html', positions=positions)

@app.route('/order', methods=['POST'])
@login_required
def place_order():
    user = current_user()
    side = request.form.get('side')
    order_type = request.form.get('order_type')
    symbol = request.form.get('symbol')
    qty = int(request.form.get('qty') or 0)
    limit_price_raw = request.form.get('limit_price')

    if not symbol or qty <= 0 or side not in ('BUY', 'SELL') or order_type not in ('MKT','LMT'):
        abort(400)

    ticker = Ticker.query.filter_by(symbol=symbol).first()
    if not ticker:
        abort(400)

    limit_price = None
    if order_type == 'LMT' and limit_price_raw:
        try:
            limit_price = Decimal(limit_price_raw)
        except Exception:
            abort(400)

    order = Order(user_id=user.id, ticker_id=ticker.id, side=side, order_type=order_type, qty=qty, status='PENDING', limit_price=limit_price)
    db.session.add(order)
    db.session.commit()

    acct = Account.query.filter_by(user_id=user.id).with_for_update().first()
    price = ticker.price
    should_fill = False
    if order_type == 'MKT':
        should_fill = True
    elif order_type == 'LMT' and limit_price is not None:
        if side == 'BUY' and price <= limit_price:
            should_fill = True
        if side == 'SELL' and price >= limit_price:
            should_fill = True

    if should_fill:
        execute_order(db, order, price, acct)

    positions = Position.query.filter_by(user_id=user.id).join(Ticker).all()
    return render_template('_order_form.html')  # re-render clean form

def execute_order(db, order, price, account):
    # record trade
    trade = Trade(order_id=order.id, price=price, qty=order.qty)
    db.session.add(trade)

    pos = Position.query.filter_by(user_id=order.user_id, ticker_id=order.ticker_id).first()
    if not pos:
        pos = Position(user_id=order.user_id, ticker_id=order.ticker_id, qty=0, avg_price=Decimal('0'))
        db.session.add(pos)

    if order.side == 'BUY':
        cost = (price * order.qty).quantize(Decimal('0.01'))
        if account.cash < cost:
            order.status = 'CANCELLED'
            db.session.commit()
            return
        new_qty = pos.qty + order.qty
        if new_qty <= 0:
            pos.qty = 0
            pos.avg_price = Decimal('0.00')
        else:
            pos.avg_price = ((Decimal(pos.qty) * pos.avg_price) + (Decimal(order.qty) * price)) / Decimal(new_qty)
            pos.qty = new_qty
        account.cash = (account.cash - cost).quantize(Decimal('0.01'))
    else:  # SELL
        proceeds = (price * order.qty).quantize(Decimal('0.01'))
        pos.qty = max(0, pos.qty - order.qty)  # no shorting
        if pos.qty == 0:
            pos.avg_price = Decimal('0.00')
        account.cash = (account.cash + proceeds).quantize(Decimal('0.01'))

    order.status = 'FILLED'
    db.session.commit()

if __name__ == '__main__':
    app.run(debug=True)
