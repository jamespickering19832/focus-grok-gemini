
from datetime import date
from app import db
from app.models import Landlord, Transaction, Account
from app.accounting_service import allocate_transaction

def process_landlord_payout(landlord_id, start_date, end_date, vat_rate):
    landlord = Landlord.query.get(landlord_id)
    if not landlord:
        raise ValueError("Landlord not found")

    landlord_account = Account.query.filter_by(landlord_id=landlord.id, type='landlord').first()
    if not landlord_account:
        raise ValueError("Landlord account not found")

    

    # Get all transactions for the landlord within the specified date range to calculate the payout.
    transactions = Transaction.query.filter(
        Transaction.landlord_id == landlord.id,
        Transaction.date.between(start_date, end_date)
    ).all()

    tenant_ids = [t.id for p in landlord.properties for t in p.tenants]
    tenant_rent_transactions = Transaction.query.filter(
        Transaction.tenant_id.in_(tenant_ids),
        Transaction.category == 'rent',
        Transaction.date.between(start_date, end_date)
    ).all()

    transactions.extend(tenant_rent_transactions)

    # Calculate rent income for commission calculation
    rent_income_for_commission = sum(t.amount for t in transactions if t.category == 'rent')

    # Calculate agency commission and VAT on commission
    agency_commission = rent_income_for_commission * landlord.commission_rate
    vat_on_commission = agency_commission * vat_rate

    # Recalculate the landlord account balance to ensure it's up-to-date
    current_landlord_balance = sum(t.amount for t in transactions)

    # The payout amount is the current calculated balance of the landlord's account
    # minus the agency commission and VAT on commission.
    # The landlord's account balance should already reflect all rent and expenses.
    payout_amount = current_landlord_balance - agency_commission - vat_on_commission

    agency_income_account = Account.query.filter_by(name='Agency Income').first()
    if not agency_income_account:
        raise ValueError("Agency Income account not found")

    vat_account = Account.query.filter_by(name='VAT').first()
    if not vat_account:
        raise ValueError("VAT account not found")

    today = date.today()

    today = date.today()

    # Get all the necessary accounts
    bank_account = Account.query.filter_by(name='Bank Account').first()
    agency_income_account = Account.query.filter_by(name='Agency Income').first()
    vat_account = Account.query.filter_by(name='VAT').first()

    if not all([bank_account, agency_income_account, vat_account]):
        raise ValueError("One or more system accounts (Bank, Agency Income, VAT) are missing.")

    # 1. Landlord account (only negative transactions)
    if landlord_account:
        db.session.add(Transaction(
            date=today,
            amount=-agency_commission,
            description='Agency Commission',
            category='fee',
            landlord_id=landlord.id,
            account_id=landlord_account.id,
            status='allocated'
        ))
        db.session.add(Transaction(
            date=today,
            amount=-vat_on_commission,
            description='VAT on Commission',
            category='vat',
            landlord_id=landlord.id,
            account_id=landlord_account.id,
            status='allocated'
        ))
        db.session.add(Transaction(
            date=today,
            amount=-payout_amount,
            description=f'Payout to {landlord.name}',
            category='payout',
            landlord_id=landlord.id,
            account_id=landlord_account.id,
            status='allocated'
        ))

    # 2. Agency Income (only positive, NOT landlord account)
    if agency_income_account:
        db.session.add(Transaction(
            date=today,
            amount=agency_commission,
            description='Agency Commission',
            category='fee',
            landlord_id=landlord.id,
            account_id=agency_income_account.id,
            status='allocated'
        ))

    # 3. VAT (only positive, NOT landlord account)
    if vat_account:
        db.session.add(Transaction(
            date=today,
            amount=vat_on_commission,
            description='VAT on Commission',
            category='vat',
            landlord_id=landlord.id,
            account_id=vat_account.id,
            status='allocated'
        ))

    # 4. Landlord Payments (only negative, NOT landlord account)
    landlord_payments_account = Account.query.filter((Account.type=='liability') | (Account.name=='Landlord Payments')).first()
    if landlord_payments_account:
        db.session.add(Transaction(
            date=today,
            amount=-payout_amount,
            description=f'Payout to {landlord.name}',
            category='payout',
            landlord_id=landlord.id,
            account_id=landlord_payments_account.id,
            status='allocated'
        ))

    db.session.commit()
