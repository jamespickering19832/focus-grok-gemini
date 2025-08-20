
import bcrypt
from app import create_app, db
from app.models import User, Role

app = create_app()

with app.app_context():
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
        # Ensure the admin user has the admin role
        if admin_role not in admin_user.roles:
            admin_user.roles.append(admin_role)
            print("Added admin role to existing admin user.")
        else:
            print("Admin user already exists and has admin role.")

    # Commit changes
    db.session.commit()
    print("Database changes committed.")
