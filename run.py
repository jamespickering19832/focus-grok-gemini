# run.py
from app import create_app

app = create_app()
from freezegun import freeze_time
from flask import session

@app.before_request
def before_request():
    if 'system_date' in session:
        freezer = freeze_time(session['system_date'])
        freezer.start()

if __name__ == "__main__":
    print(f"Using database: {app.config['SQLALCHEMY_DATABASE_URI']}")
    app.run(debug=True)