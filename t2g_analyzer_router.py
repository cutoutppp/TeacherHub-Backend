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
    # Load teacher mapping from wp16_pending_tasks.json if exists
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
                        # fallback just subject
                        if subj not in mapping:
                            mapping[subj] = teacher
    except Exception as e:
        print(f"Error loading teacher mapping: {e}")
    return mapping

@router.post("/analyze")
async def analyze_t2g_files(files: List[UploadFile] = File(...)):
    teacher_mapping = get_teacher_mapping()
    all_issues = []
    all_files_html = []
    
    for file in files:
        contents = await file.read()
        filename = file.filename
        
        try:
            try:
                df = pd.read_excel(io.BytesIO(contents), header=None)
            except:
                dfs = pd.read_html(io.BytesIO(contents), encoding='utf-8')
                df = dfs[0]
                
            # Find class level in the first 10 rows
            class_level = "Unknown"
            for i in range(min(10, len(df))):
                row_str = " ".join([str(x) for x in df.iloc[i].dropna()])
                m = re.search(r'ม\.\d+/\d+', row_str)
                if m:
                    class_level = m.group(0)
                    break

            subject_row_idx = -1
            for i in range(min(20, len(df))):
                row_data = df.iloc[i].dropna().astype(str)
                count = sum(bool(re.search(r'\d+\.\d+$', str(val).strip())) for val in row_data)
                if count > 5:
                    subject_row_idx = i
                    break
                    
            if subject_row_idx == -1:
                all_issues.append({"file": filename, "error": "ไม่พบแถวที่ระบุรายวิชาและหน่วยกิต"})
                continue

            subjects = {}
            for col_idx in range(len(df.columns)):
                val = str(df.iloc[subject_row_idx, col_idx]).strip()
                if pd.notna(df.iloc[subject_row_idx, col_idx]) and val != 'nan' and val != '':
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
                        fail_subjects_names.append({"subject": subj, "grade": grade_val})
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
                
                if (given_gpa >= 3.0 or grade_4_count >= (total_credit_subjects * 0.5)) and (ro_ms_zero_count + mopho_count == 1):
                    subj = fail_subjects_names[0]["subject"]
                    grade = fail_subjects_names[0]["grade"]
                    anomalies.append(f"เกรดเฉลี่ยสูง (GPA {given_gpa}) แต่ติด {subj} ({grade})")
                    
                    subj_code = subj.split()[0]
                    teacher = teacher_mapping.get(f"{subj_code}_{class_level}") or teacher_mapping.get(subj_code) or "ไม่พบข้อมูลครูผู้สอน"
                    contacts.append(f"{subj}: ติดต่อ {teacher}")
                    
                if total_credit_subjects >= 5:
                    if ro_ms_zero_count >= (total_credit_subjects - 2) and passed_subjects in [1, 2]:
                        anomalies.append(f"เด็กเสี่ยงออก/ขาดสอบยาว: ติด ร/0 จำนวน {ro_ms_zero_count} วิชา แต่ผ่าน {passed_subjects} วิชา")

                if anomalies:
                    all_issues.append({
                        "file": filename,
                        "class_level": class_level,
                        "student_no": student_no,
                        "student_id": student_id,
                        "student_name": student_name,
                        "gpa": given_gpa,
                        "issues": anomalies,
                        "contacts": contacts
                    })
                    
            df.fillna('', inplace=True)
            html_table = df.to_html(classes="min-w-full text-xs text-left border-collapse border border-gray-200", border=1, index=False, header=False)
            all_files_html.append({
                "filename": filename,
                "class_level": class_level,
                "html": html_table
            })
                    
        except Exception as e:
            all_issues.append({"file": filename, "error": str(e)})

    return {
        "status": "success", 
        "total_files_processed": len(files), 
        "anomalies": all_issues,
        "documents": all_files_html
    }
