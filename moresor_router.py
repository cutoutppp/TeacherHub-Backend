from fastapi import APIRouter, UploadFile, File, HTTPException
import fitz  # PyMuPDF
import io
import re

router = APIRouter(prefix="/api/moresor", tags=["moresor"])

PUA_TO_THAI = {
    '\uF700': 'ู', '\uF70A': '่', '\uF70B': '้', '\uF70C': '๊',
    '\uF70D': '๋', '\uF70E': '์', '\uF710': 'ั', '\uF711': 'ั',
    '\uF712': '็', '\uF713': '่', '\uF714': '้'
}

PREFIX_MAP = {
    'นาย': 'นาย',
    'น.ส.': 'นางสาว',
    'ด.ช.': 'เด็กชาย',
    'ด.ญ.': 'เด็กหญิง'
}

def clean_thai_text(text: str) -> str:
    # Remove zero-width spaces
    text = re.sub(r'[\u200B-\u200D\uFEFF]', '', text)
    # Map PUA characters
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
        
        # Use PyMuPDF to extract text
        doc = fitz.open(stream=content, filetype="pdf")
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
            
            for line in lines_group:
                line.sort(key=lambda x: x[0])
                line_str = " ".join([w[4] for w in line])
                extracted_lines.append(line_str)
        doc.close()
        
        full_text = "\n".join(extracted_lines)
                
        clean_text = clean_thai_text(full_text)
        lines = clean_text.split('\n')
        
        # Match header for Course Code and Class Room
        header_match = re.search(r'([ก-ฮA-Za-z0-9]+)\s*:\s*(ม\.\d+/\d+)', clean_text)
        if header_match:
            course_code = header_match.group(1)
            class_room = header_match.group(2)
            
        student_regex = re.compile(r'^(\d+)\s+(\d{5})\s+(นาย|น\.ส\.|ด\.ช\.|ด\.ญ\.)\s+(.*?)\s*([✔✘\s]*(?:ลว[✔✘\s]*)*)$')
        
        inside_summary = False
        for line in lines:
            if 'สรุปเวลา' in line:
                inside_summary = True
            if inside_summary:
                continue
                
            match = student_regex.search(line.strip())
            if match:
                seq, student_id, prefix_short, full_name_raw, marks_str = match.groups()
                
                if any(s['studentId'] == student_id for s in students):
                    continue
                    
                prefix_full = PREFIX_MAP.get(prefix_short, prefix_short)
                clean_full_name = re.sub(r'\s+', ' ', f"{prefix_full}{full_name_raw.strip()}")
                
                present_count = marks_str.count('✔')
                absent_count = marks_str.count('✘')
                leave_count = marks_str.count('ลว')
                
                students.append({
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
                
        return {
            "success": True,
            "students": students,
            "courseCode": course_code,
            "classRoom": class_room
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

GAS_URL = 'https://script.google.com/macros/s/AKfycbwEwZ_8ZKA7K9qeeUX1b00ddGWNtOM1Hd2wcoqGfOsPaKlu4pl9oDSczsW4ckZsoEHz/exec'

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
            for c in courses:
                room_str = f"{c.get('ชั้น', '')}/{c.get('กลุ่ม-ห้อง', '')}"
                if c.get("รหัสวิชา") == courseCode and room_str == classRoom:
                    credits = float(c.get("หน่วยกิต", 0))
                    return {
                        "success": True,
                        "data": {
                            "teacherName": f"{c.get('คำนำหน้า', '')}{c.get('ชื่อ', '')} {c.get('นามสกุล', '')}",
                            "courseName": c.get("วิชา", ""),
                            "credits": credits,
                            "totalHours": credits * 40
                        }
                    }
            return {"success": False, "error": "Course not found"}
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
