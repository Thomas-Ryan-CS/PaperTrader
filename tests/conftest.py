# tests/conftest.py
import os
import sys
import pytest

# Make sure project root is on sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import app, db
from models import User, Account


@pytest.fixture()
def client():
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"

    with app.app_context():
        db.create_all()
        yield app.test_client()
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def auth_user(client):
    """
    Create a user + account and log them in.
    Returns the *user_id* (int), NOT the SQLAlchemy User instance,
    so we don't fight with detached objects.
    """
    with app.app_context():
        user = User(username="tom")
        user.set_password("pass")
        db.session.add(user)
        db.session.commit()

        account = Account(user_id=user.id)
        db.session.add(account)
        db.session.commit()

        user_id = user.id

    # Log in via the test client
    client.post("/login", data={"username": "tom", "password": "pass"})

    return user_id
