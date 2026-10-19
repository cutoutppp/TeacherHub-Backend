import os
import zipfile
import shutil

# Files changed in this session
updated_files = [
    # TeacherHubPortal - Frontend build output
    (r'C:\Users\peera\Desktop\AntigravityProject\AssessmentHub\TeacherHubPortal\frontend\dist\index.html',
     r'TeacherHubPortal/frontend/dist/index.html'),
    (r'C:\Users\peera\Desktop\AntigravityProject\AssessmentHub\TeacherHubPortal\frontend\dist\assets\index-Cy1d4rCB.css',
     r'TeacherHubPortal/frontend/dist/assets/index-Cy1d4rCB.css'),
    (r'C:\Users\peera\Desktop\AntigravityProject\AssessmentHub\TeacherHubPortal\frontend\dist\assets\index-Das9jyyN.js',
     r'TeacherHubPortal/frontend/dist/assets/index-Das9jyyN.js'),
    # TeacherHub - Backend
    (r'C:\Users\peera\Desktop\AntigravityProject\TeacherHub\sgs_module\validator.py',
     r'sgs_module/validator.py'),
    (r'C:\Users\peera\Desktop\AntigravityProject\TeacherHub\sgs_module\sgs_router.py',
     r'sgs_module/sgs_router.py'),
    # Source files (for reference/deploy)
    (r'C:\Users\peera\Desktop\AntigravityProject\AssessmentHub\TeacherHubPortal\frontend\src\TeacherHub.tsx',
     r'TeacherHubPortal/frontend/src/TeacherHub.tsx'),
]

zip_path = r'C:\Users\peera\Desktop\Updated_Files_v1.2.4.zip'

with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
    for src, arcname in updated_files:
        if os.path.exists(src):
            zf.write(src, arcname)
            print(f'  + {arcname}')
        else:
            print(f'  ! NOT FOUND: {src}')

print(f'\nCreated: {zip_path}')
