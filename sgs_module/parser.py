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
    match = re.search(r'([ก-ฮ]\s*\d\s*\d\s*\d\s*\d\s*\d)', cleaned)
    if match:
        return match.group(1).replace(" ", "")
    return None

def extract_class_level(text):
    cleaned = clean_text(text)
    # Match "มัธยมศึกษาปีที่ 4/1" or "ม.4/1"
    match = re.search(r'(?:มัธยมศึกษาปีที่|ม\.)\s*(\d\s*/\s*\d+)', cleaned)
    if match:
        return "ม." + match.group(1).replace(" ", "")
    return None

import fitz


def parse_sgs_pdf(file_content):
    students = {}
    subject_code = None
    class_level = None
    max_scores = {}
    sgs_mapping = {}
    
    fitz_doc = fitz.open(stream=file_content, filetype="pdf")
    with pdfplumber.open(io.BytesIO(file_content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not subject_code:
                subject_code = extract_subject_code(text)
            if not class_level:
                class_level = extract_class_level(text)
                
            tables = page.find_tables()
            for table in tables:
                texts = table.extract()
                rows_bboxes = [r.cells for r in table.rows]
                
                # Build dynamic column mapping from headers
                if not sgs_mapping and len(texts) > 1:
                    row0 = [clean_text(x) for x in texts[0]]
                    row1 = [clean_text(x) for x in texts[1]]
                    
                    sections = [
                        {"key": "before_mid", "keywords": ["ก่อนกลางภาค", "กลอนกลางภาค", "กลอน\nกลางภาค", "ก่อน\nกลางภาค"]},
                        {"key": "mid", "keywords": ["กลางภาค"]},
                        {"key": "after_mid", "keywords": ["หลังกลางภาค", "หลพงกลางภาค", "หลพง\nกลางภาค", "หลัง\nกลางภาค"]},
                        {"key": "final", "keywords": ["ปลายภาค", "ปลาย\nภาค"]},
                        {"key": "total", "keywords": ["รวม"]},
                    ]
                    
                    for i, sec in enumerate(sections):
                        col_idx = -1
                        for j, val in enumerate(row0):
                            if any(k in val for k in sec["keywords"]):
                                if sec["key"] == "mid" and ("หลัง" in val or "หลพง" in val or "ก่อน" in val or "กลอน" in val):
                                    continue
                                # make sure 'total' doesn't match something else
                                if sec["key"] == "total" and j < 6:
                                    continue
                                col_idx = j
                                break
                                
                        if col_idx != -1:
                            sgs_mapping[sec["key"]] = col_idx
                            if col_idx < len(row1) and str(row1[col_idx]).isdigit():
                                max_scores[sec["key"]] = int(row1[col_idx])
                            
                
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
                        
                    name_bbox = get_bbox(2)
                    extracted_name = clean_text(row[2])
                    if name_bbox:
                        rect = fitz.Rect(name_bbox[0], name_bbox[1]-1, name_bbox[2], name_bbox[3]+1)
                        extracted_name = fitz_doc[page_num].get_textbox(rect).replace("\n", " ").strip()
                        
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
                    
    return {"subject_code": subject_code, "class_level": class_level, "students": students, "max_scores": max_scores, "mapping": sgs_mapping}

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
        row0 = df.iloc[0].tolist()
        row1 = df.iloc[1].tolist()
        
        # We need mapping for visual rendering on the frontend
        # The frontend HTML table will be structured exactly like the excel grid
        # We'll pass the whole grid data back to the frontend!
        
        grid_data = {
            "cols": ["" if (isinstance(x, float) and math.isnan(x)) else str(x) for x in cols],
            "row0": ["" if (isinstance(x, float) and math.isnan(x)) else str(x) for x in row0],
            "row1": ["" if (isinstance(x, float) and math.isnan(x)) else str(x) for x in row1],
            "data_rows": []
        }
        
        # Find indices
        # We know index 4 to 8 is before_mid, 9 to 10 is mid, 11 to 14 is after_mid, 15 to 16 is final (in the sample)
        # But to be robust, we should find "ก่อนกลางภาค", "กลางภาค", "หลังกลางภาค", "ปลายภาค" in cols
        
        col_mapping = {}
        nextschool_mapping = {}
        current_section = None
        for j, col_name in enumerate(cols):
            val = str(col_name).strip()
            if "ก่อนกลางภาค" in val and "รวม" not in val: current_section = "before_mid"
            elif "หลังกลางภาค" in val and "รวม" not in val: current_section = "after_mid"
            elif "กลางภาค" in val and "รวม" not in val: current_section = "mid"
            elif "ปลายภาค" in val and "รวม" not in val: current_section = "final"
            
            if current_section:
                sub_name = str(row0[j]).strip()
                
                if current_section not in nextschool_mapping:
                    nextschool_mapping[current_section] = {"sub_cols": [], "sum_idx": -1}
                    
                if "รวม" in sub_name:
                    col_mapping[f"{current_section}_sum"] = j
                    nextschool_mapping[current_section]["sum_idx"] = j
                    if j < len(row1) and not (isinstance(row1[j], float) and math.isnan(row1[j])):
                        max_scores[f"{current_section}_sum"] = float(row1[j])
                    current_section = None # end of section
                elif "สอบ" in sub_name or current_section in ["mid", "final"]:
                    # Mid or Final exam
                    col_mapping[f"{current_section}_sum"] = j
                    nextschool_mapping[current_section]["sum_idx"] = j
                    if j < len(row1) and not (isinstance(row1[j], float) and math.isnan(row1[j])):
                        max_scores[f"{current_section}_sum"] = float(row1[j])
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
