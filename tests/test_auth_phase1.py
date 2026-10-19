import os
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from datetime import timedelta
import jwt

# Import from TeacherHub-Backend
from main import app
from auth_router import create_access_token, SECRET_KEY, ALGORITHM

client = TestClient(app)

def make_token(userid: str, teaccode: str, is_admin: bool, expired: bool = False) -> str:
    teacher_data = {
        "id": 1,
        "userid": userid,
        "teaccode": teaccode,
        "name": "Test Teacher",
        "subjectgroup": "สังคมศึกษา",
        "is_admin": is_admin
    }
    delta = timedelta(minutes=-10) if expired else timedelta(minutes=60)
    return create_access_token(
        data={"sub": userid, "user": teacher_data},
        expires_delta=delta
    )

@pytest.fixture(autouse=True)
def mock_gas_external_calls():
    """Mock external GAS network calls during admin stats testing."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = b'{"status": "success", "total_academic_issues": 10}'
    with patch("urllib.request.urlopen", return_value=mock_resp):
        yield

# Case 1: AUTH_MODE not set (defaults to log), request to /api/admin/stats without token
def test_case_1_default_log_mode_missing_token(caplog, monkeypatch):
    monkeypatch.delenv("AUTH_MODE", raising=False)
    with caplog.at_level("WARNING"):
        res = client.get("/api/admin/stats")
    # Must NOT reject with 401/403 (existing behaviour preserved)
    assert res.status_code != 401
    assert res.status_code != 403
    # Must log anomaly
    assert "[AUTH-LOG] missing" in caplog.text

# Case 2: AUTH_MODE=log, request with invalid/fake token
def test_case_2_log_mode_invalid_token(caplog, monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "log")
    fake_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalid.payload"
    with caplog.at_level("WARNING"):
        res = client.get("/api/admin/stats", headers={"Authorization": f"Bearer {fake_token}"})
    assert res.status_code != 401
    assert res.status_code != 403
    assert "[AUTH-LOG] invalid" in caplog.text

# Case 3: AUTH_MODE=enforce, request without token to protected admin route -> 401
def test_case_3_enforce_mode_missing_token(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "enforce")
    res = client.get("/api/admin/stats")
    assert res.status_code == 401
    assert res.json().get("detail") == "Not authenticated"

# Case 4: AUTH_MODE=enforce, valid token but is_admin=False -> 403
def test_case_4_enforce_mode_non_admin_token(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "enforce")
    non_admin_token = make_token(userid="1234567890123", teaccode="999", is_admin=False)
    res = client.get("/api/admin/stats", headers={"Authorization": f"Bearer {non_admin_token}"})
    assert res.status_code == 403
    assert res.json().get("detail") == "Admin privileges required"

# Case 5: AUTH_MODE=enforce, valid admin token -> Status not 401/403
def test_case_5_enforce_mode_valid_admin_token(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "enforce")
    admin_token = make_token(userid="1234567890123", teaccode="440", is_admin=True)
    res = client.get("/api/admin/stats", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code not in [401, 403]
    assert res.status_code == 200

# Case 6: Open routes (/api/auth/login, GET /) have no auth requirement even in enforce mode
def test_case_6_open_routes_in_enforce_mode(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "enforce")
    # Root endpoint
    res_root = client.get("/")
    assert res_root.status_code == 200
    assert "status" in res_root.json()

    # Login endpoint rejects with 401 only if credentials bad, not missing token
    res_login = client.post("/api/auth/login", json={"idCard": "0000000000000", "pin": "000000"})
    assert res_login.status_code == 401
    assert res_login.json().get("detail") == "Incorrect username or password"

# Case 7: Tokens, PINs, and sensitive bodies are NEVER logged
def test_case_7_no_tokens_logged(caplog, monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "log")
    secret_marker_token = "eyJhbGciOiJIUzI1NiJ9.SECRET_TOKEN_PAYLOAD_NEVER_LOG.SIG"
    with caplog.at_level("WARNING"):
        client.get("/api/admin/stats", headers={"Authorization": f"Bearer {secret_marker_token}"})
    assert secret_marker_token not in caplog.text
    assert "SECRET_TOKEN_PAYLOAD_NEVER_LOG" not in caplog.text
