from app import db
from app.models import Account

def create_or_get_account(name, type_):
    account = Account.query.filter_by(name=name).first()
    if not account:
        account = Account(name=name, type=type_, balance=0.0)
        db.session.add(account)
        print(f'Created account: {name}')
    else:
        print(f'Account already exists: {name}')
    return account

# Create or get Bank Account
create_or_get_account('Bank Account', 'asset')

# Create or get Suspense Account
create_or_get_account('Suspense Account', 'suspense')

# Create or get Agency Income Account
create_or_get_account('Agency Income', 'agency_income')

# Create or get Agency Expense Account
create_or_get_account('Agency Expense', 'agency_expense')

# Create or get VAT Payable Account
create_or_get_account('VAT Payable', 'vat_payable')

# Create or get Utility Account
create_or_get_account('Utility', 'utility')

# Commit the changes to the database
db.session.commit()

print('System accounts creation/verification complete!')
