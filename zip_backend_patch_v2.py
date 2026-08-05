import os
import zipfile

src_file1 = r'C:\Users\peera\Desktop\AntigravityProject\TeacherHub\sgs_module\parser.py'
src_file2 = r'C:\Users\peera\Desktop\AntigravityProject\TeacherHub\sgs_module\doc_generator.py'
src_file3 = r'C:\Users\peera\Desktop\AntigravityProject\TeacherHub\sgs_module\sgs_router.py'
src_file4 = r'C:\Users\peera\Desktop\AntigravityProject\TeacherHub\sgs_module\work_db.py'
zip_path = r'C:\Users\peera\Desktop\TeacherHub_Backend_Patch_v2.zip'

with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
    for f, name in [
        (src_file1, 'sgs_module/parser.py'),
        (src_file2, 'sgs_module/doc_generator.py'),
        (src_file3, 'sgs_module/sgs_router.py'),
        (src_file4, 'sgs_module/work_db.py'),
    ]:
        if os.path.exists(f):
            zf.write(f, name)
            print(f'  + {name}')

print(f'\nCreated: {zip_path}')
