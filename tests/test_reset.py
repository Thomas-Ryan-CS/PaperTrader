from decimal import Decimal
from models import Position, Order, Trade, Account, Ticker

def test_reset_clears_orders_positions_and_restores_cash(client, auth_user):
    with client.application.app_context():
        from app import db
        db.session.add(Ticker(symbol="AAPL", price=Decimal("100")))
        db.session.commit()

    # buy something
    client.post("/order", data={
        "side": "BUY",
        "order_type": "MKT",
        "symbol": "AAPL",
        "qty": "5"
    })

    assert Position.query.count() == 1
    assert Order.query.count() == 1
    assert Trade.query.count() == 1

    client.post("/reset")

    assert Position.query.count() == 0
    assert Order.query.count() == 0
    assert Trade.query.count() == 0

    acc = Account.query.first()
    assert float(acc.cash) == 100000.00
