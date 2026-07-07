from fastapi import APIRouter, UploadFile, File, HTTPException
import pdfplumber
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
        
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            full_text = ""
            for page in pdf.pages:
                full_text += page.extract_text() + "\n"
                
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
