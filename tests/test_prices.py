from models import Ticker
from decimal import Decimal

def test_prices_endpoint_updates_prices(client, auth_user):
    client.get("/")  # seed tickers

    before = {t.symbol: t.price for t in Ticker.query.all()}
    r = client.get("/prices")
    assert r.status_code == 200

    after = {t.symbol: t.price for t in Ticker.query.all()}

    # ensure at least one price changed
    assert any(before[s] != after[s] for s in before)
