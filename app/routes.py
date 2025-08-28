# app/routes.py
from functools import wraps
from flask import render_template, flash, redirect, url_for, request, jsonify, Blueprint, send_from_directory, current_app
from urllib.parse import urlsplit
from . import db
from app.forms import (
    LoginForm, RegistrationForm, ManualExpenseForm, ManualRentForm, ChangeDateForm,
    AddTenantForm, AddLandlordForm, AddPropertyForm, EditTenantForm, DeleteTenantForm,
    EditLandlordForm, DeleteLandlordForm, EditPropertyForm, DeletePropertyForm,
    PayoutForm, DateRangeForm, CompanyForm, EditUserForm, AddAccountForm,
    StatementGenerationForm
)
from flask_login import current_user, login_user, logout_user, login_required
from app.models import (
    User, Transaction, Tenant, Landlord, Property, Account, AllocationHistory,
    Statement, AuditLog, Expense, RentChargeBatch, Company, Role
)
from werkzeug.utils import secure_filename
import os
import pandas as pd
from datetime import datetime, timedelta, date
from app.accounting_service import allocate_transaction
from sqlalchemy import or_, func, extract
from app.payout_service import process_landlord_payout
from app.statement_generator import generate_monthly_statement, generate_annual_statement, generate_tenant_statement
from sqlalchemy.exc import IntegrityError
import calendar
import sqlalchemy as sa
import difflib
from app.db_routes import role_required


main_bp = Blueprint('main', __name__)

def role_required(role_name):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or role_name not in [role.name for role in current_user.roles]:
                flash('You do not have permission to access this page.')
                return redirect(url_for('main.index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

ALLOWED_EXTENSIONS = {'csv'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def log_action(action, details=''):
    log = AuditLog(action=action, user_id=current_user.id, details=details)
    db.session.add(log)
    db.session.commit()

@main_bp.route('/admin/recalculate-balances/<int:account_id>')
@main_bp.route('/admin/recalculate-balances')
@login_required
@role_required('admin')
def recalculate_balances(account_id=None):
    """
    Temporary route to recalculate all account balances.
    """
    try:
        if account_id:
            accounts = [Account.query.get_or_404(account_id)]
        else:
            accounts = Account.query.all()
        
        for account in accounts:
            if account.name == 'Master Bank Account':
                continue # Calculate this last

            balance = 0
            if account.tenant_id:
                rent_charges = db.session.query(func.sum(Transaction.amount)).filter(Transaction.tenant_id == account.tenant_id, Transaction.category == 'rent_charge').scalar() or 0
                rent_paid = db.session.query(func.sum(Transaction.amount)).filter(Transaction.tenant_id == account.tenant_id, Transaction.category == 'rent').scalar() or 0
                balance = rent_paid + rent_charges
            elif account.landlord_id:
                balance = db.session.query(func.sum(Transaction.amount)).filter(Transaction.landlord_id == account.landlord_id).scalar() or 0
            else:
                balance = db.session.query(func.sum(Transaction.amount)).filter(Transaction.account_id == account.id).scalar() or 0.0
            
            account.balance = balance

        master_bank = Account.query.filter_by(name='Master Bank Account').first()
        if master_bank and (not account_id or master_bank.id == account_id):
            total_bank_amount = db.session.query(func.sum(Transaction.amount)).filter(Transaction.account_id == master_bank.id).scalar() or 0.0
            master_bank.balance = total_bank_amount

        db.session.commit()
        flash('All account balances have been successfully recalculated.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'An error occurred during recalculation: {str(e)}', 'danger')
        
    return redirect(url_for('main.accounts'))

@main_bp.route('/')
@main_bp.route('/index')
@login_required
def index():
    return render_template('index.html', title='Home')

@main_bp.route('/upload', methods=['GET', 'POST'])
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
            file_path = os.path.join(os.getcwd(), 'app', 'uploads', filename)
            file.save(file_path)
            messages = process_csv(file_path)
            for message in messages:
                flash(message)
            recalculate_balances(account_id=Account.query.filter_by(name='Master Bank Account').first().id)
            return redirect(url_for('main.uncoded_transactions'))
    return render_template('upload.html', title='Upload CSV')

def process_csv(file_path):
    messages = []
    bank_account = Account.query.filter_by(name='Master Bank Account').first()
    if not bank_account:
        messages.append('Bank Account not found. Please create it in the accounts section.')
        return messages

    try:
        df = pd.read_csv(file_path)
        for index, row in df.iterrows():
            try:
                date_str = row.get('Date', row.get('date'))
                if not isinstance(date_str, str) or pd.isna(date_str):
                    continue

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
                        continue

                if amount == 0:
                    continue

                transaction = Transaction(
                    date=date,
                    amount=amount,
                    description=description,
                    reference_code=reference_code,
                    account_id=bank_account.id
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
                messages.append(f"Error processing row {index}: {str(e)}")
                continue
        db.session.commit()
        messages.append(f'{len(df)} transactions processed successfully.')

    except Exception as e:
        messages.append(f'Error processing CSV: {str(e)}')
    
    return messages

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
    text = ''.join(raw_text.upper().split())

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

    if transaction.amount > 0:
        for tenant in tenants:
            if tenant.name:
                name_norm = ''.join(tenant.name.upper().split())
                name_score = get_partial_ratio(text, name_norm)
                if name_score >= 85:
                    transaction.category = 'rent'
                    return True, 'tenant', tenant.id

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

def get_suggestions(transaction):
    suggestions = []
    tenants = Tenant.query.all()
    landlords = Landlord.query.all()

    raw_text = ((transaction.description or '') + ' ' + (transaction.reference_code or ''))
    text = ''.join(raw_text.upper().split())

    # Tenant suggestions
    for tenant in tenants:
        if tenant.name:
            name_norm = ''.join(tenant.name.upper().split())
            name_score = get_partial_ratio(text, name_norm)
            if name_score >= 85:
                suggestions.append(('tenant', tenant.id, f"Tenant: {tenant.name} (Name Match: {name_score:.2f}%)"))
        if tenant.reference_code:
            ref_norm = ''.join(tenant.reference_code.upper().split())
            ref_score = get_partial_ratio(text, ref_norm)
            if ref_score >= 85:
                suggestions.append(('tenant', tenant.id, f"Tenant: {tenant.name} (Ref Match: {ref_score:.2f}%)"))

    # Landlord suggestions
    for landlord in landlords:
        if landlord.name:
            name_norm = ''.join(landlord.name.upper().split())
            name_score = get_partial_ratio(text, name_norm)
            if name_score >= 85:
                suggestions.append(('landlord', landlord.id, f"Landlord: {landlord.name} (Name Match: {name_score:.2f}%)"))
        if landlord.reference_code:
            ref_norm = ''.join(landlord.reference_code.upper().split())
            ref_score = get_partial_ratio(text, ref_norm)
            if ref_score >= 85:
                suggestions.append(('landlord', landlord.id, f"Landlord: {landlord.name} (Ref Match: {ref_score:.2f}%)"))

    return suggestions

@main_bp.route('/uncoded')
@login_required
def uncoded_transactions():
    uncoded = Transaction.query.filter_by(status='uncoded').all()
    tenants = Tenant.query.all()
    landlords = Landlord.query.all()
    transactions_with_suggestions = [(trans, get_suggestions(trans)) for trans in uncoded]
    return render_template('uncoded.html', transactions_with_suggestions=transactions_with_suggestions, tenants=tenants, landlords=landlords)

@main_bp.route('/allocate', methods=['POST'])
@login_required
def allocate():
    transaction_id = request.form['transaction_id']
    allocation_type = request.form['type']
    target_id = request.form['target_id']
    
    transaction = Transaction.query.get(transaction_id)
    if allocation_type == 'tenant':
        transaction.tenant_id = target_id
        transaction.category = 'rent'
    elif allocation_type == 'landlord':
        transaction.landlord_id = target_id
        transaction.category = 'expense'

    transaction.status = 'coded'
    allocate_transaction(transaction)
    db.session.commit()
    recalculate_balances(account_id=Account.query.filter_by(name='Master Bank Account').first().id)
    recalculate_balances(account_id=transaction.account_id)

    flash('Transaction allocated successfully')
    return redirect(url_for('main.uncoded_transactions'))

@main_bp.route('/statements', methods=['GET', 'POST'])
@login_required
def statements():
    form = StatementGenerationForm()
    landlords = Landlord.query.all()
    form.landlord_id.choices = [(l.id, l.name) for l in landlords]
    if form.validate_on_submit():
        landlord_id = form.landlord_id.data
        statement_type = form.statement_type.data
        
        if statement_type == 'monthly':
            start_date = form.start_date.data
            end_date = form.end_date.data
            vat_rate = form.vat_rate.data
            file_path, error = generate_monthly_statement(landlord_id, start_date, end_date, vat_rate)
            if error:
                flash(error, 'danger')
            else:
                flash('Monthly statement generated')
                return redirect(url_for('main.download_statement', filename=os.path.basename(file_path)))
        
        elif statement_type == 'annual':
            year = form.year.data
            file_path, error = generate_annual_statement(landlord_id, year)
            if error:
                flash(error, 'danger')
            else:
                flash('Annual statement generated')
                return redirect(url_for('main.download_statement', filename=os.path.basename(file_path)))

    return render_template('statements.html', landlords=landlords, form=form)

@main_bp.route('/tenant_statement', methods=['GET', 'POST'])
@login_required
def tenant_statement():
    if request.method == 'POST':
        tenant_id = int(request.form['tenant_id'])
        start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d').date()
        end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d').date()
        file_path, error = generate_tenant_statement(tenant_id, start_date, end_date)
        if error:
            flash(error, 'danger')
        else:
            flash('Tenant statement generated')
            return redirect(url_for('main.download_statement', filename=os.path.basename(file_path)))
    
    tenants = Tenant.query.all()
    return render_template('tenant_statement.html', tenants=tenants)

@main_bp.route('/generate_rent_charges', methods=['GET', 'POST'])
@login_required
def generate_rent_charges():
    if request.method == 'POST':
        charge_date = datetime.strptime(request.form['charge_date'], '%Y-%m-%d').date()
        batch = RentChargeBatch(description=f'Monthly rent charges for {charge_date.strftime("%Y-%m")}')
        db.session.add(batch)
        db.session.commit()

        tenants = Tenant.query.filter(Tenant.property_id.isnot(None)).all()
        for tenant in tenants:
            existing_charge = Transaction.query.filter(
                Transaction.tenant_id == tenant.id,
                Transaction.category == 'rent_charge',
                extract('month', Transaction.date) == charge_date.month,
                extract('year', Transaction.date) == charge_date.year
            ).first()

            if not existing_charge and tenant.property:
                rent_charge = Transaction(
                    date=charge_date,
                    amount=-abs(tenant.property.rent_amount),
                    description=f'Monthly rent for {tenant.property.address}',
                    category='rent_charge',
                    tenant_id=tenant.id,
                    status='coded',
                    rent_charge_batch_id=batch.id
                )
                db.session.add(rent_charge)
                allocate_transaction(rent_charge)
        
        db.session.commit()
        flash(f'Rent charges generated for {len(tenants)} tenants.')
        return redirect(url_for('main.rent_charge_batches'))
    
    return render_template('generate_rent_charges.html', today=date.today())

@main_bp.route('/rent_charge_batches')
@login_required
def rent_charge_batches():
    batches = RentChargeBatch.query.order_by(RentChargeBatch.timestamp.desc()).all()
    return render_template('rent_charge_batches.html', batches=batches)

@main_bp.route('/rollback_rent_charges/<int:batch_id>', methods=['POST'])
@login_required
def rollback_rent_charges(batch_id):
    batch = RentChargeBatch.query.get_or_404(batch_id)
    for transaction in batch.transactions:
        if transaction.tenant_id:
            tenant_account = Account.query.filter_by(tenant_id=transaction.tenant_id).first()
            if tenant_account:
                tenant_account.update_balance(-transaction.amount)
        db.session.delete(transaction)
    
    db.session.delete(batch)
    db.session.commit()
    flash('Rent charges batch rolled back successfully.')
    return redirect(url_for('main.rent_charge_batches'))

@main_bp.route('/download_statement/<filename>')
@login_required
def download_statement(filename):
    directory = os.path.abspath(os.path.join(os.getcwd(), 'statements'))
    return send_from_directory(directory, filename)

@main_bp.route('/accounts')
@login_required
def accounts():
    main_accounts = Account.query.filter(Account.tenant_id.is_(None), Account.landlord_id.is_(None)).order_by(Account.name).all()
    return render_template('accounts.html', accounts=main_accounts)

@main_bp.route('/account_transactions/<int:account_id>')
@login_required
def account_transactions(account_id):
    account = Account.query.get_or_404(account_id)
    form = DateRangeForm()
    transactions = Transaction.query.filter_by(account_id=account.id).order_by(Transaction.date.desc()).all()
    return render_template('account_transactions.html', account=account, transactions=transactions, form=form)

@main_bp.route('/add_account', methods=['GET', 'POST'])
@login_required
def add_account():
    form = AddAccountForm()
    if form.validate_on_submit():
        account = Account(name=form.name.data, type=form.type.data)
        db.session.add(account)
        db.session.commit()
        flash('Account created successfully!', 'success')
        return redirect(url_for('main.accounts'))
    return render_template('add_account.html', form=form)

@main_bp.route('/delete_transaction_from_account/<int:transaction_id>', methods=['POST'])
@login_required
def delete_transaction_from_account(transaction_id):
    transaction = Transaction.query.get_or_404(transaction_id)
    account_id = transaction.account_id
    tenant_id = transaction.tenant_id
    landlord_id = transaction.landlord_id

    # Reverse amounts from other affected accounts if necessary
    if transaction.category == 'fee':
        agency_income_account = Account.query.filter_by(name='Agency Income').first()
        if agency_income_account:
            agency_income_account.update_balance(-transaction.amount) # Reverse the fee
    elif transaction.category == 'vat':
        vat_account = Account.query.filter_by(name='VAT Account').first()
        if vat_account:
            vat_account.update_balance(-transaction.amount) # Reverse the VAT
    elif transaction.category == 'payout':
        landlord_payments_account = Account.query.filter_by(name='Landlord Payments').first()
        if landlord_payments_account:
            landlord_payments_account.update_balance(-transaction.amount) # Reverse the payout

    db.session.delete(transaction)
    db.session.commit()

    if account_id:
        recalculate_balances(account_id=account_id)
    if tenant_id:
        tenant_account = Account.query.filter_by(tenant_id=tenant_id).first()
        if tenant_account:
            recalculate_balances(account_id=tenant_account.id)
    if landlord_id:
        landlord_account = Account.query.filter_by(landlord_id=landlord_id).first()
        if landlord_account:
            recalculate_balances(account_id=landlord_account.id)

    # Recalculate balances for other affected accounts
    if transaction.category == 'fee':
        recalculate_balances(account_id=Account.query.filter_by(name='Agency Income').first().id)
    elif transaction.category == 'vat':
        recalculate_balances(account_id=Account.query.filter_by(name='VAT Account').first().id)
    elif transaction.category == 'payout':
        recalculate_balances(account_id=Account.query.filter_by(name='Landlord Payments').first().id)

    flash('Transaction deleted successfully!', 'success')

    if tenant_id:
        return redirect(url_for('main.tenant_account', id=tenant_id))
    elif landlord_id:
        return redirect(url_for('main.landlord_account', id=landlord_id))
    elif account_id:
        return redirect(url_for('main.account_transactions', account_id=account_id))
    else:
        return redirect(url_for('main.banking'))

@main_bp.route('/tenants')
@login_required
def tenants():
    tenants = Tenant.query.all()
    return render_template('tenants.html', tenants=tenants)

@main_bp.route('/tenant_details/<int:id>')
@login_required
def tenant_details(id):
    tenant = Tenant.query.get_or_404(id)
    property = tenant.property
    return render_template('tenant_details.html', tenant=tenant, property=property)

@main_bp.route('/add_tenant', methods=['GET', 'POST'])
@login_required
def add_tenant():
    form = AddTenantForm()
    form.property_id.choices = [(p.id, p.address) for p in Property.query.all()]
    if form.validate_on_submit():
        try:
            tenant = Tenant(
                name=form.name.data,
                email=form.email.data,
                phone_number=form.phone_number.data,
                start_date=form.start_date.data,
                reference_code=form.reference_code.data,
                property_id=form.property_id.data
            )
            db.session.add(tenant)
            db.session.flush()
            account = Account(name=f'{tenant.name} Account', type='tenant', tenant_id=tenant.id)
            db.session.add(account)
            db.session.commit()
            flash('Tenant added successfully!', 'success')
            return redirect(url_for('main.tenants'))
        except IntegrityError:
            db.session.rollback()
            flash('A tenant with that reference code already exists.', 'danger')
    return render_template('add_tenant.html', form=form)

@main_bp.route('/tenant/<int:id>/account')
@login_required
def tenant_account(id):
    tenant = Tenant.query.get_or_404(id)
    account = Account.query.filter_by(tenant_id=id).first_or_404()
    transactions = Transaction.query.filter_by(tenant_id=id).order_by(Transaction.date.desc()).all()
    return render_template('tenant_account.html', tenant=tenant, account=account, transactions=transactions)

@main_bp.route('/edit_tenant/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_tenant(id):
    tenant = Tenant.query.get_or_404(id)
    form = EditTenantForm(obj=tenant)
    form.property_id.choices = [(p.id, p.address) for p in Property.query.all()]
    if form.validate_on_submit():
        form.populate_obj(tenant)
        db.session.commit()
        flash('Tenant updated successfully!', 'success')
        return redirect(url_for('main.tenant_details', id=tenant.id))
    return render_template('edit_tenant.html', form=form, tenant=tenant)

@main_bp.route('/delete_tenant/<int:id>', methods=['POST'])
@login_required
def delete_tenant(id):
    tenant = Tenant.query.get_or_404(id)
    db.session.delete(tenant)
    db.session.commit()
    flash('Tenant deleted successfully!', 'success')
    return redirect(url_for('main.tenants'))

@main_bp.route('/landlords')
@login_required
def landlords():
    landlords = Landlord.query.all()
    return render_template('landlords.html', landlords=landlords)

@main_bp.route('/landlord_details/<int:id>')
@login_required
def landlord_details(id):
    landlord = Landlord.query.get_or_404(id)
    properties = landlord.properties.all()
    return render_template('landlord_details.html', landlord=landlord, properties=properties)

@main_bp.route('/add_landlord', methods=['GET', 'POST'])
@login_required
def add_landlord():
    form = AddLandlordForm()
    if form.validate_on_submit():
        try:
            landlord = Landlord(
                name=form.name.data,
                email=form.email.data,
                phone_number=form.phone_number.data,
                address=form.address.data,
                bank_name=form.bank_name.data,
                bank_account_number=form.bank_account_number.data,
                bank_sort_code=form.bank_sort_code.data,
                reference_code=form.reference_code.data,
                commission_rate=form.commission_rate.data
            )
            db.session.add(landlord)
            db.session.flush()  # Get landlord ID for account creation
            account = Account(name=f'{landlord.name} Account', type='landlord', landlord_id=landlord.id)
            db.session.add(account)
            db.session.commit()
            flash('Landlord added successfully!', 'success')
            return redirect(url_for('main.landlords'))
        except IntegrityError:
            db.session.rollback()
            flash('A landlord with that reference code already exists.', 'danger')
    return render_template('add_landlord.html', form=form)

@main_bp.route('/edit_landlord/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_landlord(id):
    landlord = Landlord.query.get_or_404(id)
    form = EditLandlordForm(obj=landlord)
    if form.validate_on_submit():
        form.populate_obj(landlord)
        db.session.commit()
        flash('Landlord updated successfully!', 'success')
        return redirect(url_for('main.landlord_details', id=landlord.id))
    return render_template('edit_landlord.html', form=form, landlord=landlord)

@main_bp.route('/delete_landlord/<int:id>', methods=['POST'])
@login_required
def delete_landlord(id):
    landlord = Landlord.query.get_or_404(id)
    db.session.delete(landlord)
    db.session.commit()
    flash('Landlord deleted successfully!', 'success')
    return redirect(url_for('main.landlords'))

@main_bp.route('/add_property/<int:landlord_id>', methods=['GET', 'POST'])
@login_required
def add_property(landlord_id):
    form = AddPropertyForm()
    form.utility_account_id.choices = [(a.id, a.name) for a in Account.query.filter_by(type='utility').all()]
    if form.validate_on_submit():
        property = Property(
            address=form.address.data,
            rent_amount=form.rent_amount.data,
            landlord_portion=form.landlord_portion.data,
            landlord_id=landlord_id,
            utility_account_id=form.utility_account_id.data
        )
        db.session.add(property)
        db.session.commit()
        flash('Property added successfully!', 'success')
        return redirect(url_for('main.landlord_details', id=landlord_id))
    return render_template('add_property.html', form=form, landlord_id=landlord_id)

@main_bp.route('/edit_property/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_property(id):
    property = Property.query.get_or_404(id)
    form = EditPropertyForm(obj=property)
    form.utility_account_id.choices = [(a.id, a.name) for a in Account.query.filter_by(type='utility').all()]
    if form.validate_on_submit():
        form.populate_obj(property)
        db.session.commit()
        flash('Property updated successfully!', 'success')
        return redirect(url_for('main.landlord_details', id=property.landlord_id))
    return render_template('edit_property.html', form=form, property=property)

@main_bp.route('/delete_property/<int:id>', methods=['POST'])
@login_required
def delete_property(id):
    property = Property.query.get_or_404(id)
    landlord_id = property.landlord_id
    db.session.delete(property)
    db.session.commit()
    flash('Property deleted successfully!', 'success')
    return redirect(url_for('main.landlord_details', id=landlord_id))

@main_bp.route('/landlord/<int:landlord_id>/payout', methods=['GET', 'POST'])
@login_required
def landlord_payout(landlord_id):
    form = PayoutForm()
    landlord = Landlord.query.get_or_404(landlord_id)
    if form.validate_on_submit():
        start_date = form.start_date.data
        end_date = form.end_date.data
        vat_rate = form.vat_rate.data
        try:
            process_landlord_payout(landlord_id, start_date, end_date, vat_rate)
            flash('Landlord payout processed successfully.', 'success')
        except ValueError as e:
            flash(str(e), 'danger')
        return redirect(url_for('main.landlord_account', id=landlord_id))
    
    if request.method == 'GET':
        today = date.today()
        first_day_of_month = today.replace(day=1)
        last_day_of_month = first_day_of_month.replace(day=calendar.monthrange(today.year, today.month)[1])
        form.start_date.data = first_day_of_month
        form.end_date.data = last_day_of_month

    return render_template('landlord_payout.html', form=form, landlord=landlord)

@main_bp.route('/landlord/<int:id>/account')
@login_required
def landlord_account(id):
    landlord = Landlord.query.get_or_404(id)
    account = Account.query.filter_by(landlord_id=id).first_or_404()
    balance = account.balance

    # Get tenant_ids for all properties of the landlord
    tenant_ids = [tenant.id for prop in landlord.properties for tenant in prop.tenants]

    # Query for transactions related to the landlord
    transactions_query = Transaction.query.filter(
        or_(
            Transaction.landlord_id == id,
            Transaction.tenant_id.in_(tenant_ids)
        )
    )

    # Filter out original rent transactions that have been split and rent_charge transactions
    all_transactions = transactions_query.filter(Transaction.category != 'rent_charge').order_by(Transaction.date.desc()).all()
    
    final_transactions = []
    for t in all_transactions:
        # If a transaction is a 'rent' transaction and has children, skip it
        if t.category == 'rent' and t.child_transactions.count() > 0:
            continue
        final_transactions.append(t)

    return render_template('landlord_account.html', landlord=landlord, account=account, balance=balance, transactions=final_transactions)

@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is None or not user.check_password(form.password.data):
            flash('Invalid username or password')
            return redirect(url_for('main.login'))
        login_user(user, remember=form.remember_me.data)
        next_page = request.args.get('next')
        if not next_page or urlsplit(next_page).netloc != '':
            next_page = url_for('main.index')
        return redirect(next_page)
    return render_template('login.html', title='Sign In', form=form)

@main_bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('main.index'))

@main_bp.route('/admin')
@login_required
@role_required('admin')
def admin():
    return render_template('admin.html')

@main_bp.route('/banking', methods=['GET', 'POST'])
@login_required
def banking():
    form = DateRangeForm()
    bank_account = Account.query.filter_by(name='Master Bank Account').first()
    
    if not bank_account:
        flash('Master Bank Account not found.', 'danger')
        return render_template('banking.html', transactions=None, balance=0, form=form, search='')

    query = Transaction.query.filter(
        Transaction.account_id == bank_account.id
    )

    search_term = request.form.get('search', '')
    if form.validate_on_submit() or request.method == 'POST':
        start_date = form.start_date.data
        end_date = form.end_date.data
        
        if start_date:
            query = query.filter(Transaction.date >= start_date)
        if end_date:
            query = query.filter(Transaction.date <= end_date)
        if search_term:
            query = query.filter(Transaction.description.ilike(f'%{search_term}%'))
    
    transactions = query.order_by(Transaction.date.desc()).all()
    
    balance = bank_account.balance

    return render_template('banking.html', transactions=transactions, balance=balance, form=form, search=search_term)

@main_bp.route('/delete_transaction/<int:transaction_id>', methods=['POST'])
@login_required
def delete_transaction(transaction_id):
    transaction = Transaction.query.get_or_404(transaction_id)
    account_id = transaction.account_id
    db.session.delete(transaction)
    db.session.commit()
    recalculate_balances(account_id=account_id)
    flash('Transaction deleted successfully!', 'success')
    return redirect(url_for('main.banking'))

@main_bp.route('/admin/export_db')
@login_required
@role_required('admin')
def export_db():
    try:
        project_root = os.path.abspath(os.path.join(current_app.root_path, '..'))
        backups_dir = os.path.join(project_root, 'backups')
        os.makedirs(backups_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        db_uri = current_app.config['SQLALCHEMY_DATABASE_URI']
        if db_uri.startswith('postgresql'):
            backup_file = os.path.join(backups_dir, f"backup_{timestamp}.dump")
            from urllib.parse import urlparse
            result = urlparse(db_uri)
            username = result.username
            password = result.password
            database = result.path[1:]
            host = result.hostname
            port = result.port or 5432
            os.environ['PGPASSWORD'] = password
            command = [r'C:\Program Files\PostgreSQL\17\bin\pg_dump', '-U', username, '-h', host, '-p', str(port), '-F', 'c', '-b', '-v', '-f', backup_file, database]
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = process.communicate()
            if process.returncode == 0:
                flash('Database exported successfully!', 'success')
                return send_from_directory(backups_dir, os.path.basename(backup_file), as_attachment=True)
            else:
                flash(f'Error exporting database: {stderr.decode()}', 'danger')
        elif db_uri.startswith('sqlite'):
            db_path = db_uri.split('sqlite:///')[-1]
            backup_file_path = os.path.join(backups_dir, f"backup_{timestamp}.db")
            import shutil
            shutil.copyfile(db_path, backup_file_path)
            flash('Database exported successfully!', 'success')
            return send_from_directory(backups_dir, os.path.basename(backup_file_path), as_attachment=True)
        else:
            flash('Unsupported database type for export.', 'danger')
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
    finally:
        if 'PGPASSWORD' in os.environ:
            del os.environ['PGPASSWORD']
    return redirect(url_for('main.admin'))

@main_bp.route('/admin/import_db', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def import_db():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part', 'danger')
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            flash('No selected file', 'danger')
            return redirect(request.url)
        if file:
            try:
                project_root = os.path.abspath(os.path.join(current_app.root_path, '..'))
                uploads_dir = os.path.join(project_root, 'uploads')
                os.makedirs(uploads_dir, exist_ok=True)
                backup_file_path = os.path.join(uploads_dir, secure_filename(file.filename))
                file.save(backup_file_path)
                db_uri = current_app.config['SQLALCHEMY_DATABASE_URI']
                if db_uri.startswith('postgresql'):
                    from urllib.parse import urlparse
                    result = urlparse(db_uri)
                    username = result.username
                    password = result.password
                    database = result.path[1:]
                    host = result.hostname
                    port = result.port or 5432
                    os.environ['PGPASSWORD'] = password
                    terminate_command = [r'C:\Program Files\PostgreSQL\17\bin\psql', '-U', username, '-h', host, '-p', str(port), '-d', 'postgres', '-c', f"SELECT pg_terminate_backend(pg_stat_activity.pid) FROM pg_stat_activity WHERE pg_stat_activity.datname = '{database}' AND pid <> pg_backend_pid();"]
                    terminate_process = subprocess.Popen(terminate_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    term_stdout, term_stderr = terminate_process.communicate()
                    if terminate_process.returncode != 0:
                        flash(f'Error terminating existing database connections: {term_stderr.decode()}', 'danger')
                        return redirect(url_for('main.admin'))
                    command = [r'C:\Program Files\PostgreSQL\17\bin\pg_restore', '-U', username, '-h', host, '-p', str(port), '-d', database, '--clean', '--if-exists', '-v', backup_file_path]
                    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    stdout, stderr = process.communicate()
                    if process.returncode == 0:
                        flash('Database imported successfully!', 'success')
                    else:
                        flash(f'Error importing database: {stderr.decode()}', 'danger')
                elif db_uri.startswith('sqlite'):
                    db.session.remove()
                    db.engine.dispose()
                    db_path = db_uri.split('sqlite:///')[-1]
                    import shutil
                    shutil.copyfile(backup_file_path, db_path)
                    flash('Database imported successfully!', 'success')
                else:
                    flash('Unsupported database type for import.', 'danger')
            except Exception as e:
                flash(f'An error occurred: {str(e)}', 'danger')
            finally:
                if 'PGPASSWORD' in os.environ:
                    del os.environ['PGPASSWORD']
                if os.path.exists(backup_file_path):
                    os.remove(backup_file_path)
            return redirect(url_for('main.admin'))
    return render_template('import_db.html')

@main_bp.route('/admin/reset_data', methods=['POST'])
@login_required
@role_required('admin')
def admin_reset_data():
    try:
        db.session.execute(sa.text("UPDATE property SET utility_account_id = NULL"))
        db.session.commit()
        AllocationHistory.query.delete()
        Transaction.query.delete()
        Statement.query.delete()
        Expense.query.delete()
        RentChargeBatch.query.delete()
        Account.query.delete()
        Tenant.query.delete()
        Property.query.delete()
        Landlord.query.delete()
        db.session.commit()
        flash('All data has been deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'An error occurred while deleting data: {str(e)}', 'danger')
    return redirect(url_for('main.admin'))

@main_bp.route('/agency_fees')
@login_required
def agency_fees():
    agency_income_account = Account.query.filter_by(name='Agency Income').first()
    if not agency_income_account:
        flash('Agency Income account not found.', 'danger')
        return redirect(url_for('main.index'))
    
    fees_transactions = Transaction.query.filter(
        Transaction.account_id == agency_income_account.id,
        Transaction.category.in_(['fee', 'vat'])
    ).order_by(Transaction.date.desc()).all()

    return render_template('agency_fees.html', transactions=fees_transactions, account=agency_income_account)

@main_bp.route('/view_statements')
@login_required
def view_statements():
    statements = Statement.query.order_by(Statement.date_generated.desc()).all()
    return render_template('view_statements.html', statements=statements)

@main_bp.route('/statements/download/<int:statement_id>')
@login_required
def download_generated_statement(statement_id):
    statement = Statement.query.get_or_404(statement_id)
    return send_from_directory(os.path.abspath('statements'), os.path.basename(statement.pdf_path), as_attachment=True)

@main_bp.route('/add_manual_rent', methods=['GET', 'POST'])
@login_required
def add_manual_rent():
    form = ManualRentForm()
    form.tenant_id.choices = [(t.id, t.name) for t in Tenant.query.all()]
    bank_account = Account.query.filter_by(name='Master Bank Account').first()
    if not bank_account:
        flash('Bank Account not found. Please create it in the accounts section.')
        return redirect(url_for('main.banking'))
    if form.validate_on_submit():
        transaction = Transaction(
            date=form.date.data,
            amount=form.amount.data,
            description=form.description.data,
            reference_code=form.reference_code.data,
            category='rent',
            tenant_id=form.tenant_id.data,
            status='coded',
            account_id=bank_account.id
        )
        db.session.add(transaction)
        allocate_transaction(transaction)
        db.session.commit()
        recalculate_balances(account_id=bank_account.id)
        recalculate_balances(account_id=transaction.tenant.accounts.first().id)
        flash('Manual rent payment added successfully.', 'success')
        return redirect(url_for('main.tenant_account', id=form.tenant_id.data))
    return render_template('add_manual_rent.html', form=form)

@main_bp.route('/add_manual_expense', methods=['GET', 'POST'])
@login_required
def add_manual_expense():
    form = ManualExpenseForm()
    form.landlord_id.choices = [(l.id, l.name) for l in Landlord.query.all()]
    bank_account = Account.query.filter_by(name='Master Bank Account').first()
    if not bank_account:
        flash('Bank Account not found. Please create it in the accounts section.')
        return redirect(url_for('main.banking'))
    if form.validate_on_submit():
        transaction = Transaction(
            date=form.date.data,
            amount=-form.amount.data,
            description=form.description.data,
            reference_code=form.reference_code.data,
            category='expense',
            landlord_id=form.landlord_id.data,
            status='coded',
            account_id=bank_account.id
        )
        db.session.add(transaction)
        allocate_transaction(transaction)
        db.session.commit()
        recalculate_balances(account_id=bank_account.id)
        recalculate_balances(account_id=transaction.landlord.accounts.first().id)
        flash('Manual expense added successfully.', 'success')
        return redirect(url_for('main.landlord_account', id=form.landlord_id.data))
    return render_template('add_manual_expense.html', form=form)

@main_bp.route('/reports')
@login_required
def reports():
    return render_template('reports.html')

@main_bp.route('/company', methods=['GET', 'POST'])
@login_required
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
            file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            form.logo.data.save(file_path)
            company.logo = filename
        db.session.commit()
        flash('Company information updated successfully.')
        return redirect(url_for('main.company'))
    return render_template('company.html', form=form)

@main_bp.route('/change_date', methods=['GET', 'POST'])
@login_required
def change_date():
    form = ChangeDateForm()
    if form.validate_on_submit():
        new_date = form.date.data
        # Here you would add logic to handle the date change
        flash(f'Date changed to {new_date}.')
        return redirect(url_for('main.index'))
    return render_template('change_date.html', form=form)

@main_bp.route('/admin/users')
@login_required
@role_required('admin')
def manage_users():
    users = User.query.all()
    return render_template('manage_users.html', users=users)

@main_bp.route('/register', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data, email=form.email.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('Congratulations, you have registered a new user!')
        return redirect(url_for('main.manage_users'))
    return render_template('register.html', title='Register', form=form)

@main_bp.route('/quick_add_tenant/<int:trans_id>')
@login_required
def quick_add_tenant(trans_id):
    # Placeholder for quick add tenant functionality
    flash('Quick add tenant functionality is not yet implemented.', 'info')
    return redirect(url_for('main.uncoded_transactions'))

@main_bp.route('/mark_reviewed/<int:transaction_id>', methods=['POST'])
@login_required
def mark_reviewed(transaction_id):
    # Placeholder for mark reviewed functionality
    flash('Mark reviewed functionality is not yet implemented.', 'info')
    return redirect(url_for('main.uncoded_transactions'))

@main_bp.route('/mark_as_bulk/<int:transaction_id>', methods=['POST'])
@login_required
def mark_as_bulk(transaction_id):
    # Placeholder for mark as bulk functionality
    flash('Mark as bulk functionality is not yet implemented.', 'info')
    return redirect(url_for('main.uncoded_transactions'))

@main_bp.route('/split_transaction/<int:transaction_id>')
@login_required
def split_transaction(transaction_id):
    # Placeholder for split transaction functionality
    flash('Split transaction functionality is not yet implemented.', 'info')
    return redirect(url_for('main.uncoded_transactions'))

@main_bp.route('/coded', methods=['GET', 'POST'])
@login_required
def coded_transactions():
    form = DateRangeForm()
    query = Transaction.query.filter(
        or_(Transaction.tenant_id.isnot(None), Transaction.landlord_id.isnot(None)),
        Transaction.parent_transaction_id.is_(None),
        Transaction.category.notin_(['rent_charge', 'fee', 'vat', 'payout'])
    )

    search_term = ''
    if request.method == 'POST':
        search_term = request.form.get('search', '')
        if form.validate_on_submit():
            start_date = form.start_date.data
            end_date = form.end_date.data
            
            if start_date:
                query = query.filter(Transaction.date >= start_date)
            if end_date:
                query = query.filter(Transaction.date <= end_date)
        if search_term:
            query = query.filter(Transaction.description.ilike(f'%{search_term}%'))

    coded = query.order_by(Transaction.date.desc()).all()
    return render_template('coded_transactions.html', transactions=coded, form=form, search=search_term)

@main_bp.route('/mark_as_uncoded/<int:transaction_id>', methods=['POST'])
@login_required
def mark_as_uncoded(transaction_id):
    transaction_to_uncode = Transaction.query.get_or_404(transaction_id)

    # Determine the main transaction to process
    main_transaction = transaction_to_uncode.parent_transaction or transaction_to_uncode

    # Prevent uncoding if the landlord has been paid out
    if main_transaction.tenant_id:
        tenant = Tenant.query.get(main_transaction.tenant_id)
        if tenant and tenant.property and tenant.property.landlord_id:
            payouts = Transaction.query.filter_by(landlord_id=tenant.property.landlord_id, category='payout').all()
            if any(p.date > main_transaction.date for p in payouts):
                flash('Cannot uncode. Landlord has been paid out since this transaction.', 'danger')
                return redirect(url_for('main.coded_transactions'))

    # Reverse financial effects of child transactions and delete them
    for child in main_transaction.child_transactions:
        if child.landlord_id:
            landlord_account = Account.query.filter_by(landlord_id=child.landlord_id).first()
            if landlord_account:
                landlord_account.update_balance(-child.amount)
        if child.account_id:
            # This handles agency fees, utility splits, etc.
            account = Account.query.get(child.account_id)
            if account and account.type != 'landlord': # Avoid double-counting landlord accounts
                account.update_balance(-child.amount)
        db.session.delete(child)

    # Reverse financial effect on the tenant's account from the main transaction
    if main_transaction.tenant_id:
        tenant_account = Account.query.filter_by(tenant_id=main_transaction.tenant_id).first()
        if tenant_account:
            tenant_account.update_balance(-main_transaction.amount)

    # Reset the main transaction to its original uncoded state
    main_transaction.status = 'uncoded'
    main_transaction.tenant_id = None
    main_transaction.landlord_id = None
    main_transaction.category = None
    
    db.session.commit()

    flash('Transaction and all linked payments have been successfully marked as uncoded.', 'success')
    return redirect(url_for('main.coded_transactions'))
