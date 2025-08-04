# app/db_routes.py
from flask import render_template, flash, redirect, url_for, request, send_from_directory
from werkzeug.utils import secure_filename
from app import app, db
from app.models import User, Role
from datetime import datetime
import os
import subprocess
from flask_login import login_required, current_user
from functools import wraps

def role_required(role_name):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or role_name not in [role.name for role in current_user.roles]:
                flash('You do not have permission to access this page.')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.route('/admin/export_db')
@login_required
@role_required('admin')
def export_db():
    try:
        project_root = os.path.abspath(os.path.join(app.root_path, '..'))
        backups_dir = os.path.join(project_root, 'backups')
        os.makedirs(backups_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        db_uri = app.config['SQLALCHEMY_DATABASE_URI']

        if db_uri.startswith('postgresql'):
            backup_file = os.path.join(backups_dir, f"backup_{timestamp}.dump")
            
            from urllib.parse import urlparse
            result = urlparse(db_uri)
            username = result.username
            password = result.password
            database = result.path[1:]
            host = result.hostname
            port = result.port or 5432

            os.environ['PGPASSWORD'] = password

            command = [
                r'C:\Program Files\PostgreSQL\17\bin\pg_dump',
                '-U', username,
                '-h', host,
                '-p', str(port),
                '-F', 'c',
                '-b',
                '-v',
                '-f', backup_file,
                database
            ]

            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = process.communicate()

            if process.returncode == 0:
                flash('Database exported successfully!', 'success')
                return send_from_directory(backups_dir, os.path.basename(backup_file), as_attachment=True)
            else:
                flash(f'Error exporting database: {stderr.decode()}', 'danger')

        elif db_uri.startswith('sqlite'):
            db_path = db_uri.split('sqlite:///')[-1]
            backup_file_path = os.path.join(backups_dir, f"backup_{timestamp}.db")
            import shutil
            shutil.copyfile(db_path, backup_file_path)
            flash('Database exported successfully!', 'success')
            return send_from_directory(backups_dir, os.path.basename(backup_file_path), as_attachment=True)

        else:
            flash('Unsupported database type for export.', 'danger')

    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
    
    finally:
        if 'PGPASSWORD' in os.environ:
            del os.environ['PGPASSWORD']

    return redirect(url_for('admin'))

@app.route('/admin/import_db', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def import_db():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part', 'danger')
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            flash('No selected file', 'danger')
            return redirect(request.url)
        if file:
            try:
                project_root = os.path.abspath(os.path.join(app.root_path, '..'))
                uploads_dir = os.path.join(project_root, 'uploads')
                os.makedirs(uploads_dir, exist_ok=True)
                backup_file_path = os.path.join(uploads_dir, secure_filename(file.filename))
                file.save(backup_file_path)

                db_uri = app.config['SQLALCHEMY_DATABASE_URI']

                if db_uri.startswith('postgresql'):
                    from urllib.parse import urlparse
                    result = urlparse(db_uri)
                    username = result.username
                    password = result.password
                    database = result.path[1:]
                    host = result.hostname
                    port = result.port or 5432

                    os.environ['PGPASSWORD'] = password

                    command = [
                        r'C:\Program Files\PostgreSQL\17\bin\pg_restore',
                        '-U', username,
                        '-h', host,
                        '-p', str(port),
                        '-d', database,
                        '--clean',
                        '--if-exists',
                        '-v',
                        backup_file_path
                    ]

                    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    stdout, stderr = process.communicate()

                    if process.returncode == 0:
                        flash('Database imported successfully!', 'success')
                    else:
                        flash(f'Error importing database: {stderr.decode()}', 'danger')
                
                elif db_uri.startswith('sqlite'):
                    db.session.remove()
                    db.engine.dispose()
                    db_path = db_uri.split('sqlite:///')[-1]
                    import shutil
                    shutil.copyfile(backup_file_path, db_path)
                    flash('Database imported successfully!', 'success')

                else:
                    flash('Unsupported database type for import.', 'danger')

            except Exception as e:
                flash(f'An error occurred: {str(e)}', 'danger')
            
            finally:
                if 'PGPASSWORD' in os.environ:
                    del os.environ['PGPASSWORD']
                if os.path.exists(backup_file_path):
                    os.remove(backup_file_path)

            return redirect(url_for('admin'))

    return render_template('import_db.html')
