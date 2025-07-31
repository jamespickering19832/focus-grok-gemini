# app/forms.py
from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, SubmitField, SelectField, HiddenField, BooleanField, DateField
from wtforms.validators import DataRequired, Email, Optional, NumberRange
from wtforms import DateField
from flask_wtf.file import FileField, FileAllowed

class CompanyForm(FlaskForm):
    name = StringField('Company Name', validators=[DataRequired()])
    address = StringField('Company Address', validators=[DataRequired()])
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
    submit = SubmitField('Add Rent Payment')

class ManualExpenseForm(FlaskForm):
    landlord_id = SelectField('Landlord', coerce=int, validators=[DataRequired()])
    amount = FloatField('Amount', validators=[DataRequired()])
    date = DateField('Date', format='%Y-%m-%d', validators=[DataRequired()])
    description = StringField('Description', validators=[DataRequired()])
    submit = SubmitField('Add Expense')

class PayoutForm(FlaskForm):
    start_date = DateField('Start Date', validators=[DataRequired()], format='%Y-%m-%d')
    end_date = DateField('End Date', validators=[DataRequired()], format='%Y-%m-%d')
    vat_rate = FloatField('VAT Rate', validators=[DataRequired(), NumberRange(min=0, max=1)], default=0.2)
    submit = SubmitField('Process Payout')


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
    landlord_id = HiddenField('Landlord ID')
    submit = SubmitField('Add Property')

class EditPropertyForm(FlaskForm):
    address = StringField('Address', validators=[DataRequired()])
    rent_amount = FloatField('Rent Amount', validators=[DataRequired()])
    submit = SubmitField('Save Changes')

class DeletePropertyForm(FlaskForm):
    submit = SubmitField('Delete Property')