# dummy_data.py
from app import create_app, db

app = create_app()
from app.models import Tenant, Landlord, Account, Property, ExpenseCategory

def add_dummy_data():
    with app.app_context():
        db.create_all()

        db.session.query(Tenant).delete()
        db.session.query(Landlord).delete()
        db.session.query(Account).delete()
        db.session.query(Property).delete()
        db.session.query(ExpenseCategory).delete()
        db.session.commit()

        tenant1 = Tenant(name='T001', email='tenant1@example.com', reference_code='T001REF')
        landlord1 = Landlord(name='L001', email='landlord1@example.com', reference_code='L001REF', commission_rate=0.08)
        tenant2 = Tenant(name='Rowan Howard', email='rowan@example.com', reference_code='RGH2514RDT')
        landlord2 = Landlord(name='DPC Services', email='dpc@example.com', reference_code='DPC0768995', commission_rate=0.12)
        tenant3 = Tenant(name='John Smith', email='john@example.com', reference_code='SY232HJ')
        tenant4 = Tenant(name='Test Tenant', email='test.tenant@example.com', reference_code='TESTTEN', property_id=4)
        landlord3 = Landlord(name='Property Management', email='pm@example.com', reference_code='22 PAD CRESCENT', commission_rate=0.10)
        landlord4 = Landlord(name='Test Landlord', email='test@example.com', reference_code='TESTLL', commission_rate=0.10)

        db.session.add_all([tenant1, landlord1, tenant2, landlord2, tenant3, landlord3, landlord4])
        db.session.commit()

        property1 = Property(address='123 Main St', rent_amount=1000.0, landlord_id=landlord1.id)
        property2 = Property(address='456 Oak Ave', rent_amount=580.0, landlord_id=landlord2.id)
        property3 = Property(address='789 Pine Ln', rent_amount=400.0, landlord_id=landlord3.id)
        property4 = Property(address='1 Test Street', rent_amount=1000.0, landlord_id=landlord4.id)

        db.session.add_all([property1, property2, property3, property4])
        db.session.commit()

        tenant1.property_id = property1.id
        tenant2.property_id = property2.id
        # tenant3 no property

        db.session.commit()

        account_tenant1 = Account(name=f'{tenant1.name} Account', type='tenant', tenant_id=tenant1.id)
        account_landlord1 = Account(name=f'{landlord1.name} Account', type='landlord', landlord_id=landlord1.id)
        account_tenant2 = Account(name=f'{tenant2.name} Account', type='tenant', tenant_id=tenant2.id)
        account_landlord2 = Account(name=f'{landlord2.name} Account', type='landlord', landlord_id=landlord2.id)
        account_tenant3 = Account(name=f'{tenant3.name} Account', type='tenant', tenant_id=tenant3.id)
        account_landlord3 = Account(name=f'{landlord3.name} Account', type='landlord', landlord_id=landlord3.id)
        account_tenant4 = Account(name=f'{tenant4.name} Account', type='tenant', tenant_id=tenant4.id)
        account_landlord4 = Account(name=f'{landlord4.name} Account', type='landlord', landlord_id=landlord4.id)

        agency_income_account = Account(name='Agency Income', type='agency_income')
        agency_expense_account = Account(name='Agency Expense', type='agency_expense')
        suspense_account = Account(name='Suspense Account', type='suspense')
        bank_account = Account(name='Master Bank Account', type='asset', balance=90000.0)
        utility_account = Account(name='Utility Account', type='utility')
        vat_account = Account(name='VAT Account', type='vat_payable')

        db.session.add_all([
            account_tenant1, account_landlord1, account_tenant2, account_landlord2,
            account_tenant3, account_landlord3, agency_income_account, agency_expense_account,
            account_tenant4, account_landlord4,
            suspense_account, bank_account, utility_account, vat_account
        ])

        category_maintenance = ExpenseCategory(name='Maintenance')
        category_repairs = ExpenseCategory(name='Repairs')
        category_utilities = ExpenseCategory(name='Utilities')
        category_insurance = ExpenseCategory(name='Insurance')
        category_other = ExpenseCategory(name='Other')

        db.session.add_all([
            category_maintenance, category_repairs, category_utilities,
            category_insurance, category_other
        ])

        db.session.commit()
        print("Dummy data added successfully.")

if __name__ == '__main__':
    add_dummy_data()