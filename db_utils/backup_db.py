
import os
import subprocess
import datetime

# This script is to be run from the project root directory
# It reads the database configuration from the config.py file

# Get the absolute path to the project's root directory
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# Add the project root to the Python path
import sys
sys.path.insert(0, project_root)

from config import Config

def backup_database():
    """
    Backs up the PostgreSQL database using pg_dump.
    The backup file is saved in a 'backups' directory within the project root.
    """
    db_uri = Config.SQLALCHEMY_DATABASE_URI
    if not db_uri.startswith('postgresql://'):
        print("This script only supports PostgreSQL databases.")
        return

    # Create the backups directory if it doesn't exist
    backups_dir = os.path.join(project_root, 'backups')
    os.makedirs(backups_dir, exist_ok=True)

    # Parse the database URI
    # Format: postgresql://user:password@host/dbname
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

    # Set the password for pg_dump
    os.environ['PGPASSWORD'] = password

    # Construct the pg_dump command
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(backups_dir, f"backup_{timestamp}.dump")
    command = [
        'C:\\Program Files\\PostgreSQL\\17\\bin\\pg_dump',
        '-U', username,
        '-h', host,
        '-p', str(port),
        '-F', 'c',  # Custom format, compressed
        '-b',  # Include large objects
        '-v',  # Verbose mode
        '-f', backup_file,
        database
    ]

    # Execute the command
    print(f"Backing up database '{database}' to '{backup_file}'...")
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
        if process.returncode == 0:
            print("Backup successful!")
            print(stdout.decode())
        else:
            print("Backup failed.")
            print(stderr.decode())
    except FileNotFoundError:
        print("Error: 'pg_dump' command not found. Make sure PostgreSQL client tools are installed and in your PATH.")
    finally:
        # Unset the password
        del os.environ['PGPASSWORD']

if __name__ == '__main__':
    backup_database()
