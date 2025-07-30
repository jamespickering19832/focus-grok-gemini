from app import db
from app.models import Transaction, Landlord
from datetime import date

# CONFIGURE THESE VALUES
LANDLORD_NAME = 'ALP Property Management'
PAYOUT_DATE = date(2025, 7, 25)

landlord = Landlord.query.filter_by(name=LANDLORD_NAME).first()
if not landlord:
    print(f'No landlord found with name {LANDLORD_NAME}')
    exit(1)

categories = ['fee', 'vat', 'payout']

for category in categories:
    txns = Transaction.query.filter_by(
        landlord_id=landlord.id,
        date=PAYOUT_DATE,
        category=category
    ).order_by(Transaction.id).all()
    # Keep only the first transaction, delete the rest
    for txn in txns[1:]:
        print(f'Deleting duplicate: {txn.category} {txn.amount} {txn.description}')
        db.session.delete(txn)

db.session.commit()
print('Duplicate landlord payout transactions removed.') 