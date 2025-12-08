from models import User

def test_signup_creates_user_and_account(client):
    r = client.post("/signup", data={"username": "abc", "password": "xyz"})
    assert r.status_code == 302  # redirect to dashboard

    u = User.query.filter_by(username="abc").first()
    assert u is not None
    assert u.password_hash is not None
    assert u.account is not None
    assert float(u.account.cash) == 100000.00


def test_login_success(client, auth_user):
    r = client.post("/login", data={"username": "tom", "password": "pass"})
    assert r.status_code == 302


def test_login_fail(client):
    r = client.post("/login", data={"username": "bad", "password": "pw"})
    assert b"Invalid credentials" in r.data
