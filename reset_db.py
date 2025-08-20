# reset_db.py
from app import create_app, db
from sqlalchemy import text

def reset_database():
    app = create_app()
    with app.app_context():
        # Drop all tables
        with db.engine.connect() as connection:
            with connection.begin():
                db.session.execute(text('DROP TABLE IF EXISTS "user_roles" CASCADE'))
                db.session.execute(text('DROP TABLE IF EXISTS "user" CASCADE'))
                db.session.execute(text('DROP TABLE IF EXISTS "role" CASCADE'))
                db.session.execute(text('DROP TABLE IF EXISTS "tenant" CASCADE'))
                db.session.execute(text('DROP TABLE IF EXISTS "landlord" CASCADE'))
                db.session.execute(text('DROP TABLE IF EXISTS "property" CASCADE'))
                db.session.execute(text('DROP TABLE IF EXISTS "account" CASCADE'))
                db.session.execute(text('DROP TABLE IF EXISTS "transaction" CASCADE'))
                db.session.execute(text('DROP TABLE IF EXISTS "expense_category" CASCADE'))
                db.session.execute(text('DROP TABLE IF EXISTS "expense" CASCADE'))
                db.session.execute(text('DROP TABLE IF EXISTS "allocation_history" CASCADE'))
                db.session.execute(text('DROP TABLE IF EXISTS "statement" CASCADE'))
                db.session.execute(text('DROP TABLE IF EXISTS "rent_charge_batch" CASCADE'))
                db.session.execute(text('DROP TABLE IF EXISTS "audit_log" CASCADE'))
                db.session.execute(text('DROP TABLE IF EXISTS "company" CASCADE'))
                db.session.execute(text('DROP TABLE IF EXISTS "alembic_version" CASCADE'))
        print("All tables dropped.")
        
        # Create all tables
        db.create_all()
        print("All tables created.")

if __name__ == '__main__':
    reset_database()