from app import app, db
from app.models import Landlord, Property, Tenant

with app.app_context():
    landlord_count = db.session.query(Landlord).count()
    property_count = db.session.query(Property).count()
    tenant_count = db.session.query(Tenant).count()

    print(f"Landlord count: {landlord_count}")
    print(f"Property count: {property_count}")
    print(f"Tenant count: {tenant_count}")