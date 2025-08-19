from fpdf import FPDF
from app.models import Landlord, Property, Tenant, Transaction, Expense, Account, Company, Statement
from datetime import datetime, timedelta
from app import app, db
import os
from flask import current_app, request, flash, redirect, url_for, send_from_directory, render_template
from sqlalchemy import not_, and_
from flask_login import login_required

def get_opening_balance(account, start_date):
    transactions = Transaction.query.filter(
        Transaction.account_id == account.id,
        Transaction.date < start_date,
        ~Transaction.category.in_(['payout', 'fee', 'vat'])
    ).all()
    balance = sum(t.amount for t in transactions)
    return balance

class PDF(FPDF):
    def header(self):
        # Header is now custom per page, so this can be left empty or used for default headers
        pass

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

def generate_monthly_statement(landlord_id, start_date, end_date, vat_rate):
    landlord = Landlord.query.get(landlord_id)
    if not landlord:
        return None, "Landlord not found"
    landlord_account = Account.query.filter_by(landlord_id=landlord.id).first()
    company = Company.query.first()

    if not landlord_account:
        return None, "Landlord account not found"

    opening_balance = get_opening_balance(landlord_account, start_date)

    # Get the ID of the tracking account for landlord payments to exclude it
    landlord_payments_account = Account.query.filter_by(name='Landlord Payments').first()
    landlord_payments_account_id = landlord_payments_account.id if landlord_payments_account else -1

    # Get transactions directly linked to the landlord, excluding tracking entries
    landlord_direct_transactions = Transaction.query.filter(
        Transaction.landlord_id == landlord_id,
        Transaction.date.between(start_date, end_date),
        not_(and_(Transaction.category.in_(['fee', 'vat']), Transaction.amount > 0)),
        Transaction.account_id != landlord_payments_account_id
    )

    # Get tenant IDs associated with this landlord's properties
    tenant_ids = [t.id for p in landlord.properties for t in p.tenants]

    # Get rent transactions from these tenants that are linked to the landlord
    tenant_rent_transactions = Transaction.query.filter(
        Transaction.tenant_id.in_(tenant_ids),
        Transaction.category == 'rent',
        Transaction.date.between(start_date, end_date)
    )

    # Combine and sort all relevant transactions
    all_transactions_query = landlord_direct_transactions.union(tenant_rent_transactions)
    transactions = all_transactions_query.order_by(Transaction.date).all()

    # Deduplicate by transaction id
    unique_transactions = {}
    for t in transactions:
        unique_transactions[t.id] = t
    transactions = list(unique_transactions.values())
    transactions.sort(key=lambda t: t.date)

    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Arial", size=10)

    # --- Page 1: Statement of Account ---

    # Company Logo
    if company and company.logo:
        logo_path = os.path.join(current_app.config['UPLOAD_FOLDER'], company.logo)
        if os.path.exists(logo_path):
            pdf.image(logo_path, 10, 8, 33)

    # Landlord Address Block
    pdf.set_font('Arial', '', 11)
    pdf.set_xy(10, 40)
    pdf.multi_cell(0, 5, f"{landlord.name}\n{landlord.address or ''}\n\nRef: {landlord.reference_code or ''}")

    # VAT Number
    pdf.set_xy(150, 40)
    pdf.cell(0, 5, "V.A.T. No. [Your VAT No]") # Placeholder for VAT

    # Title
    pdf.set_font('Arial', 'B', 12)
    pdf.set_xy(10, 70)
    pdf.cell(0, 10, 'STATEMENT OF ACCOUNT', 'B', 1, 'L')
    pdf.set_font('Arial', '', 11)
    pdf.cell(0, 10, f"{end_date.strftime('%d %B %Y')}", 0, 1, 'R')
    pdf.ln(5)

    # Main Content Table
    pdf.set_font('Arial', '', 11)
    pdf.cell(120, 7, 'Balance Brought forward', 'L')
    pdf.cell(40, 7, f'{opening_balance:.2f}', 'R', 1, 'R')
    pdf.ln(5)

    # Receipts
    pdf.set_font('Arial', 'B', 11)
    pdf.cell(0, 7, 'RECEIPTS', 'L', 1)
    pdf.set_font('Arial', '', 11)
    rent_received = sum(t.amount for t in transactions if t.category == 'rent')
    pdf.cell(120, 7, 'Rents', 'L')
    pdf.cell(40, 7, f'{rent_received:.2f}', 'R', 1, 'R')
    pdf.cell(120, 7, 'Other Receipts', 'L')
    pdf.cell(40, 7, '0.00', 'R', 1, 'R')
    pdf.ln(5)

    # Deductions
    pdf.set_font('Arial', 'B', 11)
    pdf.cell(0, 7, 'DEDUCTIONS', 'L', 1)
    pdf.set_font('Arial', '', 11)

    # Calculate fees and VAT
    management_fees = sum(t.amount for t in transactions if t.category == 'fee')
    vat_on_fees = management_fees * vat_rate
    commission_rate_display = f"{landlord.commission_rate * 100:.2f}"
    vat_rate_display = f"{vat_rate * 100:.2f}"

    pdf.cell(80, 7, f'Management Fees @ {commission_rate_display}%', 'L')
    pdf.cell(40, 7, f'{-management_fees:.2f}', 'R', 0, 'R')
    pdf.ln()
    pdf.cell(80, 7, f'V.A.T. @ {vat_rate_display}%', 'L')
    pdf.cell(40, 7, f'{-vat_on_fees:.2f}', 'R', 0, 'R')
    pdf.ln()

    # Expenses
    pdf.cell(0, 7, 'Expenses:', 'L')
    expenses_list = [t for t in transactions if t.category == 'expense']
    total_expenses = 0
    if expenses_list:
        pdf.ln(5)
        for exp in expenses_list:
            pdf.cell(10) # Indent
            pdf.cell(110, 7, exp.description, 'L')
            pdf.cell(40, 7, f'{-exp.amount:.2f}', 'R', 1, 'R')
            total_expenses += exp.amount
    else:
        pdf.cell(120, 7, '', 'L')
        pdf.cell(40, 7, '0.00', 'R', 1, 'R')

    pdf.ln(5)

    # Payouts
    payouts = sum(t.amount for t in transactions if t.category == 'payout')
    pdf.cell(120, 7, 'Payments on A/C of Rents Received', 'L')
    pdf.cell(40, 7, f'{-payouts:.2f}', 'R', 1, 'R')
    pdf.cell(120, 7, 'Cheque to Client\'s Bank', 'L')
    pdf.cell(40, 7, '0.00', 'R', 1, 'R')
    pdf.ln(5)


    # Closing Balance
    closing_balance = opening_balance + sum(t.amount for t in transactions)
    pdf.set_font('Arial', 'B', 11)
    pdf.cell(120, 7, 'Balance Carried forward', 'L,T')
    pdf.set_x(130)
    pdf.cell(40, 7, f'{closing_balance:.2f}', 'T,R', 0, 'R')
    pdf.set_x(170)
    pdf.cell(30, 7, f'{closing_balance:.2f}', 'T,R', 1, 'R')
    

    # --- Page 2: Landlord Rents Received ---
    pdf.add_page()
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, 'LANDLORD RENTS RECEIVED', 0, 1, 'C')
    pdf.cell(0, 10, f"LANDLORD: {landlord.name}", 0, 1, 'C')
    pdf.ln(5)

    # Table Header
    pdf.set_font('Arial', 'B', 9)
    pdf.cell(40, 7, 'Property Address', 1)
    pdf.cell(35, 7, 'Tenant Name', 1)
    pdf.cell(20, 7, 'Rent/Period', 1)
    pdf.cell(15, 7, 'Opening', 1)
    pdf.cell(15, 7, 'Water Due', 1)
    pdf.cell(15, 7, 'Rent Due', 1)
    pdf.cell(15, 7, 'Total Due', 1)
    pdf.cell(15, 7, 'Received', 1)
    pdf.cell(15, 7, 'Closing', 1, 1)

    # Table Body
    pdf.set_font('Arial', '', 8)
    total_opening = 0
    total_water = 0
    total_due = 0
    total_received = 0
    total_closing = 0

    tenants = Tenant.query.filter(Tenant.property_id.in_([p.id for p in landlord.properties])).all()
    for tenant in tenants:
        tenant_account = Account.query.filter_by(tenant_id=tenant.id).first()
        if not tenant_account: continue

        # Calculate tenant-specific values
        t_opening = get_opening_balance(tenant_account, start_date)
        t_trans = Transaction.query.filter(Transaction.tenant_id == tenant.id, Transaction.date.between(start_date, end_date)).all()
        t_due = sum(t.amount for t in t_trans if t.category == 'rent_charge')
        t_received = sum(t.amount for t in t_trans if t.category == 'rent')
        t_water_due = 0 # Placeholder
        t_total_due = t_opening + t_water_due + t_due
        t_closing = t_total_due - t_received

        pdf.cell(40, 7, tenant.property.address[:25], 1)
        pdf.cell(35, 7, tenant.name[:20], 1)
        pdf.cell(20, 7, f"{tenant.property.rent_amount:.2f} M", 1, 0, 'R')
        pdf.cell(15, 7, f"{t_opening:.2f}", 1, 0, 'R')
        pdf.cell(15, 7, f"{t_water_due:.2f}", 1, 0, 'R')
        pdf.cell(15, 7, f"{t_due:.2f}", 1, 0, 'R')
        pdf.cell(15, 7, f"{t_total_due:.2f}", 1, 0, 'R')
        pdf.cell(15, 7, f"{t_received:.2f}", 1, 0, 'R')
        pdf.cell(15, 7, f"{t_closing:.2f}", 1, 1, 'R')

        total_opening += t_opening
        total_water += t_water_due
        total_due += t_due
        total_received += t_received
        total_closing += t_closing

    # Table Footer (Totals)
    pdf.set_font('Arial', 'B', 9)
    pdf.cell(95, 7, 'TOTALS:', 1, 0, 'R')
    pdf.cell(15, 7, f"{total_opening:.2f}", 1, 0, 'R')
    pdf.cell(15, 7, f"{total_water:.2f}", 1, 0, 'R')
    pdf.cell(15, 7, f"{total_due:.2f}", 1, 0, 'R')
    pdf.cell(15, 7, f"{(total_opening + total_water + total_due):.2f}", 1, 0, 'R')
    pdf.cell(15, 7, f"{total_received:.2f}", 1, 0, 'R')
    pdf.cell(15, 7, f"{total_closing:.2f}", 1, 1, 'R')


    file_path = f"statements/landlord_{landlord_id}_{start_date.strftime('%Y-%m-%d')}.pdf"
    pdf.output(file_path)

    statement = Statement(
        type='monthly',
        start_date=start_date,
        end_date=end_date,
        landlord_id=landlord_id,
        pdf_path=file_path
    )
    db.session.add(statement)
    db.session.commit()

    return file_path, None


def generate_tenant_statement(tenant_id, start_date, end_date):
    tenant = Tenant.query.get(tenant_id)
    if not tenant:
        return None, "Tenant not found"
    tenant_account = Account.query.filter_by(tenant_id=tenant.id).first()
    company = Company.query.first()

    if not tenant_account:
        return None, "Tenant account not found"

    opening_balance = get_opening_balance(tenant_account, start_date)

    transactions = Transaction.query.filter(
        Transaction.tenant_id == tenant_id,
        Transaction.date.between(start_date, end_date)
    ).order_by(Transaction.date).all()

    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Arial", size=10)

    # Company Info
    if company:
        pdf.set_font('Arial', 'B', 14)
        pdf.cell(0, 10, company.name, 0, 1, 'C')
        pdf.set_font('Arial', size=10)
        pdf.cell(0, 5, company.address, 0, 1, 'C')
        pdf.ln(10)

    # Tenant Details
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, 'Tenant Statement', 0, 1, 'C')
    pdf.set_font('Arial', size=10)
    pdf.cell(0, 5, f'Tenant: {tenant.name}', 0, 1)
    pdf.cell(0, 5, f'Email: {tenant.email}', 0, 1)
    pdf.cell(0, 5, f"Period: {start_date.strftime('%d %b %Y')} - {end_date.strftime('%d %b %Y')}", 0, 1)
    pdf.ln(10)

    # Summary
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, 'Summary', 0, 1)
    pdf.set_font('Arial', size=10)
    pdf.set_fill_color(200, 220, 255) # Light blue background
    pdf.cell(80, 7, 'Description', 1, 0, 'L', 1)
    pdf.cell(40, 7, 'Amount', 1, 1, 'R', 1)

    rent_charged = sum(t.amount for t in transactions if t.category == 'rent_charge')
    rent_paid = sum(t.amount for t in transactions if t.category == 'rent')
    closing_balance = opening_balance - rent_charged + rent_paid

    pdf.cell(80, 7, 'Opening Balance', 1)
    pdf.cell(40, 7, f'{opening_balance:.2f}', 1, 1, 'R')
    pdf.cell(80, 7, 'Rent Charged', 1)
    pdf.cell(40, 7, f'-{rent_charged:.2f}', 1, 1, 'R')
    pdf.cell(80, 7, 'Rent Paid', 1)
    pdf.cell(40, 7, f'{rent_paid:.2f}', 1, 1, 'R')
    pdf.cell(80, 7, 'Closing Balance', 1)
    pdf.cell(40, 7, f'{closing_balance:.2f}', 1, 1, 'R')
    pdf.ln(10)

    # Transaction Details
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, 'Transaction Details', 0, 1)
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(25, 7, 'Date', 1, 0, 'L', 1)
    pdf.cell(75, 7, 'Description', 1, 0, 'L', 1)
    pdf.cell(30, 7, 'Category', 1, 0, 'L', 1)
    pdf.cell(30, 7, 'Amount', 1, 1, 'R', 1)

    pdf.set_font('Arial', size=10)
    for t in transactions:
        pdf.cell(25, 6, t.date.strftime('%d/%m/%Y'), 1)
        pdf.cell(75, 6, t.description, 1)
        pdf.cell(30, 6, t.category, 1)
        pdf.cell(30, 6, f'{t.amount:.2f}', 1, 1, 'R')

    file_path = f"statements/tenant_{tenant_id}_{start_date.strftime('%Y-%m-%d')}.pdf"
    pdf.output(file_path)

    statement = Statement(
        type='tenant',
        start_date=start_date,
        end_date=end_date,
        tenant_id=tenant_id,
        pdf_path=file_path
    )
    db.session.add(statement)
    db.session.commit()

    return file_path, None

def generate_annual_statement(landlord_id, year):
    landlord = Landlord.query.get(landlord_id)
    if not landlord:
        return None, "Landlord not found"
    start_date = datetime(year, 1, 1).date()
    end_date = datetime(year, 12, 31).date()
    company = Company.query.first()

    # Get transactions directly linked to the landlord
    landlord_direct_transactions = Transaction.query.filter(
        Transaction.landlord_id == landlord_id,
        Transaction.date.between(start_date, end_date)
    )

    # Get tenant IDs associated with this landlord's properties
    tenant_ids = [t.id for p in landlord.properties for t in p.tenants]

    # Get rent transactions from these tenants that are linked to the landlord
    tenant_rent_transactions = Transaction.query.filter(
        Transaction.tenant_id.in_(tenant_ids),
        Transaction.category == 'rent',
        Transaction.date.between(start_date, end_date)
    )

    # Combine and sort all relevant transactions
    transactions = landlord_direct_transactions.union(tenant_rent_transactions).order_by(Transaction.date).all()

    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Arial", size=10)

    # Company Info
    if company:
        pdf.set_font('Arial', 'B', 14)
        pdf.cell(0, 10, company.name, 0, 1, 'C')
        pdf.set_font('Arial', size=10)
        pdf.cell(0, 5, company.address, 0, 1, 'C')
        pdf.ln(10)

    # Landlord Details
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, 'Annual Landlord Statement', 0, 1, 'C')
    pdf.set_font('Arial', size=10)
    pdf.cell(0, 5, f'Landlord: {landlord.name}', 0, 1)
    pdf.cell(0, 5, f'Email: {landlord.email}', 0, 1)
    pdf.cell(0, 5, f'Year: {year}', 0, 1)
    pdf.ln(10)

    # Annual Summary
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, 'Annual Summary', 0, 1)
    pdf.set_font('Arial', size=10)
    pdf.set_fill_color(200, 220, 255) # Light blue background
    pdf.cell(80, 7, 'Description', 1, 0, 'L', 1)
    pdf.cell(40, 7, 'Amount', 1, 1, 'R', 1)

    total_rent = sum(t.amount for t in transactions if t.category == 'rent')
    total_expenses = sum(t.amount for t in transactions if t.category == 'expense')
    total_fees = sum(t.amount for t in transactions if t.category == 'fee')

    pdf.cell(80, 7, 'Total Rent Received', 1)
    pdf.cell(40, 7, f'{total_rent:.2f}', 1, 1, 'R')
    pdf.cell(80, 7, 'Total Expenses', 1)
    pdf.cell(40, 7, f'{total_expenses:.2f}', 1, 1, 'R')
    pdf.cell(80, 7, 'Total Agency Fees', 1)
    pdf.cell(40, 7, f'{total_fees:.2f}', 1, 1, 'R')
    pdf.ln(10)

    # Property Breakdown
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, 'Property Breakdown', 0, 1)
    pdf.set_font('Arial', size=10)

    properties = Property.query.filter_by(landlord_id=landlord_id).all()
    for prop in properties:
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(0, 10, f"Property: {prop.address}", 0, 1)
        pdf.set_font('Arial', size=10)

        prop_transactions = [t for t in transactions if t.property_id == prop.id]
        prop_rent = sum(t.amount for t in prop_transactions if t.category == 'rent')
        prop_expenses = sum(t.amount for t in prop_transactions if t.category == 'expense')

        pdf.cell(40, 7, 'Rent', 1)
        pdf.cell(0, 7, f'{prop_rent:.2f}', 1, 1, 'R')
        pdf.cell(40, 7, 'Expenses', 1)
        pdf.cell(0, 7, f'{prop_expenses:.2f}', 1, 1, 'R')
        pdf.ln(5)

    file_path = f"statements/landlord_{landlord_id}_{year}_annual.pdf"
    pdf.output(file_path)

    statement = Statement(
        type='annual',
        start_date=start_date,
        end_date=end_date,
        landlord_id=landlord_id,
        pdf_path=file_path
    )
    db.session.add(statement)
    db.session.commit()

    return file_path, None




@app.route('/generate_statement', methods=['POST'])
@login_required
def generate_statement():
    statement_type = request.form.get('statement_type')
    if statement_type == 'monthly':
        landlord_id = request.form.get('landlord_id')
        month = request.form.get('month')
        year = request.form.get('year')
        # ... logic to generate monthly statement ...
    elif statement_type == 'annual':
        landlord_id = request.form.get('landlord_id')
        year = request.form.get('year')
        # ... logic to generate annual statement ...
    elif statement_type == 'tenant':
        tenant_id = request.form.get('tenant_id')
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        # ... logic to generate tenant statement ...
    flash('Statement generated successfully.')
    return redirect(url_for('statements'))

@app.route('/view_statements')
@login_required
def view_statements():
    statements = Statement.query.order_by(Statement.date_generated.desc()).all()
    return render_template('view_statements.html', statements=statements)

@app.route('/statements/download/<int:statement_id>')
@login_required
def download_statement(statement_id):
    statement = Statement.query.get_or_404(statement_id)
    return send_from_directory(os.path.abspath('statements'), os.path.basename(statement.pdf_path), as_attachment=True)