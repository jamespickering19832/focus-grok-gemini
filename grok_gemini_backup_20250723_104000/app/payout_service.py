
from datetime import date
from app import db
from app.models import Landlord, Transaction, Account

def process_landlord_payout(landlord_id, start_date, end_date, vat_rate):
    landlord = Landlord.query.get(landlord_id)
    if not landlord:
        raise ValueError("Landlord not found")

    landlord_account = Account.query.filter_by(landlord_id=landlord.id, type='landlord').first()
    if not landlord_account:
        raise ValueError("Landlord account not found")

    transactions = Transaction.query.filter(
        Transaction.landlord_id == landlord.id,
        Transaction.date.between(start_date, end_date),
        Transaction.processed == False  # Only process unprocessed transactions
    ).all()

    rent_income = sum(t.amount for t in transactions if t.category == 'rent')
    expenses_incurred = sum(t.amount for t in transactions if t.category == 'expense')

    # Calculate agency commission and VAT on commission
    agency_commission = rent_income * landlord.commission_rate
    vat_on_commission = agency_commission * vat_rate

    # Calculate total amount to be paid out to landlord
    # This is rent received, plus expenses (which are negative), minus agency commission, minus VAT on commission
    payout_amount = rent_income + expenses_incurred - agency_commission - vat_on_commission

    today = date.today()

    bank_account = Account.query.filter_by(name='Bank Account').first()
    if not bank_account:
        raise ValueError("Bank Account not found")

    # Create transactions for commission, VAT, and payout
    # Agency Commission transaction
    commission_trans = Transaction(date=today, amount=-agency_commission, description='Agency Commission', category='fee', landlord_id=landlord.id, account_id=bank_account.id)
    db.session.add(commission_trans)
    bank_account.update_balance(-agency_commission)

    # VAT on Commission transaction
    vat_trans = Transaction(date=today, amount=-vat_on_commission, description='VAT on Commission', category='vat', landlord_id=landlord.id, account_id=bank_account.id)
    db.session.add(vat_trans)
    bank_account.update_balance(-vat_on_commission)

    # Landlord Payout transaction
    payout_trans = Transaction(date=today, amount=-payout_amount, description='Landlord Payout', category='payout', landlord_id=landlord.id, account_id=bank_account.id)
    db.session.add(payout_trans)
    bank_account.update_balance(-payout_amount)

    agency_income_account = Account.query.filter_by(name='Agency Income').first()
    if not agency_income_account:
        raise ValueError("Agency Income account not found")

    # Update landlord account balance
    landlord_account.update_balance(-(agency_commission + vat_on_commission + payout_amount))

    # Update agency income account
    agency_income_account.update_balance(agency_commission + vat_on_commission)

    # Mark processed transactions as processed
    for t in transactions:
        t.processed = True

    db.session.commit()
