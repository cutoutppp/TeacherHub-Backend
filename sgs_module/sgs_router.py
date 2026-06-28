from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import Response
import io
import base64

from .parser import parse_sgs_pdf, parse_nextschool_excel
from .validator import validate_scores
from .doc_generator import generate_wp16, generate_wp17
from .work_db import get_works_for_teacher, add_work, get_rooms_for_subject
from .score_db import load_scores_from_json

router = APIRouter()

@router.post("/api/compare")
async def compare_pdfs(
    files: list[UploadFile] = File(...),
    round_type: str = Form("final"),
    master_scores: str = Form(None)
):
    if master_scores:
        load_scores_from_json(master_scores)
        
    if len(files) < 2:
        raise HTTPException(status_code=400, detail="กรุณาอัปโหลดไฟล์ PDF อย่างน้อย 2 ไฟล์")
        
    for f in files:
        if not (f.filename.lower().endswith('.pdf') or f.filename.lower().endswith('.xlsx')):
            raise HTTPException(status_code=400, detail="ไฟล์ทั้งหมดต้องเป็นนามสกุล .pdf หรือ .xlsx เท่านั้น")
    
    sgs_files = []
    ns_files = []
    unmatched_files = []
    
    for f in files:
        content = await f.read()
        
        if f.filename.lower().endswith('.xlsx'):
            ns_data = parse_nextschool_excel(content, f.filename)
            if ns_data and len(ns_data.get("students", {})) > 0:
                ns_files.append({"filename": f.filename, "content": content, "data": ns_data})
            else:
                unmatched_files.append(f.filename)
        else:
            # Try parsing as SGS
            sgs_data = parse_sgs_pdf(content)
            if sgs_data and len(sgs_data.get("students", {})) > 0:
                sgs_files.append({"filename": f.filename, "content": content, "data": sgs_data})
            else:
                unmatched_files.append(f.filename)

    possible_pairs = []
    
    for s_idx, sgs in enumerate(sgs_files):
        sgs_students = set(sgs["data"]["students"].keys())
        sgs_subject = sgs["data"].get("subject_code", "")
        
        for n_idx, ns in enumerate(ns_files):
            ns_students = set(ns["data"]["students"].keys())
            ns_subject = ns["data"].get("subject_code", "")
            
            intersection = len(sgs_students & ns_students)
            if intersection == 0:
                continue
                
            score = intersection
            
            # Tie-breaker: If subject codes match, prioritize this pair heavily!
            if sgs_subject and ns_subject:
                # E.g. ส33205 == ส33205
                if sgs_subject == ns_subject:
                    score += 1000
                # E.g. ส33205 and 33205 (partial exact match ignoring prefix)
                elif sgs_subject[-5:] == ns_subject[-5:]:
                    score += 500
                    
            possible_pairs.append((score, s_idx, n_idx))
            
    # Sort possible pairs by score descending to assign best matches first
    possible_pairs.sort(key=lambda x: x[0], reverse=True)
    
    pairs = []
    used_sgs = set()
    used_ns = set()
    
    for score, s_idx, n_idx in possible_pairs:
        if s_idx in used_sgs or n_idx in used_ns:
            continue
        pairs.append((sgs_files[s_idx], ns_files[n_idx]))
        used_sgs.add(s_idx)
        used_ns.add(n_idx)
            
    for i, sgs in enumerate(sgs_files):
        if i not in used_sgs:
            unmatched_files.append(sgs["filename"])
            
    for i, ns in enumerate(ns_files):
        if i not in used_ns:
            unmatched_files.append(ns["filename"])
            
    if not pairs:
        raise HTTPException(status_code=400, detail="ไม่สามารถจับคู่ไฟล์ใดๆ ได้เลย โปรดตรวจสอบว่ามีไฟล์ SGS และ NextSchool ที่มีรายชื่อนักเรียนตรงกันหรือไม่")

    try:
        def render_annotated_pdf(file_content, highlights):
            import fitz
            pages_to_render = {}
            for h in highlights:
                p = h["page"]
                if p not in pages_to_render:
                    pages_to_render[p] = []
                pages_to_render[p].append(h)
                
            result_images = []
            doc = fitz.open(stream=file_content, filetype="pdf")
            for page_num in range(len(doc)):
                page = doc[page_num]
                page_highlights = pages_to_render.get(page_num, [])
                
                # Sort highlights so yellow is drawn first, then red on top
                page_highlights.sort(key=lambda h: 1 if h["color"] == "red" else 0)
                
                for h in page_highlights:
                    bbox = h["bbox"]
                    rect = fitz.Rect(bbox["x0"], bbox["top"], bbox["x1"], bbox["bottom"])
                    if h["color"] == "red":
                        color = (1, 0, 0)
                        fill_color = (1, 0.8, 0.8)
                    elif h["color"] == "green":
                        color = (0, 0.8, 0)
                        fill_color = (0.8, 1, 0.8)
                    else:
                        color = (1, 0.7, 0)
                        fill_color = (1, 0.95, 0.7)
                    page.draw_rect(rect, color=color, width=2, fill=fill_color, fill_opacity=0.4)
                    
                pix = page.get_pixmap(dpi=150)
                base64_img = base64.b64encode(pix.tobytes("png")).decode('utf-8')
                result_images.append(f"data:image/png;base64,{base64_img}")
                
            # ส่งกลับไฟล์ต้นฉบับแทนไฟล์ที่ผ่านการวาดกล่องทับ เพื่อป้องกันปัญหาไฟล์เสีย
            doc.close()
            doc_base64 = base64.b64encode(file_content).decode('utf-8')
            return result_images, doc_base64

        pair_results = []
        for sgs, ns in pairs:
            results = validate_scores(sgs["data"], ns["data"], round_type=round_type)
            
            sgs_images, sgs_pdf_b64 = render_annotated_pdf(sgs["content"], results.get("sgs_highlights", []))
            
            next_images = []
            nextschool_pdf_b64 = base64.b64encode(ns["content"]).decode('utf-8') if ns.get("content") else ""
            results["nextschool_data"] = ns["data"]
            
            results["sgs_images"] = sgs_images
            results["nextschool_images"] = next_images
            results["sgs_pdf_b64"] = sgs_pdf_b64
            results["nextschool_pdf_b64"] = nextschool_pdf_b64
            
            if ns["data"].get("is_excel"):
                results["highlights"] = {
                    "nextschool": results.get("nextschool_highlights", [])
                }
            
            results.pop("sgs_highlights", None)
            results.pop("nextschool_highlights", None)
            
            subject_code = sgs["data"].get("subject_code", "Unknown")
            class_level = sgs["data"].get("class_level", "")
            
            pair_results.append({
                "sgs_filename": sgs["filename"],
                "nextschool_filename": ns["filename"],
                "subject_code": subject_code,
                "class_level": class_level,
                "raw_data": {
                    "sgs_students": sgs["data"]["students"],
                    "nextschool_students": ns["data"]["students"],
                    "nextschool_mapping": ns["data"].get("mapping", {})
                },
                "results": results
            })
            
        return {
            "status": "success",
            "data": {
                "pairs": pair_results,
                "unmatched": unmatched_files
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/export/wp16")
async def export_wp16(request: Request):
    try:
        data = await request.json()
        pair_results = data.get("pairs", [])
        doc_bytes = generate_wp16(pair_results)
        if not doc_bytes:
            raise HTTPException(status_code=404, detail="Template not found")
            
        return Response(
            content=doc_bytes,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f"attachment; filename=WP16.docx"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/export/wp17")
async def export_wp17(request: Request):
    try:
        data = await request.json()
        pair_results = data.get("pairs", [])
        doc_bytes = generate_wp17(pair_results)
        if not doc_bytes:
            raise HTTPException(status_code=404, detail="Template not found")
            
        return Response(
            content=doc_bytes,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f"attachment; filename=WP17.docx"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/works")
async def api_get_works(teacher_name: str = None):
    works = get_works_for_teacher(teacher_name)
    return {"status": "success", "data": works}

@router.post("/api/save_work")
async def api_save_work(request: Request):
    try:
        data = await request.json()
        pair_data = data.get("pair")
        if not pair_data:
            return {"status": "error", "message": "No pair data"}
            
        teacher_info = pair_data.get("teacher_info", {})
        teacher_name = teacher_info.get("teacher_name", "Unknown Teacher")
        subject_code = teacher_info.get("subject_code", "Unknown Subject")
        class_level = teacher_info.get("class_level", "Unknown Class")
        
        # Save to DB
        add_work(teacher_name, subject_code, class_level, pair_data)
        
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.post("/api/export/wp16/saved")
async def api_export_wp16_saved(request: Request):
    try:
        data = await request.json()
        teacher_name = data.get("teacher_name")
        subject_code = data.get("subject_code", None)
        
        rooms = get_rooms_for_subject(teacher_name, subject_code)
        if not rooms:
            raise HTTPException(status_code=404, detail="No saved data found for this subject")
            
        doc_bytes = generate_wp16(rooms)
        if not doc_bytes:
            raise HTTPException(status_code=404, detail="Template not found")
            
        filename = f"WP16_{subject_code}.docx" if subject_code else f"WP16_{teacher_name}.docx"
        return Response(
            content=doc_bytes,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/export/wp17/saved")
async def api_export_wp17_saved(request: Request):
    try:
        data = await request.json()
        teacher_name = data.get("teacher_name")
        subject_code = data.get("subject_code", None)
        
        rooms = get_rooms_for_subject(teacher_name, subject_code)
        if not rooms:
            raise HTTPException(status_code=404, detail="No saved data found for this subject")
            
        doc_bytes = generate_wp17(rooms)
        if not doc_bytes:
            raise HTTPException(status_code=404, detail="Template not found")
            
        filename = f"WP17_{subject_code}.docx" if subject_code else f"WP17_{teacher_name}.docx"
        return Response(
            content=doc_bytes,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
