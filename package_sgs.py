import os
import shutil
import zipfile
import sys

base_dir = r'C:\Users\peera\Desktop\AntigravityProject'
frontend_dist = os.path.join(base_dir, r'AssessmentHub\TeacherHubPortal\frontend\dist')
sgs_dir = os.path.join(base_dir, r'AssessmentHub\SgsNextschool')
backup_dir = os.path.join(base_dir, r'AssessmentHub\SgsNextschool_backup_before_v1.5.0')
desktop_zip = r'C:\Users\peera\Desktop\SgsNextschool_v1.5.1_Package.zip'

print("1. Validating frontend dist...")
if not os.path.exists(os.path.join(frontend_dist, 'index.html')):
    print("ERROR: frontend dist/index.html not found!")
    sys.exit(1)

dist_assets = os.listdir(os.path.join(frontend_dist, 'assets'))
print(f"   Dist assets found: {dist_assets}")

print("2. Backing up existing SgsNextschool...")
if not os.path.exists(backup_dir):
    def ignore_patterns(path, names):
        return [n for n in names if n in ('node_modules', '.git', '__pycache__')]
    shutil.copytree(sgs_dir, backup_dir, ignore=ignore_patterns)
    print(f"   Backed up successfully to {backup_dir}")
else:
    print(f"   Backup already preserved at {backup_dir}")

print("3. Updating AssessmentHub/SgsNextschool...")
sgs_assets = os.path.join(sgs_dir, 'assets')
os.makedirs(sgs_assets, exist_ok=True)

# Remove old hashed index-* files
for old_f in os.listdir(sgs_assets):
    if old_f.startswith('index-') or old_f.startswith('main-'):
        try:
            os.remove(os.path.join(sgs_assets, old_f))
        except Exception:
            pass

shutil.copy2(os.path.join(frontend_dist, 'index.html'), os.path.join(sgs_dir, 'index.html'))
if os.path.exists(os.path.join(frontend_dist, 'favicon.svg')):
    shutil.copy2(os.path.join(frontend_dist, 'favicon.svg'), os.path.join(sgs_dir, 'favicon.svg'))
if os.path.exists(os.path.join(frontend_dist, 'icons.svg')):
    shutil.copy2(os.path.join(frontend_dist, 'icons.svg'), os.path.join(sgs_dir, 'icons.svg'))

for f in dist_assets:
    shutil.copy2(os.path.join(frontend_dist, 'assets', f), os.path.join(sgs_assets, f))
print("   Updated SgsNextschool files successfully!")

print("4. Creating Desktop Release Zip Package...")
files_to_zip = []

# A. Standalone Web App
for root, _, files in os.walk(sgs_dir):
    if 'node_modules' in root or '.git' in root or '__pycache__' in root or 'frontend' in root:
        continue
    for file in files:
        full_path = os.path.join(root, file)
        rel_path = os.path.relpath(full_path, sgs_dir)
        files_to_zip.append((full_path, os.path.join('SgsNextschool_WebApp', rel_path)))

# B. Backend Patch files
backend_dir = os.path.join(base_dir, 'TeacherHub-Backend')
backend_patches = [
    (os.path.join(backend_dir, 'sgs_module', 'wp16_db.py'), 'Backend_Patch/sgs_module/wp16_db.py'),
    (os.path.join(backend_dir, 'sgs_module', 'sgs_router.py'), 'Backend_Patch/sgs_module/sgs_router.py'),
    (os.path.join(backend_dir, 'sgs_module', 'work_db.py'), 'Backend_Patch/sgs_module/work_db.py'),
]
for src, arc in backend_patches:
    if os.path.exists(src):
        files_to_zip.append((src, arc))

# C. Frontend source files
fe_src = os.path.join(base_dir, r'AssessmentHub\TeacherHubPortal\frontend\src\SgsNextschool')
for f in ['Wp16Modal.tsx', 'Dashboard.tsx', 'SgsNextschool.tsx']:
    src = os.path.join(fe_src, f)
    if os.path.exists(src):
        files_to_zip.append((src, os.path.join('Source_Code', f)))

# D. Create Readme file
readme_content = """====================================================================
ระบบ SGS & NextSchool v1.5.1 (ระบบดึงนักเรียนติด 0,ร,มส,มผ อัตโนมัติ & บัฟเฟอร์เพิ่มเอง)
====================================================================

สิ่งที่ได้รับการอัปเดตในเวอร์ชันนี้:
1. ระบบดึงนักเรียนติด 0, ร, มส, มผ อัตโนมัติ:
   - เมื่อครูกด "ยืนยันข้อมูลและบันทึก (วิชานี้)" ระบบจะคัดกรองเฉพาะนักเรียนที่ผลการเรียน
     เป็น 0, ร, มส, มผ บันทึกลงในฐานข้อมูล วผ.16 (wp16_pending_tasks.json และ Excel ต้นทาง) ให้อัตโนมัติทันที
   - นักเรียนที่ได้เกรดปกติ (เช่น 1, 2, 3, 4) จะไม่ถูกดึงเข้ามาให้รก
   - เมื่อเปิดกล่องทำ วผ.16 ระบบจะนำรายชื่อนักเรียนกลุ่มนี้มาแสดงทันที พร้อมให้ระบุงานค้าง

2. บัฟเฟอร์ความปลอดภัยในหน้า วผ.16 (Wp16Modal):
   - เพิ่มปุ่ม "+ เพิ่มนักเรียน" บนแถบเครื่องมือ
   - ป๊อปอัปเพิ่มนักเรียนกรณีพิเศษ/ตกหล่น (ระบุรหัส, ชื่อ-สกุล, ชั้น/ห้อง, คะแนนเดิม, ผลการเรียนเดิม, งานค้าง)
   - มีป้ายกำกับ "[เพิ่มเอง]" แสดงชัดเจนสำหรับนักเรียนที่เพิ่มผ่านบัฟเฟอร์
   - มีปุ่มลบถังขยะ 🗑️ ที่คอลัมน์ขวาสุด สามารถลบนักเรียนที่ไม่เกี่ยวข้องออกได้ทันที

3. แผงควบคุม Master Sync ลับเฉพาะ Admin:
   - ซ่อนปุ่มซิงค์จากหน้าครูทั่วไป 100%
   - ช่องทางเปิดแผงลับ:
     * คีย์ลัด: Ctrl + Shift + S หรือ Alt + S
     * ช่องค้นหา: พิมพ์ #sync หรือ #admin
     * ทริปเปิลคลิก: คลิกที่หัวข้อ "📊 แดชบอร์ดติดตามการส่งเกรด" ติดกัน 3 ครั้ง
   - สรุปจำนวนรายการงานค้างที่บันทึกไว้ และจำนวนที่พร้อมซิงค์ขึ้น Google Sheet
   - ปุ่ม "📥 ส่งออก Excel งานค้างทั้งหมด (วผ.16 ต้นทาง)" สำหรับดาวน์โหลดไปเปิดดูออฟไลน์

โครงสร้างในไฟล์ Zip:
- SgsNextschool_WebApp/ : โฟลเดอร์หน้าเว็บพร้อมใช้งาน (index.html, assets, templates)
- Backend_Patch/       : ไฟล์ Backend สำหรับเซิร์ฟเวอร์ (wp16_db.py, sgs_router.py)
- Source_Code/         : โค้ดต้นฉบับ TypeScript (Wp16Modal, Dashboard, SgsNextschool)
====================================================================
"""
readme_path = os.path.join(base_dir, 'TeacherHub-Backend', 'scratch_readme.txt')
with open(readme_path, 'w', encoding='utf-8') as f:
    f.write(readme_content)
files_to_zip.append((readme_path, 'README_v1.5.1.txt'))

with zipfile.ZipFile(desktop_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
    for src, arc in files_to_zip:
        zf.write(src, arc)
        print(f"   [+] {arc}")

print(f"\nSUCCESS: Created release package at {desktop_zip}")
print(f"Total files packaged: {len(files_to_zip)}")
