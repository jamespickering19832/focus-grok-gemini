# run.py
from app import app

if __name__ == "__main__":
    print(f"Using database: {app.config['SQLALCHEMY_DATABASE_URI']}")
    app.run(debug=True)