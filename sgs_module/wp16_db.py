import json
import os
import pandas as pd
from datetime import datetime

WP16_DB_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'wp16_pending_tasks.json')
WP16_EXCEL_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'WP16_งานค้าง_ต้นทาง.xlsx')

def _load_wp16_db():
    if not os.path.exists(WP16_DB_FILE):
        return {}
    try:
        with open(WP16_DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def _save_wp16_db(data):
    with open(WP16_DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    try:
        rows = list(data.values())
        if rows:
            df = pd.DataFrame(rows)
            preferred_cols = [
                'special_id', 'academic_year', 'semester', 'subject_code', 'subject_name',
                'teacher_name', 'class_level', 'student_id', 'student_name',
                'old_score', 'old_grade', 'pending_task', 'remark', 'updated_at'
            ]
            actual_cols = [c for c in preferred_cols if c in df.columns] + [c for c in df.columns if c not in preferred_cols]
            df = df[actual_cols]
            df.to_excel(WP16_EXCEL_FILE, index=False)
        else:
            preferred_cols = [
                'special_id', 'academic_year', 'semester', 'subject_code', 'subject_name',
                'teacher_name', 'class_level', 'student_id', 'student_name',
                'old_score', 'old_grade', 'pending_task', 'remark', 'updated_at'
            ]
            df = pd.DataFrame(columns=preferred_cols)
            df.to_excel(WP16_EXCEL_FILE, index=False)
    except Exception as e:
        print(f'Error syncing to origin excel: {e}')

def save_pending_tasks(teacher_name, subject_code, subject_name, tasks_list, academic_year='2569', semester='1'):
    db = _load_wp16_db()
    for item in tasks_list:
        stu_id = str(item.get('student_id', '')).strip()
        if not stu_id:
            continue
        special_id = f'{subject_code}{stu_id}'
        existing = db.get(special_id, {})
        incoming_task = item.get('pending_task', '')
        # If incoming task is empty, keep existing if present
        final_task = incoming_task if (incoming_task and incoming_task.strip()) else existing.get('pending_task', '')
        final_remark = item.get('remark', '') or existing.get('remark', '')
        is_manual = item.get('is_manual', False) or existing.get('is_manual', False)

        db[special_id] = {
            'special_id': special_id,
            'academic_year': str(item.get('academic_year') or academic_year),
            'semester': str(item.get('semester') or semester),
            'subject_code': subject_code,
            'subject_name': subject_name or existing.get('subject_name', ''),
            'teacher_name': teacher_name or existing.get('teacher_name', ''),
            'class_level': item.get('class_level', '') or existing.get('class_level', ''),
            'student_id': stu_id,
            'student_name': item.get('student_name', '') or existing.get('student_name', ''),
            'old_score': str(item.get('old_score', '') if item.get('old_score') is not None else existing.get('old_score', '')),
            'old_grade': str(item.get('old_grade', '') or existing.get('old_grade', '')),
            'pending_task': final_task,
            'remark': final_remark,
            'is_manual': is_manual,
            'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
    _save_wp16_db(db)
    return len(tasks_list)

def sync_all_accumulated_tasks_to_gas():
    """Sync all accumulated pending tasks from wp16_pending_tasks.json to Google Apps Script Web App."""
    import requests
    GAS_URL = "https://script.google.com/macros/s/AKfycbwXVm3nApZRjyykmZujQ7SXUS9DhTmH9YPSHyXbGPySeSHn2PFpUvoTPWVj4bIL94f_Nw/exec"

    db = _load_wp16_db()
    items = []
    for k, v in db.items():
        task = v.get('pending_task', '')
        if task and task.strip() and task.strip() != 'สอบแก้ตัว':
            items.append({
                'specialId': v.get('special_id') or k,
                'subjCode': v.get('subject_code', ''),
                'stuId': v.get('student_id', ''),
                'pendingTask': task
            })

    if not items:
        return {'status': 'empty', 'message': 'ไม่มีข้อมูลงานค้างที่ต้องซิงค์', 'count': 0}

    payload = json.dumps({
        'action': 'batch-update-pending-tasks',
        'payload': items
    })

    try:
        resp = requests.post(
            GAS_URL,
            data=payload,
            headers={'Content-Type': 'text/plain;charset=utf-8'},
            timeout=45
        )
        try:
            gas_json = resp.json()
        except Exception:
            gas_json = {'raw': resp.text[:500]}

        if isinstance(gas_json, dict) and gas_json.get('success'):
            return {'status': 'success', 'count': len(items), 'gas_result': gas_json}
        else:
            return {
                'status': 'error',
                'message': gas_json.get('message', 'Google Apps Script ไม่สามารถประมวลผลได้') if isinstance(gas_json, dict) else str(gas_json),
                'gas_result': gas_json,
                'count': len(items)
            }
    except Exception as e:
        return {'status': 'error', 'message': str(e), 'count': len(items)}

def get_pending_tasks_for_subject(subject_code, teacher_name=None):
    db = _load_wp16_db()
    result = {}
    for k, v in db.items():
        if v.get('subject_code') == subject_code:
            if teacher_name and v.get('teacher_name') != teacher_name:
                continue
            result[v.get('student_id')] = v
    return result

def get_all_pending_tasks():
    db = _load_wp16_db()
    return list(db.values())

def remove_pending_task(subject_code, student_id):
    db = _load_wp16_db()
    special_id = f'{subject_code}{student_id}'
    if special_id in db:
        del db[special_id]
        _save_wp16_db(db)
        return True
    return False

