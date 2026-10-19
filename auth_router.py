from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from datetime import datetime, timedelta
import os
import jwt
from auth_db import get_db, Teacher, verify_pin, get_pin_hash, is_temp_pin, is_temp_pin_expired

router = APIRouter(prefix="/api/auth", tags=["auth"])

# ตั้งค่า JWT_SECRET_KEY บน Render/Cloud Run (ค่าเดียวกันทั้งสองที่); ถ้าไม่ตั้งจะใช้ค่าเดิมเพื่อไม่ให้ระบบล่ม
SECRET_KEY = os.getenv("JWT_SECRET_KEY") or "super-secret-key-teacher-hub"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 # 24 hours

class LoginRequest(BaseModel):
    idCard: str
    pin: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    teacher: dict

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, db = Depends(get_db)):
    idCard = request.idCard.strip()
    pin = request.pin.strip()
    teacher = db.get_teacher_by_userid(idCard)
    
    print(f"[LOGIN ATTEMPT] idCard: '{idCard}', found: {teacher is not None}")
    
    if not teacher:
        print(f"[LOGIN FAILED] Teacher not found for {idCard}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    # 1. First time login: only when PIN is completely empty
    if teacher.pin_hash == "":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="FIRST_TIME_LOGIN"
        )

    # 2. Temporary PIN: must change PIN before access token is granted
    if is_temp_pin(teacher.pin_hash):
        if is_temp_pin_expired(teacher.pin_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="รหัส PIN ชั่วคราวหมดอายุแล้ว (เกิน 24 ชั่วโมง) กรุณาติดต่อแอดมินเพื่อขอรีเซ็ตใหม่"
            )
        if verify_pin(pin, teacher.pin_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="MUST_CHANGE_PIN"
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    # 3. Standard PIN verification
    if not verify_pin(pin, teacher.pin_hash):
        print(f"[LOGIN FAILED] PIN mismatch for {idCard}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    # 4. PIN ที่เดาได้ (123456 / 6 ตัวท้ายเลขบัตร) — ต้องเปลี่ยนก่อนเข้าระบบ
    if pin == "123456" or (len(idCard) >= 6 and pin == idCard[-6:]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="MUST_CHANGE_PIN"
        )

    # Create token payload
    teacher_data = {
        "id": teacher.id,
        "userid": teacher.userid,
        "teaccode": teacher.teaccode,
        "name": f"{teacher.prefix or ''}{teacher.firstname or ''} {teacher.lastname or ''}".strip(),
        "subjectgroup": teacher.subjectgroup,
        "is_admin": teacher.is_admin
    }
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": teacher.userid, "user": teacher_data}, expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer", "teacher": teacher_data}

class FirstTimeRequest(BaseModel):
    idCard: str
    newPin: str

@router.post("/first-time-setup")
def first_time_setup(request: FirstTimeRequest, db = Depends(get_db)):
    idCard = request.idCard.strip()
    newPin = request.newPin.strip()

    teacher = db.get_teacher_by_userid(idCard)
    if not teacher:
        raise HTTPException(status_code=404, detail="ไม่พบข้อมูลในระบบ กรุณาติดต่อแอดมินเพื่อเพิ่มรายชื่อ")
    
    # Allow ONLY if pin_hash is genuinely empty
    if teacher.pin_hash != "":
        raise HTTPException(
            status_code=400,
            detail="คุณเคยตั้งรหัส PIN แล้ว หรือมีรหัสในระบบแล้ว กรุณาเข้าสู่ระบบด้วยรหัสของคุณ"
        )
    
    # Validation rules for new PIN
    if not (len(newPin) == 6 and newPin.isdigit()):
        raise HTTPException(status_code=400, detail="รหัส PIN ใหม่ต้องเป็นตัวเลข 6 หลักเท่านั้น")
    
    if newPin == "123456":
        raise HTTPException(status_code=400, detail="ไม่อนุญาตให้ใช้รหัส 123456 กรุณาตั้งรหัสที่มีความปลอดภัย")
    
    if len(idCard) >= 6 and newPin == idCard[-6:]:
        raise HTTPException(status_code=400, detail="ไม่อนุญาตให้ใช้เลข 6 ตัวท้ายของบัตรประชาชน")
    
    # Set new PIN
    new_hash = get_pin_hash(newPin)
    success = db.update_pin(idCard, new_hash)
    if not success:
        raise HTTPException(
            status_code=500,
            detail="ไม่สามารถบันทึกรหัสผ่านใหม่ลงระบบได้ กรุณาลองใหม่อีกครั้ง หรือติดต่อผู้ดูแลระบบ"
        )
    teacher.pin_hash = new_hash
    
    return {"status": "success", "message": "ตั้งรหัส PIN สำเร็จ!"}

class ChangePinRequest(BaseModel):
    idCard: str
    currentPin: str
    newPin: str

@router.post("/change-pin")
def change_pin(request: ChangePinRequest, db = Depends(get_db)):
    idCard = request.idCard.strip()
    currentPin = request.currentPin.strip()
    newPin = request.newPin.strip()

    teacher = db.get_teacher_by_userid(idCard)
    if not teacher:
        raise HTTPException(status_code=404, detail="ไม่พบข้อมูลในระบบ")

    # Check current PIN validity (including temporary PIN expiry)
    if is_temp_pin(teacher.pin_hash) and is_temp_pin_expired(teacher.pin_hash):
        raise HTTPException(
            status_code=400,
            detail="รหัส PIN ชั่วคราวหมดอายุแล้ว (เกิน 24 ชั่วโมง) กรุณาติดต่อแอดมินเพื่อขอรีเซ็ตใหม่"
        )

    if not verify_pin(currentPin, teacher.pin_hash):
        raise HTTPException(status_code=400, detail="รหัส PIN เดิมหรือรหัสชั่วคราวไม่ถูกต้อง")

    # Validation rules for new PIN
    if not (len(newPin) == 6 and newPin.isdigit()):
        raise HTTPException(status_code=400, detail="รหัส PIN ใหม่ต้องเป็นตัวเลข 6 หลักเท่านั้น")

    if newPin == currentPin:
        raise HTTPException(status_code=400, detail="รหัส PIN ใหม่ต้องไม่ซ้ำกับรหัสเดิม")

    if newPin == "123456":
        raise HTTPException(status_code=400, detail="ไม่อนุญาตให้ใช้รหัส 123456 กรุณาตั้งรหัสที่มีความปลอดภัย")

    if len(idCard) >= 6 and newPin == idCard[-6:]:
        raise HTTPException(status_code=400, detail="ไม่อนุญาตให้ใช้เลข 6 ตัวท้ายของบัตรประชาชน")

    new_hash = get_pin_hash(newPin)
    teacher.pin_hash = new_hash
    success = db.update_pin(idCard, new_hash)
    if not success:
        raise HTTPException(status_code=500, detail="ไม่สามารถบันทึกข้อมูลลง Google Sheet ได้")

    return {
        "status": "success",
        "message": "เปลี่ยนรหัส PIN สำเร็จเรียบร้อยแล้ว กรุณาเข้าสู่ระบบด้วยรหัสใหม่"
    }

class VerifyTokenRequest(BaseModel):
    token: str

@router.post("/verify")
def verify_token(request: VerifyTokenRequest):
    try:
        payload = jwt.decode(request.token, SECRET_KEY, algorithms=[ALGORITHM])
        return {"status": "success", "user": payload.get("user")}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
