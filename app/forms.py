# app/forms.py
from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, SubmitField, SelectField, HiddenField, BooleanField, DateField, PasswordField
from wtforms.validators import DataRequired, Email, Optional, NumberRange, EqualTo, ValidationError, Length, Regexp
from wtforms import DateField, SelectMultipleField
from flask_wtf.file import FileField, FileAllowed
from app.models import User

class ChangeDateForm(FlaskForm):
    date = DateField('Date', format='%Y-%m-%d', validators=[DataRequired()])
    submit = SubmitField('Change Date')

class EditUserForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired()])
    password = PasswordField('New Password', validators=[Optional(), Length(min=8), Regexp(r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&_]).*$', message='Password must contain uppercase, lowercase, number, and special character.')])
    password2 = PasswordField('Repeat New Password', validators=[EqualTo('password', message='Passwords must match')])
    roles = SelectMultipleField('Roles', coerce=int)
    submit = SubmitField('Save Changes')

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Login')

class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    password2 = PasswordField(
        'Repeat Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Register')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user is not None:
            raise ValidationError('Please use a different username.')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user is not None:
            raise ValidationError('Please use a different email address.')

class CompanyForm(FlaskForm):
    name = StringField('Company Name', validators=[DataRequired()])
    address = StringField('Company Address', validators=[DataRequired()])
    phone = StringField('Phone Number', validators=[Optional()])
    email = StringField('Email', validators=[Optional()])
    logo = FileField('Company Logo', validators=[FileAllowed(['jpg', 'png', 'gif'])])
    submit = SubmitField('Update Company Information')


class DateRangeForm(FlaskForm):
    start_date = DateField('Start Date', format='%Y-%m-%d', validators=[DataRequired()])
    end_date = DateField('End Date', format='%Y-%m-%d', validators=[DataRequired()])
    submit = SubmitField('Filter')

class ManualRentForm(FlaskForm):
    tenant_id = SelectField('Tenant', coerce=int, validators=[DataRequired()])
    amount = FloatField('Amount', validators=[DataRequired()])
    date = DateField('Date', format='%Y-%m-%d', validators=[DataRequired()])
    description = StringField('Description', validators=[DataRequired()])
    reference_code = StringField('Reference Code', validators=[Optional()])
    submit = SubmitField('Add Rent Payment')

class ManualExpenseForm(FlaskForm):
    landlord_id = SelectField('Landlord', coerce=int, validators=[DataRequired()])
    amount = FloatField('Amount', validators=[DataRequired()])
    date = DateField('Date', format='%Y-%m-%d', validators=[DataRequired()])
    description = StringField('Description', validators=[DataRequired()])
    reference_code = StringField('Reference Code', validators=[Optional()])
    submit = SubmitField('Add Expense')

class PayoutForm(FlaskForm):
    start_date = DateField('Start Date', validators=[DataRequired()], format='%Y-%m-%d')
    end_date = DateField('End Date', validators=[DataRequired()], format='%Y-%m-%d')
    vat_rate = FloatField('VAT Rate', validators=[DataRequired(), NumberRange(min=0, max=1)], default=0.2)
    submit = SubmitField('Process Payout')

class StatementGenerationForm(FlaskForm):
    landlord_id = SelectField('Landlord', coerce=int, validators=[DataRequired()])
    statement_type = SelectField('Statement Type', choices=[('monthly', 'Monthly'), ('annual', 'Annual')], validators=[DataRequired()])
    start_date = DateField('Start Date', format='%Y-%m-%d', validators=[Optional()])
    end_date = DateField('End Date', format='%Y-%m-%d', validators=[Optional()])
    year = StringField('Year', validators=[Optional()])
    vat_rate = FloatField('VAT Rate', validators=[DataRequired(), NumberRange(min=0, max=1)], default=0.2)
    submit = SubmitField('Generate Statement')


class AddTenantForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired()])
    phone_number = StringField('Phone Number', validators=[Optional()])
    start_date = DateField('Start Date', format='%Y-%m-%d', validators=[Optional()])
    reference_code = StringField('Reference Code', validators=[DataRequired()])
    property_id = SelectField('Property', coerce=int, validators=[Optional()])
    submit = SubmitField('Add Tenant')

class AddLandlordForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired()])
    phone_number = StringField('Phone Number', validators=[Optional()])
    address = StringField('Address', validators=[Optional()])
    bank_name = StringField('Bank Name', validators=[Optional()])
    bank_account_number = StringField('Bank Account Number', validators=[Optional()])
    bank_sort_code = StringField('Bank Sort Code', validators=[Optional()])
    reference_code = StringField('Reference Code', validators=[DataRequired()])
    commission_rate = FloatField('Commission Rate', validators=[Optional()])
    submit = SubmitField('Add Landlord')

class EditLandlordForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired()])
    phone_number = StringField('Phone Number', validators=[Optional()])
    address = StringField('Address', validators=[Optional()])
    bank_name = StringField('Bank Name', validators=[Optional()])
    bank_account_number = StringField('Bank Account Number', validators=[Optional()])
    bank_sort_code = StringField('Bank Sort Code', validators=[Optional()])
    reference_code = StringField('Reference Code', validators=[DataRequired()])
    commission_rate = FloatField('Commission Rate', validators=[Optional()])
    receives_email_statements = BooleanField('Receives Email Statements')
    submit = SubmitField('Save Changes')

class DeleteLandlordForm(FlaskForm):
    submit = SubmitField('Delete Landlord')

class EditTenantForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired()])
    phone_number = StringField('Phone Number', validators=[Optional()])
    start_date = DateField('Start Date', format='%Y-%m-%d', validators=[Optional()])
    reference_code = StringField('Reference Code', validators=[DataRequired()])
    property_id = SelectField('Property', coerce=int, validators=[DataRequired()])
    submit = SubmitField('Save Changes')

class DeleteTenantForm(FlaskForm):
    submit = SubmitField('Delete Tenant')

class AddPropertyForm(FlaskForm):
    address = StringField('Address', validators=[DataRequired()])
    rent_amount = FloatField('Rent Amount', validators=[DataRequired()])
    landlord_portion = FloatField('Landlord Portion', default=1.0, validators=[DataRequired(), NumberRange(min=0.0, max=1.0)])
    utility_account_id = SelectField('Utility Account', coerce=int, validators=[Optional()])
    landlord_id = HiddenField('Landlord ID')
    submit = SubmitField('Add Property')

class EditPropertyForm(FlaskForm):
    address = StringField('Address', validators=[DataRequired()])
    rent_amount = FloatField('Rent Amount', validators=[DataRequired()])
    landlord_portion = FloatField('Landlord Portion', validators=[DataRequired(), NumberRange(min=0.0, max=1.0)])
    utility_account_id = SelectField('Utility Account', coerce=int, validators=[Optional()])
    submit = SubmitField('Save Changes')

class DeletePropertyForm(FlaskForm):
    submit = SubmitField('Delete Property')

class AddAccountForm(FlaskForm):
    name = StringField('Account Name', validators=[DataRequired()])
    type = SelectField('Account Type', choices=[
        ('asset', 'Asset'), 
        ('liability', 'Liability'), 
        ('utility', 'Utility'), 
        ('suspense', 'Suspense'),
        ('agency_income', 'Agency Income'),
        ('agency_expense', 'Agency Expense')
    ], validators=[DataRequired()])
    submit = SubmitField('Create Account')