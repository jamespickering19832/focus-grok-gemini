# reset_db.py
from app import create_app, db
from sqlalchemy import text

def reset_database():
    app = create_app()
    with app.app_context():
        # Drop all tables
        with db.engine.connect() as connection:
            with connection.begin():
                db.session.execute(text('DROP TABLE IF EXISTS "user_roles"'))
                db.session.execute(text('DROP TABLE IF EXISTS "user"'))
                db.session.execute(text('DROP TABLE IF EXISTS "role"'))
                db.session.execute(text('DROP TABLE IF EXISTS "tenant"'))
                db.session.execute(text('DROP TABLE IF EXISTS "landlord"'))
                db.session.execute(text('DROP TABLE IF EXISTS "property"'))
                db.session.execute(text('DROP TABLE IF EXISTS "account"'))
                db.session.execute(text('DROP TABLE IF EXISTS "transaction"'))
                db.session.execute(text('DROP TABLE IF EXISTS "expense_category"'))
                db.session.execute(text('DROP TABLE IF EXISTS "expense"'))
                db.session.execute(text('DROP TABLE IF EXISTS "allocation_history"'))
                db.session.execute(text('DROP TABLE IF EXISTS "statement"'))
                db.session.execute(text('DROP TABLE IF EXISTS "rent_charge_batch"'))
                db.session.execute(text('DROP TABLE IF EXISTS "audit_log"'))
                db.session.execute(text('DROP TABLE IF EXISTS "company"'))
                db.session.execute(text('DROP TABLE IF EXISTS "alembic_version"'))
        print("All tables dropped.")
        
        # Create all tables
        db.create_all()
        print("All tables created.")

if __name__ == '__main__':
    reset_database()