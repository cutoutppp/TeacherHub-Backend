import pandas as pd
import os

SCORE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "score.xlsx")
_score_cache = None

def load_scores_from_json(json_str):
    global _score_cache
    import json
    try:
        raw_scores = json.loads(json_str)
        data = {}
        for row in raw_scores:
            subject_code = str(row.get("รหัสวิชา", "")).strip()
            if not subject_code or subject_code == "nan":
                continue
                
            before_mid = float(row.get("รวมคะแนนก่อนกลางภาค", 0) or 0)
            mid = float(row.get("สอบกลางภาค", 0) or 0)
            after_mid = float(row.get("รวมคะแนนหลังกลางภาค", 0) or 0)
            final = float(row.get("สอบปลายภาค", 0) or 0)
            
            before_mid_subs = []
            after_mid_subs = []
            
            for i in range(1, 15):
                col_name = f"คะแนนก่อนกลางภาค {i}"
                if col_name in row and row[col_name] not in [None, "", "nan", "NaN"]:
                    try:
                        before_mid_subs.append(float(row[col_name]))
                    except (ValueError, TypeError):
                        pass
                
                col_name_after = f"คะแนนหลังกลางภาค {i}"
                if col_name_after in row and row[col_name_after] not in [None, "", "nan", "NaN"]:
                    try:
                        after_mid_subs.append(float(row[col_name_after]))
                    except (ValueError, TypeError):
                        pass
                        
            data[subject_code] = {
                "before_mid": before_mid,
                "mid": mid,
                "after_mid": after_mid,
                "final": final,
                "before_mid_subs": before_mid_subs,
                "after_mid_subs": after_mid_subs
            }
            
        _score_cache = data
        print(f"Loaded {len(_score_cache)} scores from JSON")
    except Exception as e:
        print(f"Error parsing master_scores: {e}")

def load_scores():
    global _score_cache
    if _score_cache is not None:
        return _score_cache
        
    try:
        if not os.path.exists(SCORE_FILE):
            print(f"Warning: {SCORE_FILE} not found.")
            _score_cache = {}
            return _score_cache
            
        df = pd.read_excel(SCORE_FILE)
        
        # คอลัมน์ที่คาดหวัง:
        # 'รหัสวิชา'
        # 'รวมคะแนนก่อนกลางภาค' (before_mid)
        # 'สอบกลางภาค' หรือ 'คะแนนกลางภาค             50 คะแนน' (mid) -> แต่จากไฟล์คือ "สอบกลางภาค" = 15, "รวมคะแนนก่อนกลางภาค" = 35 -> รวม = 50. In NextSchool, `mid_sum` is before_mid + mid? Wait.
        # Let's check `test_max.py` or `cols.json` to see what `mid_sum` means in NextSchool. NextSchool `mid_sum` is usually the "รวมกลางภาค" column. But let's assume `before_mid_sum` is "ก่อนกลางภาค" and `mid_sum` is "กลางภาค".
        
        data = {}
        for index, row in df.iterrows():
            subject_code = str(row.get("รหัสวิชา", "")).strip()
            if not subject_code or subject_code == "nan":
                continue
                
            data[subject_code] = {
                "before_mid": pd.to_numeric(row.get("รวมคะแนนก่อนกลางภาค", 0), errors='coerce'),
                "mid": pd.to_numeric(row.get("สอบกลางภาค", 0), errors='coerce'),
                "after_mid": pd.to_numeric(row.get("รวมคะแนนหลังกลางภาค", 0), errors='coerce'),
                "final": pd.to_numeric(row.get("สอบปลายภาค", 0), errors='coerce'),
                "before_mid_subs": [],
                "after_mid_subs": []
            }
            
            # Extract subunits
            for i in range(1, 15):
                col_name = f"คะแนนก่อนกลางภาค {i}"
                if col_name in row and not pd.isna(row.get(col_name)):
                    val = pd.to_numeric(row.get(col_name), errors='coerce')
                    if pd.notna(val):
                        data[subject_code]["before_mid_subs"].append(val)
                
                col_name_after = f"คะแนนหลังกลางภาค {i}"
                if col_name_after in row and not pd.isna(row.get(col_name_after)):
                    val_after = pd.to_numeric(row.get(col_name_after), errors='coerce')
                    if pd.notna(val_after):
                        data[subject_code]["after_mid_subs"].append(val_after)
            
            # Fill NaNs with 0 for main scores
            for k in ["before_mid", "mid", "after_mid", "final"]:
                if pd.isna(data[subject_code][k]):
                    data[subject_code][k] = 0.0
                    
        _score_cache = data
        return _score_cache
    except Exception as e:
        print(f"Error loading score.xlsx: {e}")
        _score_cache = {}
        return _score_cache

def get_expected_scores(subject_code):
    scores = load_scores()
    return scores.get(subject_code)

def reload_scores():
    global _score_cache
    _score_cache = None
    return load_scores()
