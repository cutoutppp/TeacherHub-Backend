from fastapi import APIRouter, UploadFile, File, HTTPException
import pandas as pd
import numpy as np
import io
import re
import json
import os
from typing import List

router = APIRouter(prefix="/api/admin/t2g", tags=["admin_t2g"])

GOOGLE_SHEET_TEACHER_URL = "https://docs.google.com/spreadsheets/d/1-FZKnLsskjnzqpwzQ3eFIFX5oUVCwVDFiCzOIjokwL8/export?format=csv&gid=1132324994"
TEACHER_CACHE_FILE = "teacher_schedule_cache.json"
_cached_teacher_mapping = {}

def get_teacher_mapping():
    global _cached_teacher_mapping
    if _cached_teacher_mapping:
        return _cached_teacher_mapping

    mapping = {}
    
    # 1. Try fetching live from Google Sheet (View_ClassTeacher)
    try:
        import requests
        resp = requests.get(GOOGLE_SHEET_TEACHER_URL, timeout=8)
        if resp.status_code == 200:
            df = pd.read_csv(io.StringIO(resp.text))
            for _, row in df.iterrows():
                c_level = str(row['ชั้น']).strip() if pd.notna(row.get('ชั้น')) else ''
                c_room = str(row['กลุ่ม-ห้อง']).strip() if pd.notna(row.get('กลุ่ม-ห้อง')) else ''
                subj = str(row['รหัสวิชา']).strip() if pd.notna(row.get('รหัสวิชา')) else ''
                pfx = str(row['คำนำหน้า']).strip() if pd.notna(row.get('คำนำหน้า')) else ''
                first = str(row['ชื่อ']).strip() if pd.notna(row.get('ชื่อ')) else ''
                last = str(row['นามสกุล']).strip() if pd.notna(row.get('นามสกุล')) else ''
                tname = f"{pfx}{first} {last}".strip()
                
                if subj:
                    if c_level and c_room:
                        room_key = f"{c_level}/{c_room}"
                        mapping[f"{subj}_{room_key}"] = tname
                    if subj not in mapping:
                        mapping[subj] = tname
                        
            if mapping:
                _cached_teacher_mapping = mapping
                try:
                    with open(TEACHER_CACHE_FILE, "w", encoding="utf-8") as f:
                        json.dump(mapping, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass
                return _cached_teacher_mapping
    except Exception as e:
        print(f"Error fetching Google Sheet View_ClassTeacher: {e}")

    # 2. Fallback to local teacher_schedule_cache.json
    if os.path.exists(TEACHER_CACHE_FILE):
        try:
            with open(TEACHER_CACHE_FILE, "r", encoding="utf-8") as f:
                _cached_teacher_mapping = json.load(f)
                return _cached_teacher_mapping
        except Exception:
            pass

    # 3. Fallback to wp16_pending_tasks.json
    try:
        if os.path.exists("wp16_pending_tasks.json"):
            with open("wp16_pending_tasks.json", "r", encoding="utf-8") as f:
                tasks = json.load(f)
                for key, task in tasks.items():
                    subj = task.get("subject_code")
                    cls = task.get("class_level")
                    teacher = task.get("teacher_name")
                    if subj and cls and teacher:
                        mapping[f"{subj}_{cls}"] = teacher
                        if subj not in mapping:
                            mapping[subj] = teacher
    except Exception as e:
        print(f"Error loading fallback teacher mapping: {e}")
        
    _cached_teacher_mapping = mapping
    return mapping

def generate_clean_preview_html(df, student_rows, active_cols, subject_row_idx, anomaly_rows_map):
    # If no student rows or active cols detected, fallback to stripped df
    if not student_rows or not active_cols:
        # Drop all completely blank rows and columns
        clean_df = df.dropna(how='all', axis=0).dropna(how='all', axis=1).astype(object).fillna('')
        return clean_df.to_html(classes="min-w-full text-xs text-left border-collapse border border-slate-200", border=1, index=False, header=False)

    # Build clean headers
    headers = []
    for pos, col in enumerate(active_cols):
        if pos == 0:
            headers.append("เลขที่")
        elif pos == 1:
            headers.append("เลขประจำตัว")
        elif pos == 2:
            headers.append("ชื่อ - นามสกุล")
        elif pos == 3:
            headers.append("หน่วยกิต")
        elif pos == 4:
            headers.append("GPA")
        else:
            # Subject code & credits
            s_val = str(df.iloc[subject_row_idx, col]).strip()
            if s_val in ['nan', 'None', '']:
                s_val = f"วิชา {pos-4}"
            headers.append(s_val)

    html = [
        '<div class="overflow-x-auto border border-slate-200 rounded-xl shadow-sm max-h-[650px] overflow-y-auto bg-white">',
        '<table class="w-full text-xs text-left border-collapse">',
        '<thead class="bg-slate-100 text-slate-800 font-bold sticky top-0 z-20 shadow-sm border-b-2 border-slate-300">',
        '<tr>'
    ]

    for idx, h in enumerate(headers):
        align = "text-center" if idx in [0, 1, 3, 4] or idx >= 5 else "text-left"
        sticky_th = ""
        if idx == 0:
            sticky_th = "sticky left-0 bg-slate-100 z-30"
        elif idx == 1:
            sticky_th = "sticky left-[45px] bg-slate-100 z-30"
        elif idx == 2:
            sticky_th = "sticky left-[125px] bg-slate-100 z-30 border-r-2 border-slate-300"
            
        html.append(f'<th class="px-3 py-2.5 border border-slate-200 whitespace-nowrap {align} {sticky_th}">{h}</th>')
    html.append('</tr></thead><tbody>')

    for s_idx, r_idx in enumerate(student_rows):
        is_anomaly = r_idx in anomaly_rows_map
        if is_anomaly:
            issues_text = " | ".join(anomaly_rows_map[r_idx])
            tr_class = "bg-red-50 hover:bg-red-100 transition-colors border-l-4 border-red-500 font-medium"
            tr_attrs = f'class="{tr_class}" title="{issues_text}"'
        else:
            zebra = "bg-white" if s_idx % 2 == 0 else "bg-slate-50/60"
            tr_class = f"{zebra} hover:bg-indigo-50/50 transition-colors border-b border-slate-100 text-slate-700"
            tr_attrs = f'class="{tr_class}"'

        html.append(f'<tr {tr_attrs}>')
        for c_pos, col in enumerate(active_cols):
            val = str(df.iloc[r_idx, col]).strip()
            if val in ['nan', 'None']:
                val = ''
            if c_pos in [0, 1]:
                val = val.replace('.0', '')
                
            align = "text-center" if c_pos in [0, 1, 3, 4] or c_pos >= 5 else "text-left"
            td_class = f"px-2.5 py-1.5 border border-slate-200 whitespace-nowrap {align}"
            
            sticky_td = ""
            if c_pos == 0:
                sticky_td = f"sticky left-0 { 'bg-red-50' if is_anomaly else 'bg-white' } z-10 font-mono"
            elif c_pos == 1:
                sticky_td = f"sticky left-[45px] { 'bg-red-50' if is_anomaly else 'bg-white' } z-10 font-mono"
            elif c_pos == 2:
                sticky_td = f"sticky left-[125px] { 'bg-red-50' if is_anomaly else 'bg-white' } z-10 border-r-2 border-slate-300 font-medium"
            elif c_pos == 4:
                td_class += " font-bold text-slate-800"

            val_display = val
            if val in ['0', '0.0', 'ร', 'มส', 'มผ']:
                val_display = f'<span class="bg-red-100 text-red-700 font-bold px-1.5 py-0.5 rounded text-[11px] border border-red-200">{val}</span>'
            elif val in ['4', '4.0']:
                val_display = f'<span class="font-bold text-indigo-700">{val}</span>'
            elif val == 'ผ':
                val_display = f'<span class="text-emerald-600 font-medium">{val}</span>'

            html.append(f'<td class="{td_class} {sticky_td}">{val_display}</td>')
        html.append('</tr>')

    html.append('</tbody></table></div>')
    return "".join(html)

@router.post("/analyze")
async def analyze_t2g_files(files: List[UploadFile] = File(...)):
    teacher_mapping = get_teacher_mapping()
    all_issues = []
    all_subject_issues = []
    all_files_html = []
    file_results = []
    
    for file in files:
        contents = await file.read()
        filename = file.filename
        file_anomalies = []
        class_level = "ไม่ระบุห้อง"
        
        try:
            df = None
            read_error = None
            
            # 1. Try reading with pd.read_excel (xlrd for .xls, openpyxl for .xlsx)
            try:
                df = pd.read_excel(io.BytesIO(contents), header=None)
            except Exception as e1:
                read_error = str(e1)
                
            # 2. If read_excel fails, try pd.read_html
            if df is None or df.empty:
                try:
                    dfs = pd.read_html(io.BytesIO(contents), encoding='utf-8')
                    if dfs:
                        df = dfs[0]
                except Exception as e2:
                    read_error = f"{read_error} | {str(e2)}"
                    
            # 3. Fallback to BeautifulSoup html.parser if pandas html fails
            if df is None or df.empty:
                try:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(contents, 'html.parser')
                    table = soup.find('table')
                    if table:
                        rows = []
                        for tr in table.find_all('tr'):
                            row = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
                            if row:
                                rows.append(row)
                        if rows:
                            df = pd.DataFrame(rows)
                except Exception as e3:
                    read_error = f"{read_error} | {str(e3)}"
            
            if df is None or df.empty:
                raise Exception(f"ไม่สามารถอ่านไฟล์ได้ กรุณาตรวจสอบว่าเป็นไฟล์ Excel หรือ XLS ถูกต้อง: {read_error}")

            # Find class level in the first 15 rows
            for i in range(min(15, len(df))):
                row_str = " ".join([str(x) for x in df.iloc[i].dropna()])
                m = re.search(r'ม\.\d+/\d+', row_str)
                if m:
                    class_level = m.group(0)
                    break

            subject_row_idx = -1
            for i in range(min(25, len(df))):
                row_data = df.iloc[i].dropna().astype(str)
                count = sum(bool(re.search(r'\d+\.\d+$', str(val).strip())) for val in row_data)
                if count > 3:
                    subject_row_idx = i
                    break
                    
            if subject_row_idx == -1:
                html_table = generate_clean_preview_html(df, [], [], -1, {})
                err_msg = "ไม่พบแถวที่ระบุรายวิชาและหน่วยกิต (แสดงข้อมูลดิบด้านล่าง)"
                all_issues.append({"file": filename, "error": err_msg})
                file_results.append({
                    "filename": filename,
                    "class_level": class_level,
                    "total_students": 0,
                    "anomalies": [{"issues": [err_msg], "contacts": []}],
                    "html": html_table,
                    "error": err_msg
                })
                all_files_html.append({
                    "filename": filename,
                    "class_level": class_level,
                    "html": html_table
                })
                continue

            subjects = {}
            for col_idx in range(len(df.columns)):
                val = str(df.iloc[subject_row_idx, col_idx]).strip()
                if pd.notna(df.iloc[subject_row_idx, col_idx]) and val not in ['nan', '', 'None']:
                    parts = val.split()
                    if len(parts) >= 2:
                        try:
                            credit = float(parts[-1])
                            subj_name = " ".join(parts[:-1])
                            subjects[col_idx] = (subj_name, credit)
                        except ValueError:
                            pass

            # Dynamically detect key columns: no_col, id_col, name_col, credit_col, gpa_col
            no_col, id_col, name_col, credit_col, gpa_col = None, None, None, None, None
            for r in range(min(20, len(df))):
                for c in range(min(20, df.shape[1])):
                    v = str(df.iloc[r, c]).strip()
                    if 'เลขที่' in v and no_col is None: no_col = c
                    if 'เลขประจำตัว' in v and id_col is None: id_col = c
                    if ('ชื่อ' in v or 'สกุล' in v) and name_col is None: name_col = c
                    if v.upper() == 'GPA' and gpa_col is None: gpa_col = c
                    if ('หน่วยกิต' in v or v == 'น.') and credit_col is None: credit_col = c

            if gpa_col is not None and credit_col is None: credit_col = gpa_col - 1
            if no_col is None: no_col = 0
            if id_col is None: id_col = 2
            if name_col is None: name_col = 5
            if gpa_col is None: gpa_col = 7
            if credit_col is None: credit_col = gpa_col - 1
            
            student_rows = []
            for i in range(subject_row_idx + 1, len(df)):
                val = str(df.iloc[i, no_col]).replace('.0', '').strip()
                if val.isdigit() and int(val) < 100:
                    name_val = str(df.iloc[i, name_col]).strip()
                    id_val = str(df.iloc[i, id_col]).replace('.0', '').strip()
                    if id_val.isdigit() and name_val not in ['', 'nan', 'None'] and not any(k in name_val for k in ['เลขที่', 'เลขประจำตัว', 'ชื่อ', 'สกุล', 'ลงชื่อ', 'โรงเรียน', 'ผลการเรียน']):
                        student_rows.append(i)

            # Active columns: [no, id, name, credit, gpa] + all subject columns with data
            subject_cols = [c for c in range(gpa_col + 1, df.shape[1]) if any(str(df.iloc[r, c]).strip() not in ['', 'nan', 'None'] for r in student_rows)]
            active_cols = [no_col, id_col, name_col, credit_col, gpa_col] + subject_cols

            anomaly_rows_map = {}

            for row_idx in student_rows:
                student_no = str(df.iloc[row_idx, no_col]).replace('.0', '')
                student_id = str(df.iloc[row_idx, id_col]).replace('.0', '')
                student_name = str(df.iloc[row_idx, name_col]).strip()
                
                try:
                    given_gpa = float(df.iloc[row_idx, gpa_col])
                except:
                    given_gpa = 0.0

                ro_ms_zero_count = 0
                mopho_count = 0
                grade_4_count = 0
                total_credit_subjects = 0
                passed_subjects = 0
                fail_subjects_names = []
                mopho_subjects_names = []
                
                for col_idx, (subj, cred) in subjects.items():
                    grade_val = str(df.iloc[row_idx, col_idx]).strip()
                    
                    if grade_val in ['nan', 'None', '']:
                        continue
                        
                    if cred < 10:
                        total_credit_subjects += 1
                        
                    if grade_val in ['ร', 'มส', '0', '0.0']:
                        ro_ms_zero_count += 1
                        fail_subjects_names.append({"subject": subj, "grade": grade_val})
                    elif grade_val == 'มผ':
                        mopho_count += 1
                        mopho_subjects_names.append({"subject": subj, "grade": grade_val})
                    elif grade_val == 'ผ':
                        pass
                    else:
                        try:
                            num_grade = float(grade_val)
                            if num_grade > 0 and cred < 10:
                                passed_subjects += 1
                            if num_grade == 4.0:
                                grade_4_count += 1
                        except:
                            pass

                anomalies = []
                contacts = []
                
                # Rule 1: Good overall student who failed only 1-2 subjects
                if (given_gpa >= 2.0 or grade_4_count >= 2) and (1 <= (ro_ms_zero_count + mopho_count) <= 2):
                    for f_subj in fail_subjects_names + mopho_subjects_names:
                        s_name = f_subj["subject"]
                        s_grade = f_subj["grade"]
                        anomalies.append(f"ผลการเรียนดี (GPA {given_gpa} / เกรด 4 ได้ {grade_4_count} วิชา) แต่ติด {s_name} ({s_grade})")
                        subj_code = s_name.split()[0]
                        teacher = teacher_mapping.get(f"{subj_code}_{class_level}") or teacher_mapping.get(subj_code) or "ไม่พบข้อมูลครูผู้สอน"
                        contacts.append(f"{s_name}: ติดต่อ {teacher}")
                    
                # Rule 2: Chronic absence / dropout who passes only 1-2 subjects
                if total_credit_subjects >= 4:
                    if ro_ms_zero_count >= (total_credit_subjects - 3) and ro_ms_zero_count > 0 and passed_subjects in [1, 2]:
                        anomalies.append(f"เด็กเสี่ยงออก/ขาดสอบยาว: ติด ร/0/มส {ro_ms_zero_count} วิชา แต่ผ่าน {passed_subjects} วิชา")
                
                # Rule 3: Extreme fluctuation (e.g. gets 4s and also gets 0/ร/มส)
                if grade_4_count >= 2 and ro_ms_zero_count >= 1:
                    if not any("ผลการเรียนดี" in a for a in anomalies):
                        anomalies.append(f"เกรดแกว่งมาก: ได้เกรด 4 ({grade_4_count} วิชา) สลับกับติด ร/0 ({ro_ms_zero_count} วิชา)")

                # Rule 4: Passed all subjects but got มผ in activities
                if ro_ms_zero_count == 0 and mopho_count >= 1 and not anomalies:
                    for m_subj in mopho_subjects_names:
                        s_name = m_subj["subject"]
                        anomalies.append(f"ผ่านทุกวิชาแต่ไม่ผ่านกิจกรรม (ติด มผ: {s_name})")

                if anomalies:
                    anomaly_rows_map[row_idx] = anomalies
                    issue_obj = {
                        "file": filename,
                        "class_level": class_level,
                        "student_no": student_no,
                        "student_id": student_id,
                        "student_name": student_name,
                        "gpa": given_gpa,
                        "issues": anomalies,
                        "contacts": contacts
                    }
                    all_issues.append(issue_obj)
                    file_anomalies.append(issue_obj)
                    
            # --- Vertical Anomaly Detection (ระดับรายวิชา / แนวดิ่ง) ---
            file_subject_anomalies = []
            for col in active_cols[5:]:
                s_val = str(df.iloc[subject_row_idx, col]).strip()
                parts = s_val.split()
                cred = float(parts[-1]) if len(parts) >= 2 and parts[-1].replace('.', '').isdigit() else 1.0
                s_code = parts[0] if parts else s_val
                
                grades = [str(df.iloc[r, col]).strip() for r in student_rows]
                valid_grades = [g for g in grades if g not in ['', 'nan', 'None']]
                empty_count = len(grades) - len(valid_grades)
                
                subj_issues = []
                
                # 1. Missing grades (ช่องเกรดตกหล่น / ฟันหลอ)
                if 0 < empty_count < len(student_rows):
                    missing_indices = [student_rows[idx] for idx, g in enumerate(grades) if g in ['', 'nan', 'None']]
                    missing_names = [str(df.iloc[r, name_col]).strip() for r in missing_indices[:3]]
                    extra = f" และอีก {empty_count - 3} คน" if empty_count > 3 else ""
                    subj_issues.append(f"มีนักเรียนตกหล่นยังไม่กรอกเกรด {empty_count} คน ({', '.join(missing_names)}{extra})")
                    
                # 2. Zero Variance (เกรดเหมือนกันทั้งห้อง 100%) - ยกเว้นกิจกรรมที่ได้ ผ
                if len(valid_grades) >= 10 and len(set(valid_grades)) == 1:
                    u_grade = valid_grades[0]
                    if cred < 10 and u_grade != 'ผ':
                        subj_issues.append(f"เกรดเหมือนกันทั้งห้อง 100% (นักเรียนทุกคนได้เกรด {u_grade} เหมือนกันทั้งหมด {len(valid_grades)} คน)")
                        
                # 3. High Failure Rate (อัตราตกสูงผิดปกติ >= 35% และ >= 5 คน)
                fail_count = sum(g in ['0', '0.0', 'ร', 'มส', 'มผ'] for g in valid_grades)
                fail_pct = (fail_count / len(valid_grades)) * 100 if valid_grades else 0
                if fail_pct >= 35 and fail_count >= 5:
                    subj_issues.append(f"อัตราการตกสูงผิดปกติ: ติด 0/ร/มส จำนวน {fail_count} คน ({fail_pct:.0f}% ของทั้งห้อง)")
                    
                # 4. Invalid Evaluation Scale
                if cred >= 10:
                    if any(g in ['1', '1.5', '2', '2.5', '3', '3.5', '4', '4.0'] for g in valid_grades):
                        subj_issues.append("วิชากิจกรรมพัฒนาผู้เรียนแต่ใส่ผลการเรียนเป็นตัวเลข (0-4)")
                elif cred < 10:
                    if any(g in ['ผ', 'มผ'] for g in valid_grades):
                        subj_issues.append("วิชาการมีหน่วยกิตแต่ใส่ผลการเรียนเป็น ผ/มผ")

                if subj_issues:
                    teacher = teacher_mapping.get(f"{s_code}_{class_level}") or teacher_mapping.get(s_code) or "ไม่พบข้อมูลครูผู้สอน"
                    subj_obj = {
                        "file": filename,
                        "class_level": class_level,
                        "subject": s_val,
                        "subject_code": s_code,
                        "issues": subj_issues,
                        "teacher": teacher
                    }
                    file_subject_anomalies.append(subj_obj)
                    all_subject_issues.append(subj_obj)

            df = df.astype(object).fillna('')
            html_table = generate_clean_preview_html(df, student_rows, active_cols, subject_row_idx, anomaly_rows_map)
            
            file_results.append({
                "filename": filename,
                "class_level": class_level,
                "total_students": len(student_rows),
                "anomalies": file_anomalies,
                "subject_anomalies": file_subject_anomalies,
                "html": html_table,
                "error": None
            })
            
            all_files_html.append({
                "filename": filename,
                "class_level": class_level,
                "html": html_table
            })
                    
        except Exception as e:
            err_msg = str(e)
            all_issues.append({"file": filename, "error": err_msg})
            file_results.append({
                "filename": filename,
                "class_level": class_level,
                "total_students": 0,
                "anomalies": [],
                "subject_anomalies": [],
                "html": f'<div class="p-6 text-red-600 bg-red-50 rounded-lg">เกิดข้อผิดพลาดในการอ่านไฟล์: {err_msg}</div>',
                "error": err_msg
            })

    return {
        "status": "success", 
        "total_files_processed": len(files), 
        "files": file_results,
        "anomalies": all_issues,
        "subject_anomalies": all_subject_issues,
        "documents": all_files_html
    }
