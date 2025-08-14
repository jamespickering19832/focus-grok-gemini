@app.route('/company', methods=['GET', 'POST'])
def company():
    company = Company.query.first()
    form = CompanyForm(obj=company)
    if form.validate_on_submit():
        if not company:
            company = Company()
            db.session.add(company)
        form.populate_obj(company)
        if form.logo.data:
            filename = secure_filename(form.logo.data.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            form.logo.data.save(file_path)
            company.logo = filename
        db.session.commit()
        flash('Company information updated successfully.')
        return redirect(url_for('company'))
    return render_template('company.html', form=form)

@app.route('/admin')
@login_required
@role_required('admin')
def admin():
    return render_template('admin.html')

@app.route('/manage_users')
@login_required
@role_required('admin')
def manage_users():
    users = User.query.all()
    return render_template('user.html', users=users)

@app.route('/edit_user/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def edit_user(id):
    user = User.query.get_or_404(id)
    form = EditUserForm(obj=user)
    form.roles.choices = [(role.id, role.name) for role in Role.query.all()]
    if form.validate_on_submit():
        user.username = form.username.data
        user.email = form.email.data
        if form.password.data:
            user.password_hash = bcrypt.hashpw(form.password.data.encode('utf-8'), bcrypt.gensalt())
        user.roles = []
        for role_id in form.roles.data:
            role = Role.query.get(role_id)
            if role:
                user.roles.append(role)
        db.session.commit()
        flash('User updated successfully.')
        return redirect(url_for('manage_users'))
    return render_template('edit_user.html', form=form, user=user)

@app.route('/admin_reset_data', methods=['POST'])
@login_required
@role_required('admin')
def admin_reset_data():
    try:
        # Delete data from tables in reverse order of dependency
        db.session.query(AllocationHistory).delete()
        db.session.query(Transaction).delete()
        db.session.query(Statement).delete()
        db.session.query(AuditLog).delete()
        db.session.query(Expense).delete()
        db.session.query(RentChargeBatch).delete()
        db.session.query(Account).delete()
        db.session.query(Tenant).delete()
        db.session.query(Property).delete()
        db.session.query(Landlord).delete()
        db.session.query(Company).delete()

        db.session.commit()
        flash('All application data has been reset successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error resetting data: {str(e)}', 'danger')
    return redirect(url_for('admin'))