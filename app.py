import base64
from datetime import datetime, date
from decimal import Decimal
import random
from functools import wraps
import re
import feedparser
import io
import matplotlib
matplotlib.use("Agg")  # non-GUI backend
import matplotlib.pyplot as plt

# Our entire back end and DB stuff
from flask import Flask, render_template, request, redirect, url_for, session, abort, render_template_string, make_response, send_file, flash
from models import db, User, Ticker, Account, Order, Position, Trade, WatchlistItem, ScheduledTransaction

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev-insecure-key'  # fine for this project, normally would do some security stuff
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///paper.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

@app.before_request
def ensure_db():
    """Create tables on first request (simple dev setup)"""
    with app.app_context():
        db.create_all()

def current_user():
    """Get current User"""
    uid = session.get('user_id')
    if not uid:
        return None
    return User.query.get(uid)

def login_required(fn):
    """Login is requied to use this function, if not then send back to login page"""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user():
            return redirect(url_for('login'))
        return fn(*args, **kwargs)
    return wrapper

# -------- Auth --------

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    """Signup Functionality. Handles Both GET and POST. Allows user to make an account."""
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = (request.form.get('password') or '').strip()
        if not username or not password:
            return render_template('login.html', error='Enter username & password', mode='signup')
        if User.query.filter_by(username=username).first():
            return render_template('login.html', error='Username already taken', mode='signup')

        user = User(username=username)
        user.set_password(password) 
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
    """Login Functionality. Handles GET and POST. Allows user to login."""
    if request.method == 'POST':
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
    """Logout Functionality"""
    session.clear()
    return redirect(url_for('login'))

# -------- Ticker sync ------------------
def _tick_prices():
    """This is the random walk in the change of the ticker price.
       We use this because using the stock market would have been not so fun
       for grading purposes."""
    # Random walk and update DM
    for t in Ticker.query.all():
        drift = Decimal(random.randrange(-50, 51)) / Decimal('100')  # -0.50..+0.50
        t.price = max(Decimal('1.00'), (t.price + drift).quantize(Decimal('0.01')))
    db.session.commit()

    # IF LIMIT ORDER, CHECK IF WE CAN EXECUTE NOW
    open_orders = Order.query.filter_by(status="PENDING", order_type="LMT").all()
    for order in open_orders:
        ticker = Ticker.query.get(order.ticker_id)
        current_price = ticker.price

        if order.side == "BUY" and current_price <= order.limit_price:
            acct = Account.query.filter_by(user_id=order.user_id).first()
            execute_order(order, current_price, acct)

        elif order.side == "SELL" and current_price >= order.limit_price:
            acct = Account.query.filter_by(user_id=order.user_id).first()
            execute_order(order, current_price, acct)


@app.route('/dash_tick')
@login_required
def dash_tick():
    """Meant for synchronizing the price mnovement in the UI.
       may be used in other places too."""
    user = current_user()
    # move prices exactly once per tick
    _tick_prices()

    # render both fragments and send them OOB
    prices_html = render_template('_prices.html', 
                                  tickers=Ticker.query.order_by(Ticker.symbol).all())
    # reuse existing builder for watchlist content
    watchlist_html = watchlist_partial()  # returns the <table> HTML

    # wrap each with the correct target id + hx-swap-oob
    combined = f'''
      <div id="prices" hx-swap-oob="innerHTML">
        {prices_html}
      </div>
      <div id="watchlist" hx-swap-oob="innerHTML">
        {watchlist_html}
      </div>
    '''
    return combined

# -------- App pages / fragments --------

@app.route('/')
@login_required
def dashboard():
    """Our dashboard"""
    # seed demo tickers once
    if Ticker.query.count() == 0:
        tickers_list = [
            ('AAPL', 'Apple Inc.'),
            ('MSFT', 'Microsoft Corp.'),
            ('GOOG', 'Alphabet Inc.'),
            ('TSLA', 'Tesla Inc.'),
            ('AMZN', 'Amazon.com Inc.'),
            ('META', 'Meta Platforms Inc.'),
            ('NVDA', 'NVIDIA Corp.'),
            ('NFLX', 'Netflix Inc.'),
            ('AMD', 'Advanced Micro Devices'),
            ('INTC', 'Intel Corp.')
        ]
        for symbol, name in tickers_list:
            price = Decimal(random.randrange(80, 250))
            db.session.add(Ticker(symbol=symbol, name=name, price=price))
        db.session.commit()

    user = current_user()
    positions = Position.query.filter_by(user_id=user.id).join(Ticker).all()
    tickers = Ticker.query.order_by(Ticker.symbol).all()
    return render_template('dashboard.html', tickers=tickers, positions=positions)


@app.route('/search')
@login_required
def search_stocks():
    """Allows us to search for stocks"""
    query = request.args.get('q', '').strip().upper()
    if not query:
        return render_template('_search_results.html', tickers=[], query='')
    
    # Search by symbol or name
    tickers = Ticker.query.filter(
        (Ticker.symbol.like(f'%{query}%')) | 
        (Ticker.name.like(f'%{query}%'))
    ).order_by(Ticker.symbol).all()
    
    return render_template('_search_results.html', tickers=tickers, query=query)

@app.route('/positions')
@login_required
def positions_partial():
    """Gets our current positions"""
    user = current_user()
    positions = Position.query.filter_by(user_id=user.id).join(Ticker).all()
    return render_template('_positions.html', positions=positions)

@app.route('/open_orders')
@login_required
def open_orders_partial():
    """Gets our Open Orders"""
    user = current_user()
    orders = (
        Order.query
        .filter_by(user_id=user.id, status='PENDING')
        .order_by(Order.id.desc())
        .all()
    )
    return render_template('_open_orders.html', orders=orders)

@app.route('/reset', methods=['POST'])
@login_required
def reset_portfolio():
    '''Allows us to reset the portfolio to a default amount'''
    user = current_user()

    # Delete all positions and trades for the user
    Position.query.filter_by(user_id=user.id).delete()
    Trade.query.filter(Trade.order_id.in_(db.session.query(Order.id).filter_by(user_id=user.id))).delete()
    Order.query.filter_by(user_id=user.id).delete()


    #Reset account balance to 100000.0
    account = Account.query.filter_by(user_id=user.id).first()
    if account:
        account.cash = Decimal('100000.00')

    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/portfolio', methods=['GET', 'POST'])
@login_required
def portfolio():
    '''Gets our entire portfolio'''
    user = current_user()
    positions = (
        Position.query
        .filter_by(user_id=user.id)
        .join(Ticker)
        .all()
    )
    return render_template('portfolio.html', positions=positions)

@app.route('/order', methods=['POST'])
@login_required
def place_order():
    ''' places an order '''
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

    # Error not found
    if not symbol or qty <= 0 or side not in ('BUY', 'SELL') or order_type not in ('MKT', 'LMT'):
        abort(400)

    # Error not found
    ticker = Ticker.query.filter_by(symbol=symbol).first()
    if not ticker:
        abort(400)

    limit_price = None
    if order_type == 'LMT' and limit_price_raw:
        try:
            limit_price = Decimal(limit_price_raw)
        except Exception:
            # Error not found
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
    order_form_html = render_template('_order_form.html',
                                  tickers=Ticker.query.order_by(Ticker.symbol).all(),
                                  success=True)
    cash_html = render_template('_cash_balance_oob.html', user=user)
    return order_form_html + cash_html

def execute_order(order: Order, price: Decimal, account: Account) -> None:
    """Execute an Order that has been placed"""
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

        account.cash = (account.cash + proceeds).quantize(Decimal('0.01'))


    order.status = 'FILLED'
    db.session.commit()

@app.route('/transactions', methods=['GET', 'POST'])
@login_required
def transactions_partial():
    '''Get transactions'''
    user = current_user()
    trades = Trade.query.join(Order).filter(Order.user_id == user.id).order_by(Trade.id.desc()).all()
    return render_template('_transactions.html', trades=trades)


@app.route('/watchlist', methods=['GET', 'POST'])
@login_required
def watchlist():
    '''Get Watchlist'''
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

@app.route('/remove_watch', methods=['POST'])
@login_required
def remove_watch():
    symbol = (request.form.get('symbol') or '').strip().upper()
    item = WatchlistItem.query.filter_by(user_id=current_user().id, symbol=symbol).first()
    if item:
        db.session.delete(item)
        db.session.commit()
    return watchlist_partial()  # return only the table fragment


@app.route('/watchlist_partial')
@login_required
def watchlist_partial():
    user = current_user()
    items = WatchlistItem.query.filter_by(user_id=user.id).all()
    tickers = Ticker.query.all()
    tickers_map = {t.symbol: t for t in tickers}
    return render_template('_watchlist.html', items=items, tickers_map=tickers_map)


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

# news section, maybe refactor if we have time
# ----------------- Financial News -----------------

NEWS_FEEDS = [
    {
        "source": "MarketWatch",
        "url": "https://feeds.marketwatch.com/marketwatch/topstories/"
    }
]


def _strip_html(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"<.*?>", "", text)


def fetch_financial_news(per_feed_limit: int = 40):
    """Fetch and normalize financial news from multiple RSS feeds."""
    articles = []

    for feed in NEWS_FEEDS:
        parsed = feedparser.parse(feed["url"])
        for entry in parsed.entries[:per_feed_limit]:
            summary_raw = entry.get("summary") or entry.get("description") or ""
            summary_clean = _strip_html(summary_raw).strip()
            if len(summary_clean) > 260:
                summary_clean = summary_clean[:257] + "..."

            articles.append(
                {
                    "source": feed["source"],
                    "title": (entry.get("title") or "").strip(),
                    "summary": summary_clean,
                    "link": entry.get("link"),
                    "published": entry.get("published", ""),
                }
            )

    # NO slicing here – we return every article we got
    return articles

@app.route("/news")
@login_required
def news_page():
    user = current_user()
    return render_template("news.html", user=user)


@app.route("/news/tiles")
@login_required
def news_tiles():
    """Return ALL news articles on one page (no pagination)."""
    articles = fetch_financial_news(per_feed_limit=40)
    fetched_at = datetime.utcnow().strftime("%H:%M:%S UTC")

    html = render_template(
        "_news_tiles.html",
        articles=articles,
        fetched_at=fetched_at,
    )

    resp = make_response(html)
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp

@app.context_processor
def inject_user():
    return {"user": current_user()}

@app.route("/price_alerts")
@login_required
def price_alerts():
    user = current_user()

    PRICE_DELTA = 0.01  # min price change to trigger alert (e.g. $0.01)

    alerts = []
    items = WatchlistItem.query.filter_by(user_id=user.id).all()

    for item in items:
        # WatchlistItem stores symbol, not ticker_id
        ticker = Ticker.query.filter_by(symbol=item.symbol).first()
        if not ticker:
            continue

        current_price = float(ticker.price)
        last_notified = item.last_notified_price

        # First time OR significant change
        if last_notified is None or abs(current_price - last_notified) >= PRICE_DELTA:
            direction = None
            if last_notified is not None:
                direction = "up" if current_price > last_notified else "down"

            alerts.append({
                "symbol": ticker.symbol,
                "price": current_price,
                "direction": direction,
            })

            # Update so we don't alert again for the same price
            item.last_notified_price = current_price

    if alerts:
        db.session.commit()

    # alerts is a list: one entry per stock that moved
    return render_template("_price_alerts_oob.html", alerts=alerts)

@app.route("/watchlist/name", methods=["POST"])
@login_required
def update_watchlist_name():
    user = current_user()
    new_name = (request.form.get("name") or "").strip()

    if not new_name:
        new_name = "My Watchlist"

    # enforce max length
    new_name = new_name[:64]

    user.watchlist_name = new_name
    db.session.commit()

    # return just the header fragment
    return render_template("_watchlist_header.html", user=user)

def render_performance_chart_html(user):
    # Get all trades for this user in chronological order
    trades = (
        Trade.query
        .join(Order, Trade.order_id == Order.id)
        .filter(Order.user_id == user.id)
        .order_by(Trade.id)
        .all()
    )

    img_b64 = None

    if trades:
        START_EQUITY = float(Decimal("100000.00"))
        cash = START_EQUITY
        positions = {}  # ticker_id -> {"qty": int, "last_price": float}

        xs = []
        ys = []

        for idx, trade in enumerate(trades, start=1):
            order = trade.order
            ticker_id = order.ticker_id
            side = order.side  # "BUY" or "SELL"
            price = float(trade.price)
            qty = trade.qty

            if ticker_id not in positions:
                positions[ticker_id] = {"qty": 0, "last_price": price}

            if side == "BUY":
                cash -= price * qty
                positions[ticker_id]["qty"] += qty
            elif side == "SELL":
                cash += price * qty
                positions[ticker_id]["qty"] -= qty

            positions[ticker_id]["last_price"] = price

            equity = cash + sum(
                pos["qty"] * pos["last_price"] for pos in positions.values()
            )
            pnl = equity - START_EQUITY

            xs.append(idx)   # t = 1, 2, ...
            ys.append(pnl)

        # Build matplotlib figure into PNG in memory
        fig, ax = plt.subplots(figsize=(6, 3))
        ax.plot(xs, ys, marker="o", linewidth=1.5)
        ax.axhline(0, linewidth=0.8)
        ax.set_title("Portfolio PnL vs Trades")
        ax.set_xlabel("Trade # (t)")
        ax.set_ylabel("PnL ($)")
        fig.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        plt.close(fig)
        buf.seek(0)

        img_b64 = base64.b64encode(buf.read()).decode("ascii")

    # Render HTML fragment (this is the template render you were expecting)
    return render_template("_performance_chart_wrapper.html", img_b64=img_b64)


@app.route("/performance_chart.png")
@login_required
def performance_chart_png():
    user = current_user()
    # This returns HTML, not raw PNG – by design
    return render_performance_chart_html(user)

@app.route("/account")
@login_required
def account_page():
    user = current_user()

    # This makes sure anything with date <= today has occurred
    process_due_scheduled_transactions(user.id)

    account = Account.query.filter_by(user_id=user.id).first()

    upcoming = (
        ScheduledTransaction.query
        .filter_by(user_id=user.id, status="PENDING")
        .order_by(ScheduledTransaction.scheduled_date.asc())
        .all()
    )

    processed = (
        ScheduledTransaction.query
        .filter_by(user_id=user.id, status="PROCESSED")
        .order_by(ScheduledTransaction.processed_at.desc())
        .limit(10)
        .all()
    )

    return render_template(
        "account.html",
        user=user,
        account=account,
        upcoming=upcoming,
        processed=processed,
    )

def process_due_scheduled_transactions(user_id: int) -> None:
    """Apply all PENDING scheduled transactions for this user
    whose scheduled_date is today or earlier.
    """
    today = date.today()

    # Get user's account
    account = Account.query.filter_by(user_id=user_id).first()
    if not account:
        return

    txns = (
        ScheduledTransaction.query
        .filter_by(user_id=user_id, status="PENDING")
        .filter(ScheduledTransaction.scheduled_date <= today)
        .all()
    )

    for tx in txns:
        amt = Decimal(tx.amount)

        if tx.tx_type == "DEPOSIT":
            account.cash = account.cash + amt
        elif tx.tx_type == "WITHDRAW":
            account.cash = account.cash - amt

        tx.status = "PROCESSED"
        tx.processed_at = today

    if txns:
        db.session.commit()

@app.route("/schedule-transaction", methods=["POST"])
@login_required
def schedule_transaction():
    user = current_user()

    tx_type = request.form.get("tx_type", "").strip().upper()
    amount_raw = request.form.get("amount", "").strip()
    date_raw = request.form.get("scheduled_date", "").strip()

    if tx_type not in ("DEPOSIT", "WITHDRAW"):
        flash("Invalid transaction type", "error")
        return redirect(url_for("dashboard"))

    try:
        amount = Decimal(amount_raw)
        assert amount > 0
    except Exception:
        flash("Invalid amount", "error")
        return redirect(url_for("dashboard"))

    try:
        year, month, day = map(int, date_raw.split("-"))
        sched_date = date(year, month, day)
    except Exception:
        flash("Invalid date", "error")
        return redirect(url_for("dashboard"))

    # Create scheduled transaction
    tx = ScheduledTransaction(
        user_id=user.id,
        tx_type=tx_type,
        amount=amount,
        scheduled_date=sched_date,
        status="PENDING",
    )
    db.session.add(tx)
    db.session.commit()

    flash("Scheduled transaction created.", "success")
    return redirect(url_for("dashboard"))

@app.before_request
def apply_scheduled_for_logged_in_user():
    user = current_user()
    if user is None:
        return  # no one logged in, nothing to do
    process_due_scheduled_transactions(current_user().id)


START_EQUITY = Decimal("100000.00")

def compute_user_pnl(user: User) -> Decimal:
    """Compute current PnL for a user based on cash + marked-to-market positions."""
    account = Account.query.filter_by(user_id=user.id).first()
    if not account:
        return Decimal("0.00")

    equity = Decimal(account.cash or 0)

    positions = Position.query.filter_by(user_id=user.id).all()
    for pos in positions:
        if pos.qty == 0:
            continue
        ticker = pos.ticker  # relationship is already on Position
        if not ticker or ticker.price is None:
            continue
        equity += Decimal(pos.qty) * Decimal(ticker.price)

    return equity - START_EQUITY

@app.route("/leaderboard")
@login_required
def leaderboard():
    users = User.query.all()

    rows = []
    for u in users:
        pnl = compute_user_pnl(u)
        rows.append((u, pnl))

    # sort by PnL descending
    rows.sort(key=lambda tup: tup[1], reverse=True)

    leaderboard_rows = []
    current = current_user()
    for rank, (u, pnl) in enumerate(rows, start=1):
        leaderboard_rows.append({
            "rank": rank,
            "username": u.username,
            "pnl": pnl,
            "is_current": (current is not None and u.id == current.id),
        })

    return render_template("leaderboard.html", leaderboard=leaderboard_rows)

if __name__ == '__main__':
    app.run(debug=True)

