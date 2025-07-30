from app import db, app
from app.models import Account, Transaction

with app.app_context():
    bank_account = Account.query.filter_by(name='Bank Account').first()

    print(f'Bank Account: {bank_account.id if bank_account else None}')

    if bank_account:
        transactions = Transaction.query.filter_by(account_id=bank_account.id).all()
        print(f'Transactions linked to Bank Account: {len(transactions)}')
        for t in transactions[:5]:
            print(f'  ID: {t.id}, Desc: {t.description}, Amount: {t.amount}, Date: {t.date}, Status: {t.status}')