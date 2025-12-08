# tests/test_watchlist.py
from decimal import Decimal

from app import app, db
from models import WatchlistItem, Ticker


def test_add_to_watchlist(client, auth_user):
    with app.app_context():
        ticker = Ticker(symbol="AAPL", price=Decimal("100.00"))
        db.session.add(ticker)
        db.session.commit()

    r = client.post("/watchlist", data={"symbol": "AAPL"})
    assert r.status_code == 200
    assert b"AAPL" in r.data

    with app.app_context():
        item = WatchlistItem.query.first()
        assert item is not None
        assert item.symbol == "AAPL"
        assert item.user_id == auth_user


def test_remove_watchlist_item(client, auth_user):
    with app.app_context():
        ticker = Ticker(symbol="AAPL", price=Decimal("100.00"))
        db.session.add(ticker)
        db.session.add(WatchlistItem(user_id=auth_user, symbol="AAPL"))
        db.session.commit()

    r = client.post("/remove_watch", data={"symbol": "AAPL"})
    assert r.status_code == 200

    with app.app_context():
        assert WatchlistItem.query.count() == 0
