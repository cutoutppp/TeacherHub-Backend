const fs = require('fs');
const path = 'c:/Users/peera/Desktop/AntigravityProject/AssessmentHub/TeacherHubPortal/backend/admin_router.py';
let content = fs.readFileSync(path, 'utf8');

content = content.replace('db.query(Teacher).count()', 'len(db.get_all())');
content = content.replace('db.query(Teacher).all()', 'db.get_all()');
content = content.replace(
    'existing_user = db.query(Teacher).filter(Teacher.userid == teacher_data.userid).first()',
    'existing_user = db.get_teacher_by_userid(teacher_data.userid)'
);

const targetAdd = `    new_teacher = Teacher(
        userid=teacher_data.userid,
        pin_hash=pin_hash,
        teaccode=teacher_data.teaccode,
        prefix=teacher_data.prefix,
        firstname=teacher_data.firstname,
        lastname=teacher_data.lastname,
        subjectgroup=teacher_data.subjectgroup,
        is_admin=teacher_data.is_admin
    )
    
    db.add(new_teacher)
    db.commit()
    db.refresh(new_teacher)`;

const replacementAdd = `    new_teacher = Teacher(
        userid=teacher_data.userid,
        pin_hash=pin_hash,
        teaccode=teacher_data.teaccode,
        prefix=teacher_data.prefix,
        firstname=teacher_data.firstname,
        lastname=teacher_data.lastname,
        subjectgroup=teacher_data.subjectgroup,
        is_admin=teacher_data.is_admin
    )
    
    success = db.add_teacher(new_teacher)
    if not success:
        raise HTTPException(status_code=500, detail="ไม่สามารถบันทึกข้อมูลลง Google Sheet ได้")`;

content = content.replace(targetAdd, replacementAdd);

const targetReset = `    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="ไม่พบข้อมูลครูท่านนี้")
        
    raw_pin = str(teacher.userid)[-6:] if teacher.userid and len(str(teacher.userid)) >= 6 else "123456"
    teacher.pin_hash = get_pin_hash(raw_pin)
    
    db.commit()`;

const replacementReset = `    teacher = db.get_teacher_by_id(teacher_id)
    if not teacher:
        raise HTTPException(status_code=404, detail="ไม่พบข้อมูลครูท่านนี้")
        
    raw_pin = str(teacher.userid)[-6:] if teacher.userid and len(str(teacher.userid)) >= 6 else "123456"
    new_hash = get_pin_hash(raw_pin)
    
    success = db.update_pin(teacher.userid, new_hash)
    if not success:
        raise HTTPException(status_code=500, detail="ไม่สามารถบันทึกข้อมูลลง Google Sheet ได้")`;

content = content.replace(targetReset, replacementReset);

// Replace Session typing
content = content.replace(/db: Session = Depends\(get_db\)/g, 'db = Depends(get_db)');

fs.writeFileSync(path, content, 'utf8');
console.log('SUCCESS');
