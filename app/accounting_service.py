from app import db
from app.models import Account, Tenant, Landlord, Property, Transaction, AuditLog

def allocate_transaction(transaction):
    # For rent charges, only update the tenant account and do not affect the bank account
    if transaction.category == 'rent_charge' and transaction.tenant_id:
        tenant_account = Account.query.filter_by(tenant_id=transaction.tenant_id).first()
        if tenant_account:
            tenant_account.update_balance(-abs(transaction.amount))
            transaction.status = 'allocated'
        # A rent charge is between the agency and the tenant. It doesn't affect the landlord's balance until the rent is paid.
        # It also doesn't affect the bank account.
        return

    bank_account = Account.query.filter_by(name='Master Bank Account').first()
    suspense_account = Account.query.filter_by(name='Suspense Account').first()
    agency_income_account = Account.query.filter_by(name='Agency Income').first()
    agency_expense_account = Account.query.filter_by(name='Agency Expense').first()

    print(f"--- allocate_transaction called for transaction {transaction.id} ---")
    print(f"Initial: status={transaction.status}, account_id={transaction.account_id}, amount={transaction.amount}, category={transaction.category}")
    print(f"Bank Account ID: {bank_account.id if bank_account else 'None'}")
    print(f"Suspense Account ID: {suspense_account.id if suspense_account else 'None'}")

    if not all([bank_account, agency_income_account, agency_expense_account]):
        print("Missing required system accounts.")
        return

    # All transactions, whether coded or uncoded, should always be linked to the bank account for display.
    

    # Update bank account balance for all transactions that flow through it
    if bank_account:
        bank_account.update_balance(transaction.amount)
        

    # If transaction is not yet coded, it remains linked to the bank account but is marked 'uncoded'.
    # No special account handling is needed here.
    if transaction.status != 'coded':
        return

    # Skip allocation for bulk transactions; their components will be allocated
    if transaction.is_bulk:
        transaction.status = 'split' # Mark as split, not allocated
        return

    # Process coded transactions
    

    if transaction.category == 'rent' and transaction.tenant_id:
        tenant = Tenant.query.get(transaction.tenant_id)
        if not tenant:
            pass
            return
        tenant_account = Account.query.filter_by(tenant_id=tenant.id).first()
        if not tenant_account:
            pass
            return

        # Tenant's account is always credited with the full rent amount to clear their balance.
        tenant_account.update_balance(transaction.amount)

        property_ = tenant.property
        if not property_:
            pass
            return
        landlord = property_.landlord
        landlord_account = Account.query.filter_by(landlord_id=landlord.id).first()
        if not landlord_account:
            print(f"No account found for landlord {landlord.name}")
            return

        # Check for and apply utility split
        if property_.landlord_portion and property_.landlord_portion < 1.0 and property_.utility_account_id:
            utility_account = Account.query.get(property_.utility_account_id)
            if utility_account:
                landlord_share = transaction.amount * property_.landlord_portion
                utility_share = transaction.amount * (1 - property_.landlord_portion)

                landlord_account.update_balance(landlord_share)
                utility_account.update_balance(utility_share)

                # Create child transactions for ledger clarity
                landlord_tx = Transaction(
                    date=transaction.date, amount=landlord_share, description=f"Landlord share of rent from {tenant.name}",
                    category='rent_landlord_share', landlord_id=landlord.id, parent_transaction_id=transaction.id,
                    status='allocated', account_id=landlord_account.id, reference_code=transaction.reference_code
                )
                utility_tx = Transaction(
                    date=transaction.date, amount=utility_share, description=f"Utility share of rent from {tenant.name}",
                    category='rent_utility_share', account_id=utility_account.id, parent_transaction_id=transaction.id,
                    status='allocated', reference_code=transaction.reference_code
                )
                db.session.add_all([landlord_tx, utility_tx])
                
                transaction.status = 'split' # Mark original transaction as split
                
            else:
                # Fallback if utility account is not found, treat as no split
                landlord_account.update_balance(transaction.amount)
                transaction.landlord_id = landlord.id
                transaction.account_id = landlord_account.id
        else:
            # No utility split, but commission might apply
            commission_rate = landlord.commission_rate or 0.0
            
            if commission_rate > 0:
                commission = transaction.amount * commission_rate
                landlord_share = transaction.amount - commission
                
                # Update landlord account with their share
                landlord_account.update_balance(landlord_share)
                
                # Update agency income account with commission
                agency_income_account.update_balance(commission)
                
                # Create child transactions for ledger clarity
                landlord_tx = Transaction(
                    date=transaction.date, amount=landlord_share, description=f"Landlord share of rent from {tenant.name}",
                    category='rent_landlord_share', landlord_id=landlord.id, parent_transaction_id=transaction.id,
                    status='allocated', account_id=landlord_account.id, reference_code=transaction.reference_code
                )
                agency_tx = Transaction(
                    date=transaction.date, amount=commission, description=f"Commission from {tenant.name}'s rent",
                    category='fee', landlord_id=landlord.id, parent_transaction_id=transaction.id,
                    status='allocated', account_id=agency_income_account.id, reference_code=transaction.reference_code
                )
                db.session.add_all([landlord_tx, agency_tx])
                
                transaction.status = 'split' # Mark original transaction as split
            else:
                # No commission, full amount to landlord
                landlord_account.update_balance(transaction.amount)
                transaction.landlord_id = landlord.id # Associate transaction directly with landlord
                transaction.account_id = landlord_account.id

        

    elif transaction.category == 'expense' and transaction.landlord_id:
        landlord_account = Account.query.filter_by(landlord_id=transaction.landlord_id).first()
        if not landlord_account:
            print(f"No account found for landlord {landlord.name}")
            return
        print(f"Landlord account balance BEFORE expense: {landlord_account.balance:.2f}")
        landlord_account.update_balance(transaction.amount) # transaction.amount is already negative for expenses
        print(f"Landlord account balance AFTER expense: {landlord_account.balance:.2f}")
        transaction.account_id = landlord_account.id # Link expense transaction to landlord account
        print(f"Transaction {transaction.id}: Expense. Landlord account updated.")

    elif transaction.category == 'payment' and transaction.landlord_id:
        landlord_account = Account.query.filter_by(landlord_id=transaction.landlord_id).first()
        if not landlord_account:
            print(f"No account found for landlord {landlord.name}")
            return
        print(f"Landlord account balance BEFORE payment: {landlord_account.balance:.2f}")
        landlord_account.update_balance(-abs(transaction.amount)) # Payment to landlord reduces their balance
        print(f"Landlord account balance AFTER payment: {landlord_account.balance:.2f}")
        transaction.account_id = landlord_account.id # Link payment transaction to landlord account
        print(f"Transaction {transaction.id}: Landlord payment. Landlord account updated.")

    elif transaction.category == 'payout' and transaction.landlord_id:
        landlord_account = Account.query.filter_by(landlord_id=transaction.landlord_id).first()
        if not landlord_account:
            pass
            return
        landlord_account.update_balance(transaction.amount)

    # Mark transaction as allocated
    transaction.status = 'allocated'

    

    
