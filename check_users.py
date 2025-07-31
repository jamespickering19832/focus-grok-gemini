
from app import app, db
from app.models import User

with app.app_context():
    users = User.query.all()
    if not users:
        print("No users found in the database.")
    else:
        print("Existing users:")
        for user in users:
            print(f"  - Username: {user.username}, Email: {user.email}")
