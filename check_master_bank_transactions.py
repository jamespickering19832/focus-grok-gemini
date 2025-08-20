
import os
from app import create_app, db
from app.models import Transaction, Account

app = create_app()

with app.app_context():
    master_bank_account = Account.query.filter_by(name='Master Bank Account').first()

    if not master_bank_account:
        print("Master Bank Account not found.")
    else:
        transactions = Transaction.query.filter_by(account_id=master_bank_account.id).all()
        
        total_balance = 0
        
        print(f"Transactions for Master Bank Account (ID: {master_bank_account.id})")
        print("-" * 50)
        
        for t in transactions:
            print(f"ID: {t.id}, Date: {t.date}, Amount: {t.amount}, Description: {t.description}")
            total_balance += t.amount
            
        print("-" * 50)
        print(f"Calculated Balance: {total_balance}")
        print(f"Stored Balance: {master_bank_account.balance}")

