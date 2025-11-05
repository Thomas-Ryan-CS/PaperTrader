from datetime import datetime
from decimal import Decimal
import random
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, abort, render_template_string
from models import db, User, Ticker, Account, Order, Position, Trade, WatchlistItem

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev-insecure-key'  # demo only; change in real use
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///paper.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# Create tables on first request (simple dev setup)
@app.before_request
def ensure_db():
    with app.app_context():
        db.create_all()

def current_user():
    uid = session.get('user_id')
    if not uid:
        return None
    return User.query.get(uid)

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user():
            return redirect(url_for('login'))
        return fn(*args, **kwargs)
    return wrapper

# -------- Auth --------

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = (request.form.get('password') or '').strip()
        if not username or not password:
            return render_template('login.html', error='Enter username & password', mode='signup')
        if User.query.filter_by(username=username).first():
            return render_template('login.html', error='Username already taken', mode='signup')

        user = User(username=username)
        user.set_password(password)  # stores salted hash
        db.session.add(user)
        db.session.commit()

        # starting cash
        db.session.add(Account(user_id=user.id, cash=Decimal('100000.00')))
        db.session.commit()

        session['user_id'] = user.id
        return redirect(url_for('dashboard'))

    return render_template('login.html', mode='signup')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':  # <-- fixed
        username = (request.form.get('username') or '').strip()
        password = (request.form.get('password') or '').strip()
        if not username or not password:
            return render_template('login.html', error='Enter username & password')

        user = User.query.filter_by(username=username).first()
        if not user or not user.check_password(password):
            return render_template('login.html', error='Invalid credentials')

        session['user_id'] = user.id
        return redirect(url_for('dashboard'))

    # GET
    return render_template('login.html', mode='login')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# -------- App pages / fragments --------

@app.route('/')
@login_required
def dashboard():
    # seed demo tickers once
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
    # random walk each poll
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
#
#Added RESET
@app.route('/reset', methods=['POST'])
@login_required
def reset_portfolio():
    user = current_user()

    # Delete all positions and trades for the user
    Position.query.filter_by(user_id=user.id).delete()
    Trade.query.filter(Trade.order_id.in_(db.session.query(Order.id).filter_by(user_id=user.id))).delete()
    Order.query.filter_by(user_id=user.id).delete()


    #Reset account balance to 0
    account = Account.query.filter_by(user_id=user.id).first()
    if account:
        account.cash = Decimal('0.00')

    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/order', methods=['POST'])
@login_required
def place_order():
    user = current_user()
    side = request.form.get('side')
    order_type = request.form.get('order_type')
    symbol = request.form.get('symbol')
    qty_raw = request.form.get('qty')
    limit_price_raw = request.form.get('limit_price')

    # basic validation
    try:
      qty = int(qty_raw or 0)
    except ValueError:
      qty = 0

    if not symbol or qty <= 0 or side not in ('BUY', 'SELL') or order_type not in ('MKT', 'LMT'):
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

    order = Order(
        user_id=user.id,
        ticker_id=ticker.id,
        side=side,
        order_type=order_type,
        qty=qty,
        status='PENDING',
        limit_price=limit_price
    )
    db.session.add(order)
    db.session.commit()

    # with_for_update is a no-op on SQLite (fine for demo)
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
        execute_order(order, price, acct)

    # return a fresh form fragment
    return render_template('_order_form.html')

def execute_order(order: Order, price: Decimal, account: Account) -> None:
    # record trade
    db.session.add(Trade(order_id=order.id, price=price, qty=order.qty))

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
    else:  # SELL (no shorting)
        sell_qty = min(pos.qty, order.qty)  # can't sell more than you hold
        proceeds = (price * sell_qty).quantize(Decimal('0.01'))

        new_qty = pos.qty - sell_qty
        if new_qty <= 0:
            # remove the row so it won't show up in the positions list
            db.session.delete(pos)
        else:
            pos.qty = new_qty
            # avg price unchanged when partially selling
            # if you wanted FIFO/LIFO, you'd compute differently

        account.cash = (account.cash + proceeds).quantize(Decimal('0.01'))


    order.status = 'FILLED'
    db.session.commit()

@app.route('/watchlist', methods=['GET', 'POST'])
@login_required
def watchlist():
    user = current_user()

    if request.method == 'POST':
        symbol = (request.form.get('symbol') or '').strip().upper()
        if symbol:
            alreadyWatched = WatchlistItem.query.filter_by(user_id=user.id, symbol=symbol).first()
            if not alreadyWatched:
                newWatched = WatchlistItem(user_id=user.id, symbol=symbol)
                db.session.add(newWatched)
                db.session.commit()
        if request.headers.get('HX-Request'):
            return watchlist_partial()

    items = WatchlistItem.query.filter_by(user_id=user.id).all()
    prices = {}
    for item in items:
        ticker = Ticker.query.filter_by(symbol=item.symbol).first()
        if ticker:
            prices[item.symbol] = ticker.price
        else:
            prices[item.symbol] = 'N/A'

    return render_template('watchlist.html', user=user, items=items, prices=prices)

@app.route('/remove_watch/<symbol>')
@login_required
def remove_watch(symbol):
    user = current_user()
    item = WatchlistItem.query.filter_by(user_id=user.id, symbol=symbol).first()

    if item:
        db.session.delete(item)
        db.session.commit()

    return redirect(url_for('watchlist'))

@app.route('/watchlist_partial')
@login_required
def watchlist_partial():
    user = current_user()
    watchlist_items = WatchlistItem.query.filter_by(user_id=user.id).all()

    if not watchlist_items:
        return '<p>Your watchlist is empty.</p>'

    rows = []
    for item in watchlist_items:
        ticker = Ticker.query.filter_by(symbol=item.symbol).first()
        price = ticker.price if ticker else 'N/A'
        rows.append(f'<tr><td>{item.symbol}</td><td>{price}</td></tr>')

    html = f"""
    <table border="1" style="margin-top: 1em;">
      <tr><th>Symbol</th><th>Price</th></tr>
      {''.join(rows)}
    </table>
    """
    return html

@app.route('/add_watchlist_item', methods=['POST'])
@login_required
def add_watchlist_item():
    user = current_user()
    symbol = (request.form.get('symbol') or '').strip().upper()

    if symbol:
        exists = WatchlistItem.query.filter_by(user_id=user.id, symbol=symbol).first()
        if not exists:
            db.session.add(WatchlistItem(user_id=user.id, symbol=symbol))
            db.session.commit()

    return watchlist_partial()


if __name__ == '__main__':
    app.run(debug=True)
