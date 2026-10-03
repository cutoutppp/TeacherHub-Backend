import re
import os
import json
from .score_db import get_expected_scores

_OFFICIAL_MS_CACHE = None

import time
import csv
import urllib.request
from io import StringIO

_OFFICIAL_MS_CACHE_TIME = 0

def _load_official_ms():
    global _OFFICIAL_MS_CACHE, _OFFICIAL_MS_CACHE_TIME
    
    # ใช้งาน Cache เป็นเวลา 60 วินาที เพื่อไม่ให้ระบบช้าเกินไปตอนตรวจหลายๆ ไฟล์
    if _OFFICIAL_MS_CACHE is not None and time.time() - _OFFICIAL_MS_CACHE_TIME < 60:
        return _OFFICIAL_MS_CACHE

    # พยายามโหลดจาก Google Sheet ต้นฉบับล่าสุด
    try:
        url = "https://docs.google.com/spreadsheets/d/1OJh1FUnvLeIPGls4QIlture5f7GbAM0IieO8J5q9LuQ/export?format=csv&gid=1367227681"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.getcode() == 200:
                csv_data = response.read().decode('utf-8')
                reader = csv.reader(StringIO(csv_data))
                header = next(reader)
                ms_records = {}
                for row in reader:
                    if len(row) < 11: continue
                    special_id = row[0].strip()
                    scode = row[3].strip()
                    sid = row[7].strip()
                    old_grade = row[10].strip()
                    if old_grade in ["มส", "มส."]:
                        ms_records[special_id] = {
                            "special_id": special_id,
                            "subject_code": scode,
                            "student_id": sid,
                            "pending_task": row[11].strip(),
                            "remark": row[12].strip() if len(row) > 12 else ""
                        }
                _OFFICIAL_MS_CACHE = {"ms_records": ms_records, "allowed_exemptions": {}}
                _OFFICIAL_MS_CACHE_TIME = time.time()
                return _OFFICIAL_MS_CACHE
    except Exception as e:
        print("Failed to fetch GSHEET:", e)

    # Fallback to local json file if Google Sheet fails
    if _OFFICIAL_MS_CACHE is not None:
        return _OFFICIAL_MS_CACHE
    
    import os
    cur_dir = os.path.dirname(__file__)
    candidates = [
        os.path.join(cur_dir, "official_ms_list.json"),
        os.path.join(os.path.dirname(cur_dir), "official_ms_list.json"),
        os.path.join(cur_dir, "..", "..", "AssessmentHub", "SgsNextschool", "backend", "official_ms_list.json")
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    _OFFICIAL_MS_CACHE = json.load(f)
                    return _OFFICIAL_MS_CACHE
            except Exception:
                pass
    _OFFICIAL_MS_CACHE = {"ms_records": {}, "allowed_exemptions": {}}
    return _OFFICIAL_MS_CACHE

def find_header_name(grid, col_idx):
    for row_key in ["row0", "row1", "row2", "row3", "cols"]:
        row = grid.get(row_key, [])
        if col_idx < len(row):
            val = str(row[col_idx]).strip()
            if val and val.lower() != "nan" and not val.startswith("Unnamed:"):
                try:
                    float(val)
                except ValueError:
                    return val
    return ""

def validate_scores(sgs_data, nextschool_data, round_type="final", ms_list=None):
    if ms_list is None:
        ms_list = set()
    
    official_ms_db = _load_official_ms()
    official_ms_records = official_ms_db.get("ms_records", {})
    allowed_exemptions = official_ms_db.get("allowed_exemptions", {})
    subj_code = (sgs_data.get("subject_code") or nextschool_data.get("subject_code") or "").strip()
    results = {
        "precheck_passed": False,
        "precheck_message": "",
        "sgs_subject_code": sgs_data.get("subject_code"),
        "nextschool_subject_code": nextschool_data.get("subject_code"),
        "errors": [],
        "warnings": [],
        "sgs_highlights": [],
        "nextschool_highlights": [],
        "missing_students": [],
        "at_risk_students": []
    }
    
    ns_grid = nextschool_data.get("grid", {})
    
    def check_decimal(val_str):
        if not val_str or "." not in str(val_str):
            return False
        try:
            return float(val_str) % 1 != 0
        except ValueError:
            return False

    results["precheck_passed"] = True
    
    if sgs_data.get("subject_code") != nextschool_data.get("subject_code"):
        results["precheck_message"] = f"รหัสวิชาอาจไม่ตรงกัน (SGS: {sgs_data.get('subject_code')}, NextSchool: {nextschool_data.get('subject_code')})"
        results["warnings"].append({
            "student_id": "-",
            "name": "ระบบ",
            "type": "Subject Code Mismatch",
            "message": results["precheck_message"]
        })
    else:
        results["precheck_message"] = "รหัสวิชาตรงกัน"
    
    sgs_students = sgs_data.get("students", {})
    next_students = nextschool_data.get("students", {})
    
    all_student_ids = set(sgs_students.keys()).union(set(next_students.keys()))
    
    sgs_max_scores = sgs_data.get("max_scores", {})
    ns_max_scores = nextschool_data.get("max_scores", {})
    ns_mapping = nextschool_data.get("mapping", {})
    sgs_mapping = sgs_data.get("mapping", {})
    
    def add_highlight(system, page, bbox, color="red"):
        if bbox:
            if isinstance(bbox, dict) and "col_idx" in bbox:
                bbox_dict = bbox
            else:
                bbox_dict = {"x0": bbox[0], "top": bbox[1], "x1": bbox[2], "bottom": bbox[3]}
                
            if system == "sgs":
                results["sgs_highlights"].append({"page": page, "bbox": bbox_dict, "color": color})
            else:
                results["nextschool_highlights"].append({"page": page, "bbox": bbox_dict, "color": color})

    # 0. Master Score Structure Check (NextSchool Only)
    expected_scores = get_expected_scores(nextschool_data.get("subject_code"))
    if expected_scores:
        keys_to_check = [("before_mid", "ก่อนกลางภาค"), ("mid", "กลางภาค")] if round_type == "midterm" else [("before_mid", "ก่อนกลางภาค"), ("mid", "กลางภาค"), ("after_mid", "หลังกลางภาค"), ("final", "ปลายภาค")]
        
        for key, p_name in keys_to_check:
            expected = expected_scores.get(key, 0)
            actual = ns_max_scores.get(f"{key}_sum", 0)
            bbox_info = nextschool_data.get("max_scores_bboxes", {}).get(f"{key}_sum")
            
            if expected > 0:
                if actual != expected:
                    results["errors"].append({
                        "student_id": "-",
                        "name": "ส่วนหัวตาราง",
                        "type": "Score Structure Error",
                        "message": f"ตั้งค่าคะแนนเต็ม{p_name}ใน NextSchool ไม่ตรงกับไฟล์อ้างอิง (ตั้งไว้={actual}, ที่ถูกต้อง={expected})"
                    })
                    if bbox_info:
                        add_highlight("nextschool", 1 if nextschool_data.get("is_excel") else bbox_info.get("page", 0), bbox_info.get("bbox", bbox_info) if isinstance(bbox_info, dict) else bbox_info, "red")
                else:
                    if bbox_info:
                        add_highlight("nextschool", 1 if nextschool_data.get("is_excel") else bbox_info.get("page", 0), bbox_info.get("bbox", bbox_info) if isinstance(bbox_info, dict) else bbox_info, "green")

            # Check Subunits
            if key in ["before_mid", "after_mid"]:
                expected_subs = expected_scores.get(f"{key}_subs", [])
                ns_mapping_key = nextschool_data.get("mapping", {}).get(key, {})
                sub_cols = ns_mapping_key.get("sub_cols", [])
                
                # Check up to the number of expected subunits or available columns
                for i in range(max(len(expected_subs), len(sub_cols))):
                    expected_sub_val = expected_subs[i] if i < len(expected_subs) else 0
                    
                    if i < len(sub_cols):
                        actual_sub_col = sub_cols[i]
                        actual_sub_val = ns_max_scores.get(f"{key}_sub_{actual_sub_col}", 0)
                        sub_bbox_info = nextschool_data.get("max_scores_bboxes", {}).get(f"{key}_sub_{actual_sub_col}")
                        
                        unit_name = f"หน่วยย่อยที่ {i+1} ({p_name})"
                        
                        if expected_sub_val > 0:
                            if actual_sub_val != expected_sub_val:
                                results["errors"].append({
                                    "student_id": "-",
                                    "name": "ส่วนหัวตาราง",
                                    "type": "Score Structure Error",
                                    "message": f"ตั้งค่าคะแนนเต็ม {unit_name} ใน NextSchool ไม่ตรงกับไฟล์อ้างอิง (ตั้งไว้={actual_sub_val}, ที่ถูกต้อง={expected_sub_val})"
                                })
                                if sub_bbox_info:
                                    add_highlight("nextschool", 1 if nextschool_data.get("is_excel") else sub_bbox_info.get("page", 0), sub_bbox_info.get("bbox", sub_bbox_info) if isinstance(sub_bbox_info, dict) else sub_bbox_info, "red")
                            else:
                                if sub_bbox_info:
                                    add_highlight("nextschool", 1 if nextschool_data.get("is_excel") else sub_bbox_info.get("page", 0), sub_bbox_info.get("bbox", sub_bbox_info) if isinstance(sub_bbox_info, dict) else sub_bbox_info, "green")
                        else:
                            # If expected is 0 but NextSchool has a column with value > 0, it shouldn't exist
                            if actual_sub_val > 0:
                                results["errors"].append({
                                    "student_id": "-",
                                    "name": "ส่วนหัวตาราง",
                                    "type": "Score Structure Error",
                                    "message": f"พบการตั้งค่าคะแนน {unit_name} ใน NextSchool ทั้งที่แผนการประเมินไม่ได้กำหนดไว้"
                                })
                                if sub_bbox_info:
                                    add_highlight("nextschool", 1 if nextschool_data.get("is_excel") else sub_bbox_info.get("page", 0), sub_bbox_info.get("bbox", sub_bbox_info) if isinstance(sub_bbox_info, dict) else sub_bbox_info, "red")

    for sid in all_student_ids:
        sgs = sgs_students.get(sid)
        ns = next_students.get(sid)
        
        if ns and ns.get("name"):
            name = ns.get("name")
        elif sgs and sgs.get("name"):
            name = "(ไม่พบข้อมูลชื่อ)" 
        else:
            name = "(ไม่พบข้อมูลชื่อ)"
        
        if not sgs or not ns:
            results["warnings"].append({
                "student_id": sid,
                "name": name,
                "type": "Missing Data",
                "message": f"ไม่พบข้อมูลนักเรียนคนนี้ในไฟล์ {'SGS' if not sgs else 'NextSchool'}"
            })
            if not sgs:
                results["missing_students"].append({"id": sid, "name": name, "missing_in": "SGS"})
            if not ns:
                results["missing_students"].append({"id": sid, "name": name, "missing_in": "NextSchool"})
            continue

        sgs_page = sgs.get("page_num", 0)
        ns_page = ns.get("row_idx", ns.get("page_num", 0))

        # 1. Decimal Check (Error)
        score_keys = ["before_mid", "mid", "after_mid", "final"]
        if round_type == "midterm":
            score_keys = ["before_mid", "mid"]
            
        period_names = {
            "before_mid": "ก่อนกลางภาค",
            "mid": "กลางภาค",
            "after_mid": "หลังกลางภาค",
            "final": "ปลายภาค"
        }

        for key in score_keys:
            # Check SGS
            sgs_val = str(sgs.get("scores", {}).get(key, ""))
            if check_decimal(sgs_val):
                results["errors"].append({
                    "student_id": sid, "name": name, "type": "Decimal Error",
                    "message": f"SGS คะแนน {period_names.get(key, key)} มีทศนิยม ({sgs_val})"
                })
                add_highlight("sgs", sgs_page, sgs["bboxes"].get(key), "red")
                
            # Check NextSchool Sums
            ns_val = str(ns.get("sums", {}).get(key, ""))
            if check_decimal(ns_val):
                results["errors"].append({
                    "student_id": sid, "name": name, "type": "Decimal Error",
                    "message": f"NextSchool ผลรวมคะแนน {period_names.get(key, key)} มีทศนิยม ({ns_val})"
                })
                add_highlight("nextschool", ns_page, ns["bboxes"].get(f"{key}_sum"), "red")
                
            # Check NextSchool Subs
            subs = ns.get("subs", {}).get(key, {})
            sorted_subs_items = sorted(subs.items(), key=lambda x: int(x[0]))
            for i, (sub_idx, sub_val) in enumerate(sorted_subs_items):
                unit_num = i + 1
                if check_decimal(str(sub_val)):
                    try:
                        header_name = find_header_name(ns_grid, int(sub_idx))
                        display_name = f"'{header_name}'" if header_name else f"หน่วยที่ {unit_num}"
                    except (ValueError, IndexError):
                        display_name = f"หน่วยที่ {unit_num}"
                        
                    results["errors"].append({
                        "student_id": sid, "name": name, "type": "Decimal Error",
                        "message": f"NextSchool {display_name} ({period_names.get(key, key)}) มีทศนิยม ({sub_val})"
                    })
                    add_highlight("nextschool", ns_page, ns["bboxes"].get(f"{key}_sub_{sub_idx}"), "red")
                    
        # Check Total Decimal (Only for final)
        if round_type == "final":
            sgs_tot = str(sgs.get("total", ""))
            if check_decimal(sgs_tot):
                results["errors"].append({
                    "student_id": sid, "name": name, "type": "Decimal Error",
                    "message": f"SGS คะแนนรวมมีทศนิยม ({sgs_tot})"
                })
                add_highlight("sgs", sgs_page, sgs["bboxes"].get("total"), "red")
                
            ns_tot = str(ns.get("total", ""))
            if check_decimal(ns_tot):
                results["errors"].append({
                    "student_id": sid, "name": name, "type": "Decimal Error",
                    "message": f"NextSchool คะแนนรวมมีทศนิยม ({ns_tot})"
                })
                add_highlight("nextschool", ns_page, ns["bboxes"].get("total"), "red")

        # 2. Consistency & Strict Checks on SGS (Only for final)
        if round_type == "final":
            grade = str(sgs.get("grade", "")).strip()
            if grade.endswith(".0"):
                grade = grade[:-2]
            
            # check ONLY items 3, 4, 6 (indices 2, 3, 5) for Consistency
            check_indices = {2, 3, 5}
            
            # Check Characteristics (char_scores)
            char_list = sgs.get("char_scores", [])
            all_char_zero = len(char_list) > 0 and all(c in ["0", ""] for c in char_list) and any(c == "0" for c in char_list)

            if all_char_zero:
                # ถ้าเป็น 0 ทุกช่อง ให้เหลืองแต่บันทึกได้ (Warning แทน Error)
                results["warnings"].append({
                    "student_id": sid, "name": name, "type": "Characteristic Warning",
                    "message": "คุณลักษณะอันพึงประสงค์เป็น 0 ทุกช่อง (บันทึกผ่านได้)"
                })
                for i in range(len(char_list)):
                    if "char_bboxes" in sgs.get("bboxes", {}) and i < len(sgs["bboxes"]["char_bboxes"]):
                        add_highlight("sgs", sgs_page, sgs["bboxes"]["char_bboxes"][i], "yellow")
            else:
                for i, c in enumerate(char_list):
                    # Rule 1: ห้ามคะแนนเป็น 0 (ถ้าเว้นว่าง ต้องไม่ใช่เกรด 1-4)
                    if c == "0":
                        results["errors"].append({
                            "student_id": sid, "name": name, "type": "Characteristic Error",
                            "message": f"คุณลักษณะข้อที่ {i+1} เป็น 0 (คะแนนต้องเริ่มที่ 1)"
                        })
                        add_highlight("sgs", sgs_page, sgs["bboxes"]["char_bboxes"][i], "red")
                    elif c == "":
                        if grade in ["1", "1.5", "2", "2.5", "3", "3.5", "4"]:
                            results["errors"].append({
                                "student_id": sid, "name": name, "type": "Characteristic Error",
                                "message": f"เกรด {grade} บังคับว่าต้องประเมินคุณลักษณะ (ปล่อยว่างไม่ได้)"
                            })
                            add_highlight("sgs", sgs_page, sgs["bboxes"]["char_bboxes"][i], "red")

                    # Rules for checked items (3, 4, 6)
                    if i in check_indices:
                        # Rule 2: ผลการเรียน มส และ 0 ให้ 1 เท่านั้น
                        if grade in ["0", "มส"]:
                            if c not in ["0", ""] and c != "1":
                                results["errors"].append({
                                    "student_id": sid, "name": name, "type": "Characteristic Error",
                                    "message": f"เกรด {grade} บังคับให้คุณลักษณะข้อที่ {i+1} ต้องเป็น 1 เท่านั้น (ตอนนี้เป็น {c})"
                                })
                                add_highlight("sgs", sgs_page, sgs["bboxes"]["char_bboxes"][i], "red")
                        else:
                            # Rule 3: ความสอดคล้อง
                            if grade in ["1", "1.5"]:
                                if c == "3":
                                    results["warnings"].append({
                                        "student_id": sid, "name": name, "type": "Consistency Warning",
                                        "message": f"เกรดต่ำ ({grade}) แต่คุณลักษณะข้อที่ {i+1} สูง ({c})"
                                    })
                                    add_highlight("sgs", sgs_page, sgs["bboxes"]["char_bboxes"][i], "yellow")
                            elif grade == "ร":
                                if c in ["2", "3"]:
                                    results["warnings"].append({
                                        "student_id": sid, "name": name, "type": "Consistency Warning",
                                        "message": f"ติด ร ({grade}) แต่คุณลักษณะข้อที่ {i+1} สูง ({c})"
                                    })
                                    add_highlight("sgs", sgs_page, sgs["bboxes"]["char_bboxes"][i], "yellow")
                            elif grade in ["3", "3.5", "4"]:
                                if c in ["1", "0", ""]:
                                    results["warnings"].append({
                                        "student_id": sid, "name": name, "type": "Consistency Warning",
                                        "message": f"เกรดสูง ({grade}) แต่คุณลักษณะข้อที่ {i+1} ต่ำ ({c or 'ว่าง'})"
                                    })
                                    add_highlight("sgs", sgs_page, sgs["bboxes"]["char_bboxes"][i], "yellow")

            # Check Reading/Analytical Thinking (comp_scores)
            comp_list = sgs.get("comp_scores", [])
            all_comp_zero = len(comp_list) > 0 and all(c in ["0", ""] for c in comp_list) and any(c == "0" for c in comp_list)

            if all_comp_zero:
                # ถ้าเป็น 0 ทุกช่อง ให้เหลืองแต่บันทึกได้ (Warning แทน Error)
                results["warnings"].append({
                    "student_id": sid, "name": name, "type": "Reading/Analytical Warning",
                    "message": "อ่านคิดวิเคราะห์เป็น 0 ทุกช่อง (บันทึกผ่านได้)"
                })
                for i in range(len(comp_list)):
                    if "comp_bboxes" in sgs.get("bboxes", {}) and i < len(sgs["bboxes"]["comp_bboxes"]):
                        add_highlight("sgs", sgs_page, sgs["bboxes"]["comp_bboxes"][i], "yellow")
            else:
                for i, c in enumerate(comp_list):
                    if c == "" and grade in ["1", "1.5", "2", "2.5", "3", "3.5", "4"]:
                        results["errors"].append({
                            "student_id": sid, "name": name, "type": "Reading/Analytical Error",
                            "message": f"เกรด {grade} บังคับว่าต้องประเมินอ่านคิดวิเคราะห์ (ปล่อยว่างไม่ได้)"
                        })
                        add_highlight("sgs", sgs_page, sgs["bboxes"]["comp_bboxes"][i], "red")
                        continue
                    
                    if grade in ["1", "1.5"]:
                        if c == "3":
                            results["warnings"].append({
                                "student_id": sid, "name": name, "type": "Consistency Warning",
                                "message": f"เกรดต่ำ ({grade}) แต่อ่านคิดฯ ช่องที่ {i+1} สูง ({c})"
                            })
                            add_highlight("sgs", sgs_page, sgs["bboxes"]["comp_bboxes"][i], "yellow")
                    elif grade in ["0", "ร", "มส"]:
                        if c in ["2", "3"]:
                            results["warnings"].append({
                                "student_id": sid, "name": name, "type": "Consistency Warning",
                                "message": f"เกรดตก/ติด ({grade}) แต่อ่านคิดฯ ช่องที่ {i+1} สูง ({c})"
                            })
                            add_highlight("sgs", sgs_page, sgs["bboxes"]["comp_bboxes"][i], "yellow")
                    elif grade in ["3", "3.5", "4"]:
                        if c in ["0", "1"]:
                            results["warnings"].append({
                                "student_id": sid, "name": name, "type": "Consistency Warning",
                                "message": f"เกรดสูง ({grade}) แต่อ่านคิดฯ ช่องที่ {i+1} ต่ำ ({c or 'ว่าง'})"
                            })
                            add_highlight("sgs", sgs_page, sgs["bboxes"]["comp_bboxes"][i], "yellow")
        
        # 3. Mismatch Check: SGS vs NextSchool Sums (Error)
        for key in score_keys:
            sgs_val_str = sgs.get("scores", {}).get(key, "")
            ns_val_str = ns.get("sums", {}).get(key, "")
            
            # Allow blank equivalent to 0
            sgs_val = float(sgs_val_str) if sgs_val_str.replace('.', '', 1).isdigit() else 0.0
            ns_val = float(ns_val_str) if ns_val_str.replace('.', '', 1).isdigit() else 0.0
            
            if abs(sgs_val - ns_val) > 0.01:
                p_name = period_names.get(key, key)
                results["errors"].append({
                    "student_id": sid, "name": name, "type": "Score Mismatch",
                    "message": f"คะแนน{p_name}ไม่ตรงกัน (SGS = {sgs_val_str or '0'}, NextSchool = {ns_val_str or '0'})"
                })
                add_highlight("sgs", sgs_page, sgs["bboxes"].get(key), "red")
                add_highlight("nextschool", ns_page, ns["bboxes"].get(f"{key}_sum"), "red")
                
        # 4. Half Score Check (Warning) - Only for Midterm Round now (Final round uses Rule 6.1 Error)
        warning_keys = ["before_mid", "mid"] if round_type == "midterm" else []
        for key in warning_keys:
            # Check SGS
            full = sgs_max_scores.get(key)
            if full:
                val_str = sgs.get("scores", {}).get(key, "0")
                try:
                    val = float(val_str)
                    if val < (full / 2):
                        results["warnings"].append({
                            "student_id": sid, "name": name, "type": "Low Score Warning",
                            "message": f"SGS คะแนน {period_names.get(key, key)} ({val}) ต่ำกว่าครึ่งหนึ่งของ {full}"
                        })
                        add_highlight("sgs", sgs_page, sgs["bboxes"].get(key), "yellow")
                except ValueError:
                    pass
            
            # Check NextSchool Sums
            full_ns_sum = ns_max_scores.get(f"{key}_sum")
            if full_ns_sum:
                val_str_ns = ns.get("sums", {}).get(key, "0")
                try:
                    val_ns = float(val_str_ns)
                    if val_ns < (full_ns_sum / 2):
                        results["warnings"].append({
                            "student_id": sid, "name": name, "type": "Low Score Warning",
                            "message": f"NextSchool ผลรวม {period_names.get(key, key)} ({val_ns}) ต่ำกว่าครึ่งหนึ่งของ {full_ns_sum}"
                        })
                        add_highlight("nextschool", ns_page, ns["bboxes"].get(f"{key}_sum"), "yellow")
                except ValueError:
                    pass
                    
            # Check NextSchool Subs
            subs = ns.get("subs", {}).get(key, {})
            sorted_subs_items = sorted(subs.items(), key=lambda x: int(x[0]))
            for i, (sub_idx, sub_val_str) in enumerate(sorted_subs_items):
                unit_num = i + 1
                full_sub = ns_max_scores.get(f"{key}_sub_{sub_idx}")
                if full_sub:
                    try:
                        val_sub = float(sub_val_str)
                        if val_sub < (full_sub / 2):
                            thai_key = period_names.get(key, key)
                            try:
                                header_name = find_header_name(ns_grid, int(sub_idx))
                                display_name = f"'{header_name}'" if header_name else f"หน่วยที่ {unit_num}"
                            except (ValueError, IndexError):
                                display_name = f"หน่วยที่ {unit_num}"
                                
                            results["warnings"].append({
                                "student_id": sid, "name": name, "type": "Low Score Warning",
                                "message": f"NextSchool {display_name} ({thai_key}) ต่ำกว่าครึ่งหนึ่ง ({val_sub}/{full_sub})"
                            })
                            add_highlight("nextschool", ns_page, ns["bboxes"].get(f"{key}_sub_{sub_idx}"), "yellow")
                    except ValueError:
                        pass
                        
        # 5. At-Risk Check (Only for midterm round)
        if round_type == "midterm":
            max_before = ns_max_scores.get("before_mid_sum", 0)
            max_mid = ns_max_scores.get("mid_sum", 0)
            total_max = max_before + max_mid
            
            if total_max > 0:
                val_before_str = ns.get("sums", {}).get("before_mid", "0")
                val_mid_str = ns.get("sums", {}).get("mid", "0")
                try:
                    val_before = float(val_before_str) if val_before_str else 0
                except ValueError:
                    val_before = 0
                try:
                    val_mid = float(val_mid_str) if val_mid_str else 0
                except ValueError:
                    val_mid = 0
                
                total_val = val_before + val_mid
                if total_val < (total_max / 2):
                    results["at_risk_students"].append({
                        "id": sid,
                        "name": name,
                        "score": total_val,
                        "max_score": total_max,
                        "reason": "คะแนนต่ำกว่าครึ่ง"
                    })

        # 6. Additional Grade Rules (Error)
        if round_type == "final":
            sgs_grade_raw = str(sgs.get("grade", "")).strip()
            if sgs_grade_raw.endswith(".0"):
                sgs_grade_raw = sgs_grade_raw[:-2]
                
            ns_grade_raw = str(ns.get("grade", "")).strip()
            if ns_grade_raw.endswith(".0"):
                ns_grade_raw = ns_grade_raw[:-2]

            # 6.0 Grade Mismatch Check
            # ตรวจเฉพาะเมื่อมีเกรดใน SGS เท่านั้น เพราะ NextSchool อาจว่าง
            # ถ้า NextSchool มีเกรดด้วย แล้วไม่ตรงกัน ถือว่า Error
            if sgs_grade_raw:
                if ns_grade_raw and sgs_grade_raw != ns_grade_raw:
                    results["errors"].append({
                        "student_id": sid, "name": name, "type": "Grade Mismatch",
                        "message": f"ผลการเรียนไม่ตรงกัน (SGS = {sgs_grade_raw}, NextSchool = {ns_grade_raw})"
                    })
                    add_highlight("sgs", sgs_page, sgs["bboxes"].get("grade"), "red")
                    add_highlight("nextschool", ns_page, ns["bboxes"].get("grade"), "red")

            # Custom Rule: นักเรียนกรณีพิเศษ ผลการเรียนต้องได้ 1 ขึ้นไป
            special_students = [
                "ภาณุพงษ์ รสโสดา",
                "ณัฐพล โอนติ่ง",
                "ณัฏฐนันท์ มณีศรี",
                "นรภัทร ชาติตอง",
                "อภิญญา ทัศนา",
                "อำภา ด้วงทอง"
            ]
            if any(sp_name in name for sp_name in special_students):
                for g_raw, g_type, g_page, g_source, bboxes in [
                    (sgs_grade_raw, "SGS", sgs_page, "sgs", sgs.get("bboxes", {}) if sgs else {}),
                    (ns_grade_raw, "NextSchool", ns_page, "nextschool", ns.get("bboxes", {}) if ns else {})
                ]:
                    if g_raw:
                        grade_pass = False
                        try:
                            if float(g_raw) >= 1.0:
                                grade_pass = True
                        except ValueError:
                            pass
                        
                        if not grade_pass:
                            results["errors"].append({
                                "student_id": sid, "name": name, "type": "Special Student Grade Error",
                                "message": f"นักเรียนกรณีพิเศษ ({name}) ผลการเรียนต้องได้ 1 ขึ้นไป ({g_type} ให้เกรด '{g_raw}')"
                            })
                            add_highlight(g_source, g_page, bboxes.get("grade"), "red")

            # Rule 6.1: เกรด 0-4 ทุกช่องต้องผ่านครึ่ง
            # ใช้เกรดจาก SGS เป็นหลักในการตัดสิน
            # -- ตรวจว่าคุณลักษณะ / อ่านคิดวิเคราะห์ เป็น 0 ทุกช่อง (กรณีพิเศษ) --
            _char_list_chk = sgs.get("char_scores", [])
            _comp_list_chk = sgs.get("comp_scores", [])
            _char_comp_all_zero = (
                (len(_char_list_chk) > 0 and all(c in ["0", ""] for c in _char_list_chk) and any(c == "0" for c in _char_list_chk))
                or
                (len(_comp_list_chk) > 0 and all(c in ["0", ""] for c in _comp_list_chk) and any(c == "0" for c in _comp_list_chk))
            )
            if sgs_grade_raw in ["0", "1", "1.5", "2", "2.5", "3", "3.5", "4"]:
                sections = [("before_mid", "ก่อนกลางภาค"), ("mid", "กลางภาค"), ("after_mid", "หลังกลางภาค")]
                for sec, sec_name in sections:
                    sec_max = ns_max_scores.get(f"{sec}_sum", 0)
                    if sec_max > 0:
                        # --- SGS: ตรวจยอดรวม ---
                        sgs_val_str = sgs.get("scores", {}).get(sec, "0")
                        try:
                            sgs_val = float(sgs_val_str) if sgs_val_str else 0
                        except ValueError:
                            sgs_val = 0
                        if sgs_val < (sec_max / 2):
                            if _char_comp_all_zero:
                                results["warnings"].append({
                                    "student_id": sid, "name": name, "type": "Grade Rule Violation",
                                    "message": f"SGS: เกรด {sgs_grade_raw} แต่คะแนน{sec_name} ({sgs_val}) ไม่ผ่านครึ่งของ {sec_max} (คุณลักษณะ/อ่านคิดฯ เป็น 0 ทุกช่อง — บันทึกผ่านได้)"
                                })
                                add_highlight("sgs", sgs_page, sgs["bboxes"].get(sec), "yellow")
                            else:
                                results["errors"].append({
                                    "student_id": sid, "name": name, "type": "Grade Rule Violation",
                                    "message": f"SGS: เกรด {sgs_grade_raw} แต่คะแนน{sec_name} ({sgs_val}) ไม่ผ่านครึ่งของ {sec_max}"
                                })
                                add_highlight("sgs", sgs_page, sgs["bboxes"].get(sec), "red")

                        # --- NextSchool: ตรวจยอดรวม ---
                        ns_val_str = ns.get("sums", {}).get(sec, "0")
                        try:
                            ns_val = float(ns_val_str) if ns_val_str else 0
                        except ValueError:
                            ns_val = 0
                        if ns_val < (sec_max / 2):
                            if _char_comp_all_zero:
                                results["warnings"].append({
                                    "student_id": sid, "name": name, "type": "Grade Rule Violation",
                                    "message": f"NextSchool: เกรด {sgs_grade_raw} แต่ยอดรวม{sec_name} ({ns_val}) ไม่ผ่านครึ่งของ {sec_max} (คุณลักษณะ/อ่านคิดฯ เป็น 0 ทุกช่อง — บันทึกผ่านได้)"
                                })
                                add_highlight("nextschool", ns_page, ns["bboxes"].get(f"{sec}_sum"), "yellow")
                            else:
                                results["errors"].append({
                                    "student_id": sid, "name": name, "type": "Grade Rule Violation",
                                    "message": f"NextSchool: เกรด {sgs_grade_raw} แต่ยอดรวม{sec_name} ({ns_val}) ไม่ผ่านครึ่งของ {sec_max}"
                                })
                                add_highlight("nextschool", ns_page, ns["bboxes"].get(f"{sec}_sum"), "red")

                        # --- NextSchool: ตรวจแต่ละช่องย่อย ---
                        subs = ns.get("subs", {}).get(sec, {})
                        sorted_subs_items = sorted(subs.items(), key=lambda x: int(x[0]))
                        for i_sub, (sub_idx, sub_val_str) in enumerate(sorted_subs_items):
                            unit_num = i_sub + 1
                            full_sub = ns_max_scores.get(f"{sec}_sub_{sub_idx}")
                            if full_sub:
                                try:
                                    val_sub = float(sub_val_str) if sub_val_str else 0
                                    if val_sub < (full_sub / 2):
                                        try:
                                            header_name = find_header_name(ns_grid, int(sub_idx))
                                            display_name = f"'{header_name}'" if header_name else f"หน่วยที่ {unit_num}"
                                        except (ValueError, IndexError):
                                            display_name = f"หน่วยที่ {unit_num}"
                                        if _char_comp_all_zero:
                                            results["warnings"].append({
                                                "student_id": sid, "name": name, "type": "Grade Rule Violation",
                                                "message": f"NextSchool: เกรด {sgs_grade_raw} แต่ช่องย่อย {display_name} ({sec_name}) ได้ ({val_sub}) ไม่ผ่านครึ่งของ {full_sub} (คุณลักษณะ/อ่านคิดฯ เป็น 0 ทุกช่อง — บันทึกผ่านได้)"
                                            })
                                            add_highlight("nextschool", ns_page, ns["bboxes"].get(f"{sec}_sub_{sub_idx}"), "yellow")
                                        else:
                                            results["errors"].append({
                                                "student_id": sid, "name": name, "type": "Grade Rule Violation",
                                                "message": f"NextSchool: เกรด {sgs_grade_raw} แต่ช่องย่อย {display_name} ({sec_name}) ได้ ({val_sub}) ไม่ผ่านครึ่งของ {full_sub}"
                                            })
                                            add_highlight("nextschool", ns_page, ns["bboxes"].get(f"{sec}_sub_{sub_idx}"), "red")
                                except ValueError:
                                    pass

            # Rule 6.2: ติด ร สามารถมีคะแนนเก็บสะสมเดิมได้ตามจริง (เช่น 30.0 หรือคะแนนเก็บก่อนสอบปลายภาค)
            # ไม่บังคับให้คะแนนรวมต้องว่างเปล่า (ตามระเบียบวัดผลและใบ วผ.16)

            # Rule 6.3: ติด มส ห้ามมีคะแนนหลังกลางภาค (ยอดรวม + แต่ละช่องย่อย) และคะแนนปลายภาค
            # ตรวจแยกกัน: SGS ตามเกรด SGS / NextSchool ตามเกรด NextSchool
            
            # -------------------------------------------------------------
            # Rule 6.3: ตรวจสอบ มส. ตามประกาศทางการ (เวลาเรียนไม่ถึง 80%)
            # -------------------------------------------------------------
            sp_key = f"{subj_code}{sid}"
            is_official_ms = sp_key in official_ms_records
            is_allowed_to_test = sp_key in allowed_exemptions

            # กฎ มส. ข้อที่ 1: ตรวจว่ามีใครให้ มส. เองทีหลังหรือไม่ (Unauthorized มส.)
            if sgs_grade_raw == "มส" or ns_grade_raw == "มส":
                if is_allowed_to_test:
                    results["errors"].append({
                        "student_id": sid, "name": name, "type": "Unauthorized MS Error",
                        "message": f"นักเรียนได้รับอนุญาตให้เข้าสอบวิชานี้แล้วตามประกาศทางการ (แก้เวลาเรียนแล้ว) ห้ามให้ผลการเรียน 'มส' ต้องประเมินและให้เกรดตามปกติ"
                    })
                    if sgs_grade_raw == "มส":
                        add_highlight("sgs", sgs_page, sgs["bboxes"].get("grade"), "red")
                    if ns_grade_raw == "มส":
                        add_highlight("nextschool", ns_page, ns["bboxes"].get("grade"), "red")
                elif official_ms_records and not is_official_ms:
                    results["errors"].append({
                        "student_id": sid, "name": name, "type": "Unauthorized MS Error",
                        "message": f"นักเรียนได้ผลการเรียน 'มส' ในวิชานี้ ({subj_code}) แต่ไม่อยู่ในประกาศรายชื่อ มส. ทางการของโรงเรียน (เวลาเรียนไม่ถึง 80%) — อาจเป็นการให้ มส. เองทีหลังโดยไม่ได้รับอนุมัติ"
                    })
                    if sgs_grade_raw == "มส":
                        add_highlight("sgs", sgs_page, sgs["bboxes"].get("grade"), "red")
                    if ns_grade_raw == "มส":
                        add_highlight("nextschool", ns_page, ns["bboxes"].get("grade"), "red")
                elif ms_list and sid not in ms_list:
                    results["errors"].append({
                        "student_id": sid, "name": name, "type": "Grade Rule Violation",
                        "message": "ติด 'มส' แต่นักเรียนไม่มีชื่อในประกาศรายชื่อผู้มีสิทธิ์สอบ"
                    })
                    if sgs_grade_raw == "มส":
                        add_highlight("sgs", sgs_page, sgs["bboxes"].get("grade"), "red")
                    if ns_grade_raw == "มส":
                        add_highlight("nextschool", ns_page, ns["bboxes"].get("grade"), "red")

            # กฎ มส. ข้อที่ 2: ตรวจว่าไปแอบให้เกรดนักเรียนที่ มส. โดยไม่ได้ตั้งใจหรือไม่ (Accidental grading)
            if is_official_ms and round_type == "final":
                ms_info = official_ms_records[sp_key]
                ms_reason = ms_info.get("pending_task") or ms_info.get("remark") or "เวลาเรียนไม่ถึง 80%"
                
                # ถ้าครูใส่เกรดอื่นที่ไม่ใช่ มส. (เช่น 0, 1, 2, 3, 4, ร)
                if sgs_grade_raw and sgs_grade_raw != "มส":
                    results["errors"].append({
                        "student_id": sid, "name": name, "type": "Official MS Violation",
                        "message": f"SGS: นักเรียนมีรายชื่อติด 'มส.' ทางการในวิชานี้ ({ms_reason}) ไม่อนุญาตให้เข้าสอบ แต่ครูให้เกรด '{sgs_grade_raw}' — ห้ามให้เกรดเด็ดขาด ต้องให้ผลการเรียน 'มส' เท่านั้น"
                    })
                    add_highlight("sgs", sgs_page, sgs["bboxes"].get("grade"), "red")

                if ns_grade_raw and ns_grade_raw != "มส":
                    results["errors"].append({
                        "student_id": sid, "name": name, "type": "Official MS Violation",
                        "message": f"NextSchool: นักเรียนมีรายชื่อติด 'มส.' ทางการในวิชานี้ ({ms_reason}) ไม่อนุญาตให้เข้าสอบ แต่มีเกรด '{ns_grade_raw}' — ห้ามให้เกรดเด็ดขาด ต้องให้ผลการเรียน 'มส' เท่านั้น"
                    })
                    add_highlight("nextschool", ns_page, ns["bboxes"].get("grade"), "red")

            for sec, sec_name in [("after_mid", "หลังกลางภาค"), ("final", "ปลายภาค")]:

                # --- SGS: ตรวจเฉพาะเมื่อ SGS grade เป็น มส ---
                if sgs_grade_raw == "มส":
                    sgs_val_str = sgs.get("scores", {}).get(sec, "")
                    try:
                        sgs_val = float(sgs_val_str) if sgs_val_str else 0
                    except ValueError:
                        sgs_val = 0
                    if sgs_val > 0:
                        results["errors"].append({
                            "student_id": sid, "name": name, "type": "Grade Rule Violation",
                            "message": f"SGS: ติด 'มส' แต่มีการกรอกคะแนน{sec_name} ({sgs_val}) ต้องเว้นว่าง"
                        })
                        add_highlight("sgs", sgs_page, sgs["bboxes"].get(sec), "red")

                # --- NextSchool: ตรวจเฉพาะเมื่อ NS grade เป็น มส ---
                if ns_grade_raw == "มส":
                    # ยอดรวม
                    if sec == "final":
                        ns_val_str = ns.get("final", "") or ns.get("sums", {}).get("final", "")
                    else:
                        ns_val_str = ns.get("sums", {}).get(sec, "")
                    try:
                        ns_val = float(ns_val_str) if ns_val_str else 0
                    except ValueError:
                        ns_val = 0
                    if ns_val > 0:
                        results["errors"].append({
                            "student_id": sid, "name": name, "type": "Grade Rule Violation",
                            "message": f"NextSchool: ติด 'มส' แต่มียอดรวมคะแนน{sec_name} ({ns_val}) ต้องเว้นว่าง"
                        })
                        bbox_key = f"{sec}_sum" if sec == "after_mid" else "final"
                        add_highlight("nextschool", ns_page, ns["bboxes"].get(bbox_key), "red")

                    # ช่องย่อย (หลังกลางภาค และ ปลายภาค)
                    subs = ns.get("subs", {}).get(sec, {})
                    sorted_subs_items = sorted(subs.items(), key=lambda x: int(x[0]))
                    for i_sub, (sub_idx, sub_val_str) in enumerate(sorted_subs_items):
                        unit_num = i_sub + 1
                        try:
                            val_sub = float(sub_val_str) if sub_val_str else 0
                        except ValueError:
                            val_sub = 0
                        if val_sub > 0:
                            try:
                                header_name = find_header_name(ns_grid, int(sub_idx))
                                display_name = f"'{header_name}'" if header_name else f"หน่วยที่ {unit_num}"
                            except (ValueError, IndexError):
                                display_name = f"หน่วยที่ {unit_num}"
                            results["errors"].append({
                                "student_id": sid, "name": name, "type": "Grade Rule Violation",
                                "message": f"NextSchool: ติด 'มส' แต่ช่องย่อย {display_name} ({sec_name}) มีคะแนน ({val_sub}) ต้องเว้นว่าง"
                            })
                            add_highlight("nextschool", ns_page, ns["bboxes"].get(f"{sec}_sub_{sub_idx}"), "red")

    return results
