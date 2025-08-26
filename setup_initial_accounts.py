# setup_initial_accounts.py
from app import create_app, db
from app.models import Account

def add_initial_accounts():
    app = create_app()
    with app.app_context():
        # Check if accounts already exist to avoid duplicates
        if Account.query.filter_by(name='Agency Income').first():
            print("Initial accounts already seem to exist. Aborting.")
            return

        agency_income_account = Account(name='Agency Income', type='agency_income')
        agency_expense_account = Account(name='Agency Expense', type='agency_expense')
        suspense_account = Account(name='Suspense Account', type='suspense')
        bank_account = Account(name='Master Bank Account', type='asset', balance=90000.0)
        utility_account = Account(name='Utility Account', type='utility')
        vat_account = Account(name='VAT Account', type='vat_payable')

        db.session.add_all([
            agency_income_account, agency_expense_account,
            suspense_account, bank_account, utility_account, vat_account
        ])

        db.session.commit()
        print("Initial agency and bank accounts added successfully.")

if __name__ == '__main__':
    add_initial_accounts()