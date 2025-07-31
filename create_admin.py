
import bcrypt
from app import app, db
from app.models import User, Role

with app.app_context():
    db.create_all() # Ensure all tables are created

    # Check if admin role exists, if not create it
    admin_role = Role.query.filter_by(name='admin').first()
    if not admin_role:
        admin_role = Role(name='admin')
        db.session.add(admin_role)
        print("Admin role created.")

    # Check if admin user exists
    admin_user = User.query.filter_by(username='admin').first()
    if not admin_user:
        # Hash the password
        password = 'adminpassword'
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

        # Create the admin user
        admin_user = User(
            username='admin',
            email='admin@example.com',
            password_hash=hashed_password
        )
        admin_user.roles.append(admin_role)
        db.session.add(admin_user)
        print("Admin user created.")
    else:
        print("Admin user already exists.")

    # Commit changes
    db.session.commit()
    print("Database changes committed.")
