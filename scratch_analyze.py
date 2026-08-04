import pdfplumber

def dump_pdf_structure(pdf_path):
    print(f"--- Analyzing: {pdf_path} ---")
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        tables = page.find_tables()
        for table in tables:
            texts = table.extract()
            print("Headers:")
            print(f"Row 0 (len {len(texts[0])}):", texts[0])
            if len(texts) > 1:
                print(f"Row 1 (len {len(texts[1])}):", texts[1])
            if len(texts) > 2:
                print(f"Data Row (len {len(texts[2])}):", texts[2])
            break

dump_pdf_structure(r'C:\Users\peera\Desktop\New folder\5-10ปพ.5-2569-1-ท32201การพูด.pdf')
