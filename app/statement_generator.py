from fpdf import FPDF
from app.models import Landlord, Property, Tenant, Transaction, Expense, Account, Company, Statement
from datetime import datetime, timedelta
from flask import current_app, session
from app import db
import os
from sqlalchemy import not_, and_

def get_opening_balance(account, start_date):
    balance = 0
    if account.landlord_id:
        transactions = Transaction.query.filter(
            Transaction.landlord_id == account.landlord_id,
            Transaction.date < start_date
        ).all()
        balance += sum(t.amount for t in transactions)
    elif account.tenant_id:
        trans = Transaction.query.filter(
            Transaction.tenant_id == account.tenant_id,
            Transaction.date < start_date
        ).all()
        balance += sum(t.amount for t in trans)
    else:
        trans = Transaction.query.filter(
            Transaction.account_id == account.id,
            Transaction.date < start_date
        ).all()
        balance += sum(t.amount for t in trans)
    return balance

class PDF(FPDF):
    def header(self):
        pass
    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

def generate_monthly_statement(landlord_id, start_date, end_date, vat_rate):
    landlord = Landlord.query.get(landlord_id)
    if not landlord:
        return None, "Landlord not found"

    if not start_date:
        if 'current_date' in session:
            start_date = datetime.strptime(session['current_date'], '%Y-%m-%d').date().replace(day=1)
        else:
            start_date = datetime.utcnow().date().replace(day=1)
    if not end_date:
        end_date = (start_date + timedelta(days=31)).replace(day=1) - timedelta(days=1)
    landlord_account = Account.query.filter_by(landlord_id=landlord.id).first()
    company = Company.query.first()
    if not landlord_account:
        return None, "Landlord account not found"
    opening_balance = get_opening_balance(landlord_account, start_date)
    landlord_payments_account = Account.query.filter_by(name='Landlord Payments').first()
    landlord_payments_account_id = landlord_payments_account.id if landlord_payments_account else -1
    transactions = Transaction.query.filter(
        Transaction.landlord_id == landlord_id,
        Transaction.date.between(start_date, end_date)
    ).all()
    transactions.sort(key=lambda t: t.date)
    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Arial", size=10)
    if company and company.logo:
        logo_path = os.path.join(current_app.config['UPLOAD_FOLDER'], company.logo)
        if os.path.exists(logo_path):
            pdf.image(logo_path, 10, 8, 33)
    pdf.set_font('Arial', '', 11)
    pdf.set_xy(10, 40)
    pdf.multi_cell(0, 5, f"{landlord.name}\n{landlord.address_line_1 or ''}\n{landlord.town or ''}\n{landlord.postcode or ''}\n\nRef: {landlord.reference_code or ''}")
    pdf.set_xy(150, 40)
    pdf.cell(0, 5, "V.A.T. No. [Your VAT No]")
    pdf.set_font('Arial', 'B', 12)
    pdf.set_xy(10, 70)
    pdf.cell(0, 10, 'STATEMENT OF ACCOUNT', 'B', 1, 'L')
    pdf.set_font('Arial', '', 11)
    pdf.cell(0, 10, f"{end_date.strftime('%d %B %Y')}", 0, 1, 'R')
    pdf.ln(5)
    pdf.set_font('Arial', '', 11)
    pdf.cell(120, 7, 'Balance Brought forward', 'L')
    pdf.cell(40, 7, f'{opening_balance:.2f}', 'R', 1, 'R')
    pdf.ln(5)
    pdf.set_font('Arial', 'B', 11)
    pdf.cell(0, 7, 'RECEIPTS', 'L', 1)
    pdf.set_font('Arial', '', 11)
    rent_received = sum(t.amount for t in transactions if t.category in ['rent', 'rent_landlord_share'])
    pdf.cell(120, 7, 'Rents', 'L')
    pdf.cell(40, 7, f'{rent_received:.2f}', 'R', 1, 'R')
    pdf.cell(120, 7, 'Other Receipts', 'L')
    pdf.cell(40, 7, '0.00', 'R', 1, 'R')
    pdf.ln(5)
    pdf.set_font('Arial', 'B', 11)
    pdf.cell(0, 7, 'DEDUCTIONS', 'L', 1)
    pdf.set_font('Arial', '', 11)
    management_fees = sum(t.amount for t in transactions if t.category == 'fee')
    vat_on_fees = sum(t.amount for t in transactions if t.category == 'vat')
    commission_rate_display = f"{landlord.commission_rate * 100:.2f}"
    vat_rate_display = f"{vat_rate * 100:.2f}"
    pdf.cell(80, 7, f'Management Fees @ {commission_rate_display}%', 'L')
    pdf.cell(40, 7, f'{management_fees:.2f}', 'R', 0, 'R')
    pdf.ln()
    pdf.cell(80, 7, f'V.A.T. @ {vat_rate_display}%', 'L')
    pdf.cell(40, 7, f'{vat_on_fees:.2f}', 'R', 0, 'R')
    pdf.ln()
    pdf.cell(0, 7, 'Expenses:', 'L')
    expenses_list = [t for t in transactions if t.category == 'expense']
    if expenses_list:
        pdf.ln(5)
        for exp in expenses_list:
            pdf.cell(10)
            pdf.cell(110, 7, exp.description, 'L')
            pdf.cell(40, 7, f'{-exp.amount:.2f}', 'R', 1, 'R')
    else:
        pdf.cell(120, 7, '', 'L')
        pdf.cell(40, 7, '0.00', 'R', 1, 'R')
    pdf.ln(5)
    payouts = sum(t.amount for t in transactions if t.category == 'payout')
    pdf.cell(120, 7, 'Payments on A/C of Rents Received', 'L')
    pdf.cell(40, 7, f'{-payouts:.2f}', 'R', 1, 'R')
    pdf.cell(120, 7, 'Cheque to Client\'s Bank', 'L')
    pdf.cell(40, 7, '0.00', 'R', 1, 'R')
    pdf.ln(5)
    closing_balance = opening_balance + sum(t.amount for t in transactions)
    pdf.set_font('Arial', 'B', 11)
    pdf.cell(120, 7, 'Balance Carried forward', 'L,T')
    pdf.set_x(130)
    pdf.cell(40, 7, f'{closing_balance:.2f}', 'T,R', 0, 'R')
    pdf.set_x(170)
    pdf.cell(30, 7, f'{closing_balance:.2f}', 'T,R', 1, 'R')
    file_path = f"statements/landlord_{landlord_id}_{start_date.strftime('%Y-%m-%d')}.pdf"
    pdf.output(file_path)
    statement = Statement(type='monthly', start_date=start_date, end_date=end_date, landlord_id=landlord_id, pdf_path=file_path)
    db.session.add(statement)
    db.session.commit()
    return file_path, None

def generate_tenant_statement(tenant_id, start_date, end_date):
    tenant = Tenant.query.get(tenant_id)
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
    pdf.cell(0, 5, f'Period: {start_date.strftime('%d %b %Y')} - {end_date.strftime('%d %b %Y')}', 0, 1)
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
    pdf.cell(40, 7, f'{rent_charged:.2f}', 1, 1, 'R')
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
    statement = Statement(type='tenant', start_date=start_date, end_date=end_date, tenant_id=tenant_id, pdf_path=file_path)
    db.session.add(statement)
    db.session.commit()
    return file_path, None

def generate_annual_statement(landlord_id, year):
    landlord = Landlord.query.get(landlord_id)
    start_date = datetime(int(year), 1, 1).date()
    end_date = datetime(int(year), 12, 31).date()
    company = Company.query.first()

    transactions = Transaction.query.filter(
        Transaction.landlord_id == landlord_id,
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
    total_vat = sum(t.amount for t in transactions if t.category == 'vat')

    pdf.cell(80, 7, 'Total Rent Received', 1)
    pdf.cell(40, 7, f'{total_rent:.2f}', 1, 1, 'R')
    pdf.cell(80, 7, 'Total Expenses', 1)
    pdf.cell(40, 7, f'{total_expenses:.2f}', 1, 1, 'R')
    pdf.cell(80, 7, 'Total Agency Fees', 1)
    pdf.cell(40, 7, f'{total_fees:.2f}', 1, 1, 'R')
    pdf.cell(80, 7, 'Total VAT', 1)
    pdf.cell(40, 7, f'{total_vat:.2f}', 1, 1, 'R')
    pdf.ln(10)

    # Property Breakdown
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, 'Property Breakdown', 0, 1)
    pdf.set_font('Arial', size=10)

    properties = Property.query.filter_by(landlord_id=landlord_id).all()
    for prop in properties:
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(0, 10, f"Property: {prop.address_line_1}, {prop.town}, {prop.postcode}", 0, 1)
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
    statement = Statement(type='annual', start_date=start_date, end_date=end_date, landlord_id=landlord_id, pdf_path=file_path)
    db.session.add(statement)
    db.session.commit()
    return file_path, None
