import re
from .score_db import get_expected_scores

def validate_scores(sgs_data, nextschool_data, round_type="final"):
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
                ns_mapping = nextschool_data.get("mapping", {}).get(key, {})
                sub_cols = ns_mapping.get("sub_cols", [])
                
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
        
        name = ns.get("name") if ns else (sgs.get("name") if sgs else "Unknown")
        
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

        for key in score_keys:
            # Check SGS
            sgs_val = str(sgs.get("scores", {}).get(key, ""))
            if check_decimal(sgs_val):
                results["errors"].append({
                    "student_id": sid, "name": name, "type": "Decimal Error",
                    "message": f"SGS คะแนน {key} มีทศนิยม ({sgs_val})"
                })
                add_highlight("sgs", sgs_page, sgs["bboxes"].get(key), "red")
                
            # Check NextSchool Sums
            ns_val = str(ns.get("sums", {}).get(key, ""))
            if check_decimal(ns_val):
                results["errors"].append({
                    "student_id": sid, "name": name, "type": "Decimal Error",
                    "message": f"NextSchool ผลรวมคะแนน {key} มีทศนิยม ({ns_val})"
                })
                add_highlight("nextschool", ns_page, ns["bboxes"].get(f"{key}_sum"), "red")
                
            # Check NextSchool Subs
            subs = ns.get("subs", {}).get(key, {})
            for sub_idx, sub_val in subs.items():
                if check_decimal(str(sub_val)):
                    results["errors"].append({
                        "student_id": sid, "name": name, "type": "Decimal Error",
                        "message": f"NextSchool คะแนนย่อยช่องที่ {sub_idx} ({key}) มีทศนิยม ({sub_val})"
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

        # 2. Consistency Check (Error) on SGS (Only for final)
        if round_type == "final":
            grade = str(sgs.get("grade", ""))
            
            is_low_grade = grade in ["0", "1", "1.5", "ร", "มส"]
            is_high_grade = grade in ["3", "3.5", "4"]
            
            if is_low_grade or is_high_grade:
                # skip items 1, 2, 5, 8, 9 (indices 0, 1, 4, 7, 8)
                skip_indices = {0, 1, 4, 7, 8}
                
                # Check Characteristics (char_scores)
                for i, c in enumerate(sgs.get("char_scores", [])):
                    if i in skip_indices:
                        continue
                        
                    if is_low_grade and c in ["2", "3"]:
                        results["warnings"].append({
                            "student_id": sid, "name": name, "type": "Consistency Warning",
                            "message": f"เกรดต่ำ ({grade}) แต่คุณลักษณะข้อที่ {i+1} สูง ({c})"
                        })
                        add_highlight("sgs", sgs_page, sgs["bboxes"]["char_bboxes"][i], "yellow")
                        
                    elif is_high_grade and c in ["0", "1", ""]:
                        # also warn if blank ("") when it's supposed to be high
                        results["warnings"].append({
                            "student_id": sid, "name": name, "type": "Consistency Warning",
                            "message": f"เกรดสูง ({grade}) แต่คุณลักษณะข้อที่ {i+1} ต่ำ ({c or 'ว่าง'})"
                        })
                        add_highlight("sgs", sgs_page, sgs["bboxes"]["char_bboxes"][i], "yellow")
            
                # Check Reading/Analytical Thinking (comp_scores)
                for i, c in enumerate(sgs.get("comp_scores", [])):
                    if is_low_grade and c in ["2", "3"]:
                        results["warnings"].append({
                            "student_id": sid, "name": name, "type": "Consistency Warning",
                            "message": f"เกรดต่ำ ({grade}) แต่อ่านคิดฯ ช่องที่ {i+1} สูง ({c})"
                        })
                        add_highlight("sgs", sgs_page, sgs["bboxes"]["comp_bboxes"][i], "yellow")
                        
                    elif is_high_grade and c in ["0", "1", ""]:
                        results["warnings"].append({
                            "student_id": sid, "name": name, "type": "Consistency Warning",
                            "message": f"เกรดสูง ({grade}) แต่อ่านคิดฯ ช่องที่ {i+1} ต่ำ ({c or 'ว่าง'})"
                        })
                        add_highlight("sgs", sgs_page, sgs["bboxes"]["comp_bboxes"][i], "yellow")
                    
        # 3. Mismatch Check: SGS vs NextSchool Sums (Error)
        period_names = {
            "before_mid": "ก่อนกลางภาค",
            "mid": "กลางภาค",
            "after_mid": "หลังกลางภาค",
            "final": "ปลายภาค"
        }
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
                
        # 4. Half Score Check (Warning)
        warning_keys = ["before_mid", "mid"] if round_type == "midterm" else ["before_mid", "mid", "after_mid"]
        for key in warning_keys: # Skip final
            # Check SGS
            full = sgs_max_scores.get(key)
            if full:
                val_str = sgs.get("scores", {}).get(key, "0")
                try:
                    val = float(val_str)
                    if val < (full / 2):
                        results["warnings"].append({
                            "student_id": sid, "name": name, "type": "Low Score Warning",
                            "message": f"SGS คะแนน {key} ({val}) ต่ำกว่าครึ่งหนึ่งของ {full}"
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
                        period_names = {"before_mid": "ก่อนกลางภาค", "mid": "กลางภาค", "after_mid": "หลังกลางภาค", "final": "ปลายภาค"}
                        thai_key = period_names.get(key, key)
                        results["warnings"].append({
                            "student_id": sid, "name": name, "type": "Low Score Warning",
                            "message": f"NextSchool ผลรวม {thai_key} ({val_ns}) ต่ำกว่าครึ่งหนึ่งของ {full_ns_sum}"
                        })
                        add_highlight("nextschool", ns_page, ns["bboxes"].get(f"{key}_sum"), "yellow")
                except ValueError:
                    pass
                    
            # Check NextSchool Subs
            subs = ns.get("subs", {}).get(key, {})
            # Build sorted sub key list for this period to get sequential unit number
            period_sub_keys_sorted = sorted(
                [k for k in ns_max_scores.keys() if k.startswith(f"{key}_sub_")],
                key=lambda k: int(k.split("_sub_")[-1])
            )
            sub_idx_to_unit = {k.split("_sub_")[-1]: (i + 1) for i, k in enumerate(period_sub_keys_sorted)}
            
            for sub_idx, sub_val_str in subs.items():
                full_sub = ns_max_scores.get(f"{key}_sub_{sub_idx}")
                if full_sub:
                    try:
                        val_sub = float(sub_val_str)
                        if val_sub < (full_sub / 2):
                            period_names = {"before_mid": "ก่อนกลางภาค", "mid": "กลางภาค", "after_mid": "หลังกลางภาค", "final": "ปลายภาค"}
                            thai_key = period_names.get(key, key)
                            unit_num = sub_idx_to_unit.get(str(sub_idx), sub_idx)
                            results["warnings"].append({
                                "student_id": sid, "name": name, "type": "Low Score Warning",
                                "message": f"NextSchool คะแนนย่อย {thai_key} หน่วยที่ {unit_num} ({val_sub}) ต่ำกว่าครึ่งหนึ่งของ {full_sub}"
                            })
                            add_highlight("nextschool", ns_page, ns["bboxes"].get(f"{key}_sub_{sub_idx}"), "yellow")
                    except ValueError:
                        pass
                        
        # 5. At-Risk Check
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
        else: # Final round
            # Check grade first
            grade = str(ns.get("grade", "")).strip()
            # Clean .0 for grades
            if grade.endswith(".0"):
                grade = grade[:-2]
                
            is_at_risk = False
            reason = ""
            
            if grade in ["0", "ร", "มส", "มผ"]:
                is_at_risk = True
                reason = f"ผลการเรียน {grade}"
            else:
                # Check if any main column is less than half
                sections = ["before_mid", "mid", "after_mid", "final"]
                for sec in sections:
                    sec_max = ns_max_scores.get(f"{sec}_sum", 0)
                    if sec_max > 0:
                        val_str = ns.get("sums", {}).get(sec, "0")
                        try:
                            val = float(val_str) if val_str else 0
                            if val < (sec_max / 2):
                                is_at_risk = True
                                sec_names = {"before_mid": "ก่อนกลางภาค", "mid": "กลางภาค", "after_mid": "หลังกลางภาค", "final": "ปลายภาค"}
                                reason = f"คะแนน{sec_names[sec]}ไม่ผ่านครึ่ง"
                                break
                        except ValueError:
                            pass
                            
            if is_at_risk:
                results["at_risk_students"].append({
                    "id": sid,
                    "name": name,
                    "score": grade if grade in ["0", "ร", "มส"] else "-",
                    "max_score": "-",
                    "reason": reason
                })

    return results
