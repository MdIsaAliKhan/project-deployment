from flask import Blueprint, render_template, request, redirect, url_for, jsonify
from flask_login import login_required, current_user
from app import get_db_connection
from app.auth.routes import role_required

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/dashboard")
@login_required
@role_required("admin")
def dashboard():
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("SELECT COUNT(*) as cnt FROM users WHERE role='teacher'")
    teacher_count = cur.fetchone()["cnt"]
    cur.execute("SELECT COUNT(*) as cnt FROM users WHERE role='student'")
    student_count = cur.fetchone()["cnt"]
    cur.execute("SELECT COUNT(*) as cnt FROM exams")
    exam_count = cur.fetchone()["cnt"]
    cur.execute("SELECT COUNT(*) as cnt FROM results")
    result_count = cur.fetchone()["cnt"]
    cur.execute("SELECT COUNT(*) as cnt FROM users WHERE role='student' AND is_blocked=1")
    blocked_count = cur.fetchone()["cnt"]
    cur.execute("SELECT COUNT(*) as cnt FROM text_exams")
    text_exam_count = cur.fetchone()["cnt"]
    cur.execute("SELECT COUNT(*) as cnt FROM text_submissions WHERE is_evaluated=0")
    pending_eval = cur.fetchone()["cnt"]
    cur.execute("SELECT setting_value FROM settings WHERE setting_key='face_auth_enabled'")
    row = cur.fetchone()
    face_auth_enabled = (row["setting_value"] == "1") if row else True
    conn.close()
    return render_template("admin/dashboard.html",
        teacher_count=teacher_count, student_count=student_count,
        exam_count=exam_count, result_count=result_count,
        blocked_count=blocked_count, text_exam_count=text_exam_count,
        pending_eval=pending_eval, face_auth_enabled=face_auth_enabled)


@admin_bp.route("/toggle-face-auth", methods=["POST"])
@login_required
@role_required("admin")
def toggle_face_auth():
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("SELECT setting_value FROM settings WHERE setting_key='face_auth_enabled'")
    row = cur.fetchone()
    new_val = "0" if (row and row["setting_value"] == "1") else "1"
    cur.execute("INSERT INTO settings (setting_key, setting_value) VALUES ('face_auth_enabled',%s) ON DUPLICATE KEY UPDATE setting_value=%s", (new_val, new_val))
    conn.commit(); conn.close()
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/teachers")
@login_required
@role_required("admin")
def teachers():
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("""
        SELECT u.*, (SELECT COUNT(*) FROM exams WHERE teacher_id=u.id) as exam_count
        FROM users u WHERE u.role='teacher' ORDER BY u.created_at DESC
    """)
    teachers = cur.fetchall()
    conn.close()
    return render_template("admin/teachers.html", teachers=teachers)


@admin_bp.route("/add-teacher", methods=["POST"])
@login_required
@role_required("admin")
def add_teacher():
    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        cur.execute("INSERT INTO users (name,email,password,role) VALUES (%s,%s,%s,'teacher')",
            (request.form["name"].strip(), request.form["email"].strip(), request.form["password"]))
        conn.commit()
    except Exception: pass
    conn.close()
    return redirect(url_for("admin.teachers"))


@admin_bp.route("/delete-teacher/<int:uid>")
@login_required
@role_required("admin")
def delete_teacher(uid):
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("DELETE FROM users WHERE id=%s AND role='teacher'", (uid,))
    conn.commit(); conn.close()
    return redirect(url_for("admin.teachers"))


@admin_bp.route("/students")
@login_required
@role_required("admin")
def students():
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("""
        SELECT u.*,
          (SELECT COUNT(*) FROM results WHERE student_id=u.id) as attempt_count,
          (SELECT MAX(score) FROM results WHERE student_id=u.id) as best_score
        FROM users u WHERE u.role='student' ORDER BY u.created_at DESC
    """)
    students = cur.fetchall()
    conn.close()
    return render_template("admin/students.html", students=students)


@admin_bp.route("/add-student", methods=["POST"])
@login_required
@role_required("admin")
def add_student():
    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        cur.execute("INSERT INTO users (name,email,password,role) VALUES (%s,%s,%s,'student')",
            (request.form["name"].strip(), request.form["email"].strip(), request.form["password"]))
        conn.commit()
    except Exception: pass
    conn.close()
    return redirect(url_for("admin.students"))


@admin_bp.route("/delete-student/<int:uid>")
@login_required
@role_required("admin")
def delete_student(uid):
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("DELETE FROM users WHERE id=%s AND role='student'", (uid,))
    conn.commit(); conn.close()
    return redirect(url_for("admin.students"))


@admin_bp.route("/block-student/<int:uid>")
@login_required
@role_required("admin")
def block_student(uid):
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("SELECT is_blocked FROM users WHERE id=%s", (uid,))
    row = cur.fetchone()
    new_status = 0 if row and row["is_blocked"] else 1
    cur.execute("UPDATE users SET is_blocked=%s WHERE id=%s", (new_status, uid))
    conn.commit(); conn.close()
    return redirect(url_for("admin.students"))


@admin_bp.route("/results")
@login_required
@role_required("admin")
def results():
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("""
        SELECT r.*, u.name as student_name, u.email as student_email,
               e.title as exam_title, e.total_marks
        FROM results r JOIN users u ON r.student_id=u.id JOIN exams e ON r.exam_id=e.id
        ORDER BY r.submitted_at DESC
    """)
    results = cur.fetchall()
    conn.close()
    return render_template("admin/results.html", results=results)


@admin_bp.route("/result/<int:rid>/edit", methods=["POST"])
@login_required
@role_required("admin")
def edit_result(rid):
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("UPDATE results SET score=%s,correct_count=%s,wrong_count=%s,skipped_count=%s WHERE id=%s",
        (request.form.get("score",0), request.form.get("correct_count",0),
         request.form.get("wrong_count",0), request.form.get("skipped_count",0), rid))
    conn.commit(); conn.close()
    return redirect(url_for("admin.results"))


@admin_bp.route("/result/<int:rid>/delete")
@login_required
@role_required("admin")
def delete_result(rid):
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("DELETE FROM results WHERE id=%s", (rid,))
    conn.commit(); conn.close()
    return redirect(url_for("admin.results"))


# ─── TEXT EXAM RESULT VISIBILITY ─────────────────────────────────────────────
@admin_bp.route("/text-exams")
@login_required
@role_required("admin")
def text_exams():
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("""
        SELECT te.*, u.name as teacher_name,
          (SELECT COUNT(*) FROM text_submissions WHERE exam_id=te.id) as submission_count,
          (SELECT COUNT(*) FROM text_submissions WHERE exam_id=te.id AND is_evaluated=1) as evaluated_count
        FROM text_exams te JOIN users u ON te.teacher_id=u.id ORDER BY te.created_at DESC
    """)
    exams = cur.fetchall()
    conn.close()
    return render_template("admin/text_exams.html", exams=exams)


@admin_bp.route("/text-exam/<int:exam_id>/toggle-publish")
@login_required
@role_required("admin")
def toggle_text_publish(exam_id):
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("SELECT result_published FROM text_exams WHERE id=%s", (exam_id,))
    row = cur.fetchone()
    if row:
        cur.execute("UPDATE text_exams SET result_published=%s WHERE id=%s",
            (0 if row["result_published"] else 1, exam_id))
        conn.commit()
    conn.close()
    return redirect(url_for("admin.text_exams"))


# ─── PLAGIARISM ───────────────────────────────────────────────────────────────
@admin_bp.route("/api/exams")
@login_required
@role_required("admin")
def api_exams():
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("SELECT id, title FROM exams ORDER BY created_at DESC")
    exams = [{"id": r["id"], "title": r["title"]} for r in cur.fetchall()]
    conn.close()
    return jsonify(exams)


@admin_bp.route("/api/plagiarism")
@login_required
@role_required("admin")
def api_plagiarism():
    exam_id   = request.args.get("exam_id", type=int)
    threshold = request.args.get("threshold", 60, type=int)
    if not exam_id: return jsonify({"pairs": []})
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("""
        SELECT r.student_id, u.name as student_name, r.answers FROM results r
        JOIN users u ON r.student_id=u.id WHERE r.exam_id=%s ORDER BY r.submitted_at
    """, (exam_id,))
    rows = cur.fetchall()
    conn.close()
    import json as _json
    students = []
    for row in rows:
        try: answers = _json.loads(row["answers"]) if row["answers"] else {}
        except Exception: answers = {}
        text = " ".join(str(v) for v in answers.values()) if isinstance(answers, dict) else str(answers)
        students.append({"name": row["student_name"], "text": text})
    def jaccard(a, b):
        if not a or not b: return 0
        sa = set(a.lower().split()); sb = set(b.lower().split())
        inter = len(sa & sb); union = len(sa | sb)
        return round((inter / union) * 100) if union else 0
    pairs = []
    for i in range(len(students)):
        for j in range(i+1, len(students)):
            sim = jaccard(students[i]["text"], students[j]["text"])
            if sim >= threshold:
                pairs.append({"student1": students[i]["name"], "student2": students[j]["name"], "similarity": sim})
    pairs.sort(key=lambda x: x["similarity"], reverse=True)
    return jsonify({"pairs": pairs})
