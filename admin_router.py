from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from auth_db import get_db, Teacher
from auth_router import get_current_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])

import urllib.request
import json
import ssl

GAS_WEB_APP_URL = "https://script.google.com/macros/s/AKfycbwXVm3nApZRjyykmZujQ7SXUS9DhTmH9YPSHyXbGPySeSHn2PFpUvoTPWVj4bIL94f_Nw/exec"

@router.get("/stats")
def get_school_stats(db = Depends(get_db), admin = Depends(get_current_admin)):
    total_teachers = len(db.get_all())
    
    # Initialize with default zero values
    stats = {
        "total_teachers": total_teachers,
        "total_academic_issues": 0,
        "students_total": 0,
        "students_fixed": 0,
        "sgs_progress": {"submitted": 0, "total": 0, "percentage": 0},
        "ioc_progress": {"submitted": 0, "total": 0, "percentage": 0}
    }

    if GAS_WEB_APP_URL:
        try:
            # ดึงข้อมูลจาก Google Apps Script
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            req = urllib.request.Request(f"{GAS_WEB_APP_URL}?action=get_stats")
            with urllib.request.urlopen(req, context=ctx, timeout=30) as response:
                gas_data = json.loads(response.read().decode())
                
                # นำข้อมูลจริงมาแทนที่
                if "total_academic_issues" in gas_data:
                    stats["total_academic_issues"] = gas_data["total_academic_issues"]
                if "sgs_progress" in gas_data:
                    stats["sgs_progress"] = gas_data["sgs_progress"]
                if "ioc_progress" in gas_data:
                    stats["ioc_progress"] = gas_data["ioc_progress"]
        except Exception as e:
            print(f"Failed to fetch from GAS: {e}")
            pass # Fallback to mock data on error
            
    return stats

@router.get("/teachers")
def get_all_teachers(db = Depends(get_db), admin = Depends(get_current_admin)):
    teachers = db.get_all()
    return [{"id": t.id, "userid": t.userid, "teaccode": t.teaccode, "name": f"{t.prefix}{t.firstname} {t.lastname}", "subjectgroup": t.subjectgroup, "is_admin": t.is_admin} for t in teachers]

from pydantic import BaseModel
from auth_db import get_pin_hash

class TeacherCreate(BaseModel):
    userid: str
    teaccode: str
    prefix: str
    firstname: str
    lastname: str
    subjectgroup: str
    is_admin: bool = False

@router.post("/teachers")
def create_teacher(teacher_data: TeacherCreate, db = Depends(get_db), admin = Depends(get_current_admin)):
    # Check if userid already exists
    existing_user = db.get_teacher_by_userid(teacher_data.userid)
    if existing_user:
        raise HTTPException(status_code=400, detail="เลขบัตรประชาชนนี้มีในระบบแล้ว")
    
    # Generate PIN: Last 6 digits of userid, or 123456
    raw_pin = str(teacher_data.userid)[-6:] if teacher_data.userid and len(str(teacher_data.userid)) >= 6 else "123456"
    pin_hash = get_pin_hash(raw_pin)
    
    new_teacher = Teacher(
        userid=teacher_data.userid,
        pin_hash=pin_hash,
        teaccode=teacher_data.teaccode,
        prefix=teacher_data.prefix,
        firstname=teacher_data.firstname,
        lastname=teacher_data.lastname,
        subjectgroup=teacher_data.subjectgroup,
        is_admin=teacher_data.is_admin
    )
    
    success = db.add_teacher(new_teacher)
    if not success:
        raise HTTPException(status_code=500, detail="ไม่สามารถบันทึกข้อมูลลง Google Sheet ได้")
    
    return {"status": "success", "message": "เพิ่มครูใหม่สำเร็จ", "raw_pin": raw_pin}

@router.post("/teachers/{teacher_id}/reset_pin")
def reset_teacher_pin(teacher_id: int, db = Depends(get_db), admin = Depends(get_current_admin)):
    teacher = db.get_teacher_by_id(teacher_id)
    if not teacher:
        raise HTTPException(status_code=404, detail="ไม่พบข้อมูลครูท่านนี้")
        
    raw_pin = str(teacher.userid)[-6:] if teacher.userid and len(str(teacher.userid)) >= 6 else "123456"
    new_hash = get_pin_hash(raw_pin)
    
    success = db.update_pin(teacher.userid, new_hash)
    if not success:
        raise HTTPException(status_code=500, detail="ไม่สามารถบันทึกข้อมูลลง Google Sheet ได้")
    
    return {"status": "success", "message": "รีเซ็ตรหัสผ่านสำเร็จ", "new_pin": raw_pin}
