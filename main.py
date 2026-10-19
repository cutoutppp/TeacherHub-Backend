from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from auth_router import router as auth_router
from teacher_tasks import router as dashboard_router
from admin_router import router as admin_router

app = FastAPI(title="TeacherHub Central Portal")

import os

# Allow CORS for frontend
raw_origins = os.getenv("ALLOWED_ORIGINS", "")
if raw_origins.strip():
    allowed_origins = [o.strip() for o in raw_origins.split(",") if o.strip()]
else:
    allowed_origins = [
        "https://cutoutppp.github.io",
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:5173",
        "*"
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=1000)

from sgs_module.sgs_router import router as sgs_router
from moresor_router import router as moresor_router
from t2g_analyzer_router import router as t2g_analyzer_router

app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(admin_router)
app.include_router(sgs_router)
app.include_router(moresor_router)
app.include_router(t2g_analyzer_router)

@app.get("/")
def read_root():
    return {"status": "TeacherHub Backend is running"}
