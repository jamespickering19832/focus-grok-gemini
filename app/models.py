# app/models.py
from datetime import datetime
from app import db
from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship
from flask_login import UserMixin
import bcrypt

# Association table for User and Role many-to-many relationship
user_roles = db.Table('user_roles',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('role_id', db.Integer, db.ForeignKey('role.id'), primary_key=True)
)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.LargeBinary(128))
    roles = db.relationship('Role', secondary=user_roles, lazy='subquery',
        backref=db.backref('users', lazy=True))

    def __repr__(self):
        return f'<User {self.username}>'

    def set_password(self, password):
        self.password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

    def check_password(self, password):
        return bcrypt.checkpw(password.encode('utf-8'), self.password_hash)

class Role(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)

    def __repr__(self):
        return f'<Role {self.name}>'

class Tenant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), index=True)
    email = db.Column(db.String(120), index=True)
    phone_number = db.Column(db.String(20))
    start_date = db.Column(db.Date)
    reference_code = db.Column(db.String(64), unique=True, index=True)
    property_id = db.Column(db.Integer, db.ForeignKey('property.id'))
    accounts = db.relationship('Account', backref='tenant', lazy='dynamic')
    transactions = db.relationship('Transaction', backref='tenant_transaction', lazy='dynamic')

    def __repr__(self):
        return f'<Tenant {self.name}>'

class Landlord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), index=True)
    email = db.Column(db.String(120), index=True)
    phone_number = db.Column(db.String(20))
    address = db.Column(db.String(256))
    bank_name = db.Column(db.String(128))
    bank_account_number = db.Column(db.String(30))
    bank_sort_code = db.Column(db.String(10))
    reference_code = db.Column(db.String(64), unique=True, index=True)
    commission_rate = db.Column(db.Float, default=0.1)
    receives_email_statements = db.Column(db.Boolean, default=True)
    properties = db.relationship('Property', backref='landlord', lazy='dynamic')
    accounts = db.relationship('Account', backref='landlord', lazy='dynamic')
    transactions = db.relationship('Transaction', backref='landlord_transaction', lazy='dynamic')

    def __repr__(self):
        return f'<Landlord {self.name}>'

class Property(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    address = db.Column(db.String(256))
    rent_amount = db.Column(db.Float, default=0.0)  # Monthly rent amount
    landlord_id = db.Column(db.Integer, db.ForeignKey('landlord.id'))
    landlord_portion = db.Column(db.Float, nullable=True)
    utility_account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=True)
    tenants = db.relationship('Tenant', backref='property', lazy='dynamic')
    expenses = db.relationship('Expense', backref='property', lazy='dynamic')

    def __repr__(self):
        return f'<Property {self.address}>'

class Account(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128))
    type = db.Column(db.String(64))  # tenant, landlord, agency_income, agency_expense, suspense, asset, vat_payable, utility
    balance = db.Column(db.Float, default=0.0)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'))
    landlord_id = db.Column(db.Integer, db.ForeignKey('landlord.id'))
    transactions = db.relationship('Transaction', backref='account', lazy='dynamic')

    def update_balance(self, amount):
        self.balance += amount

    def __repr__(self):
        return f'<Account {self.name} Balance: {self.balance}>'

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date)
    amount = db.Column(db.Float)
    description = db.Column(db.String(256))
    reference_code = db.Column(db.String(128))
    status = db.Column(db.String(64), default='uncoded')  # uncoded, coded, allocated
    category = db.Column(db.String(64))  # rent, expense, fee, rent_charge, etc.
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'))
    landlord_id = db.Column(db.Integer, db.ForeignKey('landlord.id'))
    account_id = db.Column(db.Integer, db.ForeignKey('account.id'))
    rent_charge_batch_id = db.Column(db.Integer, db.ForeignKey('rent_charge_batch.id'))
    allocation_history = db.relationship('AllocationHistory', backref='transaction', lazy='dynamic')
    processed = db.Column(db.Boolean, default=False, nullable=False)
    is_bulk = db.Column(db.Boolean, default=False, nullable=False)
    parent_transaction_id = db.Column(db.Integer, db.ForeignKey('transaction.id'), nullable=True)
    property_id = db.Column(db.Integer, db.ForeignKey('property.id'), nullable=True) # Added property_id
    reviewed = db.Column(db.Boolean, default=False, nullable=False)

    def __repr__(self):
        return f'<Transaction {self.description} Amount {self.amount}>'

class ExpenseCategory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64))
    expenses = db.relationship('Expense', backref='category', lazy='dynamic')

    def __repr__(self):
        return f'<ExpenseCategory {self.name}>'

class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(256))
    amount = db.Column(db.Float)
    date = db.Column(db.Date)
    property_id = db.Column(db.Integer, db.ForeignKey('property.id'))
    category_id = db.Column(db.Integer, db.ForeignKey('expense_category.id'))

    def __repr__(self):
        return f'<Expense {self.description} Amount {self.amount}>'

class AllocationHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey('transaction.id'))
    allocated_to = db.Column(db.String(128))
    allocated_date = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer)  # For audit
    notes = db.Column(db.String(256))

class Statement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(64))  # monthly, annual, tenant, landlord
    date_generated = db.Column(db.DateTime, default=datetime.utcnow)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    landlord_id = db.Column(db.Integer, db.ForeignKey('landlord.id'))
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'))
    property_id = db.Column(db.Integer, db.ForeignKey('property.id'))
    pdf_path = db.Column(db.String(256))
    delivered = db.Column(db.Boolean, default=False)

    landlord = db.relationship('Landlord', backref='statements')
    tenant = db.relationship('Tenant', backref='statements')

    def __repr__(self):
        return f'<Statement {self.type} for {self.start_date} to {self.end_date}>'

class RentChargeBatch(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    description = db.Column(db.String(256))
    transactions = db.relationship('Transaction', backref='rent_charge_batch', lazy='dynamic')

    def __repr__(self):
        return f'<RentChargeBatch {self.description} at {self.timestamp}>'

class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(256))
    user_id = db.Column(db.Integer)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    details = db.Column(db.Text)

class Company(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128))
    address = db.Column(db.String(256))
    logo = db.Column(db.String(256))  # Path to logo file

    def __repr__(self):
        return f'<Company {self.name}>'