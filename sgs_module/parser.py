import pdfplumber
import re
import io
import pandas as pd
import math

def clean_text(text):
    if not text:
        return ""
    return re.sub(r'[\u200b\u200e\u200f]', '', text).strip()

def extract_subject_code(text):
    cleaned = clean_text(text)
    match = re.search(r'([ก-ฮA-Za-z]\s*\d\s*\d\s*\d\s*\d\s*\d)', cleaned)
    if match:
        code = match.group(1).replace(" ", "")
        if code.startswith("ข"):
            code = "I" + code[1:]
        return code
    return None

def extract_subject_name(text):
    cleaned = clean_text(text)
    # Match something like "ชื่อรายวิชา วิทยาศาสตร์กายภาพ ระดับชั้น"
    match = re.search(r'ชื่อรายวิชา\s+(.+?)\s+(?:ระดับชั้น|มัธยม|ม\.)', cleaned)
    if match:
        return match.group(1).strip()
    return None

def extract_class_level(text):
    cleaned = clean_text(text)
    # Match "มัธยมศึกษาปีที่ 4/1", "ม.4/1", "มัธยมศึกษาปีที่ 4 ห้อง 1"
    match = re.search(r'(?:มัธยมศึกษาปีที่|ม\.)\s*(\d+)\s*(?:/|ห้อง)\s*(\d+)', cleaned)
    if match:
        return "ม." + match.group(1).strip() + "/" + match.group(2).strip()
    
    # Fallback to the old one just in case
    match = re.search(r'(?:มัธยมศึกษาปีที่|ม\.)\s*(\d\s*/\s*\d+)', cleaned)
    if match:
        return "ม." + match.group(1).replace(" ", "")
    return None

import fitz


def parse_sgs_pdf(file_content):
    students = {}
    subject_code = None
    subject_name = None
    class_level = None
    max_scores = {}
    sgs_mapping = {}
    
    fitz_doc = fitz.open(stream=file_content, filetype="pdf")
    with pdfplumber.open(io.BytesIO(file_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not subject_code:
                subject_code = extract_subject_code(text)
            if not subject_name:
                subject_name = extract_subject_name(text)
            if not class_level:
                class_level = extract_class_level(text)
                
            tables = page.find_tables()
            for table in tables:
                texts = table.extract()
                rows_bboxes = [r.cells for r in table.rows]
                
                # Build dynamic column mapping from headers
                if not sgs_mapping and len(texts) > 1:
                    # Hardcode indices because PyMuPDF often merges header cells differently than data rows
                    # In SGS, the data rows consistently align with: 
                    # 1=เลขประจำตัว, 2=ชื่อ, 3=เลขที่, 4=ก่อนกลางภาค, 5=กลางภาค, 6=หลังกลางภาค, 7=ปลายภาค, 8=รวม
                    sgs_mapping = {
                        "before_mid": 4,
                        "mid": 5,
                        "after_mid": 6,
                        "final": 7,
                        "total": 8
                    }
                    
                    row1 = [clean_text(x) for x in texts[1]]
                    for key, col_idx in sgs_mapping.items():
                        if col_idx < len(row1) and str(row1[col_idx]).isdigit():
                            max_scores[key] = int(row1[col_idx])
                            
                
                for row_text, row_bbox in zip(texts, rows_bboxes):
                    row = row_text
                    if not row or len(row) < 30 or not clean_text(row[1]).isdigit():
                        continue
                        
                    student_id = clean_text(row[1])
                    
                    def get_bbox(idx):
                        if idx < len(row_bbox) and row_bbox[idx]:
                            return row_bbox[idx]
                        return None
                        
                    grade = clean_text(row[10]) if len(row) > 10 else ""
                    char_scores = [clean_text(x) for x in row[11:19]] if len(row) > 18 else []
                    comp_scores = [clean_text(x) for x in row[22:27]] if len(row) > 26 else []
                    
                    char_bboxes = [get_bbox(i) for i in range(11, 19)] if len(row) > 18 else []
                    comp_bboxes = [get_bbox(i) for i in range(22, 27)] if len(row) > 26 else []
                    extracted_name = clean_text(row[2]).replace("\n", " ")
                        
                    student_data = {
                        "student_id": student_id,
                        "name": extracted_name,
                        "total": clean_text(row[8]) if len(row) > 8 else "",
                        "grade": grade,
                        "char_scores": char_scores,
                        "comp_scores": comp_scores,
                        "page_num": page_num,
                        "bboxes": {
                            "total": get_bbox(8) if len(row) > 8 else None,
                            "grade": get_bbox(10) if len(row) > 10 else None,
                            "char_bboxes": char_bboxes,
                            "comp_bboxes": comp_bboxes
                        },
                        "scores": {}
                    }
                    
                    # Store main scores dynamically
                    for key, idx in sgs_mapping.items():
                        if idx < len(row):
                            student_data["scores"][key] = clean_text(row[idx])
                            student_data["bboxes"][key] = get_bbox(idx)
                            student_data["page_num"] = page_num
                    students[student_id] = student_data
                    
    fitz_doc.close()
    return {"subject_code": subject_code, "subject_name": subject_name, "class_level": class_level, "students": students, "max_scores": max_scores, "mapping": sgs_mapping}

def parse_nextschool_excel(file_content, filename):
    try:
        import pandas as pd
        import math
        import re
        
        df = pd.read_excel(io.BytesIO(file_content))
        
        # Parse subject code and class level from filename
        # e.g., 381516-ปพ.5_ส31101_ม.4_11_โรงเรียนพัฒนานิคม.xlsx
        subject_code = None
        class_level = None
        match = re.search(r'_([ก-ฮA-Za-z0-9]+)_(ม\.\d+_\d+)_', filename)
        if match:
            subject_code = match.group(1)
            class_level = match.group(2).replace("_", "/")
            
        students = {}
        max_scores = {}
        
        # Row 0 is subunit names, Row 1 is max scores
        # "ก่อนกลางภาค", "กลางภาค", "หลังกลางภาค", "ปลายภาค"
        # Columns start at index 4
        
        cols = df.columns.tolist()
        row0 = df.iloc[0].tolist() if len(df) > 0 else []
        row1 = df.iloc[1].tolist() if len(df) > 1 else []
        row2 = df.iloc[2].tolist() if len(df) > 2 else []
        row3 = df.iloc[3].tolist() if len(df) > 3 else []
        
        grid_data = {
            "cols": ["" if (isinstance(x, float) and math.isnan(x)) else str(x) for x in cols],
            "row0": ["" if (isinstance(x, float) and math.isnan(x)) else str(x) for x in row0],
            "row1": ["" if (isinstance(x, float) and math.isnan(x)) else str(x) for x in row1],
            "row2": ["" if (isinstance(x, float) and math.isnan(x)) else str(x) for x in row2],
            "row3": ["" if (isinstance(x, float) and math.isnan(x)) else str(x) for x in row3],
            "data_rows": []
        }
        
        col_mapping = {}
        nextschool_mapping = {}
        current_section = None
        for j in range(len(cols)):
            c_val = str(cols[j]).strip() if j < len(cols) else ""
            r0_val = str(row0[j]).strip() if j < len(row0) else ""
            r1_val = str(row1[j]).strip() if j < len(row1) else ""
            r2_val = str(row2[j]).strip() if j < len(row2) else ""
            
            full_header = c_val + " " + r0_val + " " + r1_val + " " + r2_val
            
            is_before_mid = ("ก่อนกลางภาค" in c_val and "รวม" not in c_val) or ("ก่อนกลางภาค" in r0_val and "รวม" not in r0_val) or ("ก่อนกลางภาค" in r1_val and "รวม" not in r1_val) or ("ก่อนกลางภาค" in r2_val and "รวม" not in r2_val)
            is_after_mid = ("หลังกลางภาค" in c_val and "รวม" not in c_val) or ("หลังกลางภาค" in r0_val and "รวม" not in r0_val) or ("หลังกลางภาค" in r1_val and "รวม" not in r1_val) or ("หลังกลางภาค" in r2_val and "รวม" not in r2_val)
            is_mid = ("กลางภาค" in c_val and "รวม" not in c_val and not is_before_mid and not is_after_mid) or ("กลางภาค" in r0_val and "รวม" not in r0_val and not is_before_mid and not is_after_mid) or ("กลางภาค" in r1_val and "รวม" not in r1_val and not is_before_mid and not is_after_mid) or ("กลางภาค" in r2_val and "รวม" not in r2_val and not is_before_mid and not is_after_mid)
            is_final = ("ปลายภาค" in c_val and "รวม" not in c_val) or ("ปลายภาค" in r0_val and "รวม" not in r0_val) or ("ปลายภาค" in r1_val and "รวม" not in r1_val) or ("ปลายภาค" in r2_val and "รวม" not in r2_val)
            
            if is_before_mid: current_section = "before_mid"
            elif is_after_mid: current_section = "after_mid"
            elif is_mid: current_section = "mid"
            elif is_final: current_section = "final"
            
            if current_section:
                if current_section not in nextschool_mapping:
                    nextschool_mapping[current_section] = {"sub_cols": [], "sum_idx": -1}
                
                sub_name = full_header
                if "รวม" in sub_name:
                    col_mapping[f"{current_section}_sum"] = j
                    nextschool_mapping[current_section]["sum_idx"] = j
                    if j < len(row1) and not (isinstance(row1[j], float) and math.isnan(row1[j])):
                        max_scores[f"{current_section}_sum"] = float(row1[j])
                    elif j < len(row2) and not (isinstance(row2[j], float) and math.isnan(row2[j])):
                        max_scores[f"{current_section}_sum"] = float(row2[j])
                    current_section = None # end of section
                elif "สอบ" in sub_name or current_section in ["mid", "final"]:
                    col_mapping[f"{current_section}_sum"] = j
                    nextschool_mapping[current_section]["sum_idx"] = j
                    if j < len(row1) and not (isinstance(row1[j], float) and math.isnan(row1[j])):
                        max_scores[f"{current_section}_sum"] = float(row1[j])
                    elif j < len(row2) and not (isinstance(row2[j], float) and math.isnan(row2[j])):
                        max_scores[f"{current_section}_sum"] = float(row2[j])
                else:
                    col_mapping[f"{current_section}_sub_{j}"] = j
                    nextschool_mapping[current_section]["sub_cols"].append(j)
                    if j < len(row1) and not (isinstance(row1[j], float) and math.isnan(row1[j])):
                        max_scores[f"{current_section}_sub_{j}"] = float(row1[j])
        
        for i in range(2, len(df)):
            row = df.iloc[i].tolist()
            student_id = str(row[1]).strip()
            if student_id and student_id != "nan":
                if student_id.endswith(".0"):
                    student_id = student_id[:-2]
                    
                student_name = str(row[2]).strip()
                student_data = {
                    "student_id": student_id,
                    "name": student_name,
                    "total": str(row[18]).strip() if len(row) > 18 else "",
                    "grade": str(row[19]).strip() if len(row) > 19 else "",
                    "sums": {},
                    "subs": {
                        "before_mid": {},
                        "after_mid": {},
                        "mid": {},
                        "final": {}
                    },
                    "bboxes": {},
                    "row_idx": i # To reference the HTML table row
                }
                
                # We save all scores mapped by column index
                for key, j in col_mapping.items():
                    val = row[j]
                    if isinstance(val, float) and math.isnan(val):
                        str_val = ""
                    else:
                        str_val = str(val).strip()
                    
                    student_data["bboxes"][key] = {"col_idx": j}
                    
                    if key.endswith("_sum"):
                        student_data["sums"][key[:-4]] = str_val
                    else:
                        # e.g. before_mid_sub_4
                        parts = key.split("_sub_")
                        if len(parts) == 2:
                            student_data["subs"][parts[0]][parts[1]] = str_val
                            
                # Auto-sum if missing
                for sec in ["before_mid", "after_mid", "mid", "final"]:
                    if sec not in student_data["sums"] or not str(student_data["sums"][sec]).strip():
                        sec_sum = 0
                        has_val = False
                        for sub_val in student_data["subs"][sec].values():
                            try:
                                sec_sum += float(sub_val)
                                has_val = True
                            except ValueError:
                                pass
                        if has_val:
                            # Format without trailing .0 if integer
                            student_data["sums"][sec] = str(int(sec_sum)) if sec_sum.is_integer() else str(sec_sum)
                            
                students[student_id] = student_data
                
                # Append to grid_data for frontend rendering
                grid_data["data_rows"].append({
                    "student_id": student_id,
                    "cells": ["" if (isinstance(x, float) and math.isnan(x)) else str(x) for x in row],
                    "row_idx": i
                })
                
        # Send max_scores_bboxes as just col_idx for frontend to highlight
        # Since frontend expects "bboxes": {"page": 0, "bbox": ...} we'll send "col_idx"
        max_scores_bboxes = {}
        for key, j in col_mapping.items():
            max_scores_bboxes[key] = {"col_idx": j}
            
        return {
            "subject_code": subject_code, 
            "class_level": class_level, 
            "students": students, 
            "max_scores": max_scores, 
            "max_scores_bboxes": max_scores_bboxes,
            "mapping": nextschool_mapping,
            "grid_data": grid_data,
            "is_excel": True
        }
    except Exception as e:
        print(f"Error parsing NextSchool Excel: {e}")
        return None
