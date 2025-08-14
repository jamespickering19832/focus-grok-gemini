from app import db
from app.models import Account, Tenant, Landlord, Property, Transaction, AuditLog

def allocate_transaction(transaction):
    # For rent charges, only update the tenant account and do not affect the bank account
    if transaction.category == 'rent_charge' and transaction.tenant_id:
        tenant_account = Account.query.filter_by(tenant_id=transaction.tenant_id).first()
        if tenant_account:
            tenant_account.update_balance(-abs(transaction.amount)) # Rent charge increases tenant debt (makes balance more negative)
            transaction.status = 'allocated'
            print(f"Transaction {transaction.id}: Rent charge. Tenant account updated.")
        else:
            print(f"No account found for tenant with ID {transaction.tenant_id}")
        # Also update landlord account for rent charges, as it represents expected income
        tenant = Tenant.query.get(transaction.tenant_id)
        if tenant and tenant.property and tenant.property.landlord:
            landlord_account = Account.query.filter_by(landlord_id=tenant.property.landlord.id).first()
            if landlord_account:
                landlord_account.update_balance(abs(transaction.amount)) # Landlord expects to receive rent
                print(f"Transaction {transaction.id}: Rent charge. Landlord account updated.")
        # Also update bank account for rent charges (expected inflow)
        bank_account = Account.query.filter_by(name='Bank Account').first()
        if bank_account:
            bank_account.update_balance(abs(transaction.amount))
            print(f"Transaction {transaction.id}: Rent charge. Bank account updated.")
        return # Stop further processing for rent charges

    bank_account = Account.query.filter_by(name='Bank Account').first()
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
    # Ensure the transaction's account_id is the bank_account.id if it's not already.
    if transaction.account_id != bank_account.id:
        transaction.account_id = bank_account.id

    # Update bank account balance for all transactions that flow through it
    if bank_account:
        bank_account.update_balance(transaction.amount)
        print(f"Transaction {transaction.id}: Bank account updated with amount {transaction.amount}.")

    # If transaction is not yet coded, it remains linked to the bank account but is marked 'uncoded'.
    # No special account handling is needed here.
    if transaction.status != 'coded':
        print(f"Transaction {transaction.id} is not coded. No further allocation needed at this time.")
        return

    # Skip allocation for bulk transactions; their components will be allocated
    if transaction.is_bulk:
        print(f"Transaction {transaction.id} is a bulk transaction. Skipping direct allocation.")
        transaction.status = 'split' # Mark as split, not allocated
        return

    # Process coded transactions
    print(f"Transaction {transaction.id} is coded. Processing...")

    if transaction.category == 'rent' and transaction.tenant_id:
        tenant = Tenant.query.get(transaction.tenant_id)
        if not tenant:
            print(f"No tenant found for ID {transaction.tenant_id}")
            return
        tenant_account = Account.query.filter_by(tenant_id=tenant.id).first()
        if not tenant_account:
            print(f"No account found for tenant {tenant.name}")
            return

        # Tenant's account is always credited with the full rent amount to clear their balance.
        tenant_account.update_balance(transaction.amount)
        print(f"Tenant account for {tenant.name} credited with {transaction.amount}")

        property_ = tenant.property
        if not property_:
            print("No property assigned to this tenant")
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
                    status='allocated', account_id=landlord_account.id
                )
                utility_tx = Transaction(
                    date=transaction.date, amount=utility_share, description=f"Utility share of rent from {tenant.name}",
                    category='rent_utility_share', account_id=utility_account.id, parent_transaction_id=transaction.id,
                    status='allocated'
                )
                db.session.add_all([landlord_tx, utility_tx])
                
                transaction.status = 'split' # Mark original transaction as split
                print(f"Transaction {transaction.id}: Rent payment SPLIT. Landlord: {landlord_share}, Utility: {utility_share}")
            else:
                # Fallback if utility account is misconfigured
                landlord_account.update_balance(transaction.amount)
                print(f"Transaction {transaction.id}: Rent payment. Utility account not found. Full amount to landlord.")
        else:
            # No split configured, allocate full amount to landlord
            landlord_account.update_balance(transaction.amount)
            print(f"Transaction {transaction.id}: Rent payment. Full amount to landlord.")

        # Link original transaction to tenant account for their records
        transaction.account_id = tenant_account.id

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
            print(f"No account found for landlord {transaction.landlord_id}")
            return
        print(f"Landlord account balance BEFORE payout: {landlord_account.balance:.2f}")
        landlord_account.update_balance(transaction.amount) # Payout increases landlord's balance
        print(f"Landlord account balance AFTER payout: {landlord_account.balance:.2f}")
        transaction.account_id = landlord_account.id # Link payout transaction to landlord account
        print(f"Transaction {transaction.id}: Landlord payout. Landlord account updated.")

    # Mark transaction as allocated
    transaction.status = 'allocated'

    print(f"Transaction {transaction.id} status set to allocated. Final account_id={transaction.account_id}")

    log = AuditLog(action='allocation', details=f'Transaction {transaction.id} allocated')
    db.session.add(log)
    db.session.commit()
    print(f"Audit log for transaction {transaction.id} added.")
