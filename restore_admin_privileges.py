
from app import app, db
from app.models import User, Role

with app.app_context():
    # Find the admin user
    admin_user = User.query.filter_by(username='admin').first()

    if admin_user:
        # Find or create the admin role
        admin_role = Role.query.filter_by(name='admin').first()
        if not admin_role:
            admin_role = Role(name='admin')
            db.session.add(admin_role)
            db.session.commit()
            print("Admin role created.")

        # Assign the admin role to the admin user if not already assigned
        if admin_role not in admin_user.roles:
            admin_user.roles.append(admin_role)
            db.session.commit()
            print("Admin privileges restored for 'admin' user.")
        else:
            print("'admin' user already has admin privileges.")
    else:
        print("'admin' user not found.")
