import bcrypt
import urllib.request
import urllib.parse
import json
from pydantic import BaseModel
from typing import Optional
import ssl

MASTERDATA_GAS_URL = "https://script.google.com/macros/s/AKfycbwgO1B9LfXkGJNpDei8--Tqt8HkwVOL9yb6jnAG5MOzQVQzZGxAOJTM-wRWxo_vgTgfgw/exec"

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

def verify_pin(plain_pin: str, hashed_pin: str) -> bool:
    if not hashed_pin or not plain_pin:
        return False
    try:
        return bcrypt.checkpw(plain_pin.encode('utf-8'), hashed_pin.encode('utf-8'))
    except Exception:
        return False

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
            
            req = urllib.request.Request(f"{self.url}?action=get_all_teachers", method='GET')
            with urllib.request.urlopen(req, context=ctx) as response:
                body = response.read().decode('utf-8')
                data = json.loads(body)
                if data.get('status') == 'success':
                    raw_teachers = data.get('data', [])
                    self._cache = []
                    for idx, row in enumerate(raw_teachers):
                        is_admin_flag = str(row.get('IsAdmin', '')).lower() == 'true' or str(row.get('TeacCode', '')) == '444'
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
            
        # Update local cache immediately
        for t in self._cache:
            if t.userid == str(userid):
                t.pin_hash = new_pin
                break
                
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            
            payload = json.dumps({
                "action": "update_pin",
                "payload": {
                    "userid": str(userid),
                    "new_pin": new_pin
                }
            }).encode('utf-8')
            req = urllib.request.Request(self.url, data=payload, method='POST', headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, context=ctx) as response:
                res = json.loads(response.read().decode('utf-8'))
                return res.get('status') == 'success'
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
