from fastapi import APIRouter, UploadFile, File, HTTPException
import pandas as pd
import numpy as np
import io
import re
import json
import os
from typing import List

router = APIRouter(prefix="/api/admin/t2g", tags=["admin_t2g"])

def get_teacher_mapping():
    mapping = {}
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
        print(f"Error loading teacher mapping: {e}")
    return mapping

def generate_preview_html(df, anomaly_rows_map, subject_row_idx):
    html = ['<div class="overflow-x-auto border border-gray-200 rounded-xl shadow-inner max-h-[650px] overflow-y-auto bg-white"><table class="w-full text-xs text-left border-collapse">']
    for r_idx in range(len(df)):
        row = df.iloc[r_idx]
        is_anomaly = r_idx in anomaly_rows_map
        is_subject = (r_idx == subject_row_idx)
        
        tr_attrs = ""
        if is_anomaly:
            issues_text = " | ".join(anomaly_rows_map[r_idx])
            tr_attrs = f'class="bg-red-50 hover:bg-red-100 transition-colors border-l-4 border-red-500 font-medium" title="{issues_text}"'
        elif is_subject:
            tr_attrs = 'class="bg-slate-100 text-slate-800 font-bold sticky top-0 z-10 border-b-2 border-slate-300 shadow-sm"'
        elif r_idx < subject_row_idx:
            tr_attrs = 'class="bg-slate-50 text-slate-600 font-semibold border-b border-gray-100"'
        else:
            zebra = "bg-white" if r_idx % 2 == 0 else "bg-slate-50/50"
            tr_attrs = f'class="{zebra} hover:bg-blue-50/50 border-b border-gray-100 text-slate-700 transition-colors"'
            
        html.append(f'<tr {tr_attrs}>')
        for c_idx in range(len(df.columns)):
            val = str(row.iloc[c_idx])
            if val in ['nan', 'None']:
                val = ''
            td_class = "px-2.5 py-1.5 border border-gray-200 whitespace-nowrap"
            if is_anomaly and c_idx in [1, 3, 5, 8]:
                td_class += " font-bold text-red-600"
            html.append(f'<td class="{td_class}">{val}</td>')
        html.append('</tr>')
    html.append('</table></div>')
    return "".join(html)

@router.post("/analyze")
async def analyze_t2g_files(files: List[UploadFile] = File(...)):
    teacher_mapping = get_teacher_mapping()
    all_issues = []
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
                # Still output document table even if subjects row not auto-detected
                html_table = generate_preview_html(df, {}, -1)
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

            no_col, id_col, name_col, credit_col, gpa_col = 1, 3, 5, 7, 8
            
            student_rows = []
            for i in range(subject_row_idx + 1, len(df)):
                val = str(df.iloc[i, no_col]).replace('.0', '').strip()
                if val.isdigit():
                    student_rows.append(i)

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
                    
            df = df.astype(object).fillna('')
            html_table = generate_preview_html(df, anomaly_rows_map, subject_row_idx)
            
            file_results.append({
                "filename": filename,
                "class_level": class_level,
                "total_students": len(student_rows),
                "anomalies": file_anomalies,
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
                "html": f'<div class="p-6 text-red-600 bg-red-50 rounded-lg">เกิดข้อผิดพลาดในการอ่านไฟล์: {err_msg}</div>',
                "error": err_msg
            })

    return {
        "status": "success", 
        "total_files_processed": len(files), 
        "files": file_results,
        "anomalies": all_issues,
        "documents": all_files_html
    }
