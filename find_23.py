import pdfplumber

def find_23(pdf_path):
    print(f"--- Analyzing: {pdf_path} ---")
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.find_tables()
            for table in tables:
                texts = table.extract()
                for i, row in enumerate(texts):
                    if row and "23.0" in [str(x) for x in row]:
                        print(f"FOUND IN ROW {i}!")
                        print("Data:", row)
                        return True
    return False

import glob
for f in glob.glob(r'C:\Users\peera\Desktop\New folder\*.pdf'):
    if find_23(f):
        break
