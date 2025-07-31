# app/__init__.py
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_mail import Mail
import os

app = Flask(__name__)
app.config.from_object('config.Config')

# Ensure directories exist
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

if not os.path.exists(app.config['STATEMENTS_FOLDER']):
    os.makedirs(app.config['STATEMENTS_FOLDER'])

db = SQLAlchemy(app)
migrate = Migrate(app, db)
mail = Mail(app)

from app import routes, models
from app.forms import *

@app.cli.command('send-monthly-statements')
def send_monthly_statements():
    "Send monthly landlord statements via email."
    from app.models import Landlord
    from app.statement_generator import generate_monthly_statement
    from flask_mail import Message
    from datetime import datetime, timedelta

    with app.app_context():
        today = datetime.now().date()
        first_day_of_month = today.replace(day=1)
        last_day_of_month = (today.replace(month=today.month % 12 + 1, day=1) - timedelta(days=1))

        landlords = Landlord.query.all()
        for landlord in landlords:
            if landlord.email and landlord.receives_email_statements:
                try:
                    # Generate statement PDF
                    pdf_path = generate_monthly_statement(landlord.id, first_day_of_month, last_day_of_month)
                    
                    msg = Message(
                        subject=f"Monthly Statement - {first_day_of_month.strftime('%B %Y')}",
                        sender=app.config['MAIL_USERNAME'],
                        recipients=[landlord.email]
                    )
                    msg.body = f"Dear {landlord.name},\n\nPlease find attached your monthly statement for {first_day_of_month.strftime('%B %Y')}.\n\nRegards,\nYour Letting Agency"
                    
                    with app.open_resource(pdf_path) as fp:
                        msg.attach(
                            filename=os.path.basename(pdf_path),
                            content_type="application/pdf",
                            data=fp.read()
                        )
                    mail.send(msg)
                    print(f"Sent statement to {landlord.email}")
                except Exception as e:
                    print(f"Failed to send statement to {landlord.email}: {e}")