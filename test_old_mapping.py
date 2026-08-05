import pdfplumber
import re

def clean_text(text):
    if text is None: return ""
    return str(text).replace('\n', ' ').strip()

def get_mapping(pdf_path):
    print(f"--- Analyzing: {pdf_path} ---")
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        tables = page.find_tables()
        for table in tables:
            texts = table.extract()
            row0 = [clean_text(x) for x in texts[0]]
            
            sgs_mapping = {}
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
                        if sec["key"] == "total" and j < 6:
                            continue
                        col_idx = j
                        break
                        
                if col_idx != -1:
                    sgs_mapping[sec["key"]] = col_idx
            print("Mapping:", sgs_mapping)
            print("row0:", row0)
            break

import glob
for f in glob.glob(r'C:\Users\peera\Desktop\New folder\*.pdf'):
    get_mapping(f)
