# app/routes.py
from flask import render_template, flash, redirect, url_for, request
from werkzeug.utils import secure_filename
from app import app, db
from app.models import Tenant, Landlord, Transaction, Account, Property, AllocationHistory, Statement, AuditLog, Expense, RentChargeBatch, Company
from datetime import datetime, timedelta, date
import os
import pandas as pd
import difflib

from app import mail
from flask_mail import Message
from app.forms import AddTenantForm, AddLandlordForm, AddPropertyForm, EditTenantForm, DeleteTenantForm, EditLandlordForm, DeleteLandlordForm, EditPropertyForm, DeletePropertyForm, PayoutForm, ManualRentForm, ManualExpenseForm, DateRangeForm, CompanyForm
from app.payout_service import process_landlord_payout
from sqlalchemy.exc import IntegrityError
import calendar
import sqlalchemy as sa

ALLOWED_EXTENSIONS = {'csv'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/', methods=['GET', 'POST'])
@app.route('/index', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part')
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            flash(f'File {filename} uploaded successfully.')
            process_csv(file_path)
            return redirect(url_for('uncoded_transactions'))
    return render_template('index.html', title='Upload CSV')

def process_csv(file_path):
    bank_account = Account.query.filter_by(name='Bank Account').first()
    if not bank_account:
        flash('Bank Account not found. Please create it in the accounts section.')
        return

    try:
        df = pd.read_csv(file_path)
        for index, row in df.iterrows():
            try:
                date_str = row.get('Date', row.get('date'))
                if not isinstance(date_str, str) or pd.isna(date_str):
                    continue  # Skip rows with invalid or missing date

                amount = row.get('Amount', row.get('amount'))
                if pd.isna(amount):
                    continue
                amount = float(amount)

                description = row.get('Memo', row.get('description', ''))
                reference_code = row.get('Subcategory', row.get('reference_code', ''))

                try:
                    date = datetime.strptime(date_str, '%Y-%m-%d').date()
                except ValueError:
                    try:
                        date = datetime.strptime(date_str, '%d/%m/%Y').date()
                    except ValueError:
                        continue  # Skip invalid date

                if amount == 0:
                    continue

                transaction = Transaction(
                    date=date,
                    amount=amount,
                    description=description,
                    reference_code=reference_code,
                    account_id=bank_account.id # Link to bank account
                )

                matched, match_type, match_id = match_transaction(transaction)
                if matched:
                    transaction.status = 'coded'
                    if match_type == 'tenant':
                        transaction.tenant_id = match_id
                    else:
                        transaction.landlord_id = match_id
                else:
                    transaction.status = 'uncoded'

                db.session.add(transaction)

                if transaction.status == 'coded':
                    allocate_transaction(transaction)

            except Exception as e:
                flash(f"Error processing row {index}: {str(e)}")
                continue
        db.session.commit() # Commit all transactions after processing the CSV

    except Exception as e:
        flash(f'Error processing CSV: {str(e)}')

def get_partial_ratio(long_text, pattern):
    long_text = long_text.upper()
    pattern = pattern.upper()
    if len(pattern) > len(long_text):
        long_text, pattern = pattern, long_text
    len_p = len(pattern)
    max_ratio = 0
    for i in range(len(long_text) - len_p + 1):
        sub = long_text[i:i + len_p]
        matcher = difflib.SequenceMatcher(None, sub, pattern)
        ratio = matcher.ratio()
        if ratio > max_ratio:
            max_ratio = ratio
    return max_ratio * 100

def match_transaction(transaction):
    tenants = Tenant.query.all()
    landlords = Landlord.query.all()

    raw_text = ((transaction.description or '') + ' ' + (transaction.reference_code or ''))
    text = ''.join(raw_text.upper().split())  # Remove all whitespace and upper

    # Prioritize exact matches for reference codes
    if transaction.reference_code:
        normalized_trans_ref = ''.join(transaction.reference_code.upper().split())
        for tenant in tenants:
            if tenant.reference_code and normalized_trans_ref == ''.join(tenant.reference_code.upper().split()):
                transaction.category = 'rent'
                return True, 'tenant', tenant.id
        for landlord in landlords:
            if landlord.reference_code and normalized_trans_ref == ''.join(landlord.reference_code.upper().split()):
                if transaction.amount > 0:
                    transaction.category = 'payment'
                else:
                    transaction.category = 'expense'
                return True, 'landlord', landlord.id

    # Fallback to fuzzy matching on description/name
    # Prioritize tenant matching for positive amounts (rent payments)
    if transaction.amount > 0:
        for tenant in tenants:
            if tenant.name:
                name_norm = ''.join(tenant.name.upper().split())
                name_score = get_partial_ratio(text, name_norm)
                if name_score >= 85:
                    transaction.category = 'rent'
                    return True, 'tenant', tenant.id

    # General fuzzy matching
    for tenant in tenants:
        if tenant.reference_code:
            ref_norm = ''.join(tenant.reference_code.upper().split())
            ref_score = get_partial_ratio(text, ref_norm)
            if ref_score >= 85:
                if transaction.amount > 0:
                    transaction.category = 'rent'
                else:
                    transaction.category = 'fee'
                return True, 'tenant', tenant.id
        if tenant.name:
            name_norm = ''.join(tenant.name.upper().split())
            name_score = get_partial_ratio(text, name_norm)
            if name_score >= 85:
                if transaction.amount > 0:
                    transaction.category = 'rent'
                else:
                    transaction.category = 'fee'
                return True, 'tenant', tenant.id

    for landlord in landlords:
        if landlord.reference_code:
            ref_norm = ''.join(landlord.reference_code.upper().split())
            ref_score = get_partial_ratio(text, ref_norm)
            if ref_score >= 85:
                if transaction.amount > 0:
                    transaction.category = 'payment'
                else:
                    transaction.category = 'expense'
                return True, 'landlord', landlord.id
        if landlord.name:
            name_norm = ''.join(landlord.name.upper().split())
            name_score = get_partial_ratio(text, name_norm)
            if name_score >= 85:
                if transaction.amount > 0:
                    transaction.category = 'payment'
                else:
                    transaction.category = 'expense'
                return True, 'landlord', landlord.id

    return False, None, None

def allocate_transaction(transaction):
    bank_account = Account.query.filter_by(name='Bank Account').first()
    suspense_account = Account.query.filter_by(name='Suspense Account').first()
    agency_income_account = Account.query.filter_by(name='Agency Income').first()
    agency_expense_account = Account.query.filter_by(name='Agency Expense').first()

    print(f"--- allocate_transaction called for transaction {transaction.id} ---")
    print(f"Initial: status={transaction.status}, account_id={transaction.account_id}")
    print(f"Bank Account ID: {bank_account.id if bank_account else 'None'}")
    print(f"Suspense Account ID: {suspense_account.id if suspense_account else 'None'}")

    if not all([bank_account, suspense_account, agency_income_account, agency_expense_account]):
        flash('Missing required system accounts (Bank, Suspense, Agency Income, Agency Expense).')
        print("Missing required system accounts.")
        return

    # All transactions, whether coded or uncoded, should always be linked to the bank account for display.
    # The suspense account is for balance tracking of uncoded items.
    # Ensure the transaction's account_id is the bank_account.id if it's not already.
    if transaction.account_id != bank_account.id:
        transaction.account_id = bank_account.id

    # Update bank account balance for all transactions that flow through it
    bank_account.update_balance(transaction.amount)

    # If transaction is not yet coded, update suspense account balance
    if transaction.status != 'coded':
        print(f"Transaction {transaction.id} is not coded. Updating suspense account.")
        suspense_account.update_balance(transaction.amount)
        # No commit here, commit at the end of the function
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
            flash(f'No tenant found for ID {transaction.tenant_id}')
            print(f"No tenant found for ID {transaction.tenant_id}")
            return
        tenant_account = Account.query.filter_by(tenant_id=tenant.id).first()
        if not tenant_account:
            flash(f'No account found for tenant {tenant.name}')
            print(f"No account found for tenant {tenant.name}")
            return

        property_ = tenant.property
        if not property_:
            flash('No property assigned to this tenant')
            print("No property assigned to this tenant")
            return
        landlord = property_.landlord
        landlord_account = Account.query.filter_by(landlord_id=landlord.id).first()
        if not landlord_account:
            flash(f'No account found for landlord {landlord.name}')
            print(f"No account found for landlord {landlord.name}")
            return

        # Rent payment: Tenant pays (reduces tenant liability), Landlord receives (increases landlord asset/liability to agency)
        tenant_account.update_balance(transaction.amount)  # Tenant account increases (they paid, so credit)
        landlord_account.update_balance(transaction.amount) # Landlord account increases (they received rent)
        transaction.landlord_id = landlord.id # Link rent transaction to landlord for statements
        print(f"Transaction {transaction.id}: Rent payment. Tenant account updated. Landlord account updated.")

    elif transaction.category == 'rent_charge' and transaction.tenant_id:
        tenant_account = Account.query.filter_by(tenant_id=transaction.tenant_id).first()
        if not tenant_account:
            flash(f'No account found for tenant {tenant.name}')
            print(f"No account found for tenant {tenant.name}")
            return
        # Rent charge: Tenant account decreases (they owe more)
        tenant_account.update_balance(-transaction.amount)
        print(f"Transaction {transaction.id}: Rent charge. Tenant account updated.")

    elif transaction.category == 'expense' and transaction.landlord_id:
        landlord_account = Account.query.filter_by(landlord_id=transaction.landlord_id).first()
        if not landlord_account:
            flash(f'No account found for landlord {landlord.name}')
            print(f"No account found for landlord {landlord.name}")
            return
        # Expense: Landlord account decreases (expense charged to them)
        landlord_account.update_balance(transaction.amount) # transaction.amount is already negative for expenses
        print(f"Transaction {transaction.id}: Expense. Landlord account updated.")

    elif transaction.category == 'payment' and transaction.landlord_id:
        landlord_account = Account.query.filter_by(landlord_id=transaction.landlord_id).first()
        if not landlord_account:
            flash(f'No account found for landlord {landlord.name}')
            print(f"No account found for landlord {landlord.name}")
            return
        # Landlord payment (e.g., landlord pays into their account): Landlord account increases
        landlord_account.update_balance(transaction.amount)
        print(f"Transaction {transaction.id}: Landlord payment. Landlord account updated.")

    # Mark transaction as allocated
    transaction.status = 'allocated'
    # db.session.commit() # Removed this commit
    print(f"Transaction {transaction.id} status set to allocated. Final account_id={transaction.account_id}")

    log = AuditLog(action='allocation', details=f'Transaction {transaction.id} allocated')
    db.session.add(log)
    # db.session.commit() # Removed this commit
    print(f"Audit log for transaction {transaction.id} added.")

def find_suggestions(transaction):
    suggestions = []
    tenants = Tenant.query.all()
    landlords = Landlord.query.all()

    # Prioritize suggestions based on reference code
    if transaction.reference_code:
        normalized_trans_ref = ''.join(transaction.reference_code.upper().split())
        for tenant in tenants:
            if tenant.reference_code and normalized_trans_ref == ''.join(tenant.reference_code.upper().split()):
                suggestions.append(('tenant', tenant.id, f"{tenant.name} (Exact Reference Code Match)"))
        for landlord in landlords:
            if landlord.reference_code and normalized_trans_ref == ''.join(landlord.reference_code.upper().split()):
                suggestions.append(('landlord', landlord.id, f"{landlord.name} (Exact Reference Code Match)"))

    # Suggestion based on amount (if not already suggested by reference code)
    for tenant in tenants:
        if tenant.property and tenant.property.rent_amount == transaction.amount and ('tenant', tenant.id, f"{tenant.name} (Exact Reference Code Match)") not in suggestions:
            suggestions.append(('tenant', tenant.id, f"{tenant.name} (Rent amount match)"))

    # Suggestion based on name (if not already suggested by reference code)
    for tenant in tenants:
        if difflib.get_close_matches(transaction.description, [tenant.name]) and ('tenant', tenant.id, f"{tenant.name} (Exact Reference Code Match)") not in suggestions:
            suggestions.append(('tenant', tenant.id, f"{tenant.name} (Name match)"))
    
    for landlord in landlords:
        if difflib.get_close_matches(transaction.description, [landlord.name]) and ('landlord', landlord.id, f"{landlord.name} (Exact Reference Code Match)") not in suggestions:
            suggestions.append(('landlord', landlord.id, f"{landlord.name} (Name match)"))

    return suggestions

@app.route('/uncoded')
def uncoded_transactions():
    uncoded = Transaction.query.filter(
        Transaction.status == 'uncoded',
        sa.or_(
            Transaction.reviewed == False,
            Transaction.is_bulk == True
        )
    ).all()
    tenants = Tenant.query.all()
    landlords = Landlord.query.all()
    
    transactions_with_suggestions = []
    for trans in uncoded:
        suggestions = find_suggestions(trans)
        transactions_with_suggestions.append((trans, suggestions))

    return render_template('uncoded.html', transactions_with_suggestions=transactions_with_suggestions, tenants=tenants, landlords=landlords)

@app.route('/mark_reviewed/<int:transaction_id>', methods=['POST'])
def mark_reviewed(transaction_id):
    transaction = Transaction.query.get_or_404(transaction_id)
    transaction.reviewed = True
    db.session.commit()
    flash('Transaction marked as reviewed.')
    return redirect(url_for('uncoded_transactions'))

@app.route('/mark_as_bulk/<int:transaction_id>', methods=['POST'])
def mark_as_bulk(transaction_id):
    transaction = Transaction.query.get_or_404(transaction_id)
    transaction.is_bulk = True
    db.session.commit()
    flash('Transaction marked as bulk. You can now split it.')
    return redirect(url_for('uncoded_transactions'))

@app.route('/split_transaction/<int:transaction_id>', methods=['GET', 'POST'])
def split_transaction(transaction_id):
    transaction = Transaction.query.get_or_404(transaction_id)
    if not transaction.is_bulk:
        flash('This transaction is not marked as bulk and cannot be split.', 'danger')
        return redirect(url_for('uncoded_transactions'))

    if request.method == 'POST':
        total_split_amount = 0
        i = 0
        split_transactions_data = []
        while True:
            amount_key = f'amount_{i}'
            description_key = f'description_{i}'
            category_key = f'category_{i}'
            type_key = f'type_{i}'
            target_id_key = f'target_id_{i}'

            if amount_key not in request.form:
                break

            amount = float(request.form[amount_key])
            description = request.form[description_key]
            category = request.form[category_key]
            type_ = request.form[type_key]
            target_id = int(request.form[target_id_key])

            total_split_amount += amount
            split_transactions_data.append({
                'amount': amount,
                'description': description,
                'category': category,
                'type': type_,
                'target_id': target_id
            })
            i += 1

        if abs(total_split_amount - transaction.amount) > 0.01: # Allow for floating point inaccuracies
            flash('Sum of split amounts does not match the original transaction amount.', 'danger')
            return redirect(url_for('split_transaction', transaction_id=transaction.id))

        for item in split_transactions_data:
            new_transaction = Transaction(
                date=transaction.date,
                amount=item['amount'],
                description=item['description'],
                category=item['category'],
                account_id=transaction.account_id, # Keep the same bank account
                parent_transaction_id=transaction.id,
                status='coded' # New split transactions are coded by default
            )
            if item['type'] == 'tenant':
                new_transaction.tenant_id = item['target_id']
            elif item['type'] == 'landlord':
                new_transaction.landlord_id = item['target_id']
            # Handle agency type if needed, e.g., assign to a default agency account

            db.session.add(new_transaction)
            allocate_transaction(new_transaction)

        transaction.status = 'split' # Mark original transaction as split
        db.session.commit()
        flash('Bulk transaction split successfully!', 'success')
        return redirect(url_for('uncoded_transactions'))

    tenants_query = Tenant.query.all()
    landlords_query = Landlord.query.all()
    tenants = [{'id': t.id, 'name': t.name} for t in tenants_query]
    landlords = [{'id': l.id, 'name': l.name} for l in landlords_query]
    return render_template('split_transaction.html', transaction=transaction, tenants=tenants, landlords=landlords)

@app.route('/allocate', methods=['POST'])
def allocate():
    transaction_id = request.form['transaction_id']
    allocation_type = request.form['type']
    target_id = request.form['target_id']
    notes = request.form.get('notes', '')

    transaction = Transaction.query.get(transaction_id)
    if allocation_type == 'tenant':
        transaction.tenant_id = target_id
    elif allocation_type == 'landlord':
        transaction.landlord_id = target_id

    transaction.category = request.form.get('category', 'other')
    transaction.status = 'coded'
    db.session.commit()

    allocate_transaction(transaction)

    history = AllocationHistory(transaction_id=transaction.id, allocated_to=f'{allocation_type} {target_id}', notes=notes)
    db.session.add(history)
    db.session.commit()
    log_action('allocate', f'Transaction {transaction.id} allocated to {allocation_type} {target_id}')

    flash('Transaction allocated successfully')
    return redirect(url_for('uncoded_transactions'))

from app.statement_generator import generate_monthly_statement, generate_annual_statement, generate_tenant_statement

@app.route('/tenant_statement', methods=['GET', 'POST'])
def tenant_statement():
    if request.method == 'POST':
        tenant_id = int(request.form['tenant_id'])
        start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d').date()
        end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d').date()
        file_path = generate_tenant_statement(tenant_id, start_date, end_date)
        flash('Tenant statement generated')
        return redirect(url_for('download_statement', filename=os.path.basename(file_path)))

    tenants = Tenant.query.all()
    return render_template('tenant_statement.html', tenants=tenants)
from flask import send_from_directory

@app.route('/statements', methods=['GET', 'POST'])
def statements():
    today = datetime.now().date()
    first_day_of_month = today.replace(day=1)
    last_day_of_month = (today.replace(month=today.month % 12 + 1, day=1) - timedelta(days=1))

    if request.method == 'POST':
        landlord_id = int(request.form['landlord_id'])
        statement_type = request.form['statement_type']
        
        if statement_type == 'monthly':
            start_date_str = request.form['start_date']
            end_date_str = request.form['end_date']
            
            if not start_date_str:
                start_date = first_day_of_month
            else:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            
            if not end_date_str:
                end_date = last_day_of_month
            else:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

            file_path = generate_monthly_statement(landlord_id, start_date, end_date)
            flash('Monthly statement generated')
            return redirect(url_for('download_statement', filename=os.path.basename(file_path)))
        
        elif statement_type == 'annual':
            year = int(request.form['year'])
            file_path = generate_annual_statement(landlord_id, year)
            flash('Annual statement generated')
            return redirect(url_for('download_statement', filename=os.path.basename(file_path)))

    landlords = Landlord.query.all()
    return render_template('statements.html', landlords=landlords, 
                           current_month_start=first_day_of_month.strftime('%Y-%m-%d'), 
                           current_month_end=last_day_of_month.strftime('%Y-%m-%d'))

@app.route('/download_statement/<filename>')
def download_statement(filename):
    return send_from_directory(os.path.join(app.root_path, '..', 'statements'), filename)

def generate_landlord_statement(landlord_id, start_date, end_date):
    landlord = Landlord.query.get(landlord_id)
    properties = Property.query.filter_by(landlord_id=landlord_id).all()

    transactions = Transaction.query.filter(
        Transaction.date.between(start_date, end_date),
        Transaction.landlord_id == landlord_id
    ).all()

    for prop in properties:
        tenant_trans = Transaction.query.filter(
            Transaction.date.between(start_date, end_date),
            Transaction.tenant_id.in_([t.id for t in prop.tenants.all()])
        ).all()
        transactions += tenant_trans

    opening_balance = get_opening_balance(landlord, start_date, 'landlord')
    rent_received = sum(t.amount for t in transactions if t.category == 'rent' and t.amount > 0)
    expenses = sum(abs(t.amount) for t in transactions if t.category == 'expense' and t.amount < 0)
    fees = rent_received * landlord.commission_rate
    net = rent_received - expenses - fees
    closing_balance = opening_balance + net

    pdf_path = os.path.join(app.config['STATEMENTS_FOLDER'], f'landlord_{landlord_id}_{start_date}.txt')

    with open(pdf_path, 'w') as f:
        f.write(f'Landlord Statement for {landlord.name}\nPeriod: {start_date} to {end_date}\n')
        f.write(f'Opening Balance: {opening_balance}\nRent Received: {rent_received}\n')
        f.write(f'Expenses: {expenses}\nAgency Fees: {fees}\nNet: {net}\nClosing Balance: {closing_balance}\n')

    statement = Statement(
        type='monthly',
        start_date=start_date,
        end_date=end_date,
        landlord_id=landlord_id,
        pdf_path=pdf_path
    )
    db.session.add(statement)
    db.session.commit()

@app.route('/generate_rent_charges', methods=['GET', 'POST'])
def generate_rent_charges():
    today = datetime.now().date()
    if request.method == 'POST':
        charge_date = datetime.strptime(request.form['charge_date'], '%Y-%m-%d').date()
        
        # Create a new rent charge batch
        batch = RentChargeBatch(
            description=f'Monthly rent charges for {charge_date.strftime('%Y-%m')}',
            timestamp=datetime.utcnow()
        )
        db.session.add(batch)
        db.session.commit()

        tenants = Tenant.query.filter(Tenant.property_id.isnot(None)).all()
        print(f"Found {len(tenants)} tenants with properties.")
        for tenant in tenants:
            # Determine the charge date for this tenant
            charge_month = charge_date.month
            charge_year = charge_date.year

            rent_charge_day = 1 # Default to first of the month
            if tenant.start_date:
                rent_charge_day = tenant.start_date.day
            
            # Adjust rent_charge_day if it's greater than the number of days in the charge_month
            max_days_in_month = calendar.monthrange(charge_year, charge_month)[1]
            if rent_charge_day > max_days_in_month:
                rent_charge_day = max_days_in_month

            rent_charge_date = date(charge_year, charge_month, rent_charge_day)

            # Check if a rent charge already exists for this tenant for this month
            existing_charge = Transaction.query.filter(
                Transaction.tenant_id == tenant.id,
                Transaction.category == 'rent_charge',
                db.extract('month', Transaction.date) == rent_charge_date.month,
                db.extract('year', Transaction.date) == rent_charge_date.year
            ).first()

            if existing_charge:
                flash(f'Rent charge for {tenant.name} for {rent_charge_date.strftime('%B %Y')} already exists. Skipping.')
                continue

            prop = tenant.property
            rent = prop.rent_amount
            transaction = Transaction(
                date=rent_charge_date,
                amount=rent,
                description=f'Monthly rent charge for {prop.address}',
                category='rent_charge',
                tenant_id=tenant.id,
                status='coded',
                rent_charge_batch_id=batch.id
            )
            db.session.add(transaction)
            db.session.commit()
            allocate_transaction(transaction)
        log_action('generate_rent_charges', f'Generated rent charges for {len(tenants)} tenants in batch {batch.id}')
        flash(f'Rent charges generated for {len(tenants)} tenants.')
        return redirect(url_for('rent_charge_batches'))

    return render_template('generate_rent_charges.html', today=today)

@app.route('/rent_charge_batches')
def rent_charge_batches():
    batches = RentChargeBatch.query.order_by(RentChargeBatch.timestamp.desc()).all()
    return render_template('rent_charge_batches.html', batches=batches)

@app.route('/rollback_rent_charges/<int:batch_id>', methods=['POST'])
def rollback_rent_charges(batch_id):
    batch = RentChargeBatch.query.get_or_404(batch_id)
    for transaction in batch.transactions:
        # Reverse the allocation
        if transaction.category == 'rent_charge' and transaction.tenant_id:
            tenant_account = Account.query.filter_by(tenant_id=transaction.tenant_id).first()
            if tenant_account:
                tenant_account.update_balance(transaction.amount) # Reverse the negative charge
        db.session.delete(transaction)
    db.session.delete(batch)
    db.session.commit()
    log_action('rollback_rent_charges', f'Rolled back rent charge batch {batch.id}')
    flash(f'Rent charge batch {batch.id} rolled back successfully.')
    return redirect(url_for('rent_charge_batches'))

def get_opening_balance(entity, date, type_):
    if type_ == 'landlord':
        account = Account.query.filter_by(landlord_id=entity.id).first()
    elif type_ == 'tenant':
        account = Account.query.filter_by(tenant_id=entity.id).first()
    if account:
        return account.balance
    return 0.0

@app.route('/reports')
def reports():
    unallocated = Transaction.query.filter_by(status='uncoded').count()
    tenant_accounts = Account.query.filter_by(type='tenant').all()
    landlord_accounts = Account.query.filter_by(type='landlord').all()
    agency_income = Account.query.filter_by(type='agency_income').all()
    agency_expenses = Account.query.filter_by(type='agency_expense').all()
    return render_template('reports.html', unallocated=unallocated, 
                           tenant_accounts=tenant_accounts, 
                           landlord_accounts=landlord_accounts, 
                           agency_income=agency_income,
                           agency_expenses=agency_expenses)

@app.route('/accounts')
def accounts():
    tenant_accounts = Account.query.filter_by(type='tenant').all()
    landlord_accounts = Account.query.filter_by(type='landlord').all()
    agency_accounts = Account.query.filter(Account.type.in_(['agency_income', 'agency_expense'])).all()
    return render_template('accounts.html', tenant_accounts=tenant_accounts, landlord_accounts=landlord_accounts, agency_accounts=agency_accounts)

@app.route('/agency_fees')
def agency_fees():
    agency_income_account = Account.query.filter_by(name='Agency Income').first()
    if not agency_income_account:
        flash('Agency Income account not found.', 'danger')
        return redirect(url_for('index'))
    
    fees_transactions = Transaction.query.filter(
        Transaction.account_id == agency_income_account.id,
        Transaction.category.in_(['fee', 'vat'])
    ).order_by(Transaction.date.desc()).all()

    return render_template('agency_fees.html', transactions=fees_transactions, account=agency_income_account)

@app.route('/banking')
def banking():
    bank_account = Account.query.filter_by(name='Bank Account').first()
    agency_income_account = Account.query.filter_by(name='Agency Income').first()
    agency_expense_account = Account.query.filter_by(name='Agency Expense').first()
    utility_account = Account.query.filter_by(type='utility').first()

    accounts = {
        'bank': bank_account,
        'agency_income': agency_income_account,
        'agency_expense': agency_expense_account,
        'utility': utility_account
    }

    # Fetch recent transactions for each account
    if bank_account: accounts['bank'].recent_transactions = Transaction.query.filter_by(account_id=bank_account.id).order_by(Transaction.date.desc()).limit(5).all()
    if agency_income_account: accounts['agency_income'].recent_transactions = Transaction.query.filter_by(account_id=agency_income_account.id).order_by(Transaction.date.desc()).limit(5).all()
    if agency_expense_account: accounts['agency_expense'].recent_transactions = Transaction.query.filter_by(account_id=agency_expense_account.id).order_by(Transaction.date.desc()).limit(5).all()
    if utility_account: accounts['utility'].recent_transactions = Transaction.query.filter_by(account_id=utility_account.id).order_by(Transaction.date.desc()).limit(5).all()

    return render_template('banking.html', accounts=accounts)

@app.route('/account_transactions/<int:account_id>', methods=['GET', 'POST'])
def account_transactions(account_id):
    account = Account.query.get_or_404(account_id)
    form = DateRangeForm()
    search = request.args.get('search', '')

    today = datetime.now().date()
    first_day_of_month = today.replace(day=1)
    last_day_of_month = (today.replace(month=today.month % 12 + 1, day=1) - timedelta(days=1))

    start_date = first_day_of_month
    end_date = last_day_of_month

    if form.validate_on_submit():
        start_date = form.start_date.data
        end_date = form.end_date.data

    form.start_date.data = start_date
    form.end_date.data = end_date

    query = Transaction.query.filter(
        Transaction.account_id == account.id,
        Transaction.date.between(start_date, end_date)
    )

    if search:
        query = query.filter(Transaction.description.ilike(f'%{search}%'))

    transactions = query.order_by(Transaction.date.desc()).all()

    return render_template('account_transactions.html', account=account, transactions=transactions, form=form, search=search)

@app.route('/tenants', methods=['GET'])
def tenants():
    search = request.args.get('search', '')
    if search:
        tenants = Tenant.query.filter(Tenant.name.ilike(f'%{search}%')).all()
    else:
        tenants = Tenant.query.all()
    return render_template('tenants.html', tenants=tenants, search=search)

def log_action(action, details=''):
    log = AuditLog(action=action, details=details)
    db.session.add(log)
    db.session.commit()

@app.route('/add_tenant', methods=['GET', 'POST'])
def add_tenant():
    form = AddTenantForm()
    form.property_id.choices = [(0, 'No Property')] + [(p.id, p.address) for p in Property.query.all()]
    if form.validate_on_submit():
        try:
            tenant = Tenant(name=form.name.data, email=form.email.data, phone_number=form.phone_number.data, start_date=form.start_date.data, reference_code=form.reference_code.data)
            if form.property_id.data != 0:
                tenant.property_id = form.property_id.data
            db.session.add(tenant)
            db.session.flush() # Use flush to check for integrity errors before commit

            account = Account(name=f'{tenant.name} Account', type='tenant', tenant_id=tenant.id)
            db.session.add(account)
            db.session.commit()
            log_action('add_tenant', f'Tenant {tenant.name} added')
            flash('Tenant added successfully')
            return redirect(url_for('tenants'))
        except IntegrityError:
            db.session.rollback()
            flash('Reference Code already exists. Please use a unique code.', 'danger')
            return render_template('add_tenant.html', form=form)
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"Error in {getattr(form, field).label.text}: {error}")
    return render_template('add_tenant.html', form=form)

@app.route('/quick_add_tenant/<int:trans_id>', methods=['GET', 'POST'])
def quick_add_tenant(trans_id):
    trans = Transaction.query.get_or_404(trans_id)
    form = AddTenantForm()
    form.property_id.choices = [(0, 'No Property')] + [(p.id, p.address) for p in Property.query.all()]
    # Pre-fill
    form.name.data = trans.description or ''
    form.reference_code.data = trans.reference_code or ''

    if form.validate_on_submit():
        tenant = Tenant(name=form.name.data, email=form.email.data, phone_number=form.phone_number.data, start_date=datetime.utcnow().date(), reference_code=form.reference_code.data)
        if form.property_id.data != 0:
            tenant.property_id = form.property_id.data
        db.session.add(tenant)
        db.session.commit()
        account = Account(name=f'{tenant.name} Account', type='tenant', tenant_id=tenant.id)
        db.session.add(account)
        db.session.commit()
        # Allocate the transaction to this new tenant
        trans.tenant_id = tenant.id
        trans.category = 'rent'
        trans.status = 'coded'
        db.session.commit()
        allocate_transaction(trans)
        log_action('quick_add_tenant', f'Tenant {tenant.name} added and transaction {trans.id} allocated')
        flash('Tenant added and transaction allocated')
        return redirect(url_for('uncoded_transactions'))
    return render_template('add_tenant.html', form=form, trans=trans)

@app.route('/tenant/<int:id>')
def tenant_details(id):
    tenant = Tenant.query.get_or_404(id)
    property_ = tenant.property
    return render_template('tenant_details.html', tenant=tenant, property=property_)

@app.route('/edit_tenant/<int:id>', methods=['GET', 'POST'])
def edit_tenant(id):
    tenant = Tenant.query.get_or_404(id)
    form = EditTenantForm()
    form.property_id.choices = [(0, 'No Property')] + [(p.id, p.address) for p in Property.query.all()]
    if form.validate_on_submit():
        tenant.name = form.name.data
        tenant.email = form.email.data
        tenant.phone_number = form.phone_number.data
        tenant.start_date = form.start_date.data
        tenant.reference_code = form.reference_code.data
        if form.property_id.data != 0:
            tenant.property_id = form.property_id.data
        else:
            tenant.property_id = None
        db.session.commit()
        log_action('edit_tenant', f'Tenant {tenant.name} (ID: {tenant.id}) updated')
        flash('Tenant updated successfully')
        return redirect(url_for('tenant_details', id=tenant.id))
    elif request.method == 'GET':
        form.name.data = tenant.name
        form.email.data = tenant.email
        form.phone_number.data = tenant.phone_number
        form.start_date.data = tenant.start_date
        form.reference_code.data = tenant.reference_code
        form.property_id.data = tenant.property_id if tenant.property_id else 0
    return render_template('edit_tenant.html', form=form, tenant=tenant)

@app.route('/delete_tenant/<int:id>', methods=['POST'])
def delete_tenant(id):
    tenant = Tenant.query.get_or_404(id)
    # Delete associated account
    account = Account.query.filter_by(tenant_id=tenant.id).first()
    if account:
        db.session.delete(account)
    # Disassociate transactions
    Transaction.query.filter_by(tenant_id=tenant.id).update({'tenant_id': None})
    db.session.delete(tenant)
    db.session.commit()
    log_action('delete_tenant', f'Tenant {tenant.name} (ID: {tenant.id}) deleted')
    flash('Tenant deleted successfully')
    return redirect(url_for('tenants'))

@app.route('/tenant/<int:id>/account')
def tenant_account(id):
    tenant = Tenant.query.get_or_404(id)
    account = Account.query.filter_by(tenant_id=id).first()
    if not account:
        flash('No account found for this tenant')
        return redirect(url_for('tenant_details', id=id))
    transactions = Transaction.query.filter_by(tenant_id=id).order_by(Transaction.date.desc()).all()
    return render_template('tenant_account.html', tenant=tenant, account=account, transactions=transactions)

@app.route('/charge_tenant_rent/<int:tenant_id>', methods=['POST'])
def charge_tenant_rent(tenant_id):
    tenant = Tenant.query.get_or_404(tenant_id)
    if not tenant.property:
        flash('Tenant is not associated with a property, cannot charge rent.')
        return redirect(url_for('tenant_account', id=tenant_id))

    # Determine the charge date for this tenant
    today = datetime.utcnow().date()
    charge_month = today.month
    charge_year = today.year

    rent_charge_day = 1 # Default to first of the month
    if tenant.start_date:
        rent_charge_day = tenant.start_date.day
    
    # Adjust rent_charge_day if it's greater than the number of days in the charge_month
    max_days_in_month = calendar.monthrange(charge_year, charge_month)[1]
    if rent_charge_day > max_days_in_month:
        rent_charge_day = max_days_in_month

    rent_charge_date = date(charge_year, charge_month, rent_charge_day)

    # Check if a rent charge already exists for this tenant for this month
    existing_charge = Transaction.query.filter(
        Transaction.tenant_id == tenant.id,
        Transaction.category == 'rent_charge',
        db.extract('month', Transaction.date) == charge_month,
        db.extract('year', Transaction.date) == charge_year
    ).first()

    if existing_charge:
        flash(f'Rent charge for {tenant.name} for {rent_charge_date.strftime('%B %Y')} already exists. Please delete the existing charge to re-charge.')
        return redirect(url_for('tenant_account', id=tenant_id))

    rent_amount = tenant.property.rent_amount
    transaction = Transaction(
        date=rent_charge_date,
        amount=rent_amount, # Store rent charges as positive
        description=f'Monthly rent charge for {tenant.property.address}',
        category='rent_charge',
        tenant_id=tenant.id,
        status='coded'
    )
    db.session.add(transaction)
    db.session.commit()
    allocate_transaction(transaction)
    log_action('charge_tenant_rent', f'Charged rent {rent_amount} to tenant {tenant.name} (ID: {tenant.id})')
    flash(f'Monthly rent of {rent_amount} charged to {tenant.name}.')
    return redirect(url_for('tenant_account', id=tenant_id))

@app.route('/delete_transaction_from_account/<int:transaction_id>', methods=['POST'])
def delete_transaction_from_account(transaction_id):
    transaction = Transaction.query.get_or_404(transaction_id)
    account = Account.query.get_or_404(transaction.account_id)

    # Reverse the transaction's effect on the account balance
    account.update_balance(-transaction.amount)

    db.session.delete(transaction)
    db.session.commit()
    log_action('delete_transaction', f'Transaction {transaction.id} deleted from account {account.id}. Balance updated.')
    flash('Transaction deleted successfully.')
    return redirect(url_for('account_transactions', account_id=account.id))

@app.route('/landlords', methods=['GET'])
def landlords():
    search = request.args.get('search', '')
    if search:
        landlords = Landlord.query.filter(Landlord.name.ilike(f'%{search}%')).all()
    else:
        landlords = Landlord.query.all()
    return render_template('landlords.html', landlords=landlords, search=search)

@app.route('/add_landlord', methods=['GET', 'POST'])
def add_landlord():
    form = AddLandlordForm()
    if form.validate_on_submit():
        try:
            commission = form.commission_rate.data or 0.1
            landlord = Landlord(name=form.name.data, email=form.email.data, phone_number=form.phone_number.data, address=form.address.data, bank_name=form.bank_name.data, bank_account_number=form.bank_account_number.data, bank_sort_code=form.bank_sort_code.data, reference_code=form.reference_code.data, commission_rate=commission)
            db.session.add(landlord)
            db.session.flush() # Use flush to check for integrity errors before commit

            account = Account(name=f'{landlord.name} Account', type='landlord', landlord_id=landlord.id)
            db.session.add(account)
            db.session.commit()
            log_action('add_landlord', f'Landlord {landlord.name} added')
            flash('Landlord added successfully')
            return redirect(url_for('landlords'))
        except IntegrityError:
            db.session.rollback()
            flash('Reference Code already exists. Please use a unique code.', 'danger')
            return render_template('add_landlord.html', form=form)
    return render_template('add_landlord.html', form=form)

@app.route('/add_property/<int:landlord_id>', methods=['GET', 'POST'])
def add_property(landlord_id):
    form = AddPropertyForm()
    form.landlord_id.data = landlord_id
    if form.validate_on_submit():
        property_ = Property(address=form.address.data, rent_amount=form.rent_amount.data, landlord_id=landlord_id)
        db.session.add(property_)
        db.session.commit()
        log_action('add_property', f'Property {property_.address} added')
        flash('Property added successfully')
        return redirect(url_for('landlord_details', id=landlord_id))
    return render_template('add_property.html', form=form)

@app.route('/edit_property/<int:id>', methods=['GET', 'POST'])
def edit_property(id):
    property_ = Property.query.get_or_404(id)
    form = EditPropertyForm()
    if form.validate_on_submit():
        property_.address = form.address.data
        property_.rent_amount = form.rent_amount.data
        db.session.commit()
        log_action('edit_property', f'Property {property_.address} (ID: {property_.id}) updated')
        flash('Property updated successfully')
        return redirect(url_for('landlord_details', id=property_.landlord_id))
    elif request.method == 'GET':
        form.address.data = property_.address
        form.rent_amount.data = property_.rent_amount
    return render_template('edit_property.html', form=form, property=property_)

@app.route('/delete_property/<int:id>', methods=['POST'])
def delete_property(id):
    property_ = Property.query.get_or_404(id)
    # Disassociate tenants
    for tenant in property_.tenants:
        tenant.property_id = None
    db.session.delete(property_)
    db.session.commit()
    log_action('delete_property', f'Property {property_.address} (ID: {property_.id}) deleted')
    flash('Property deleted successfully')
    return redirect(url_for('landlord_details', id=property_.landlord_id))

@app.route('/landlord/<int:id>')
def landlord_details(id):
    landlord = Landlord.query.get_or_404(id)
    properties = landlord.properties.all()
    return render_template('landlord_details.html', landlord=landlord, properties=properties)

@app.route('/edit_landlord/<int:id>', methods=['GET', 'POST'])
def edit_landlord(id):
    landlord = Landlord.query.get_or_404(id)
    form = EditLandlordForm()
    if form.validate_on_submit():
        landlord.name = form.name.data
        landlord.email = form.email.data
        landlord.phone_number = form.phone_number.data
        landlord.address = form.address.data
        landlord.bank_name = form.bank_name.data
        landlord.bank_account_number = form.bank_account_number.data
        landlord.bank_sort_code = form.bank_sort_code.data
        landlord.reference_code = form.reference_code.data
        landlord.commission_rate = form.commission_rate.data
        db.session.commit()
        log_action('edit_landlord', f'Landlord {landlord.name} (ID: {landlord.id}) updated')
        flash('Landlord updated successfully')
        return redirect(url_for('landlord_details', id=landlord.id))
    elif request.method == 'GET':
        form.name.data = landlord.name
        form.email.data = landlord.email
        form.phone_number.data = landlord.phone_number
        form.address.data = landlord.address
        form.bank_name.data = landlord.bank_name
        form.bank_account_number.data = landlord.bank_account_number
        form.bank_sort_code.data = landlord.bank_sort_code
        form.reference_code.data = landlord.reference_code
        form.commission_rate.data = landlord.commission_rate
    return render_template('edit_landlord.html', form=form, landlord=landlord)

@app.route('/delete_landlord/<int:id>', methods=['POST'])
def delete_landlord(id):
    landlord = Landlord.query.get_or_404(id)
    # Delete associated account
    account = Account.query.filter_by(landlord_id=landlord.id).first()
    if account:
        db.session.delete(account)
    # Disassociate properties and tenants
    for prop in landlord.properties:
        for tenant in prop.tenants:
            tenant.property_id = None
        prop.landlord_id = None
    Transaction.query.filter_by(landlord_id=landlord.id).update({'landlord_id': None})
    db.session.delete(landlord)
    db.session.commit()
    log_action('delete_landlord', f'Landlord {landlord.name} (ID: {landlord.id}) deleted')
    flash('Landlord deleted successfully')
    return redirect(url_for('landlords'))

@app.route('/landlord/<int:id>/account')
def landlord_account(id):
    landlord = Landlord.query.get_or_404(id)
    account = Account.query.filter_by(landlord_id=id).first()
    if not account:
        flash('No account found for this landlord')
        return redirect(url_for('landlord_details', id=id))
    transactions = Transaction.query.filter_by(landlord_id=id).order_by(Transaction.date.desc()).all()
    return render_template('landlord_account.html', landlord=landlord, account=account, transactions=transactions)

@app.route('/landlord/<int:landlord_id>/payout', methods=['GET', 'POST'])
def landlord_payout(landlord_id):
    from datetime import datetime, timedelta
    form = PayoutForm()
    if request.method == 'GET':
        today = datetime.now().date()
        first_day_of_month = today.replace(day=1)
        last_day_of_month = (today.replace(month=today.month % 12 + 1, day=1) - timedelta(days=1))
        form.start_date.data = first_day_of_month
        form.end_date.data = last_day_of_month
    if form.validate_on_submit():
        start_date = form.start_date.data
        end_date = form.end_date.data
        vat_rate = form.vat_rate.data
        try:
            process_landlord_payout(landlord_id, start_date, end_date, vat_rate)
            flash('Landlord payout processed successfully.', 'success')
        except ValueError as e:
            flash(str(e), 'danger')
        return redirect(url_for('landlord_account', id=landlord_id))
    return render_template('landlord_payout.html', form=form, landlord_id=landlord_id)

@app.route('/disburse', methods=['GET', 'POST'])
def disburse():
    if request.method == 'POST':
        landlord_id = int(request.form['landlord_id'])
        amount = float(request.form['amount'])
        disburse_date = datetime.strptime(request.form['disburse_date'], '%Y-%m-%d').date()

        landlord = Landlord.query.get(landlord_id)
        landlord_account = Account.query.filter_by(landlord_id=landlord_id).first()
        bank_account = Account.query.filter_by(name='Bank Account').first()

        if landlord_account.balance < amount:
            flash('Insufficient balance')
            return redirect(url_for('disburse'))

        transaction = Transaction(
            date=disburse_date,
            amount=-amount,  # Negative for payout
            description=f'Disbursement to {landlord.name}',
            category='payment',
            landlord_id=landlord_id,
            status='coded'
        )
        db.session.add(transaction)
        db.session.commit()
        allocate_transaction(transaction)
        log_action('disburse', f'Disbursed {amount} to {landlord.name}')
        flash('Disbursement processed')
        return redirect(url_for('landlord_account', id=landlord_id))

    landlords = Landlord.query.all()
    return render_template('disburse.html', landlords=landlords)

@app.route('/add_manual_rent', methods=['GET', 'POST'])
def add_manual_rent():
    form = ManualRentForm()
    form.tenant_id.choices = [(t.id, t.name) for t in Tenant.query.all()]
    bank_account = Account.query.filter_by(name='Bank Account').first()
    if not bank_account:
        flash('Bank Account not found. Please create it in the accounts section.')
        return redirect(url_for('banking'))
    if form.validate_on_submit():
        transaction = Transaction(
            date=form.date.data,
            amount=form.amount.data,
            description=form.description.data,
            category='rent',
            tenant_id=form.tenant_id.data,
            status='coded',
            account_id=bank_account.id # Link to bank account
        )
        db.session.add(transaction)
        # db.session.commit() # Removed this commit
        allocate_transaction(transaction)
        db.session.commit()
        flash('Manual rent payment added successfully.', 'success')
        return redirect(url_for('tenant_account', id=form.tenant_id.data))
    return render_template('add_manual_rent.html', form=form)

@app.route('/add_manual_expense', methods=['GET', 'POST'])
def add_manual_expense():
    form = ManualExpenseForm()
    form.landlord_id.choices = [(l.id, l.name) for l in Landlord.query.all()]
    bank_account = Account.query.filter_by(name='Bank Account').first()
    if not bank_account:
        flash('Bank Account not found. Please create it in the accounts section.')
        return redirect(url_for('banking'))
    if form.validate_on_submit():
        transaction = Transaction(
            date=form.date.data,
            amount=-form.amount.data,  # Expenses are negative
            description=form.description.data,
            category='expense',
            landlord_id=form.landlord_id.data,
            status='coded',
            account_id=bank_account.id # Link to bank account
        )
        db.session.add(transaction)
        # db.session.commit() # Removed this commit
        allocate_transaction(transaction)
        db.session.commit()
        flash('Manual expense added successfully.', 'success')
        return redirect(url_for('landlord_account', id=form.landlord_id.data))
    return render_template('add_manual_expense.html', form=form)

@app.route('/company', methods=['GET', 'POST'])
def company():
    company = Company.query.first()
    form = CompanyForm(obj=company)
    if form.validate_on_submit():
        if not company:
            company = Company()
            db.session.add(company)
        form.populate_obj(company)
        if form.logo.data:
            filename = secure_filename(form.logo.data.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            form.logo.data.save(file_path)
            company.logo = filename
        db.session.commit()
        flash('Company information updated successfully.')
        return redirect(url_for('company'))
    return render_template('company.html', form=form)
