
from datetime import date, datetime
from flask import session
from app import db
from app.models import Landlord, Transaction, Account
from app.accounting_service import allocate_transaction
import logging

logging.basicConfig(level=logging.INFO)

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

    # Filter out original rent transactions that have been split
    split_rent_ids = [t.parent_transaction_id for t in transactions if t.category in ['rent_landlord_share', 'rent_utility_share']]
    
    final_transactions = [t for t in transactions if not (t.category == 'rent' and t.id in split_rent_ids)]

    payout_reference = landlord.reference_code
    logging.info(f"Payout reference for landlord {landlord_id}: {payout_reference}")

    # Calculate rent income for commission calculation based on the landlord's actual share
    rent_income_for_commission = sum(t.amount for t in final_transactions if t.category == 'rent_landlord_share' or (t.category == 'rent' and t.id not in split_rent_ids))

    # Calculate agency commission and VAT on commission
    agency_commission = rent_income_for_commission * landlord.commission_rate
    vat_on_commission = agency_commission * vat_rate

    # Calculate total expenses for the period
    total_expenses = sum(t.amount for t in final_transactions if t.category == 'expense' and t.landlord_id == landlord_id)

    # The payout amount is the rent income minus expenses, commission, and VAT.
    # Note: expenses are stored as negative values, so we add them.
    payout_amount = rent_income_for_commission + total_expenses - agency_commission - vat_on_commission

    agency_income_account = Account.query.filter_by(name='Agency Income').first()
    if not agency_income_account:
        raise ValueError("Agency Income account not found")

    vat_account = Account.query.filter_by(name='VAT Account').first()
    if not vat_account:
        raise ValueError("VAT account not found")

    if 'current_date' in session:
        today = datetime.strptime(session['current_date'], '%Y-%m-%d').date()
    else:
        today = date.today()

    # Get all the necessary accounts
    bank_account = Account.query.filter_by(name='Master Bank Account').first()
    agency_income_account = Account.query.filter_by(name='Agency Income').first()
    vat_account = Account.query.filter_by(name='VAT Account').first()

    if not bank_account:
        raise ValueError("Master Bank Account not found.")
    if not agency_income_account:
        raise ValueError("Agency Income account not found.")
    if not vat_account:
        raise ValueError("VAT account not found.")

    # 1. Landlord account (only negative transactions)
    if landlord_account:
        # Update landlord's balance
        landlord_account.update_balance(-agency_commission)
        landlord_account.update_balance(-vat_on_commission)
        landlord_account.update_balance(-payout_amount)

        db.session.add(Transaction(
            date=today,
            amount=-agency_commission,
            description=f'Agency Commission {payout_reference}',
            category='fee',
            landlord_id=landlord.id,
            account_id=landlord_account.id,
            status='allocated',
            reference_code=payout_reference
        ))
        db.session.add(Transaction(
            date=today,
            amount=-vat_on_commission,
            description=f'VAT on Commission {payout_reference}',
            category='vat',
            landlord_id=landlord.id,
            account_id=landlord_account.id,
            status='allocated',
            reference_code=payout_reference
        ))

    # 2. Agency Income (only positive, NOT landlord account)
    if agency_income_account:
        agency_income_account.update_balance(agency_commission)
        db.session.add(Transaction(
            date=today,
            amount=agency_commission,
            description=f'Agency Commission {payout_reference}',
            category='fee',
            account_id=agency_income_account.id,
            status='allocated',
            reference_code=payout_reference
        ))

    # 3. VAT (only positive, NOT landlord account)
    if vat_account:
        vat_account.update_balance(vat_on_commission)
        db.session.add(Transaction(
            date=today,
            amount=vat_on_commission,
            description=f'VAT on Commission {payout_reference}',
            category='vat',
            account_id=vat_account.id,
            status='allocated',
            reference_code=payout_reference
        ))

    # 4. Landlord Payments (only negative, NOT landlord account)
    landlord_payments_account = Account.query.filter_by(name='Landlord Payments').first()
    if landlord_payments_account:
        landlord_payments_account.update_balance(-payout_amount)
        db.session.add(Transaction(
            date=today,
            amount=-payout_amount,
            description=f'Payout to {landlord.name}',
            category='payout',
            landlord_id=landlord.id,
            account_id=landlord_payments_account.id,
            status='allocated',
            reference_code=payout_reference
        ))

    db.session.commit()
