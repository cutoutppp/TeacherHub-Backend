import os
import zipfile

src_file = r'C:\Users\peera\Desktop\AntigravityProject\TeacherHub\sgs_module\validator.py'
zip_path = r'C:\Users\peera\Desktop\TeacherHub_Backend_Patch.zip'

with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
    if os.path.exists(src_file):
        zf.write(src_file, r'sgs_module/validator.py')
        print(f'  + sgs_module/validator.py')
    else:
        print(f'  ! NOT FOUND: {src_file}')

print(f'\nCreated: {zip_path}')
