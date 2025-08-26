# reset_db.py
from app import create_app, db
from sqlalchemy import text

def reset_database():
    app = create_app()
    with app.app_context():
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
        
        # Create all tables
        db.create_all()
        print("All tables created.")

if __name__ == '__main__':
    reset_database()
