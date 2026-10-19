import re

path = r'C:\Users\peera\Desktop\AntigravityProject\TeacherHub\sgs_module\validator.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Fix 'ผลรวม {key}' -> 'ผลรวม {thai_key}'
old_sum_warn = """results["warnings"].append({
                            "student_id": sid, "name": name, "type": "Low Score Warning",
                            "message": f"NextSchool ผลรวม {key} ({val_ns}) ต่ำกว่าครึ่งหนึ่งของ {full_ns_sum}"
                        })"""

new_sum_warn = """period_names = {"before_mid": "ก่อนกลางภาค", "mid": "กลางภาค", "after_mid": "หลังกลางภาค", "final": "ปลายภาค"}
                        thai_key = period_names.get(key, key)
                        results["warnings"].append({
                            "student_id": sid, "name": name, "type": "Low Score Warning",
                            "message": f"NextSchool ผลรวม {thai_key} ({val_ns}) ต่ำกว่าครึ่งหนึ่งของ {full_ns_sum}"
                        })"""
content = content.replace(old_sum_warn, new_sum_warn)

# 2. Fix 'ช่อง {sub_idx}' -> 'หน่วยที่ {sub_idx}'
old_sub_warn = 'message": f"NextSchool คะแนนย่อย {thai_key} ช่อง {sub_idx} ({val_sub}) ต่ำกว่าครึ่งหนึ่งของ {full_sub}"'
new_sub_warn = 'message": f"NextSchool คะแนนย่อย {thai_key} หน่วยที่ {sub_idx} ({val_sub}) ต่ำกว่าครึ่งหนึ่งของ {full_sub}"'
content = content.replace(old_sub_warn, new_sub_warn)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed validator messages")
