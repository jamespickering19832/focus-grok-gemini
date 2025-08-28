
# initialize_app.py
import bcrypt
from sqlalchemy import text
from app import create_app, db
from app.models import User, Role, Account

def reset_database():
    """Drops all tables and recreates them."""
    try:
        print("Dropping all tables...")
        cascade = ""
        if db.engine.name == 'postgresql':
            cascade = " CASCADE"

        tables = [
            "user_roles", "user", "role", "tenant", "landlord", "property",
            "account", "transaction", "expense_category", "expense",
            "allocation_history", "statement", "rent_charge_batch",
            "audit_log", "company", "alembic_version"
        ]

        with db.engine.connect() as connection:
            with connection.begin():
                for table_name in tables:
                    connection.execute(text(f'DROP TABLE IF EXISTS "{table_name}"{cascade}'))
        
        print("All tables dropped.")
        
        db.create_all()
        print("All tables created.")
        db.session.commit()
    except Exception as e:
        print(f"An error occurred during database reset: {e}")
        db.session.rollback()
        raise

def create_admin():
    """Creates the default admin role and user."""
    try:
        print("Setting up admin user...")
        admin_role = Role.query.filter_by(name='admin').first()
        if not admin_role:
            admin_role = Role(name='admin')
            db.session.add(admin_role)
            print("Admin role created.")

        admin_user = User.query.filter_by(username='admin').first()
        if not admin_user:
            password = 'adminpassword'
            hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
            admin_user = User(
                username='admin',
                email='admin@example.com',
                password_hash=hashed_password
            )
            admin_user.roles.append(admin_role)
            db.session.add(admin_user)
            print("Admin user created.")
        else:
            if admin_role not in admin_user.roles:
                admin_user.roles.append(admin_role)
                print("Added admin role to existing admin user.")
            else:
                print("Admin user already exists and has admin role.")
        db.session.commit()
    except Exception as e:
        print(f"An error occurred during admin creation: {e}")
        db.session.rollback()
        raise

def setup_initial_accounts():
    """Sets up the initial chart of accounts."""
    try:
        print("Setting up initial accounts...")
        if Account.query.filter_by(name='Agency Income').first():
            print("Initial accounts already seem to exist. Skipping.")
            return

        accounts_to_add = [
            Account(name='Agency Income', type='agency_income'),
            Account(name='Agency Expense', type='agency_expense'),
            Account(name='Suspense Account', type='suspense'),
            Account(name='Master Bank Account', type='asset', balance=90000.0),
            Account(name='Utility Account', type='utility'),
            Account(name='VAT Account', type='vat_payable'),
            Account(name='Landlord Payments', type='liability')
        ]
        
        db.session.add_all(accounts_to_add)
        db.session.commit()
        print("Initial agency and bank accounts added successfully.")
    except Exception as e:
        print(f"An error occurred during account setup: {e}")
        db.session.rollback()
        raise

if __name__ == '__main__':
    print("--- Starting Application Initialization Script ---")
    print("WARNING: This script will completely reset your database.")
    proceed = input("Do you want to continue? (y/n): ")

    if proceed.lower() == 'y':
        app = create_app()
        with app.app_context():
            reset_database()
            create_admin()
            setup_initial_accounts()
        print("--- Application Initialization Complete ---")
    else:
        print("Initialization cancelled.")
