# app/__init__.py
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_mail import Mail
from flask_login import LoginManager
from flask_talisman import Talisman
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os



db = SQLAlchemy()
migrate = Migrate()
mail = Mail()
login_manager = LoginManager()
login_manager.login_view = 'main.login'
talisman = Talisman()
limiter = Limiter(key_func=get_remote_address)

def create_app():
    app = Flask(__name__)
    app.config.from_object('config.Config')

    # Ensure directories exist
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])

    if not os.path.exists(app.config['STATEMENTS_FOLDER']):
        os.makedirs(app.config['STATEMENTS_FOLDER'])

    db.init_app(app)
    migrate.init_app(app, db)
    mail.init_app(app)
    login_manager.init_app(app)
    talisman.init_app(app, content_security_policy={
        'default-src': ["'self'"],
        'style-src': ["'self'", 'stackpath.bootstrapcdn.com'],
        'script-src': ["'self'", 'code.jquery.com', 'cdn.jsdelivr.net', 'stackpath.bootstrapcdn.com'],
        'img-src': ["'self'", 'data:'],
        'font-src': ["'self'", 'stackpath.bootstrapcdn.com'],
    })
    limiter.init_app(app)

    from .routes import main_bp
    app.register_blueprint(main_bp)

    with app.app_context():
        from . import models
        
        @login_manager.user_loader
        def load_user(user_id):
            return models.User.query.get(int(user_id))
            return models.User.query.get(int(user_id))

        from .models import Account
        def create_or_get_account(name, type_):
            account = Account.query.filter_by(name=name).first()
            if not account:
                account = Account(name=name, type=type_, balance=0.0)
                db.session.add(account)
                print(f'Created account: {name}')
            else:
                print(f'Account already exists: {name}')
            return account

        # Create or get Bank Account
        create_or_get_account('Master Bank Account', 'asset')

        # Create or get Suspense Account
        create_or_get_account('Suspense Account', 'suspense')

        # Create or get Agency Income Account
        create_or_get_account('Agency Income', 'agency_income')

        # Create or get Agency Expense Account
        create_or_get_account('Agency Expense', 'agency_expense')

        # Create or get Admin Fee Account
        create_or_get_account('Admin Fee Account', 'agency_income')

        # Create or get VAT Payable Account
        create_or_get_account('VAT Account', 'vat_payable')

        # Create or get Utility Account
        create_or_get_account('Utility Account', 'utility')

        # Create or get Admin Fee Account
        create_or_get_account('Admin Fee Account', 'agency_income')

        # Create or get VAT Payable Account
        create_or_get_account('VAT Account', 'vat_payable')

        db.session.commit()

    @app.cli.command("recalculate-balances")
    def recalculate_balances_command():
        """Recalculates balances for all accounts."""
        from .models import Account, Transaction
        
        accounts = Account.query.all()
        if not accounts:
            print("No accounts found.")
            return

        print(f"Found {len(accounts)} accounts. Recalculating balances...")

        for account in accounts:
            if account.name == 'Master Bank Account':
                total_amount = db.session.query(db.func.sum(Transaction.amount)).scalar()
            else:
                total_amount = db.session.query(db.func.sum(Transaction.amount)).filter(Transaction.account_id == account.id).scalar()

            new_balance = total_amount if total_amount is not None else 0.0
            account.balance = new_balance
            print(f"Account '{account.name}' (ID: {account.id}): New balance = {new_balance:.2f}")

        db.session.commit()
        print("\nAll account balances have been recalculated and updated successfully.")

    return app
