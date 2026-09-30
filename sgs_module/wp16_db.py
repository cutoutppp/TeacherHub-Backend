import json
import os
import pandas as pd
from datetime import datetime

WP16_DB_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'wp16_pending_tasks.json')
WP16_EXCEL_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'WP16_งานค้าง_ต้นทาง.xlsx')
WP16_DESKTOP_FILE = os.path.join(os.environ.get('USERPROFILE', r'C:\Users\peera'), 'Desktop', 'WP16_งานค้าง_ต้นทาง.xlsx')

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
        rows = []
        for k, v in data.items():
            r = dict(v)
            yr = str(r.get('academic_year') or '2569')
            sem = str(r.get('semester') or '1')
            r['year_term'] = f"{yr}/{sem}" if (yr and sem) else str(yr or sem or '')
            rows.append(r)

        thai_col_map = {
            'special_id': 'เลขเฉพาะ',
            'academic_year': 'ปีการศึกษา',
            'semester': 'ภาคเรียน',
            'subject_code': 'รหัสวิชา',
            'subject_name': 'ชื่อวิชา',
            'teacher_name': 'ครูผู้สอน',
            'class_level': 'ชั้น/ห้อง',
            'student_id': 'เลขประจำตัว',
            'student_name': 'ชื่อ-นามสกุล',
            'old_score': 'คะแนนเดิม',
            'old_grade': 'ผลการเรียนเดิม',
            'pending_task': 'งานค้าง',
            'remark': 'หมายเหตุ',
            'updated_at': 'วันที่บันทึก'
        }
        preferred_cols = list(thai_col_map.keys())
        if rows:
            df = pd.DataFrame(rows)
            for col in preferred_cols:
                if col not in df.columns:
                    df[col] = ''
            df = df[preferred_cols]
            df = df.rename(columns=thai_col_map)
        else:
            df = pd.DataFrame(columns=[thai_col_map[c] for c in preferred_cols])
            
        with pd.ExcelWriter(WP16_EXCEL_FILE, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='WP16_งานค้าง', index=False)
            
        # Copy to Desktop so user can access it immediately
        try:
            import shutil
            shutil.copy2(WP16_EXCEL_FILE, WP16_DESKTOP_FILE)
        except Exception:
            pass
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
        is_manual = item.get('is_manual', False) or existing.get('is_manual', False)
        final_remark = item.get('remark', '') or existing.get('remark', '')
        if is_manual and not final_remark:
            final_remark = '[เพิ่มเอง]'

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
    
    # Auto-sync to Google Sheets in background
    try:
        import threading
        threading.Thread(target=sync_all_accumulated_tasks_to_gas, daemon=True).start()
    except Exception as e:
        print(f"Failed to start GAS sync thread: {e}")
        
    return len(tasks_list)

def sync_all_accumulated_tasks_to_gas(target_gas_url=None):
    """Sync all accumulated pending tasks from wp16_pending_tasks.json to Google Apps Script Web App (sgsnextschool)."""
    import requests
    GAS_URL = target_gas_url or "https://script.google.com/macros/s/AKfycbxzpP9b_eBJUU5KaNX1CbMOLHygMsrUdO7earro-bQIs8lMS9H6YM6Z6mlamm3jJd1fDQ/exec"

    db = _load_wp16_db()
    items = []
    for k, v in db.items():
        yr = str(v.get('academic_year', '2569'))
        sem = str(v.get('semester', '1'))
        term_str = f"{yr}/{sem}" if (yr and sem) else str(yr or sem or '')
        items.append({
            'special_id': v.get('special_id') or k,
            'specialId': v.get('special_id') or k,
            'academic_year': yr,
            'semester': sem,
            'year_term': term_str,
            'termStr': term_str,
            'subject_code': v.get('subject_code', ''),
            'subjCode': v.get('subject_code', ''),
            'subject_name': v.get('subject_name', ''),
            'subjName': v.get('subject_name', ''),
            'teacher_name': v.get('teacher_name', ''),
            'teacherName': v.get('teacher_name', ''),
            'class_level': v.get('class_level', ''),
            'classLevel': v.get('class_level', ''),
            'student_id': v.get('student_id', ''),
            'stuId': v.get('student_id', ''),
            'student_name': v.get('student_name', ''),
            'stuName': v.get('student_name', ''),
            'old_score': v.get('old_score', ''),
            'old_grade': v.get('old_grade', '0'),
            'oldGrade': v.get('old_grade', '0'),
            'pending_task': v.get('pending_task', ''),
            'pendingTask': v.get('pending_task', ''),
            'remark': v.get('remark', ''),
            'updated_at': v.get('updated_at', '')
        })

    if not items:
        return {'status': 'empty', 'message': 'ไม่มีข้อมูลงานค้างที่ต้องซิงค์', 'count': 0}

    payload = json.dumps({
        'action': 'sync-wp16-sheet',
        'items': items
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

        if isinstance(gas_json, dict) and (gas_json.get('success') or gas_json.get('status') == 'success'):
            print(f"[GAS SYNC] Successfully synced {len(items)} items to sgsnextschool Google Sheet.")
            return {'status': 'success', 'count': len(items), 'gas_result': gas_json}
        else:
            print(f"[GAS SYNC] GAS returned: {gas_json}")
            return {
                'status': 'error',
                'message': gas_json.get('message', 'Google Apps Script ไม่สามารถประมวลผลได้') if isinstance(gas_json, dict) else str(gas_json),
                'gas_result': gas_json,
                'count': len(items)
            }
    except Exception as e:
        print(f"[GAS SYNC] Error: {e}")
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
        try:
            import threading
            threading.Thread(target=sync_all_accumulated_tasks_to_gas, daemon=True).start()
        except Exception:
            pass
        return True
    return False

