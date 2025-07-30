


import pandas as pd
import os
from pathlib import Path
from app import app, db
from app.models import Landlord, Tenant, Property, Account
from sqlalchemy.exc import IntegrityError
import csv
import sys

def import_data():
    with app.app_context():
        # Clear existing data (optional, for fresh import)
        db.session.query(Tenant).delete()
        db.session.query(Property).delete()
        db.session.query(Landlord).delete()
        db.session.query(Account).delete() # Clear accounts as well
        db.session.commit()

        # Define file paths
        master_text_path = Path('D:/focus grok gemini/focus data/mastertextdata.txt')

        # Define expected column names
        expected_columns = [
            'LandlordCode', 'LandlordName', 'LandlordEmail', 'LandlordPhoneNumber',
            'PropertyAddress', 'PropertyLandlordCode',
            'TenantCode', 'TenantName', 'TenantPropertyAddress', 'TenantEmail', 'TenantPhoneNumber'
        ]

        # Read the mastertextdata.txt file using csv module for better control
        print(f"Attempting to read mastertextdata.txt from: {master_text_path.resolve()}")
        data = []
        header = []
        header_found = False
        with open(master_text_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            for i, row in enumerate(reader):
                if not header_found:
                    # Check if this row contains the expected column names
                    if all(col in ''.join(row) for col in ['LandlordCode', 'PropertyAddress', 'TenantCode']):
                        header = [h.strip() for h in row]
                        header_found = True
                    continue
                data.append(row[:len(header)]) # Truncate row to match header length
        
        if not header_found:
            print("Error: Could not find the header row in mastertextdata.txt. Please check the file format.")
            return

        # Create DataFrame from the read data
        master_df = pd.DataFrame(data, columns=header)

        # Standardize relevant columns
        for col in ['LandlordCode', 'PropertyAddress', 'TenantPropertyAddress']:
            if col in master_df.columns:
                master_df[col] = master_df[col].astype(str).str.strip().str.lower()

        # --- Debugging: Print master_df head and columns ---
        print("\n--- mastertextdata.txt Head (after custom parsing) ---")
        print(master_df.head())
        print("\n--- mastertextdata.txt Columns (after custom parsing) ---")
        print(master_df.columns)

        # --- Process Landlords ---
        print("\n--- Processing Landlords ---")
        unique_landlords = master_df[['LandlordCode', 'LandlordName', 'LandlordEmail', 'LandlordPhoneNumber']].drop_duplicates()
        
        # Create a mapping from original LandlordCode to new generated reference_code
        landlord_code_mapping = {}

        for index, row in unique_landlords.iterrows():
            original_landlord_code = str(row['LandlordCode']).strip()
            landlord_name = str(row['LandlordName']).strip()
            landlord_email = str(row['LandlordEmail']).strip() if pd.notna(row['LandlordEmail']) else None
            landlord_phone = str(row['LandlordPhoneNumber']).strip() if pd.notna(row['LandlordPhoneNumber']) else None

            # Handle NaN landlord codes
            if original_landlord_code == 'nan':
                print(f"  Skipping landlord due to NaN code: {landlord_name}")
                continue

            # Generate unique landlord reference code if too short or not unique
            new_landlord_code = f"{original_landlord_code}_LLRef{int(index):03d}".lower()

            landlord = Landlord.query.filter_by(reference_code=new_landlord_code).first()
            if not landlord:
                landlord = Landlord(reference_code=new_landlord_code, name=landlord_name, 
                                    email=landlord_email, phone_number=landlord_phone)
                db.session.add(landlord)
                db.session.flush()
                account = Account(name=f'{landlord.name} Account', type='landlord', landlord_id=landlord.id)
                db.session.add(account)
                print(f"  Adding new landlord: {landlord.name} ({landlord.reference_code})")
            else:
                print(f"  Landlord already exists: {landlord.name} ({landlord.reference_code})")
            
            landlord_code_mapping[original_landlord_code.lower()] = new_landlord_code
        db.session.commit()

        # --- Process Properties ---
        print("\n--- Processing Properties ---")
        unique_properties = master_df[['PropertyAddress', 'PropertyLandlordCode']].drop_duplicates()

        for index, row in unique_properties.iterrows():
            property_address = row['PropertyAddress'] # Already standardized upfront
            original_landlord_code_prop = str(row['PropertyLandlordCode']).strip()

            # Use the mapping to get the correct landlord reference code
            landlord_code_prop = landlord_code_mapping.get(original_landlord_code_prop.lower(), original_landlord_code_prop.lower())

            # Find landlord by code
            landlord = Landlord.query.filter_by(reference_code=landlord_code_prop).first()
            print(f"    Debugging Property: original_landlord_code_prop={original_landlord_code_prop}, landlord_code_prop={landlord_code_prop}, found_landlord={landlord.reference_code if landlord else 'None'}")
            landlord_id = landlord.id if landlord else None

            property_ = Property(address=property_address, landlord_id=landlord_id)
            if not property_:
                db.session.add(property_)
                print(f"  Adding new property: {property_address} linked to landlord ID: {landlord_id}")
            else:
                print(f"  Property already exists: {property_address}")
        db.session.commit()

        # --- Process Tenants ---
        print("\n--- Processing Tenants ---")
        # Iterate through all rows in master_df to process tenants
        for index, row in master_df.iterrows():
            tenant_code_raw = str(row['TenantCode']).strip()
            tenant_name = str(row['TenantName']).strip()
            tenant_property_address = row['TenantPropertyAddress'] # Already standardized upfront
            tenant_email = str(row['TenantEmail']).strip() if pd.notna(row['TenantEmail']) else None
            tenant_phone = str(row['LandlordPhoneNumber']).strip() if pd.notna(row['LandlordPhoneNumber']) else None
            property_landlord_code_from_tenant_row = str(row['PropertyLandlordCode']).strip() # Get landlord code from current tenant row

            # Generate unique tenant reference code
            new_tenant_reference_code = f"{tenant_code_raw}-{tenant_property_address.replace(' ', '')}" # Example: combine code and property address

            # Find property by standardized address
            property_ = Property.query.filter_by(address=tenant_property_address).first()
            property_id = property_.id if property_ else None

            # If property not found, create it and try to link to a landlord
            if not property_id:
                landlord_for_property_id = None
                if property_landlord_code_from_tenant_row:
                    landlord_for_property_code_mapped = landlord_code_mapping.get(property_landlord_code_from_tenant_row.lower(), property_landlord_code_from_tenant_row.lower())
                    landlord_for_property = Landlord.query.filter_by(reference_code=landlord_for_property_code_mapped).first()
                    if landlord_for_property:
                        landlord_for_property_id = landlord_for_property.id

                property_ = Property(address=tenant_property_address, landlord_id=landlord_for_property_id)
                db.session.add(property_)
                db.session.flush() # Flush to get the property ID
                property_id = property_.id
                print(f"  Created new property for tenant: {tenant_property_address} linked to landlord ID: {landlord_for_property_id}")

            tenant = Tenant.query.filter_by(reference_code=new_tenant_reference_code).first()
            if not tenant:
                tenant = Tenant(reference_code=new_tenant_reference_code, name=tenant_name, 
                                email=tenant_email, phone_number=tenant_phone, 
                                property_id=property_id)
                db.session.add(tenant)
                db.session.flush()
                account = Account(name=f'{tenant.name} Account', type='tenant', tenant_id=tenant.id)
                db.session.add(account)
                print(f"  Adding new tenant: {tenant_name} ({new_tenant_reference_code}) linked to property ID: {property_id}")
            else:
                print(f"  Tenant already exists: {tenant.name} ({new_tenant_reference_code})")
        db.session.commit()

        print("Data import complete!")

if __name__ == '__main__':
    import_data()
