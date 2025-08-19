# app/routes.py
from flask import render_template, flash, redirect, url_for, request
from werkzeug.utils import secure_filename
from app import app, db
from app.models import Tenant, Landlord, Transaction, Account, Property, AllocationHistory, Statement, AuditLog, Expense, RentChargeBatch, Company, User, Role
from datetime import datetime, timedelta, date
import os
import pandas as pd
import difflib

from app import mail
from flask_mail import Message
from app.forms import AddTenantForm, AddLandlordForm, AddPropertyForm, EditTenantForm, DeleteTenantForm, EditLandlordForm, DeleteLandlordForm, EditPropertyForm, DeletePropertyForm, PayoutForm, ManualRentForm, ManualExpenseForm, DateRangeForm, CompanyForm, LoginForm, EditUserForm
from app.payout_service import process_landlord_payout
from sqlalchemy.exc import IntegrityError
import calendar
import sqlalchemy as sa
from flask_login import login_required, login_user, logout_user, current_user
import bcrypt
from app.db_routes import role_required

ALLOWED_EXTENSIONS = {'csv'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
@app.route('/index')
@login_required
def index():
    return render_template('index.html', title='Home')

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload_file():
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
    return render_template('upload.html', title='Upload CSV')

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
            description=f'Monthly rent charges for {charge_date.strftime("%Y-%m")}',
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
                flash(f'Rent charge for {tenant.name} for {rent_charge_date.strftime("%B %Y")} already exists. Skipping.')
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
                tenant_account.update_balance(transaction.amount) # Add back the charged amount
        db.session.delete(transaction)
    
    db.session.delete(batch)
    db.session.commit()
    log_action('rollback_rent_charges', f'Rolled back rent charges for batch {batch_id}')
    flash('Rent charges rolled back successfully.')
    return redirect(url_for('rent_charge_batches'))
        