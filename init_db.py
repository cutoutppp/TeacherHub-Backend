from sqlalchemy.orm import Session
from auth_db import engine, SessionLocal, Teacher, get_pin_hash, Base

def init_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    
    admin = db.query(Teacher).filter(Teacher.userid == "1234567890123").first()
    if not admin:
        new_teacher = Teacher(
            userid="1234567890123",
            pin_hash=get_pin_hash("1234"),
            teaccode="001",
            prefix="นาย",
            firstname="ทดสอบ",
            lastname="ระบบ",
            subjectgroup="คอมพิวเตอร์"
        )
        db.add(new_teacher)
        db.commit()
        print("Created dummy teacher: 1234567890123 / 1234")
    else:
        print("Dummy teacher already exists.")
    
    db.close()

if __name__ == "__main__":
    init_db()
