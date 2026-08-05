import os

main_path = r'C:\Users\peera\Desktop\AntigravityProject\AssessmentHub\SgsNextschool\backend\main.py'
router_path = r'C:\Users\peera\Desktop\AntigravityProject\TeacherHub\sgs_module\sgs_router.py'

with open(main_path, 'r', encoding='utf-8') as f:
    main_content = f.read()

fallback_def = ''
idx = main_content.find('def _get_fallback_demo_rooms')
if idx != -1:
    end_idx = main_content.find('def ', idx + 10)
    fallback_def = main_content[idx:end_idx].strip()

with open(router_path, 'r', encoding='utf-8') as rf:
    router_content = rf.read()
    
if fallback_def and fallback_def not in router_content:
    router_content = router_content.replace('@router.post("/api/export/wp16/saved")', fallback_def + '\n\n@router.post("/api/export/wp16/saved")')
    with open(router_path, 'w', encoding='utf-8') as wf:
        wf.write(router_content)
    print('Added fallback def')
else:
    print('Already has fallback def or not found')

