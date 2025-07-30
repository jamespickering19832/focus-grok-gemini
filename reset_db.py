# reset_db.py
from app import app, db
from app.models import Landlord, Property, Tenant, Account, Transaction
from dummy_data import add_dummy_data

def reset_database():
    with app.app_context():
        # Drop all tables
        db.drop_all()
        print("All tables dropped.")
        
        # Create all tables
        db.create_all()
        print("All tables created.")

if __name__ == '__main__':
    reset_database()