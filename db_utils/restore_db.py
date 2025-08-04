
import os
import subprocess

# This script is to be run from the project root directory
# It reads the database configuration from the config.py file

# Get the absolute path to the project's root directory
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# Add the project root to the Python path
import sys
sys.path.insert(0, project_root)

from config import Config

def restore_database():
    """
    Restores the PostgreSQL database from a backup file using pg_restore.
    The user is prompted to select a backup file from the 'backups' directory.
    """
    db_uri = Config.SQLALCHEMY_DATABASE_URI
    if not db_uri.startswith('postgresql://'):
        print("This script only supports PostgreSQL databases.")
        return

    backups_dir = os.path.join(project_root, 'backups')
    if not os.path.isdir(backups_dir):
        print(f"Backup directory not found: {backups_dir}")
        return

    backup_files = [f for f in os.listdir(backups_dir) if f.endswith('.dump')]
    if not backup_files:
        print(f"No backup files found in {backups_dir}")
        return

    print("Please select a backup file to restore:")
    for i, filename in enumerate(backup_files):
        print(f"  {i + 1}: {filename}")

    try:
        selection = int(input("Enter the number of the backup file: ")) - 1
        if not 0 <= selection < len(backup_files):
            print("Invalid selection.")
            return
        backup_file = os.path.join(backups_dir, backup_files[selection])
    except ValueError:
        print("Invalid input. Please enter a number.")
        return

    # Parse the database URI
    try:
        from urllib.parse import urlparse
        result = urlparse(db_uri)
        username = result.username
        password = result.password
        database = result.path[1:]  # Remove the leading '/'
        host = result.hostname
        port = result.port or 5432
    except ImportError:
        print("Could not import urlparse. Please ensure you are using Python 3.")
        return
    except Exception as e:
        print(f"Error parsing database URI: {e}")
        return

    # Set the password for pg_restore
    os.environ['PGPASSWORD'] = password

    # Construct the pg_restore command
    command = [
        'C:\\Program Files\\PostgreSQL\\17\\bin\\pg_restore',
        '-U', username,
        '-h', host,
        '-p', str(port),
        '-d', database,
        '--clean',  # Drop database objects before recreating them
        '--if-exists', # Don't report an error if the object doesn't exist
        '-v',  # Verbose mode
        backup_file
    ]

    # Execute the command
    print(f"Restoring database '{database}' from '{backup_file}'...")
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
        if process.returncode == 0:
            print("Restore successful!")
            print(stdout.decode())
        else:
            print("Restore failed.")
            print(stderr.decode())
    except FileNotFoundError:
        print("Error: 'pg_restore' command not found. Make sure PostgreSQL client tools are installed and in your PATH.")
    finally:
        # Unset the password
        del os.environ['PGPASSWORD']

if __name__ == '__main__':
    restore_database()
