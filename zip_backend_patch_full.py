import os
import zipfile

src_file1 = r'C:\Users\peera\Desktop\AntigravityProject\TeacherHub\sgs_module\validator.py'
src_file2 = r'C:\Users\peera\Desktop\AntigravityProject\TeacherHub\sgs_module\parser.py'
zip_path = r'C:\Users\peera\Desktop\TeacherHub_Backend_Patch.zip'

with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
    if os.path.exists(src_file1):
        zf.write(src_file1, r'sgs_module/validator.py')
        print(f'  + sgs_module/validator.py')
    
    if os.path.exists(src_file2):
        zf.write(src_file2, r'sgs_module/parser.py')
        print(f'  + sgs_module/parser.py')

print(f'\nCreated: {zip_path}')
