import os
import zipfile

def create_zip(source_dir, zip_filename, exclude_dirs):
    with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(source_dir):
            # Exclude directories
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            
            for file in files:
                file_path = os.path.join(root, file)
                # Add file to zip relative to the source directory
                arcname = os.path.relpath(file_path, start=os.path.dirname(source_dir))
                zipf.write(file_path, arcname)
    print(f"Created: {zip_filename}")

exclude = {'node_modules', '.venv', 'venv', '__pycache__', 'dist', '.git', 'backend'}

frontend_src = r'C:\Users\peera\Desktop\AntigravityProject\AssessmentHub'
frontend_zip = r'C:\Users\peera\Desktop\AssessmentHub_Frontend_v1.2.4.zip'
create_zip(frontend_src, frontend_zip, exclude)

