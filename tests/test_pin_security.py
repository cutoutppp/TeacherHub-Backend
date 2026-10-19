import pytest
import time
from fastapi.testclient import TestClient
from main import app
from auth_db import MasterDatabase, Teacher, get_pin_hash, create_temp_pin
from auth_router import create_access_token

class MockDB:
    def __init__(self):
        self.teachers = [
            Teacher(
                id=1,
                userid="1100100888999",
                pin_hash=get_pin_hash("998877"),
                teaccode="101",
                prefix="ครู",
                firstname="สมชาย",
                lastname="ทดสอบ",
                subjectgroup="คณิตศาสตร์",
                is_admin=False
            ),
            Teacher(
                id=2,
                userid="1100200654321",
                pin_hash=get_pin_hash("112233"),
                teaccode="444",
                prefix="ครู",
                firstname="แอดมิน",
                lastname="สูงสุด",
                subjectgroup="บริหาร",
                is_admin=True
            ),
            Teacher(
                id=3,
                userid="1100300999999",
                pin_hash="", # Genuinely empty PIN
                teaccode="102",
                prefix="ครู",
                firstname="ครูใหม่",
                lastname="ไม่มีรหัส",
                subjectgroup="ภาษาไทย",
                is_admin=False
            )
        ]
        
    def get_all(self):
        return self.teachers
        
    def get_teacher_by_id(self, tid: int):
        for t in self.teachers:
            if t.id == tid:
                return t
        return None
        
    def get_teacher_by_userid(self, uid: str):
        for t in self.teachers:
            if t.userid == str(uid).strip():
                return t
        return None
        
    def update_pin(self, userid: str, new_pin: str):
        for t in self.teachers:
            if t.userid == str(userid).strip():
                t.pin_hash = new_pin
                return True
        return False

@pytest.fixture
def client_and_db():
    from auth_db import get_db
    mock_db = MockDB()
    app.dependency_overrides[get_db] = lambda: mock_db
    client = TestClient(app)
    yield client, mock_db
    app.dependency_overrides.clear()

def test_admin_reset_pin_requires_auth(client_and_db):
    client, db = client_and_db
    # 1. No auth header -> 401
    resp = client.post("/api/admin/teachers/1/reset_pin")
    assert resp.status_code == 401

    # 2. Non-admin token -> 403
    non_admin_token = create_access_token(
        data={"sub": "1100100888999", "user": {"userid": "1100100888999", "is_admin": False, "teaccode": "101"}}
    )
    resp = client.post(
        "/api/admin/teachers/1/reset_pin",
        headers={"Authorization": f"Bearer {non_admin_token}"}
    )
    assert resp.status_code == 403
    assert "Admin privileges required" in resp.json().get("detail", "")

def test_admin_reset_pin_generates_random_pin_not_last6(client_and_db):
    client, db = client_and_db
    admin_token = create_access_token(
        data={"sub": "1100200654321", "user": {"userid": "1100200654321", "is_admin": True, "teaccode": "444"}}
    )
    
    teacher = db.get_teacher_by_id(1)
    last6 = teacher.userid[-6:] # '123456'
    
    resp = client.post(
        "/api/admin/teachers/1/reset_pin",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert resp.status_code == 200
    data = resp.json()
    temp_pin = data.get("temp_pin")
    
    assert len(temp_pin) == 6
    assert temp_pin.isdigit()
    assert temp_pin != last6, "Temporary PIN must NOT be the last 6 digits of ID"
    assert teacher.pin_hash.startswith("TMP:")

def test_login_with_temp_pin_prompts_must_change_pin(client_and_db):
    client, db = client_and_db
    teacher = db.get_teacher_by_id(1)
    raw_pin, temp_hash = create_temp_pin(valid_hours=24)
    teacher.pin_hash = temp_hash
    
    # Login with valid temp PIN -> 401 with detail MUST_CHANGE_PIN
    resp = client.post(
        "/api/auth/login",
        json={"idCard": teacher.userid, "pin": raw_pin}
    )
    assert resp.status_code == 401
    assert resp.json().get("detail") == "MUST_CHANGE_PIN"

def test_login_with_expired_temp_pin_fails(client_and_db):
    client, db = client_and_db
    teacher = db.get_teacher_by_id(1)
    # Expired 1 hour ago
    raw_pin = "889900"
    expired_time = int(time.time() - 3600)
    teacher.pin_hash = f"TMP:{expired_time}:{get_pin_hash(raw_pin)}"
    
    resp = client.post(
        "/api/auth/login",
        json={"idCard": teacher.userid, "pin": raw_pin}
    )
    assert resp.status_code == 401
    assert "หมดอายุแล้ว" in resp.json().get("detail", "")

def test_change_pin_validation_and_success(client_and_db):
    client, db = client_and_db
    teacher = db.get_teacher_by_id(1)
    raw_pin, temp_hash = create_temp_pin(valid_hours=24)
    teacher.pin_hash = temp_hash
    
    # 1. Invalid current PIN -> 400
    resp = client.post(
        "/api/auth/change-pin",
        json={"idCard": teacher.userid, "currentPin": "000000", "newPin": "987654"}
    )
    assert resp.status_code == 400
    assert "ไม่ถูกต้อง" in resp.json().get("detail", "")

    # 2. Forbidden new PIN: 123456 -> 400
    resp = client.post(
        "/api/auth/change-pin",
        json={"idCard": teacher.userid, "currentPin": raw_pin, "newPin": "123456"}
    )
    assert resp.status_code == 400
    assert "123456" in resp.json().get("detail", "")

    # 3. Forbidden new PIN: last 6 digits of ID -> 400
    resp = client.post(
        "/api/auth/change-pin",
        json={"idCard": teacher.userid, "currentPin": raw_pin, "newPin": teacher.userid[-6:]}
    )
    assert resp.status_code == 400
    assert "6 ตัวท้าย" in resp.json().get("detail", "")

    # 4. Forbidden new PIN: repeat current PIN -> 400
    resp = client.post(
        "/api/auth/change-pin",
        json={"idCard": teacher.userid, "currentPin": raw_pin, "newPin": raw_pin}
    )
    assert resp.status_code == 400
    assert "ไม่ซ้ำกับรหัสเดิม" in resp.json().get("detail", "")

    # 5. Forbidden new PIN: non-6-digits -> 400
    resp = client.post(
        "/api/auth/change-pin",
        json={"idCard": teacher.userid, "currentPin": raw_pin, "newPin": "123"}
    )
    assert resp.status_code == 400
    assert "6 หลัก" in resp.json().get("detail", "")

    # 6. Valid new PIN -> 200
    valid_new_pin = "741852"
    resp = client.post(
        "/api/auth/change-pin",
        json={"idCard": teacher.userid, "currentPin": raw_pin, "newPin": valid_new_pin}
    )
    assert resp.status_code == 200
    assert "สำเร็จ" in resp.json().get("message", "")
    assert teacher.pin_hash.startswith("$2b$") or teacher.pin_hash.startswith("$2a$")

    # Now login with the new PIN should succeed!
    login_resp = client.post(
        "/api/auth/login",
        json={"idCard": teacher.userid, "pin": valid_new_pin}
    )
    assert login_resp.status_code == 200
    assert "access_token" in login_resp.json()

def test_first_time_setup_strict_empty_pin(client_and_db):
    client, db = client_and_db
    # Teacher 1 has a PIN set -> first-time-setup MUST be rejected
    teacher1 = db.get_teacher_by_id(1)
    assert teacher1.pin_hash != ""
    resp = client.post(
        "/api/auth/first-time-setup",
        json={"idCard": teacher1.userid, "newPin": "987654"}
    )
    assert resp.status_code == 400
    assert "เคยตั้งรหัส PIN แล้ว" in resp.json().get("detail", "")

    # Teacher 3 has empty PIN -> first-time-setup allowed
    teacher3 = db.get_teacher_by_id(3)
    assert teacher3.pin_hash == ""
    resp = client.post(
        "/api/auth/first-time-setup",
        json={"idCard": teacher3.userid, "newPin": "654987"}
    )
    assert resp.status_code == 200
    assert teacher3.pin_hash.startswith("$2b$") or teacher3.pin_hash.startswith("$2a$")


# --- create_teacher / teacher list lockdown + guessable PIN (Claude review fix) ---

def _admin_headers():
    tok = create_access_token(data={"sub": "1100200654321", "user": {"userid": "1100200654321", "is_admin": True, "teaccode": "444"}})
    return {"Authorization": f"Bearer {tok}"}

def _teacher_headers():
    tok = create_access_token(data={"sub": "1100100888999", "user": {"userid": "1100100888999", "is_admin": False, "teaccode": "101"}})
    return {"Authorization": f"Bearer {tok}"}

NEW_TEACHER = {"userid": "1100400111222", "teaccode": "999", "prefix": "ครู", "firstname": "ปลอม",
               "lastname": "แอดมิน", "subjectgroup": "x", "is_admin": True}

def test_create_teacher_requires_admin(client_and_db):
    client, db = client_and_db
    db.add_teacher = lambda t: (db.teachers.append(t) or True)
    assert client.post("/api/admin/teachers", json=NEW_TEACHER).status_code == 401
    assert client.post("/api/admin/teachers", json=NEW_TEACHER, headers=_teacher_headers()).status_code == 403
    assert db.get_teacher_by_userid(NEW_TEACHER["userid"]) is None

def test_create_teacher_gets_random_temp_pin(client_and_db):
    client, db = client_and_db
    db.add_teacher = lambda t: (db.teachers.append(t) or True)
    resp = client.post("/api/admin/teachers", json=NEW_TEACHER, headers=_admin_headers())
    assert resp.status_code == 200
    raw = resp.json()["raw_pin"]
    assert raw.isdigit() and len(raw) == 6 and raw != NEW_TEACHER["userid"][-6:]
    assert db.get_teacher_by_userid(NEW_TEACHER["userid"]).pin_hash.startswith("TMP:")

def test_teacher_list_requires_admin(client_and_db):
    client, _ = client_and_db
    assert client.get("/api/admin/teachers").status_code == 401
    assert client.get("/api/admin/teachers", headers=_teacher_headers()).status_code == 403
    assert client.get("/api/admin/teachers", headers=_admin_headers()).status_code == 200

@pytest.mark.parametrize("weak", ["123456", "LAST6"])
def test_login_with_guessable_pin_must_change(client_and_db, weak):
    client, db = client_and_db
    t = db.get_teacher_by_id(1)
    pin = t.userid[-6:] if weak == "LAST6" else weak
    t.pin_hash = get_pin_hash(pin)
    resp = client.post("/api/auth/login", json={"idCard": t.userid, "pin": pin})
    assert resp.status_code == 401 and resp.json()["detail"] == "MUST_CHANGE_PIN"
    assert "access_token" not in resp.text

def test_login_with_strong_pin_still_works(client_and_db):
    client, db = client_and_db
    resp = client.post("/api/auth/login", json={"idCard": "1100100888999", "pin": "998877"})
    assert resp.status_code == 200 and "access_token" in resp.json()
