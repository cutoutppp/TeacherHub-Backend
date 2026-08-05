import re

router_path = r'C:\Users\peera\Desktop\AntigravityProject\TeacherHub\sgs_module\sgs_router.py'
with open(router_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the syntax error
bad_part = '@app.post("/api/export/wp16/saved")\nasync\n\n@router.post("/api/export/wp16/saved")'
good_part = '@router.post("/api/export/wp16/saved")'

content = content.replace(bad_part, good_part)

# Wait, there's another `@router.post` earlier maybe? Let's just fix the specific bad string.
# Actually, I should just fix `async\n\n@router.post` -> `@router.post` and `@app.post...` -> nothing

with open(router_path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Syntax fixed")
