from app import app, db
from app.models import Landlord, Property, Tenant

with app.app_context():
    print("\n--- Sample Landlord Data ---")
    landlords = Landlord.query.limit(5).all()
    for landlord in landlords:
        print(f"Code: {landlord.reference_code}, Name: {landlord.name}, Email: {landlord.email}, Phone: {landlord.phone_number}")

    print("\n--- Sample Property Data ---")
    properties = Property.query.limit(5).all()
    for prop in properties:
        landlord_name = prop.landlord.name if prop.landlord else "N/A"
        print(f"Address: {prop.address}, Landlord: {landlord_name} (ID: {prop.landlord_id})")

    print("\n--- Sample Tenant Data ---")
    tenants = Tenant.query.limit(5).all()
    for tenant in tenants:
        property_address = tenant.property.address if tenant.property else "N/A"
        print(f"Code: {tenant.reference_code}, Name: {tenant.name}, Property: {property_address} (ID: {tenant.property_id})")