import bcrypt
import urllib.request
import urllib.parse
import json
from pydantic import BaseModel
from typing import Optional
import ssl
import os
import time
import secrets

MASTERDATA_GAS_URL = "https://script.google.com/macros/s/AKfycbwgO1B9LfXkGJNpDei8--Tqt8HkwVOL9yb6jnAG5MOzQVQzZGxAOJTM-wRWxo_vgTgfgw/exec"
# คีย์ลับที่ GAS ใช้ตรวจว่าเป็น backend จริง (ตั้งค่าเดียวกันใน Script Properties ของ GAS)
# ถ้าไม่ตั้งจะไม่ส่ง key ไป — พฤติกรรมเหมือนเดิม
MASTERDATA_API_KEY = os.getenv("MASTERDATA_API_KEY", "")

ADMIN_TEACCODES = {'444', '440', '242', '842', '234'}

class Teacher(BaseModel):
    id: int = 0
    userid: str
    pin_hash: str
    teaccode: str
    prefix: str
    firstname: str
    lastname: str
    subjectgroup: str
    is_admin: bool = False

def is_temp_pin(stored_pin: str) -> bool:
    """Check if stored PIN is a temporary PIN (prefix TMP:<expiry>:<bcrypt>)"""
    return bool(stored_pin and stored_pin.startswith("TMP:"))

def parse_temp_pin(stored_pin: str) -> tuple[int, str]:
    """Parse (expiry_timestamp, bcrypt_hash) from TMP:<expiry>:<bcrypt>"""
    parts = stored_pin.split(":", 2)
    if len(parts) == 3:
        try:
            return int(parts[1]), parts[2]
        except ValueError:
            pass
    return 0, ""

def is_temp_pin_expired(stored_pin: str) -> bool:
    """Returns True if the temporary PIN has passed its expiry timestamp"""
    if not is_temp_pin(stored_pin):
        return False
    expiry, _ = parse_temp_pin(stored_pin)
    return time.time() > expiry

def create_temp_pin(valid_hours: int = 24) -> tuple[str, str]:
    """Generates (raw_6digit_pin, stored_tmp_format) with 24h expiration"""
    raw_pin = f"{secrets.randbelow(1000000):06d}"
    expiry = int(time.time() + (valid_hours * 3600))
    hashed = get_pin_hash(raw_pin)
    stored = f"TMP:{expiry}:{hashed}"
    return raw_pin, stored

def verify_pin(plain_pin: str, hashed_pin: str) -> bool:
    if not hashed_pin or not plain_pin:
        return False
    if is_temp_pin(hashed_pin):
        expiry, b_hash = parse_temp_pin(hashed_pin)
        if time.time() > expiry:
            return False
        try:
            return bcrypt.checkpw(plain_pin.encode('utf-8'), b_hash.encode('utf-8'))
        except Exception:
            return plain_pin == b_hash
    try:
        return bcrypt.checkpw(plain_pin.encode('utf-8'), hashed_pin.encode('utf-8'))
    except Exception:
        return plain_pin == hashed_pin

def get_pin_hash(pin: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pin.encode('utf-8'), salt).decode('utf-8')

class MasterDatabase:
    def __init__(self):
        self.url = MASTERDATA_GAS_URL
        self._cache = []
        self._is_loaded = False
        
    def fetch_all(self):
        if not self.url or self.url == "INSERT_GAS_URL_HERE":
            print("MASTERDATA_GAS_URL not set")
            return []
            
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            
            query = "action=get_all_teachers"
            if MASTERDATA_API_KEY:
                query += "&key=" + urllib.parse.quote(MASTERDATA_API_KEY)
            req = urllib.request.Request(f"{self.url}?{query}", method='GET')
            with urllib.request.urlopen(req, context=ctx) as response:
                body = response.read().decode('utf-8')
                data = json.loads(body)
                if data.get('status') == 'success':
                    raw_teachers = data.get('data', [])
                    self._cache = []
                    for idx, row in enumerate(raw_teachers):
                        is_admin_flag = str(row.get('IsAdmin', '')).lower() == 'true' or str(row.get('TeacCode', '')).strip() in ADMIN_TEACCODES
                        t = Teacher(
                            id=idx + 1,
                            userid=str(row.get('UserID', '')).strip(),
                            pin_hash=str(row.get('PIN', '')).strip(),
                            teaccode=str(row.get('TeacCode', '')).strip(),
                            prefix=str(row.get('Prefix', '')).strip(),
                            firstname=str(row.get('FirstName', '')).strip(),
                            lastname=str(row.get('LastName', '')).strip(),
                            subjectgroup=str(row.get('SubjectGroup', '')).strip(),
                            is_admin=is_admin_flag
                        )
                        self._cache.append(t)
                    self._is_loaded = True
                    return self._cache
        except Exception as e:
            print(f"Error fetching Masterdata: {e}")
        return self._cache

    def get_teacher_by_userid(self, userid: str) -> Optional[Teacher]:
        if not self._is_loaded:
            self.fetch_all()
            
        for t in self._cache:
            if t.userid == str(userid):
                return t
        
        # Fallback: force refresh and try again
        self.fetch_all()
        for t in self._cache:
            if t.userid == str(userid):
                return t
        return None
        
    def get_teacher_by_id(self, tid: int) -> Optional[Teacher]:
        if not self._is_loaded:
            self.fetch_all()
        for t in self._cache:
            if t.id == tid:
                return t
        return None
        
    def get_all(self):
        if not self._is_loaded:
            self.fetch_all()
        return self._cache
        
    def update_pin(self, userid: str, new_pin: str):
        if not self.url or self.url == "INSERT_GAS_URL_HERE":
            return False
            
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            
            payload = json.dumps({
                "action": "update_pin",
                "key": MASTERDATA_API_KEY,
                "payload": {
                    "userid": str(userid),
                    "new_pin": new_pin
                }
            }).encode('utf-8')
            req = urllib.request.Request(self.url, data=payload, method='POST', headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, context=ctx) as response:
                res = json.loads(response.read().decode('utf-8'))
                if res.get('status') == 'success':
                    for t in self._cache:
                        if t.userid == str(userid):
                            t.pin_hash = new_pin
                            break
                    return True
                else:
                    print(f"Error from GAS update_pin: {res}")
                    return False
        except Exception as e:
            print(f"Error updating PIN: {e}")
            return False
            
    def add_teacher(self, teacher: Teacher):
        if not self.url or self.url == "INSERT_GAS_URL_HERE":
            return False
            
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            
            payload = json.dumps({
                "action": "add_teacher",
                "key": MASTERDATA_API_KEY,
                "payload": {
                    "UserID": teacher.userid,
                    "PIN": teacher.pin_hash,
                    "TeacCode": teacher.teaccode,
                    "Prefix": teacher.prefix,
                    "FirstName": teacher.firstname,
                    "LastName": teacher.lastname,
                    "SubjectGroup": teacher.subjectgroup,
                    "IsAdmin": 'TRUE' if teacher.is_admin else 'FALSE'
                }
            }).encode('utf-8')
            req = urllib.request.Request(self.url, data=payload, method='POST', headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, context=ctx) as response:
                res = json.loads(response.read().decode('utf-8'))
                if res.get('status') == 'success':
                    self.fetch_all() # Refresh cache
                    return True
                return False
        except Exception as e:
            print(f"Error adding teacher: {e}")
            return False

# Global instance
db_instance = MasterDatabase()

# Dependency for FastAPI
def get_db():
    yield db_instance
