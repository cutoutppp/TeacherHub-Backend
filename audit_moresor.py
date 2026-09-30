import os
import sys
import json
import glob
from sgs_module.parser import parse_sgs_pdf
from sgs_module.validator import _load_official_ms

sys.stdout.reconfigure(encoding='utf-8')

def audit_sgs_files(target_path):
    official_db = _load_official_ms()
    ms_records = official_db.get("ms_records", {})
    allowed_exemptions = official_db.get("allowed_exemptions", {})

    print("=" * 60)
    print("📋 เครื่องมือตรวจสอบความถูกต้องของผลการเรียน มส. (SGS vs ประกาศทางการ)")
    print(f"📊 ฐานข้อมูล มส. ทางการ: {len(ms_records)} รายการ, ได้รับอนุญาตให้สอบ: {len(allowed_exemptions)} รายการ")
    print("=" * 60)

    pdf_files = []
    if os.path.isfile(target_path):
        pdf_files = [target_path]
    elif os.path.isdir(target_path):
        pdf_files = glob.glob(os.path.join(target_path, "**", "*.pdf"), recursive=True)
    else:
        print(f"❌ ไม่พบไฟล์หรือโฟลเดอร์: {target_path}")
        return

    print(f"🔍 พบไฟล์ PDF ที่จะตรวจสอบ: {len(pdf_files)} ไฟล์\n")

    unauthorized_ms = []
    accidental_grades = []
    accidental_final_scores = []
    allowed_given_ms = []
    correct_ms = []

    for fpath in pdf_files:
        try:
            with open(fpath, "rb") as f:
                content = f.read()
            sgs_data = parse_sgs_pdf(content)
            if not sgs_data or not sgs_data.get("students"):
                continue

            scode = sgs_data.get("subject_code", "").strip()
            teacher = sgs_data.get("teacher_name", "").strip()

            for sid, stu in sgs_data.get("students", {}).items():
                sname = stu.get("name") or sid
                grade = str(stu.get("grade", "")).strip()
                if grade.endswith(".0"): grade = grade[:-2]
                final_score = stu.get("scores", {}).get("final", "")
                try:
                    final_val = float(final_score) if final_score else 0
                except ValueError:
                    final_val = 0

                sp_key = f"{scode}{sid}"
                is_official_ms = sp_key in ms_records
                is_allowed = sp_key in allowed_exemptions

                # 1. ครูให้ มส แต่ไม่อยู่ในประกาศทางการ
                if grade == "มส":
                    if is_allowed:
                        allowed_given_ms.append({
                            "subject_code": scode, "student_id": sid, "name": sname,
                            "teacher": teacher, "file": os.path.basename(fpath)
                        })
                    elif not is_official_ms:
                        unauthorized_ms.append({
                            "subject_code": scode, "student_id": sid, "name": sname,
                            "teacher": teacher, "file": os.path.basename(fpath)
                        })
                    else:
                        correct_ms.append({
                            "subject_code": scode, "student_id": sid, "name": sname,
                            "teacher": teacher, "file": os.path.basename(fpath)
                        })

                # 2. เด็กติด มส ทางการ แต่ครูดันให้เกรดอื่น หรือกรอกคะแนนปลายภาค
                if is_official_ms:
                    if grade and grade != "มส":
                        accidental_grades.append({
                            "subject_code": scode, "student_id": sid, "name": sname,
                            "grade": grade, "teacher": teacher, "remark": ms_records[sp_key].get("pending_task", ""),
                            "file": os.path.basename(fpath)
                        })
                    if final_val > 0:
                        accidental_final_scores.append({
                            "subject_code": scode, "student_id": sid, "name": sname,
                            "final_score": final_val, "teacher": teacher, "file": os.path.basename(fpath)
                        })

        except Exception as e:
            pass

    # แสดงผลการตรวจสอบ
    print("📊 สรุปผลการตรวจสอบ:")
    print(f"  - มส. ที่ถูกต้องตามประกาศ: {len(correct_ms)} รายการ")
    print(f"  - ⚠️ ครูให้ มส. เองทีหลัง (ไม่อยู่ในประกาศทางการ): {len(unauthorized_ms)} รายการ")
    print(f"  - ❌ แอบให้เกรดเด็ก มส. ทางการโดยไม่ได้ตั้งใจ: {len(accidental_grades)} รายการ")
    print(f"  - ❌ กรอกคะแนนสอบปลายภาคให้เด็ก มส.: {len(accidental_final_scores)} รายการ")
    print(f"  - ⚠️ เด็กได้รับอนุมัติให้สอบ แต่ครูยังให้ มส.: {len(allowed_given_ms)} รายการ")

    if accidental_grades:
        print("\n" + "=" * 60)
        print("🚨 รายละเอียด: เด็กติด มส. ทางการ แต่ครูเผลอให้เกรดอื่น:")
        for item in accidental_grades:
            print(f"   - [{item['subject_code']}] รหัส {item['student_id']} {item['name']} | เกรดที่ครูให้: {item['grade']} (เหตุผล มส: {item['remark']}) | ครู: {item['teacher']} ({item['file']})")

    if unauthorized_ms:
        print("\n" + "=" * 60)
        print("⚠️ รายละเอียด: ครูให้ มส. เองทีหลัง (ไม่อยู่ในประกาศทางการ):")
        for item in unauthorized_ms:
            print(f"   - [{item['subject_code']}] รหัส {item['student_id']} {item['name']} | ครู: {item['teacher']} ({item['file']})")

    if allowed_given_ms:
        print("\n" + "=" * 60)
        print("⚠️ รายละเอียด: เด็กได้รับอนุมัติให้สอบแล้ว แต่ครูยังให้ มส.:")
        for item in allowed_given_ms:
            print(f"   - [{item['subject_code']}] รหัส {item['student_id']} {item['name']} | ครู: {item['teacher']} ({item['file']})")

    print("\n" + "=" * 60)

if __name__ == '__main__':
    target = sys.argv[1] if len(sys.argv) > 1 else r"c:\Users\peera\Desktop\AntigravityProject"
    audit_sgs_files(target)
