from fpdf import FPDF
from app.models import Landlord, Property, Tenant, Transaction, Expense, Account, Company
from datetime import datetime, timedelta
from app import db
import os
from flask import current_app

def get_opening_balance(account, start_date):
    transactions = Transaction.query.filter(
        Transaction.account_id == account.id,
        Transaction.date < start_date
    ).all()
    balance = sum(t.amount for t in transactions)
    return balance

class PDF(FPDF):
    def header(self):
        company = Company.query.first()
        if company and company.logo:
            logo_path = os.path.join(current_app.config['UPLOAD_FOLDER'], company.logo)
            if os.path.exists(logo_path):
                self.image(logo_path, 10, 8, 33)
        self.set_font('Arial', 'B', 12)
        self.cell(0, 10, 'Statement', 0, 1, 'C')

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

def generate_monthly_statement(landlord_id, start_date, end_date):
    landlord = Landlord.query.get(landlord_id)
    landlord_account = Account.query.filter_by(landlord_id=landlord.id).first()
    company = Company.query.first()

    if not landlord_account:
        return None

    opening_balance = get_opening_balance(landlord_account, start_date)

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
    pdf.cell(0, 10, 'Landlord Statement', 0, 1, 'C')
    pdf.set_font('Arial', size=10)
    pdf.cell(0, 5, f'Landlord: {landlord.name}', 0, 1)
    pdf.cell(0, 5, f'Email: {landlord.email}', 0, 1)
    pdf.cell(0, 5, f'Period: {start_date.strftime('%d %b %Y')} - {end_date.strftime('%d %b %Y')}', 0, 1)
    pdf.ln(10)

    # Summary
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, 'Summary', 0, 1)
    pdf.set_font('Arial', size=10)
    pdf.set_fill_color(200, 220, 255) # Light blue background
    pdf.cell(80, 7, 'Description', 1, 0, 'L', 1)
    pdf.cell(40, 7, 'Amount', 1, 1, 'R', 1)

    rent_received = sum(t.amount for t in transactions if t.category == 'rent')
    expenses = sum(t.amount for t in transactions if t.category == 'expense')
    fees = sum(t.amount for t in transactions if t.category == 'fee')
    payouts = sum(t.amount for t in transactions if t.category == 'payout')
    
    pdf.cell(80, 7, 'Opening Balance', 1)
    pdf.cell(40, 7, f'{opening_balance:.2f}', 1, 1, 'R')
    pdf.cell(80, 7, 'Rent Received', 1)
    pdf.cell(40, 7, f'{rent_received:.2f}', 1, 1, 'R')
    pdf.cell(80, 7, 'Expenses', 1)
    pdf.cell(40, 7, f'{expenses:.2f}', 1, 1, 'R')
    pdf.cell(80, 7, 'Agency Fees', 1)
    pdf.cell(40, 7, f'{fees:.2f}', 1, 1, 'R')
    pdf.cell(80, 7, 'Payouts', 1)
    pdf.cell(40, 7, f'{payouts:.2f}', 1, 1, 'R')

    closing_balance = opening_balance + sum(t.amount for t in transactions)
    pdf.set_font('Arial', 'B', 10)
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

    file_path = f"statements/landlord_{landlord_id}_{start_date.strftime('%Y-%m-%d')}.pdf"
    pdf.output(file_path)
    return file_path


def generate_tenant_statement(tenant_id, start_date, end_date):
    tenant = Tenant.query.get(tenant_id)
    tenant_account = Account.query.filter_by(tenant_id=tenant.id).first()
    company = Company.query.first()

    if not tenant_account:
        return None

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
    return file_path

def generate_annual_statement(landlord_id, year):
    landlord = Landlord.query.get(landlord_id)
    start_date = datetime(year, 1, 1).date()
    end_date = datetime(year, 12, 31).date()
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
    return file_path
