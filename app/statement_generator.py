from fpdf import FPDF
from app.models import Landlord, Property, Tenant, Transaction, Expense, Account, Company, Statement
from datetime import datetime, timedelta
from flask import current_app
from app import db
import os
from sqlalchemy import not_, and_

def get_opening_balance(account, start_date):
    balance = 0
    if account.landlord_id:
        direct_trans = Transaction.query.filter(
            Transaction.landlord_id == account.landlord_id,
            Transaction.date < start_date
        ).all()
        balance += sum(t.amount for t in direct_trans)
        landlord = Landlord.query.get(account.landlord_id)
        tenant_ids = [t.id for p in landlord.properties for t in p.tenants]
        rent_trans = Transaction.query.filter(
            Transaction.tenant_id.in_(tenant_ids),
            Transaction.category == 'rent',
            Transaction.date < start_date
        ).all()
        balance += sum(t.amount for t in rent_trans)
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
    direct_transactions = Transaction.query.filter(
        Transaction.landlord_id == landlord_id,
        Transaction.date.between(start_date, end_date),
        Transaction.account_id != landlord_payments_account_id
    ).all()
    tenant_ids = [t.id for p in landlord.properties for t in p.tenants]
    tenant_transactions = Transaction.query.filter(
        Transaction.tenant_id.in_(tenant_ids),
        Transaction.category.in_(['rent', 'rent_landlord_share']),
        Transaction.date.between(start_date, end_date)
    ).all()
    all_related_transactions_map = {t.id: t for t in direct_transactions + tenant_transactions}
    all_related_transactions = list(all_related_transactions_map.values())
    split_rent_parent_ids = {
        t.parent_transaction_id for t in all_related_transactions 
        if t.category == 'rent_landlord_share' and t.parent_transaction_id
    }
    transactions = [
        t for t in all_related_transactions
        if not (t.category == 'rent' and t.id in split_rent_parent_ids)
    ]
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
    pdf.multi_cell(0, 5, f"{landlord.name}\n{landlord.address or ''}\n\nRef: {landlord.reference_code or ''}")
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
    vat_on_fees = management_fees * vat_rate
    commission_rate_display = f"{landlord.commission_rate * 100:.2f}"
    vat_rate_display = f"{vat_rate * 100:.2f}"
    pdf.cell(80, 7, f'Management Fees @ {commission_rate_display}%', 'L')
    pdf.cell(40, 7, f'{-management_fees:.2f}', 'R', 0, 'R')
    pdf.ln()
    pdf.cell(80, 7, f'V.A.T. @ {vat_rate_display}%', 'L')
    pdf.cell(40, 7, f'{-vat_on_fees:.2f}', 'R', 0, 'R')
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
    # ... (implementation from history)
    pass

def generate_annual_statement(landlord_id, year):
    # ... (implementation from history)
    pass
