# tests/test_orders.py
from decimal import Decimal

from app import app, db
from models import Ticker, Account, Order, Position, Trade


def test_market_buy_order_fills_and_updates_position(client, auth_user):
    # auth_user is user_id (int)
    with app.app_context():
        ticker = Ticker(symbol="AAPL", price=Decimal("100.00"))
        db.session.add(ticker)
        db.session.commit()

    # place market buy
    r = client.post("/order", data={
        "side": "BUY",
        "order_type": "MKT",
        "symbol": "AAPL",
        "qty": "10",
    })
    assert r.status_code == 200

    with app.app_context():
        pos = Position.query.filter_by(user_id=auth_user).first()
        assert pos is not None
        assert pos.qty == 10
        assert float(pos.avg_price) == 100.00

        acct = Account.query.filter_by(user_id=auth_user).first()
        assert acct is not None
        assert float(acct.cash) == 100000 - 100 * 10

        order = Order.query.first()
        assert order.status == "FILLED"

        assert Trade.query.count() == 1


def test_insufficient_cash_cancels_buy(client, auth_user):
    # Very expensive ticker so we can't afford it
    with app.app_context():
        ticker = Ticker(symbol="GOOG", price=Decimal("250000.00"))
        db.session.add(ticker)
        db.session.commit()

    client.post("/order", data={
        "side": "BUY",
        "order_type": "MKT",
        "symbol": "GOOG",
        "qty": "1",
    })

    with app.app_context():
        order = Order.query.first()
        assert order is not None
        assert order.status == "CANCELLED"

        # Your current app *does* leave a Position row with qty = 0
        pos = Position.query.first()
        assert pos is not None
        assert pos.qty == 0

        acct = Account.query.filter_by(user_id=auth_user).first()
        assert float(acct.cash) == 100000.00


def test_sell_reduces_position_and_deletes_if_zero(client, auth_user):
    with app.app_context():
        ticker = Ticker(symbol="AAPL", price=Decimal("50.00"))
        db.session.add(ticker)
        db.session.commit()

    # buy 10
    client.post("/order", data={
        "side": "BUY",
        "order_type": "MKT",
        "symbol": "AAPL",
        "qty": "10",
    })

    # sell 10
    client.post("/order", data={
        "side": "SELL",
        "order_type": "MKT",
        "symbol": "AAPL",
        "qty": "10",
    })

    with app.app_context():
        # app deletes Position row when quantity hits zero
        assert Position.query.count() == 0


def test_limit_buy_only_fills_when_price_meets_condition(client, auth_user):
    with app.app_context():
        ticker = Ticker(symbol="AAPL", price=Decimal("150.00"))
        db.session.add(ticker)
        db.session.commit()

    # 1) Post LMT buy at 140 while price is 150 -> should NOT fill
    client.post("/order", data={
        "side": "BUY",
        "order_type": "LMT",
        "symbol": "AAPL",
        "qty": "10",
        "limit_price": "140",
    })

    with app.app_context():
        first_order = Order.query.order_by(Order.id.asc()).first()
        assert first_order is not None
        assert first_order.status == "PENDING"
        assert Position.query.count() == 0

    # 2) Drop price to 120
    with app.app_context():
        ticker = Ticker.query.filter_by(symbol="AAPL").first()
        ticker.price = Decimal("120.00")
        db.session.commit()

    # 3) Post another LMT buy at 140 with price now 120 -> should FILL
    client.post("/order", data={
        "side": "BUY",
        "order_type": "LMT",
        "symbol": "AAPL",
        "qty": "10",
        "limit_price": "140",  # make sure this is present
    })

    with app.app_context():
        last_order = Order.query.order_by(Order.id.desc()).first()
        assert last_order is not None
        assert last_order.status == "FILLED"

        pos = Position.query.filter_by(user_id=auth_user).first()
        assert pos is not None
        assert pos.qty == 10
        assert float(pos.avg_price) == 120.00
