from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
import fitz  # PyMuPDF
import io
import httpx
import re
from typing import List, Optional, Any

router = APIRouter(prefix="/api/moresor", tags=["moresor"])

PUA_TO_THAI = {
    '\uF700': 'ู', '\uF70A': '่', '\uF70B': '้', '\uF70C': '๊',
    '\uF70D': '๋', '\uF70E': '์', '\uF710': 'ั', '\uF711': 'ั',
    '\uF712': '็', '\uF713': '่', '\uF714': '้'
}
GAS_URL = 'https://script.google.com/macros/s/AKfycbwEwZ_8ZKA7K9qeeUX1b00ddGWNtOM1Hd2wcoqGfOsPaKlu4pl9oDSczsW4ckZsoEHz/exec'

PREFIX_MAP = {
    'นาย': 'นาย',
    'น.ส.': 'นางสาว',
    'ด.ช.': 'เด็กชาย',
    'ด.ญ.': 'เด็กหญิง'
}

def clean_thai_text(text: str) -> str:
    text = re.sub(r'[\u200B-\u200D\uFEFF]', '', text)
    for pua, thai in PUA_TO_THAI.items():
        text = text.replace(pua, thai)
    return text

@router.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...)):
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="File must be a PDF")
    
    try:
        content = await file.read()
        students = []
        course_code = ''
        class_room = ''
        
        doc = fitz.open(stream=content, filetype="pdf")
        
        # New alignment variables
        date_columns = [] # list of {text, x}
        all_student_marks = [] # list of dicts with student marks mapped to x
        
        extracted_lines = []
        for page in doc:
            words = page.get_text("words")
            lines_group = []
            for w in sorted(words, key=lambda x: x[1]):
                y_center = (w[1] + w[3]) / 2
                found = False
                for line in lines_group:
                    line_top = min(lw[1] for lw in line)
                    line_bottom = max(lw[3] for lw in line)
                    if line_top <= y_center <= line_bottom:
                        line.append(w)
                        found = True
                        break
                if not found:
                    lines_group.append([w])
            
            # Find date columns if not found yet
            if not date_columns:
                for line in lines_group:
                    line.sort(key=lambda x: x[0])
                    # If this line has many digits and looks like a header
                    if sum(1 for w in line if clean_thai_text(w[4]).isdigit()) >= 10:
                        # Extract digits as columns
                        for w in line:
                            t = clean_thai_text(w[4])
                            if t.isdigit():
                                date_columns.append({"text": t, "x": (w[0] + w[2]) / 2})
                        if date_columns:
                            break

            for line in lines_group:
                line.sort(key=lambda x: x[0])
                line_str = " ".join([w[4] for w in line])
                extracted_lines.append(line_str)
                
                # Check if it's a student line to extract raw marks and x coordinates
                clean_text_line = clean_thai_text(line_str)
                match = re.search(r'^(\d+)\s+(\d{5,6})', clean_text_line)
                if match:
                    student_id = match.group(2)
                    marks_data = []
                    for w in line:
                        clean_w = clean_thai_text(w[4])
                        # marks can be ✔ ✘ ลป / X ส ล. H ล 
                        if clean_w in ('✔', '✘', 'ลป', '/', 'X', 'x', 'ส', 'ล.', 'H', 'ล'):
                            marks_data.append({"text": clean_w, "x": (w[0] + w[2]) / 2})
                    all_student_marks.append({"studentId": student_id, "marks": marks_data})
                    
        full_text = "\n".join(extracted_lines)
        clean_text = clean_thai_text(full_text)
        lines = clean_text.split('\n')
        
        course_code = ""
        class_room = ""
        
        # Try finding header in new clean_text first
        header_match = re.search(r'([ก-ฮa-zA-Z]?\d{5})[^\d]*?(ม\.\d+/\d+|\d+/\d+)', clean_text)
        if header_match:
            course_code = header_match.group(1)
            class_room = header_match.group(2)
        else:
            header_match = re.search(r'([฀-๿A-Za-z0-9/]+)\s*[:|]\s*(ม\.\d+(?:/\d+)?)', clean_text)
            if header_match:
                course_code = header_match.group(1)
                class_room = header_match.group(2)
                
        # --- FALLBACK: Try original get_text("text") method first ---
        old_full_text = ""
        for page in doc:
            old_full_text += page.get_text("text") + "\n"
        doc.close()
        
        old_clean_text = clean_thai_text(old_full_text)
        old_lines = old_clean_text.split('\n')
        
        # If still not found, try finding header in old_clean_text
        if not course_code or not class_room:
            header_match = re.search(r'([ก-ฮa-zA-Z]?\d{5})[^\d]*?(ม\.\d+/\d+|\d+/\d+)', old_clean_text)
            if header_match:
                course_code = header_match.group(1)
                class_room = header_match.group(2)
            else:
                header_match = re.search(r'([฀-๿A-Za-z0-9/]+)\s*[:|]\s*(ม\.\d+(?:/\d+)?)', old_clean_text)
                if header_match:
                    course_code = header_match.group(1)
                    class_room = header_match.group(2)
            
        student_regex = re.compile(r'^(\d+)\s+(\d{5,6})\s+(.*?)\s+([✔✘/Xxสล\.H\s]+)$')
        

        
        def extract_students(target_lines):
            result = []
            inside_summary = False
            for line in target_lines:
                if 'สรุปเวลา' in line:
                    inside_summary = True
                if inside_summary:
                    continue
                    
                match = student_regex.search(line.strip())
                if match:
                    seq, student_id, name_raw, marks_str = match.groups()
                    if any(s['studentId'] == student_id for s in result):
                        continue
                        
                    clean_full_name = re.sub(r'\s+', ' ', name_raw.strip())
                    present_count = marks_str.count('✔') + marks_str.count('/')
                    absent_count = marks_str.count('✘') + marks_str.count('X') + marks_str.count('x')
                    leave_count = len(re.findall(r'ล[ก-ฮ]', marks_str)) + marks_str.count('ส') + marks_str.count('ล.') + marks_str.count('H') + marks_str.count('ล')
                    
                    result.append({
                        "no": int(seq),
                        "studentId": student_id,
                        "fullName": clean_full_name,
                        "classRoom": class_room,
                        "courseCode": course_code,
                        "present": present_count,
                        "absent": absent_count,
                        "leave": leave_count,
                        "totalAttended": present_count + leave_count
                    })
            return result

        # 1. Try original method
        students = extract_students(old_lines)
        
        # 2. If it fails, try the new demo method
        if not students:
            students = extract_students(lines)
                
        if len(students) > 0 and all(s['present'] == 0 for s in students):
            return {
                "success": False,
                "error": "ไม่สามารถบันทึกได้ เนื่องจากแบบฟอร์มนี้ยังไม่ได้เช็คชื่อ (นักเรียนได้ ✘ หรือ X ทุกคน)"
            }
            
        # ROUND 3 LOGIC: Find missing columns
        missing_columns = []
        if date_columns and all_student_marks:
            for i, col in enumerate(date_columns):
                has_mark = False
                for student in all_student_marks:
                    for mark in student["marks"]:
                        if abs(mark["x"] - col["x"]) < 15:
                            has_mark = True
                            break
                    if has_mark:
                        break
                
                if not has_mark:
                    missing_columns.append({
                        "colIndex": i + 1,
                        "dateText": col["text"]
                    })
                
        return {
            "success": True,
            "students": students,
            "courseCode": course_code,
            "classRoom": class_room,
            "missingColumns": missing_columns
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/masterdata")
async def get_masterdata(payload: dict):
    import httpx
    try:
        courseCode = payload.get("courseCode")
        classRoom = payload.get("classRoom")
        
        async with httpx.AsyncClient(verify=False, follow_redirects=True) as client:
            res = await client.get(f"{GAS_URL}?action=getDashboardData")
            result = res.json()
            
            if not result.get("success"):
                return {"success": False, "error": "Failed to fetch dashboard data"}
                
            courses = result.get("courses", [])

            def normalize_level(s):
                """Remove ม. prefix and strip whitespace for comparison"""
                return str(s).replace('ม.', '').strip()

            # Normalize incoming classRoom from PDF (e.g. "ม.5/1" → "5/1")
            norm_class_room = normalize_level(classRoom)
            # Split into level and room parts for flexible matching
            cr_parts = norm_class_room.split('/')
            cr_level = cr_parts[0] if len(cr_parts) > 0 else norm_class_room
            cr_room = cr_parts[1] if len(cr_parts) > 1 else ''

            for c in courses:
                master_code = str(c.get('รหัสวิชา', '')).strip()
                master_name = str(c.get('วิชา', '')).strip()
                master_level = normalize_level(c.get('ชั้น', ''))
                master_room = str(c.get('กลุ่ม-ห้อง', '')).strip()

                # Room match: compare normalized level and room number
                level_match = (master_level == cr_level)
                room_match_num = (master_room == cr_room) if cr_room else True
                room_match = level_match and room_match_num

                # Fallback: also allow if classRoom starts with master full room string
                if not room_match:
                    master_room_str = f"{master_level}/{master_room}"
                    room_match = norm_class_room.startswith(master_room_str) or norm_class_room.startswith(master_level)

                # Code match: exact or prefix match
                code_match = False
                norm_course_code = courseCode.strip()
                if master_code:
                    code_match = (master_code == norm_course_code) or norm_course_code.startswith(master_code)
                elif master_name:
                    # No code in masterdata — match by subject name
                    code_match = norm_course_code.startswith(master_name) or master_name in norm_course_code

                if room_match and code_match:
                    credits = float(c.get("หน่วยกิต", 0))
                    return {
                        "success": True,
                        "data": {
                            "teacherName": f"{c.get('คำนำหน้า', '')}{c.get('ชื่อ', '')} {c.get('นามสกุล', '')}".strip(),
                            "courseName": c.get("วิชา", ""),
                            "courseCode": master_code if master_code else master_name,
                            "classRoom": f"{master_level}/{master_room}" if master_room else master_level,
                            "credits": credits,
                            "totalHours": int(credits * 40),
                            "subjectGroup": c.get("กลุ่มสาระ", c.get("กลุ่มสาระการเรียนรู้", "อื่นๆ"))
                        }
                    }
            return {"success": False, "error": "Course not found in View_ClassTeacher"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.post("/export")
async def export_data(payload: dict):
    import httpx
    try:
        gas_payload = {"action": "submitReport"}
        gas_payload.update(payload)
        async with httpx.AsyncClient(verify=False, follow_redirects=True) as client:
            res = await client.post(GAS_URL, json=gas_payload)
            return res.json()
    except Exception as e:
        return {"success": False, "error": str(e)}

class UploadDriveRequest(BaseModel):
    fileBase64: str
    fileName: str
    courseCode: str
    classRoom: str
    teacherName: str
    subjectGroup: str

@router.post("/upload-pdf-drive")
async def upload_pdf_drive(req: UploadDriveRequest):
    import httpx
    try:
        gas_payload = {
            "action": "uploadPDFToDrive",
            "fileBase64": req.fileBase64,
            "fileName": req.fileName,
            "courseCode": req.courseCode,
            "classRoom": req.classRoom,
            "teacherName": req.teacherName,
            "subjectGroup": req.subjectGroup
        }
        async with httpx.AsyncClient(verify=False, follow_redirects=True, timeout=60.0) as client:
            res = await client.post(GAS_URL, json=gas_payload)
            return res.json()
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.post("/update-status")
async def update_status(payload: dict):
    import httpx
    try:
        gas_payload = {"action": "updateStudentStatus"}
        gas_payload.update(payload)
        async with httpx.AsyncClient(verify=False, follow_redirects=True) as client:
            res = await client.post(GAS_URL, json=gas_payload)
            return res.json()
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.get("/overview")
async def get_overview():
    import httpx
    try:
        async with httpx.AsyncClient(verify=False, follow_redirects=True) as client:
            res = await client.get(f"{GAS_URL}?action=getAllStudentReports")
            return res.json()
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.get("/dashboard")
async def get_dashboard():
    import httpx
    try:
        async with httpx.AsyncClient(verify=False, follow_redirects=True) as client:
            res = await client.get(f"{GAS_URL}?action=getDashboardData")
            return res.json()
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.get("/config")
async def get_config():
    import httpx
    try:
        async with httpx.AsyncClient(verify=False, follow_redirects=True) as client:
            res = await client.get(f"{GAS_URL}?action=getConfig")
            return res.json()
    except Exception as e:
        return {"success": False, "error": str(e)}
