
import zipfile
import os
import datetime

def create_zip_backup(output_filename, base_dir, exclude_dirs, exclude_files_patterns):
    with zipfile.ZipFile(output_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(base_dir):
            # Exclude specified directories
            dirs[:] = [d for d in dirs if os.path.join(root, d) not in [os.path.join(base_dir, ed) for ed in exclude_dirs]]
            
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, base_dir)

                # Exclude files matching patterns
                excluded = False
                for pattern in exclude_files_patterns:
                    if fnmatch.fnmatch(file, pattern):
                        excluded = True
                        break
                
                if not excluded:
                    zipf.write(file_path, arcname)
    print(f"Backup created: {output_filename}")

if __name__ == "__main__":
    import fnmatch # Import fnmatch here
    
    base_directory = "D:\focus grok gemini"
    exclude_directories = ["venv", "__pycache__", "uploads"]
    exclude_file_patterns = ["*.db", "*.pyc"]

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"grok_gemini_backup_{timestamp}.zip"

    create_zip_backup(backup_filename, base_directory, exclude_directories, exclude_file_patterns)
