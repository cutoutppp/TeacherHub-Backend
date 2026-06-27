from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from auth_db import get_db, Teacher
from pydantic import BaseModel
from typing import List, Dict, Any
import urllib.request
import urllib.parse
import json

GAS_URL = "https://script.google.com/macros/s/AKfycbwXVm3nApZRjyykmZujQ7SXUS9DhTmH9YPSHyXbGPySeSHn2PFpUvoTPWVj4bIL94f_Nw/exec"
IOC_GAS_URL = "https://script.google.com/macros/s/AKfycbwzTGLKrviXPtOldU7Q8g7GqCInLW6-Y9NfQzEg72Yr7y-VZabNnDlcBRIR726FV-6T/exec"
def fetch_gas_tasks(teacher_name: str, action: str = 'tasks'):
    url = f"{GAS_URL}?action={action}&mode=teacher&keyword={urllib.parse.quote(teacher_name)}"
    try:
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req) as response:
            if response.status == 200:
                body = response.read().decode('utf-8')
                return json.loads(body)
    except Exception as e:
        print(f"Error fetching GAS API: {e}")
    return []

def fetch_ioc_pending(teaccode: str):
    url = f"{IOC_GAS_URL}?action=getPendingEvaluations&teac_code={urllib.parse.quote(str(teaccode))}"
    try:
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req) as response:
            if response.status == 200:
                body = response.read().decode('utf-8')
                data = json.loads(body)
                if data.get('status') == 'success':
                    pending_list = data.get('data', [])
                    return len(pending_list)
    except Exception as e:
        print(f"Error fetching IOC API: {e}")
    return 0

def fetch_ioc_my_projects(teaccode: str, teacher_name: str):
    try:
        data = json.dumps({
            "action": "getMyProjects", 
            "payload": {"teac_code": str(teaccode), "teacher_name": teacher_name}
        }).encode('utf-8')
        req = urllib.request.Request(IOC_GAS_URL, data=data, method='POST', headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req) as response:
            if response.status == 200:
                body = response.read().decode('utf-8')
                res = json.loads(body)
                if res.get('status') == 'success':
                    return res.get('data', [])
    except Exception as e:
        print(f"Error fetching IOC My Projects: {e}")
    return []

def fetch_ioc_subjects(teaccode: str):
    url = f"{IOC_GAS_URL}?action=getSubjects&teac_code={urllib.parse.quote(str(teaccode))}"
    try:
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req) as response:
            if response.status == 200:
                body = response.read().decode('utf-8')
                data = json.loads(body)
                if data.get('status') == 'success':
                    return data.get('data', [])
    except Exception as e:
        print(f"Error fetching IOC Subjects: {e}")
    return []


SGS_GAS_URL = "https://script.google.com/macros/s/AKfycbxzpP9b_eBJUU5KaNX1CbMOLHygMsrUdO7earro-bQIs8lMS9H6YM6Z6mlamm3jJd1fDQ/exec"

def fetch_sgs_data():
    try:
        req = urllib.request.Request(SGS_GAS_URL, method='GET')
        with urllib.request.urlopen(req) as response:
            if response.status == 200:
                body = response.read().decode('utf-8')
                return json.loads(body)
    except Exception as e:
        print(f"Error fetching SGS API: {e}")
    return {}

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

class DashboardStats(BaseModel):
    academic_issues: int
    sgs_submitted: int
    sgs_total: int
    ioc_status: str
    ioc_my_projects_status: str
    subject_breakdown: List[Dict[str, Any]] = []
    ioc_breakdown: List[Dict[str, Any]] = []
    sgs_breakdown: List[Dict[str, Any]] = []

@router.get("/stats/{userid}")
def get_dashboard_stats(userid: str, db = Depends(get_db)):
    teacher = db.get_teacher_by_userid(userid)
    if not teacher:
        return {
            "academic_issues": 0,
            "sgs_submitted": 0,
            "sgs_total": 0,
            "ioc_status": "ไม่พบข้อมูล",
            "ioc_my_projects_status": "ไม่พบข้อมูล",
            "subject_breakdown": [],
            "ioc_breakdown": []
        }
    
    teacher_name = f"{teacher.prefix or ''}{teacher.firstname or ''} {teacher.lastname or ''}".strip()
    
    # Fetch both pending and completed tasks to get full stats
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_tasks = executor.submit(fetch_gas_tasks, teacher_name, 'tasks')
        future_history = executor.submit(fetch_gas_tasks, teacher_name, 'history')
        future_ioc = executor.submit(fetch_ioc_pending, str(teacher.teaccode))
        future_my_projects = executor.submit(fetch_ioc_my_projects, str(teacher.teaccode), teacher_name)
        future_ioc_subjects = executor.submit(fetch_ioc_subjects, str(teacher.teaccode))
        future_sgs = executor.submit(fetch_sgs_data)
        
        tasks = future_tasks.result()
        history = future_history.result()
        pending_ioc = future_ioc.result()
        my_projects = future_my_projects.result()
        ioc_subjects = future_ioc_subjects.result()
        sgs_data = future_sgs.result()
    
    subject_counts = {}
    
    # Process pending tasks
    for task in tasks:
        subj = f"{task.get('subjCode', '')} {task.get('subjName', '')}".strip()
        if subj:
            if subj not in subject_counts:
                subject_counts[subj] = {"total": 0, "fixed": 0, "pending": 0}
            subject_counts[subj]["pending"] += 1
            subject_counts[subj]["total"] += 1
            
    # Process completed/history tasks
    for task in history:
        subj = f"{task.get('subjCode', '')} {task.get('subjName', '')}".strip()
        if subj:
            if subj not in subject_counts:
                subject_counts[subj] = {"total": 0, "fixed": 0, "pending": 0}
            subject_counts[subj]["fixed"] += 1
            subject_counts[subj]["total"] += 1
            
    subject_breakdown = [
        {
            "subject": k, 
            "total": v["total"],
            "fixed": v["fixed"],
            "pending": v["pending"]
        } 
        for k, v in subject_counts.items()
    ]
    
    academic_issues = sum(v["pending"] for v in subject_counts.values())
    
    if pending_ioc > 0:
        ioc_status = f"ค้างประเมิน {pending_ioc} รายการ"
    else:
        ioc_status = "ไม่มีงานค้าง"
        
    # Process my projects
    completed_projects = sum(1 for p in my_projects if p.get("status", "") in ["สมบูรณ์", "completed"])
    total_projects = len(my_projects)
    incomplete_projects = total_projects - completed_projects
    
    if total_projects == 0:
        ioc_my_projects_status = "ยังไม่มีข้อมูล"
    elif completed_projects < total_projects:
        ioc_my_projects_status = ""
    else:
        ioc_my_projects_status = f"ประเมินเสร็จสิ้น {total_projects} ชุด"
        
    ioc_breakdown = []
    for subj in ioc_subjects:
        subj_code = subj.get('subject_code', '')
        subj_name = subj.get('subject_name', '')
        midterm_status = 'ยังไม่สร้าง'
        final_status = 'ยังไม่สร้าง'
        
        for proj in my_projects:
            if proj.get('subject_code') == subj_code:
                exam_type = proj.get('exam_type', '')
                status = proj.get('status', '')
                
                status_th = "รอประเมิน" if status == "waiting" else "ประเมินเสร็จสิ้น" if status == "completed" else "ไม่ผ่าน/แก้ไข" if status == "rejected" else status
                
                if 'กลางภาค' in exam_type:
                    midterm_status = status_th
                elif 'ปลายภาค' in exam_type:
                    final_status = status_th
                    
        ioc_breakdown.append({
            "subject_code": subj_code,
            "subject_name": subj_name,
            "midterm_status": midterm_status,
            "final_status": final_status
        })
    
    # Process SGS breakdown from SgsNextschool GAS Data
    sgs_teachers = sgs_data.get("teachers", [])
    sgs_submissions = sgs_data.get("submissions", [])
    
    my_sgs_classes = [t for t in sgs_teachers if t.get("teacher_name") == teacher_name]
    sgs_submissions.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    
    sgs_breakdown = []
    for cls in my_sgs_classes:
        subj_code = cls.get("subject_code", "")
        class_room = cls.get("class_level", "")
        
        mid_subs = [s for s in sgs_submissions if s.get("subject_code") == subj_code and s.get("class_level") == class_room and s.get("round") == "กลางภาค" and s.get("teacher_name") == teacher_name]
        midterm_status = mid_subs[0].get("status", "❌ ยังไม่ส่ง") if mid_subs else "❌ ยังไม่ส่ง"
        
        fin_subs = [s for s in sgs_submissions if s.get("subject_code") == subj_code and s.get("class_level") == class_room and s.get("round") == "ปลายภาค" and s.get("teacher_name") == teacher_name]
        final_status = fin_subs[0].get("status", "❌ ยังไม่ส่ง") if fin_subs else "❌ ยังไม่ส่ง"
        
        # Resolve subject name from ioc_subjects as fallback
        subj_name = ""
        for ioc_s in ioc_subjects:
            if ioc_s.get("subject_code") == subj_code:
                subj_name = ioc_s.get("subject_name", "")
                break
                
        sgs_breakdown.append({
            "subject_code": subj_code,
            "subject_name": subj_name,
            "class_room": class_room,
            "midterm_status": midterm_status,
            "final_status": final_status,
        })
        
    sgs_total = len(my_sgs_classes)
    sgs_submitted = len([s for s in sgs_breakdown if "สมบูรณ์" in s["midterm_status"] or "สมบูรณ์" in s["final_status"]])
    
    return {
        "academic_issues": academic_issues,
        "sgs_submitted": sgs_submitted,
        "sgs_total": sgs_total,
        "ioc_status": ioc_status,
        "ioc_my_projects_status": ioc_my_projects_status,
        "subject_breakdown": subject_breakdown,
        "ioc_breakdown": ioc_breakdown,
        "sgs_breakdown": sgs_breakdown
    }
