from app import app, db
from app.models import User, Role
import bcrypt
from sqlalchemy import text

def create_roles_and_admin_user():
    with app.app_context():
        # Create roles
        admin_role = Role(name='admin')
        user_role = Role(name='user')
        landlord_role = Role(name='Landlord')
        tenant_role = Role(name='Tenant')
        db.session.add(admin_role)
        db.session.add(user_role)
        db.session.add(landlord_role)
        db.session.add(tenant_role)
        db.session.commit()
        print("Roles created.")

        # Create a default admin user
        hashed_password = bcrypt.hashpw('adminpassword'.encode('utf-8'), bcrypt.gensalt())
        admin_user = User(username='admin', email='admin@example.com', password_hash=hashed_password)
        db.session.add(admin_user)
        db.session.commit()
        print("Default admin user 'admin' created.")
        
        # Assign admin role to the admin user
        admin_user.roles.append(admin_role)
        db.session.commit()
        print("Admin role assigned to 'admin' user.")

if __name__ == '__main__':
    create_roles_and_admin_user()
