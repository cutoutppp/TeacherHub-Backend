from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from datetime import datetime, timedelta
import jwt
from auth_db import get_db, Teacher, verify_pin, get_pin_hash

router = APIRouter(prefix="/api/auth", tags=["auth"])

SECRET_KEY = "super-secret-key-teacher-hub" # In production, use env variable
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
    
    if not teacher or not verify_pin(pin, teacher.pin_hash):
        if teacher:
            print(f"[LOGIN FAILED] PIN mismatch for {idCard}")
        else:
            print(f"[LOGIN FAILED] Teacher not found for {idCard}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
        
    is_default_pin = (pin == "123456" or pin == "" or (len(idCard) >= 6 and pin == idCard[-6:]))
    if is_default_pin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="FIRST_TIME_LOGIN"
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
    teacher = db.get_teacher_by_userid(request.idCard)
    if not teacher:
        raise HTTPException(status_code=404, detail="ไม่พบข้อมูลในระบบ กรุณาติดต่อแอดมินเพื่อเพิ่มรายชื่อ")
    
    # Check if they are using default PIN (last 6 digits of ID Card or 123456)
    default_pin1 = request.idCard[-6:] if len(request.idCard) >= 6 else "123456"
    default_pin2 = "123456"
    default_pin3 = ""
    
    is_default = verify_pin(default_pin1, teacher.pin_hash) or verify_pin(default_pin2, teacher.pin_hash) or verify_pin(default_pin3, teacher.pin_hash)
    
    if not is_default:
        raise HTTPException(status_code=400, detail="คุณได้ตั้งรหัส PIN ไปแล้ว กรุณาเข้าสู่ระบบด้วยรหัสของคุณ")
    
    # Set new PIN
    new_hash = get_pin_hash(request.newPin)
    teacher.pin_hash = new_hash
    db.update_pin(request.idCard, new_hash)
    
    return {"status": "success", "message": "ตั้งรหัส PIN สำเร็จ!"}

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
