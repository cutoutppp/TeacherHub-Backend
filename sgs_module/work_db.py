import json
import os
from datetime import datetime

DB_FILE = "work_db.json"

def _load_db():
    if not os.path.exists(DB_FILE):
        return {}
    try:
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def _save_db(data):
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def add_work(teacher_name, subject_code, class_level, pair_data):
    db = _load_db()
    if teacher_name not in db:
        db[teacher_name] = {}
        
    if subject_code not in db[teacher_name]:
        db[teacher_name][subject_code] = {}
        
    db[teacher_name][subject_code][class_level] = {
        "timestamp": datetime.now().isoformat(),
        "data": pair_data
    }
    
    _save_db(db)

def get_works_for_teacher(teacher_name):
    db = _load_db()
    if not teacher_name or teacher_name not in db:
        return db
    return {teacher_name: db.get(teacher_name, {})}

def get_rooms_for_subject(teacher_name, subject_code=None):
    db = _load_db()
    teacher_data = db.get(teacher_name, {})
    if subject_code:
        subject_data = teacher_data.get(subject_code, {})
        return [v["data"] for v in subject_data.values()]
    else:
        # Return all rooms across all subjects for this teacher
        all_rooms = []
        for subj_code, subj_data in teacher_data.items():
            all_rooms.extend([v["data"] for v in subj_data.values()])
        return all_rooms

def get_rooms_for_group(group_name=None, teacher_names=None):
    db = _load_db()
    all_rooms = []
    for t_name, teacher_data in db.items():
        if teacher_names and t_name not in teacher_names:
            continue
        for subj_code, subj_data in teacher_data.items():
            all_rooms.extend([v["data"] for v in subj_data.values()])
    return all_rooms

def remove_student_from_work_db(subject_code, student_id, teacher_name=None):
    db = _load_db()
    changed = False
    for t_name, teacher_data in db.items():
        if teacher_name and t_name != teacher_name:
            continue
        if subject_code in teacher_data:
            for c_level, room_obj in teacher_data[subject_code].items():
                raw = room_obj.get("data", {}).get("raw_data", {})
                sgs_stus = raw.get("sgs_students")
                if isinstance(sgs_stus, dict) and student_id in sgs_stus:
                    del sgs_stus[student_id]
                    changed = True
                elif isinstance(sgs_stus, list):
                    orig_len = len(sgs_stus)
                    raw["sgs_students"] = [s for s in sgs_stus if str(s.get("student_id", "")).strip() != str(student_id).strip()]
                    if len(raw["sgs_students"]) != orig_len:
                        changed = True
    if changed:
        _save_db(db)
    return changed

