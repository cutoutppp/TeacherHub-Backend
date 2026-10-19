import os

main_path = r'C:\Users\peera\Desktop\AntigravityProject\AssessmentHub\SgsNextschool\backend\main.py'
router_path = r'C:\Users\peera\Desktop\AntigravityProject\TeacherHub\sgs_module\sgs_router.py'

with open(main_path, 'r', encoding='utf-8') as f:
    main_content = f.read()

idx = main_content.find('@app.post("/api/export/wp16/saved")')
if idx != -1:
    endpoints = main_content[idx:]
    endpoints = endpoints.replace('@app.post', '@router.post')
    
    with open(router_path, 'r', encoding='utf-8') as rf:
        router_content = rf.read()
        
    ridx = router_content.find('@router.post("/api/export/wp16/saved")')
    if ridx != -1:
        router_content = router_content[:ridx] + endpoints
    else:
        router_content += '\n\n' + endpoints
        
    # Make sure urllib.parse.quote is imported in sgs_router.py
    if 'from urllib.parse import quote' not in router_content:
        router_content = 'from urllib.parse import quote\n' + router_content
        
    # Replace generate_wp25_group with missing imports if any
    if 'generate_wp25_group' not in router_content and 'from doc_generator import' in router_content:
        router_content = router_content.replace('from doc_generator import generate_wp25, generate_wp16, generate_wp17', 'from doc_generator import generate_wp25, generate_wp16, generate_wp17, generate_wp25_group')
    
    with open(router_path, 'w', encoding='utf-8') as wf:
        wf.write(router_content)
    print('Patched sgs_router.py')
else:
    print('Could not find endpoints')

