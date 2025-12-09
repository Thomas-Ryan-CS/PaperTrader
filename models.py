from decimal import Decimal
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash  # NEW

# db accessor
db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    watchlist_name = db.Column(db.String(64), nullable=True)

    # helpers
    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

class Ticker(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(12), unique=True, nullable=False)
    name = db.Column(db.String(64), nullable=True)
    price = db.Column(db.Numeric(12,2), nullable=False, default=Decimal('100.00'))

class Account(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    cash = db.Column(db.Numeric(14,2), nullable=False, default=Decimal('100000.00'))
    user = db.relationship('User', backref=db.backref('account', uselist=False))

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    ticker_id = db.Column(db.Integer, db.ForeignKey('ticker.id'), nullable=False)
    side = db.Column(db.String(4), nullable=False)      # BUY/SELL
    order_type = db.Column(db.String(3), nullable=False)  # MKT/LMT
    qty = db.Column(db.Integer, nullable=False)
    limit_price = db.Column(db.Numeric(12,2), nullable=True)
    status = db.Column(db.String(12), nullable=False, default='PENDING')
    user = db.relationship('User')
    ticker = db.relationship('Ticker')

class Position(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    ticker_id = db.Column(db.Integer, db.ForeignKey('ticker.id'), nullable=False)
    qty = db.Column(db.Integer, nullable=False, default=0)
    avg_price = db.Column(db.Numeric(12,2), nullable=False, default=Decimal('0.00'))
    user = db.relationship('User')
    ticker = db.relationship('Ticker')
    __table_args__ = (db.UniqueConstraint('user_id', 'ticker_id', name='uix_user_ticker'),)

class Trade(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    price = db.Column(db.Numeric(12,2), nullable=False)
    qty = db.Column(db.Integer, nullable=False)
    order = db.relationship('Order')

class WatchlistItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    symbol = db.Column(db.String(64), nullable=False)
    user = db.relationship('User')
    last_notified_price = db.Column(db.Float, nullable=True)
    
