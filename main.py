from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from auth_router import router as auth_router
from teacher_tasks import router as dashboard_router
from admin_router import router as admin_router

app = FastAPI(title="TeacherHub Central Portal")

# Allow CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from sgs_module.sgs_router import router as sgs_router

app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(admin_router)
app.include_router(sgs_router)

@app.get("/")
def read_root():
    return {"status": "TeacherHub Backend is running"}
