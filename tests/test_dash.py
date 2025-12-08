from models import Ticker

def test_dashboard_seeds_tickers(client, auth_user):
    r = client.get("/")
    assert r.status_code == 200

    assert Ticker.query.count() == 10  # your seeded list length

    symbols = {t.symbol for t in Ticker.query.all()}
    assert "AAPL" in symbols
    assert "MSFT" in symbols
