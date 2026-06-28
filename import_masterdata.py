import pandas as pd
import math
import os
from sqlalchemy.orm import Session
from auth_db import engine, SessionLocal, Teacher, get_pin_hash, Base

def import_data():
    file_path = '../../Masterdata.xlsx'
    
    if not os.path.exists(file_path):
        print(f"Error: Could not find {file_path}")
        return

    print("Reading Masterdata.xlsx...")
    df = pd.read_excel(file_path)
    
    # Initialize DB schema
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    
    # Optional: Clear existing data (except admin maybe, or just clear all)
    db.query(Teacher).delete()
    db.commit()
    
    imported_count = 0
    for index, row in df.iterrows():
        # Clean data
        userid = str(row['UserID']).strip() if not pd.isna(row['UserID']) else ""
        if not userid or userid.lower() == 'nan':
            continue
            
        teaccode = str(row['TeacCode']).strip() if not pd.isna(row['TeacCode']) else ""
        prefix = str(row['Prefix']).strip() if not pd.isna(row['Prefix']) else ""
        firstname = str(row['FirstName']).strip() if not pd.isna(row['FirstName']) else ""
        lastname = str(row['LastName']).strip() if not pd.isna(row['LastName']) else ""
        subjectgroup = str(row['SubjectGroup']).strip() if not pd.isna(row['SubjectGroup']) else ""
        
        # Handle PIN (now 6 digits)
        raw_pin = row['PIN']
        if pd.isna(raw_pin):
            # Fallback to last 6 digits of UserID if PIN is missing, or 123456
            pin = userid[-6:] if len(userid) >= 6 else "123456"
        else:
            if isinstance(raw_pin, float):
                pin = str(int(raw_pin)).zfill(6)
            else:
                pin = str(raw_pin).strip().zfill(6)
                
        pin_hash = get_pin_hash(pin)
        
        # Admin assignment
        is_admin = (teaccode == "444")
        
        teacher = Teacher(
            userid=userid,
            pin_hash=pin_hash,
            teaccode=teaccode,
            prefix=prefix,
            firstname=firstname,
            lastname=lastname,
            subjectgroup=subjectgroup,
            is_admin=is_admin
        )
        db.add(teacher)
        imported_count += 1
        
    db.commit()
    db.close()
    print(f"Successfully imported {imported_count} teachers from Masterdata.")

if __name__ == "__main__":
    import_data()
