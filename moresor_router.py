from fastapi import APIRouter, File, UploadFile, HTTPException
from pydantic import BaseModel
import httpx
import re
import fitz  # PyMuPDF
from typing import List, Optional, Any

router = APIRouter(prefix="/api/moresor", tags=["moresor"])

GAS_URL = "https://script.google.com/macros/s/AKfycbwEwZ_8ZKA7K9qeeUX1b00ddGWNtOM1Hd2wcoqGfOsPaKlu4pl9oDSczsW4ckZsoEHz/exec"

class MasterDataRequest(BaseModel):
    courseCode: str
    classRoom: str

class ExportRequest(BaseModel):
    data: List[dict]
    courseCode: str
    classRoom: str
    teacherName: str

class UpdateStatusRequest(BaseModel):
    courseCode: str
    classRoom: str
    studentId: str
    allowExam: bool
    remark: Optional[str] = None

@router.post("/masterdata")
async def get_masterdata(req: MasterDataRequest):
    # Proxy to GAS: Fetch all dashboard data and filter out the masterdata locally in Python
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{GAS_URL}?action=getDashboardData", follow_redirects=True)
            data = resp.json()
            if not data.get("success"):
                return {"success": False, "error": "Failed to fetch from GAS"}
            
            courses = data.get("courses", [])
            
            # Extract grade and room (e.g. ม.5/9 -> ม.5, 9)
            grade = req.classRoom
            room = ""
            match = re.search(r'(ม\.\d+)/(\d+)', req.classRoom)
            if match:
                grade = match.group(1)
                room = match.group(2)
                
            for c in courses:
                if str(c.get("รหัสวิชา")).strip() == str(req.courseCode).strip() and \
                   str(c.get("ชั้น")).strip() == grade and \
                   str(c.get("กลุ่ม-ห้อง")).strip() == room:
                    
                    prefix = c.get("คำนำหน้า", "")
                    fname = c.get("ชื่อ", "")
                    lname = c.get("นามสกุล", "")
                    teacherName = f"{prefix}{fname} {lname}".strip()
                    
                    credits_str = c.get("หน่วยกิต", 0)
                    try:
                        credits_val = float(credits_str)
                    except:
                        credits_val = 0
                        
                    totalHours = int(credits_val * 40)
                    courseName = c.get("วิชา", "")
                    
                    return {
                        "success": True,
                        "data": {
                            "teacherName": teacherName,
                            "totalHours": totalHours,
                            "courseName": courseName
                        }
                    }
            return {"success": False, "error": "Course not found in View_ClassTeacher"}
        except Exception as e:
            return {"success": False, "error": str(e)}

@router.post("/export")
async def export_data(req: ExportRequest):
    # Translate frontend's export request to GAS's submitReport action
    async with httpx.AsyncClient() as client:
        payload = {
            "action": "submitReport",
            "data": req.data,
            "courseCode": req.courseCode,
            "classRoom": req.classRoom,
            "teacherName": req.teacherName
        }
        try:
            resp = await client.post(GAS_URL, json=payload, follow_redirects=True)
            return resp.json()
        except Exception as e:
            return {"success": False, "error": str(e)}

@router.post("/update-status")
async def update_status(req: UpdateStatusRequest):
    # Translate frontend's update-status request to GAS's updateStudentStatus action
    async with httpx.AsyncClient() as client:
        payload = {
            "action": "updateStudentStatus",
            "courseCode": req.courseCode,
            "classRoom": req.classRoom,
            "studentId": req.studentId,
            "allowExam": req.allowExam,
            "remark": req.remark
        }
        try:
            resp = await client.post(GAS_URL, json=payload, follow_redirects=True)
            return resp.json()
        except Exception as e:
            return {"success": False, "error": str(e)}

@router.get("/dashboard")
async def get_dashboard():
    # Proxy to GAS getDashboardData
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{GAS_URL}?action=getDashboardData", follow_redirects=True)
            return resp.json()
        except Exception as e:
            return {"success": False, "error": str(e)}

@router.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...)):
    try:
        content = await file.read()
        doc = fitz.open(stream=content, filetype="pdf")
        
        full_text = ""
        for page in doc:
            full_text += page.get_text("text") + "\n"
            
        course_code_match = re.search(r'รหัสวิชา\s*([A-Za-zก-ฮ0-9]+)', full_text)
        class_room_match = re.search(r'ชั้น\s*(ม\.\d+/\d+)', full_text)
        
        courseCode = course_code_match.group(1) if course_code_match else "Unknown"
        classRoom = class_room_match.group(1) if class_room_match else "Unknown"
        
        students = []
        # Pattern matching for student data
        pattern = r'^(\d+)\s+(\d{5})\s+(ด\.ช\.|ด\.ญ\.|นาย|นางสาว|น\.ส\.)\s*([^\s]+)\s+([^\s]+)\s+(\d+)\s+([A-Za-z0-9]+)'
        
        for line in full_text.split('\n'):
            line = line.strip()
            match = re.search(pattern, line)
            if match:
                no = match.group(1)
                studentId = match.group(2)
                prefix = match.group(3)
                fname = match.group(4)
                lname = match.group(5)
                
                students.append({
                    "ที่": no,
                    "รหัสประจำตัว": studentId,
                    "คำนำหน้า": prefix,
                    "ชื่อ": fname,
                    "นามสกุล": lname,
                    "อนุญาตให้เข้าสอบ": False
                })
        
        return {
            "success": True,
            "courseCode": courseCode,
            "classRoom": classRoom,
            "data": students
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
