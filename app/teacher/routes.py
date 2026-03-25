from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app import get_db_connection

teacher_bp = Blueprint("teacher", __name__)


# ─── DASHBOARD ───────────────────────────────────────────────────────────────
@teacher_bp.route("/dashboard")
@login_required
def dashboard():
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("""
        SELECT e.*,
          (SELECT COUNT(*) FROM questions WHERE exam_id=e.id) as question_count,
          (SELECT COUNT(*) FROM results WHERE exam_id=e.id) as submission_count
        FROM exams e WHERE e.teacher_id=%s ORDER BY e.created_at DESC LIMIT 5
    """, (current_user.id,))
    recent_exams = cur.fetchall()
    cur.execute("SELECT COUNT(*) as cnt FROM exams WHERE teacher_id=%s", (current_user.id,))
    exam_count = cur.fetchone()["cnt"]
    cur.execute("SELECT COUNT(*) as cnt FROM questions q JOIN exams e ON q.exam_id=e.id WHERE e.teacher_id=%s", (current_user.id,))
    total_questions = cur.fetchone()["cnt"]
    cur.execute("SELECT COUNT(*) as cnt FROM results r JOIN exams e ON r.exam_id=e.id WHERE e.teacher_id=%s", (current_user.id,))
    total_submissions = cur.fetchone()["cnt"]
    cur.execute("SELECT COUNT(*) as cnt FROM student_groups WHERE teacher_id=%s", (current_user.id,))
    group_count = cur.fetchone()["cnt"]
    cur.execute("SELECT COUNT(*) as cnt FROM practice_exams WHERE teacher_id=%s", (current_user.id,))
    practice_count = cur.fetchone()["cnt"]
    cur.execute("SELECT COUNT(*) as cnt FROM text_exams WHERE teacher_id=%s", (current_user.id,))
    text_exam_count = cur.fetchone()["cnt"]
    conn.close()
    return render_template("teacher/dashboard.html",
        recent_exams=recent_exams, exam_count=exam_count,
        total_questions=total_questions, total_submissions=total_submissions,
        group_count=group_count, practice_count=practice_count,
        text_exam_count=text_exam_count)


# ─── MCQ EXAMS ───────────────────────────────────────────────────────────────
@teacher_bp.route("/exams")
@login_required
def my_exams():
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("""
        SELECT e.*,
          (SELECT COUNT(*) FROM questions WHERE exam_id=e.id) as question_count,
          (SELECT COUNT(*) FROM results WHERE exam_id=e.id) as submission_count
        FROM exams e WHERE e.teacher_id=%s ORDER BY e.created_at DESC
    """, (current_user.id,))
    exams = cur.fetchall()
    conn.close()
    return render_template("teacher/my_exams.html", exams=exams)


@teacher_bp.route("/results")
@login_required
def my_results():
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("""
        SELECT r.*, u.name as student_name, u.email as student_email,
               e.title as exam_title, e.total_marks
        FROM results r JOIN users u ON r.student_id=u.id JOIN exams e ON r.exam_id=e.id
        WHERE e.teacher_id=%s ORDER BY r.submitted_at DESC
    """, (current_user.id,))
    results = cur.fetchall()
    conn.close()
    return render_template("teacher/my_results.html", results=results)


@teacher_bp.route("/create-exam", methods=["GET", "POST"])
@login_required
def create_exam():
    if request.method == "POST":
        title       = request.form["title"]
        description = request.form.get("description", "")
        duration    = int(request.form.get("duration_minutes", 30))
        is_active   = int(request.form.get("is_active", 1))
        conn = get_db_connection()
        cur  = conn.cursor()
        cur.execute(
            "INSERT INTO exams (title,description,teacher_id,duration_minutes,is_active) VALUES (%s,%s,%s,%s,%s)",
            (title, description, current_user.id, duration, is_active)
        )
        exam_id = cur.lastrowid
        conn.commit(); conn.close()
        return redirect(url_for("teacher.exam_questions", exam_id=exam_id))
    return render_template("teacher/create_exam.html")


@teacher_bp.route("/exam/<int:exam_id>/toggle-active")
@login_required
def toggle_exam_active(exam_id):
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("SELECT is_active FROM exams WHERE id=%s AND teacher_id=%s", (exam_id, current_user.id))
    row = cur.fetchone()
    if row:
        cur.execute("UPDATE exams SET is_active=%s WHERE id=%s", (0 if row["is_active"] else 1, exam_id))
        conn.commit()
    conn.close()
    return redirect(url_for("teacher.my_exams"))


@teacher_bp.route("/exam/<int:exam_id>/questions")
@login_required
def exam_questions(exam_id):
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("SELECT * FROM exams WHERE id=%s AND teacher_id=%s", (exam_id, current_user.id))
    exam = cur.fetchone()
    if not exam:
        conn.close(); return redirect(url_for("teacher.my_exams"))
    cur.execute("SELECT * FROM questions WHERE exam_id=%s", (exam_id,))
    questions = cur.fetchall()
    conn.close()
    return render_template("teacher/exam_questions.html", exam=exam, questions=questions)


@teacher_bp.route("/exam/<int:exam_id>/add-question", methods=["POST"])
@login_required
def add_question(exam_id):
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute(
        "INSERT INTO questions (exam_id,question,option_a,option_b,option_c,option_d,correct_option,marks) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        (exam_id, request.form["question"], request.form["a"], request.form["b"],
         request.form["c"], request.form["d"], request.form["correct"], int(request.form.get("marks", 1)))
    )
    cur.execute("UPDATE exams SET total_marks=(SELECT COALESCE(SUM(marks),0) FROM questions WHERE exam_id=%s) WHERE id=%s", (exam_id, exam_id))
    conn.commit(); conn.close()
    return redirect(url_for("teacher.exam_questions", exam_id=exam_id))


@teacher_bp.route("/question/<int:q_id>/delete")
@login_required
def delete_question(q_id):
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("SELECT exam_id FROM questions WHERE id=%s", (q_id,))
    q = cur.fetchone()
    if q:
        exam_id = q["exam_id"]
        cur.execute("DELETE FROM questions WHERE id=%s", (q_id,))
        cur.execute("UPDATE exams SET total_marks=COALESCE((SELECT SUM(marks) FROM questions WHERE exam_id=%s),0) WHERE id=%s", (exam_id, exam_id))
        conn.commit(); conn.close()
        return redirect(url_for("teacher.exam_questions", exam_id=exam_id))
    conn.close()
    return redirect(url_for("teacher.my_exams"))


@teacher_bp.route("/exam/<int:exam_id>/delete")
@login_required
def delete_exam(exam_id):
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("DELETE FROM exams WHERE id=%s AND teacher_id=%s", (exam_id, current_user.id))
    conn.commit(); conn.close()
    return redirect(url_for("teacher.my_exams"))


@teacher_bp.route("/exam/<int:exam_id>/results")
@login_required
def exam_results(exam_id):
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("SELECT * FROM exams WHERE id=%s AND teacher_id=%s", (exam_id, current_user.id))
    exam = cur.fetchone()
    if not exam:
        conn.close(); return redirect(url_for("teacher.my_results"))
    cur.execute("""
        SELECT r.*, u.name, u.email FROM results r
        JOIN users u ON r.student_id=u.id WHERE r.exam_id=%s ORDER BY r.submitted_at DESC
    """, (exam_id,))
    results = cur.fetchall()
    conn.close()
    return render_template("teacher/exam_results.html", exam=exam, results=results)


# ─── TEXT / DESCRIPTIVE EXAMS ─────────────────────────────────────────────────
@teacher_bp.route("/text-exams")
@login_required
def text_exams():
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("""
        SELECT te.*,
          (SELECT COUNT(*) FROM text_questions WHERE exam_id=te.id) as question_count,
          (SELECT COUNT(*) FROM text_submissions WHERE exam_id=te.id) as submission_count
        FROM text_exams te WHERE te.teacher_id=%s ORDER BY te.created_at DESC
    """, (current_user.id,))
    exams = cur.fetchall()
    conn.close()
    return render_template("teacher/text_exams.html", exams=exams)


@teacher_bp.route("/text-exam/create", methods=["GET", "POST"])
@login_required
def create_text_exam():
    if request.method == "POST":
        title       = request.form["title"]
        description = request.form.get("description", "")
        duration    = int(request.form.get("duration_minutes", 60))
        is_active   = int(request.form.get("is_active", 1))
        conn = get_db_connection()
        cur  = conn.cursor()
        cur.execute(
            "INSERT INTO text_exams (title,description,teacher_id,duration_minutes,is_active) VALUES (%s,%s,%s,%s,%s)",
            (title, description, current_user.id, duration, is_active)
        )
        exam_id = cur.lastrowid
        conn.commit(); conn.close()
        return redirect(url_for("teacher.text_exam_questions", exam_id=exam_id))
    return render_template("teacher/create_text_exam.html")


@teacher_bp.route("/text-exam/<int:exam_id>/questions")
@login_required
def text_exam_questions(exam_id):
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("SELECT * FROM text_exams WHERE id=%s AND teacher_id=%s", (exam_id, current_user.id))
    exam = cur.fetchone()
    if not exam:
        conn.close(); return redirect(url_for("teacher.text_exams"))
    cur.execute("SELECT * FROM text_questions WHERE exam_id=%s", (exam_id,))
    questions = cur.fetchall()
    conn.close()
    return render_template("teacher/text_exam_questions.html", exam=exam, questions=questions)


@teacher_bp.route("/text-exam/<int:exam_id>/add-question", methods=["POST"])
@login_required
def add_text_question(exam_id):
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute(
        "INSERT INTO text_questions (exam_id,question,marks,model_answer,key_points) VALUES (%s,%s,%s,%s,%s)",
        (exam_id, request.form["question"], int(request.form.get("marks", 5)),
         request.form.get("model_answer", ""), request.form.get("key_points", ""))
    )
    cur.execute("UPDATE text_exams SET total_marks=(SELECT COALESCE(SUM(marks),0) FROM text_questions WHERE exam_id=%s) WHERE id=%s", (exam_id, exam_id))
    conn.commit(); conn.close()
    return redirect(url_for("teacher.text_exam_questions", exam_id=exam_id))


@teacher_bp.route("/text-question/<int:q_id>/delete")
@login_required
def delete_text_question(q_id):
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("SELECT exam_id FROM text_questions WHERE id=%s", (q_id,))
    q = cur.fetchone()
    if q:
        exam_id = q["exam_id"]
        cur.execute("DELETE FROM text_questions WHERE id=%s", (q_id,))
        cur.execute("UPDATE text_exams SET total_marks=COALESCE((SELECT SUM(marks) FROM text_questions WHERE exam_id=%s),0) WHERE id=%s", (exam_id, exam_id))
        conn.commit(); conn.close()
        return redirect(url_for("teacher.text_exam_questions", exam_id=exam_id))
    conn.close()
    return redirect(url_for("teacher.text_exams"))


@teacher_bp.route("/text-exam/<int:exam_id>/delete")
@login_required
def delete_text_exam(exam_id):
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("DELETE FROM text_exams WHERE id=%s AND teacher_id=%s", (exam_id, current_user.id))
    conn.commit(); conn.close()
    return redirect(url_for("teacher.text_exams"))


@teacher_bp.route("/text-exam/<int:exam_id>/toggle")
@login_required
def toggle_text_exam(exam_id):
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("SELECT is_active FROM text_exams WHERE id=%s AND teacher_id=%s", (exam_id, current_user.id))
    row = cur.fetchone()
    if row:
        cur.execute("UPDATE text_exams SET is_active=%s WHERE id=%s", (0 if row["is_active"] else 1, exam_id))
        conn.commit()
    conn.close()
    return redirect(url_for("teacher.text_exams"))


@teacher_bp.route("/text-exam/<int:exam_id>/submissions")
@login_required
def text_exam_submissions(exam_id):
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("SELECT * FROM text_exams WHERE id=%s AND teacher_id=%s", (exam_id, current_user.id))
    exam = cur.fetchone()
    if not exam:
        conn.close(); return redirect(url_for("teacher.text_exams"))
    cur.execute("""
        SELECT ts.*, u.name as student_name, u.email as student_email
        FROM text_submissions ts JOIN users u ON ts.student_id=u.id
        WHERE ts.exam_id=%s ORDER BY ts.submitted_at DESC
    """, (exam_id,))
    submissions = cur.fetchall()
    conn.close()
    return render_template("teacher/text_submissions.html", exam=exam, submissions=submissions)


@teacher_bp.route("/text-submission/<int:sub_id>/evaluate", methods=["GET", "POST"])
@login_required
def evaluate_submission(sub_id):
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("""
        SELECT ts.*, u.name as student_name, te.title as exam_title, te.teacher_id, te.total_marks
        FROM text_submissions ts
        JOIN users u ON ts.student_id=u.id
        JOIN text_exams te ON ts.exam_id=te.id
        WHERE ts.id=%s
    """, (sub_id,))
    submission = cur.fetchone()
    if not submission or submission["teacher_id"] != current_user.id:
        conn.close(); return redirect(url_for("teacher.text_exams"))

    cur.execute("""
        SELECT ta.*, tq.question, tq.marks as max_marks, tq.model_answer, tq.key_points
        FROM text_answers ta JOIN text_questions tq ON ta.question_id=tq.id
        WHERE ta.submission_id=%s ORDER BY tq.id
    """, (sub_id,))
    answers = cur.fetchall()

    if request.method == "POST":
        total = 0
        for ans in answers:
            awarded = int(request.form.get(f"marks_{ans['id']}", 0))
            comment = request.form.get(f"comment_{ans['id']}", "")
            cur.execute(
                "UPDATE text_answers SET awarded_marks=%s, teacher_comment=%s WHERE id=%s",
                (awarded, comment, ans["id"])
            )
            total += awarded
        cur.execute(
            "UPDATE text_submissions SET total_score=%s, is_evaluated=1 WHERE id=%s",
            (total, sub_id)
        )
        conn.commit(); conn.close()
        return redirect(url_for("teacher.text_exam_submissions", exam_id=submission["exam_id"]))

    conn.close()
    return render_template("teacher/evaluate_submission.html",
        submission=submission, answers=answers)


# ─── STUDENT GROUPS ───────────────────────────────────────────────────────────
@teacher_bp.route("/groups")
@login_required
def groups():
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("""
        SELECT sg.*,
          (SELECT COUNT(*) FROM group_members WHERE group_id=sg.id) as member_count,
          (SELECT COUNT(*) FROM practice_exams WHERE group_id=sg.id) as exam_count
        FROM student_groups sg WHERE sg.teacher_id=%s ORDER BY sg.created_at DESC
    """, (current_user.id,))
    groups = cur.fetchall()
    conn.close()
    return render_template("teacher/groups.html", groups=groups)


@teacher_bp.route("/groups/create", methods=["GET", "POST"])
@login_required
def create_group():
    conn = get_db_connection()
    cur  = conn.cursor()
    if request.method == "POST":
        name        = request.form["name"]
        description = request.form.get("description", "")
        cur.execute(
            "INSERT INTO student_groups (name, description, teacher_id) VALUES (%s,%s,%s)",
            (name, description, current_user.id)
        )
        group_id = cur.lastrowid
        conn.commit(); conn.close()
        return redirect(url_for("teacher.manage_group", group_id=group_id))

    # Fetch students with their average scores for easy grouping
    cur.execute("""
        SELECT u.id, u.name, u.email,
          COALESCE(ROUND(AVG(r.score / NULLIF(e.total_marks,0) * 100), 1), 0) as avg_pct,
          COUNT(r.id) as attempts
        FROM users u
        LEFT JOIN results r ON r.student_id=u.id
        LEFT JOIN exams e ON e.id=r.exam_id
        WHERE u.role='student' AND u.is_blocked=0
        GROUP BY u.id ORDER BY avg_pct ASC
    """)
    students = cur.fetchall()
    conn.close()
    return render_template("teacher/create_group.html", students=students)


@teacher_bp.route("/groups/<int:group_id>")
@login_required
def manage_group(group_id):
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("SELECT * FROM student_groups WHERE id=%s AND teacher_id=%s", (group_id, current_user.id))
    group = cur.fetchone()
    if not group:
        conn.close(); return redirect(url_for("teacher.groups"))
    cur.execute("""
        SELECT u.id, u.name, u.email,
          COALESCE(ROUND(AVG(r.score / NULLIF(e.total_marks,0) * 100), 1), 0) as avg_pct
        FROM group_members gm JOIN users u ON gm.student_id=u.id
        LEFT JOIN results r ON r.student_id=u.id
        LEFT JOIN exams e ON e.id=r.exam_id
        WHERE gm.group_id=%s GROUP BY u.id
    """, (group_id,))
    members = cur.fetchall()
    cur.execute("""
        SELECT u.id, u.name, u.email
        FROM users u WHERE u.role='student' AND u.is_blocked=0
          AND u.id NOT IN (SELECT student_id FROM group_members WHERE group_id=%s)
    """, (group_id,))
    non_members = cur.fetchall()
    cur.execute("""
        SELECT pe.*,
          (SELECT COUNT(*) FROM practice_questions WHERE exam_id=pe.id) as question_count,
          (SELECT COUNT(*) FROM practice_results WHERE exam_id=pe.id) as submission_count
        FROM practice_exams pe WHERE pe.group_id=%s ORDER BY pe.created_at DESC
    """, (group_id,))
    practice_exams = cur.fetchall()
    conn.close()
    return render_template("teacher/manage_group.html",
        group=group, members=members, non_members=non_members,
        practice_exams=practice_exams)


@teacher_bp.route("/groups/<int:group_id>/add-member", methods=["POST"])
@login_required
def add_group_member(group_id):
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("SELECT id FROM student_groups WHERE id=%s AND teacher_id=%s", (group_id, current_user.id))
    if cur.fetchone():
        student_ids = request.form.getlist("student_ids")
        for sid in student_ids:
            try:
                cur.execute("INSERT IGNORE INTO group_members (group_id, student_id) VALUES (%s,%s)", (group_id, sid))
            except Exception:
                pass
        conn.commit()
    conn.close()
    return redirect(url_for("teacher.manage_group", group_id=group_id))


@teacher_bp.route("/groups/<int:group_id>/remove-member/<int:student_id>")
@login_required
def remove_group_member(group_id, student_id):
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("SELECT id FROM student_groups WHERE id=%s AND teacher_id=%s", (group_id, current_user.id))
    if cur.fetchone():
        cur.execute("DELETE FROM group_members WHERE group_id=%s AND student_id=%s", (group_id, student_id))
        conn.commit()
    conn.close()
    return redirect(url_for("teacher.manage_group", group_id=group_id))


@teacher_bp.route("/groups/<int:group_id>/delete")
@login_required
def delete_group(group_id):
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("DELETE FROM student_groups WHERE id=%s AND teacher_id=%s", (group_id, current_user.id))
    conn.commit(); conn.close()
    return redirect(url_for("teacher.groups"))


@teacher_bp.route("/groups/<int:group_id>/analytics")
@login_required
def group_analytics(group_id):
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("SELECT * FROM student_groups WHERE id=%s AND teacher_id=%s", (group_id, current_user.id))
    group = cur.fetchone()
    if not group:
        conn.close(); return redirect(url_for("teacher.groups"))
    cur.execute("""
        SELECT pe.id, pe.title, pe.total_marks,
          COUNT(pr.id) as attempt_count,
          COALESCE(ROUND(AVG(pr.score),1), 0) as avg_score,
          COALESCE(MAX(pr.score), 0) as max_score,
          COALESCE(MIN(pr.score), 0) as min_score
        FROM practice_exams pe
        LEFT JOIN practice_results pr ON pr.exam_id=pe.id
        WHERE pe.group_id=%s GROUP BY pe.id ORDER BY pe.created_at DESC
    """, (group_id,))
    exam_stats = cur.fetchall()
    cur.execute("""
        SELECT u.name, u.email,
          COUNT(pr.id) as attempts,
          COALESCE(ROUND(AVG(pr.score / NULLIF(pe.total_marks,0) * 100),1), 0) as avg_pct,
          COALESCE(MAX(pr.score), 0) as best_score
        FROM group_members gm JOIN users u ON gm.student_id=u.id
        LEFT JOIN practice_results pr ON pr.student_id=u.id
        LEFT JOIN practice_exams pe ON pe.id=pr.exam_id AND pe.group_id=%s
        WHERE gm.group_id=%s GROUP BY u.id ORDER BY avg_pct DESC
    """, (group_id, group_id))
    student_stats = cur.fetchall()
    conn.close()
    return render_template("teacher/group_analytics.html",
        group=group, exam_stats=exam_stats, student_stats=student_stats)


# ─── PRACTICE EXAMS ──────────────────────────────────────────────────────────
@teacher_bp.route("/groups/<int:group_id>/practice/create", methods=["GET", "POST"])
@login_required
def create_practice_exam(group_id):
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("SELECT * FROM student_groups WHERE id=%s AND teacher_id=%s", (group_id, current_user.id))
    group = cur.fetchone()
    if not group:
        conn.close(); return redirect(url_for("teacher.groups"))
    if request.method == "POST":
        cur.execute(
            "INSERT INTO practice_exams (title,description,teacher_id,group_id,duration_minutes,is_active) VALUES (%s,%s,%s,%s,%s,%s)",
            (request.form["title"], request.form.get("description",""),
             current_user.id, group_id, int(request.form.get("duration_minutes", 30)),
             int(request.form.get("is_active", 1)))
        )
        exam_id = cur.lastrowid
        conn.commit(); conn.close()
        return redirect(url_for("teacher.practice_exam_questions", exam_id=exam_id))
    conn.close()
    return render_template("teacher/create_practice_exam.html", group=group)


@teacher_bp.route("/practice/<int:exam_id>/questions")
@login_required
def practice_exam_questions(exam_id):
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("""
        SELECT pe.*, sg.name as group_name FROM practice_exams pe
        JOIN student_groups sg ON pe.group_id=sg.id
        WHERE pe.id=%s AND pe.teacher_id=%s
    """, (exam_id, current_user.id))
    exam = cur.fetchone()
    if not exam:
        conn.close(); return redirect(url_for("teacher.groups"))
    cur.execute("SELECT * FROM practice_questions WHERE exam_id=%s", (exam_id,))
    questions = cur.fetchall()
    conn.close()
    return render_template("teacher/practice_exam_questions.html", exam=exam, questions=questions)


@teacher_bp.route("/practice/<int:exam_id>/add-question", methods=["POST"])
@login_required
def add_practice_question(exam_id):
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute(
        "INSERT INTO practice_questions (exam_id,question,option_a,option_b,option_c,option_d,correct_option,marks) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        (exam_id, request.form["question"], request.form["a"], request.form["b"],
         request.form["c"], request.form["d"], request.form["correct"], int(request.form.get("marks", 1)))
    )
    cur.execute("UPDATE practice_exams SET total_marks=(SELECT COALESCE(SUM(marks),0) FROM practice_questions WHERE exam_id=%s) WHERE id=%s", (exam_id, exam_id))
    conn.commit(); conn.close()
    return redirect(url_for("teacher.practice_exam_questions", exam_id=exam_id))


@teacher_bp.route("/practice-question/<int:q_id>/delete")
@login_required
def delete_practice_question(q_id):
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("SELECT exam_id FROM practice_questions WHERE id=%s", (q_id,))
    q = cur.fetchone()
    if q:
        exam_id = q["exam_id"]
        cur.execute("DELETE FROM practice_questions WHERE id=%s", (q_id,))
        cur.execute("UPDATE practice_exams SET total_marks=COALESCE((SELECT SUM(marks) FROM practice_questions WHERE exam_id=%s),0) WHERE id=%s", (exam_id, exam_id))
        conn.commit(); conn.close()
        return redirect(url_for("teacher.practice_exam_questions", exam_id=exam_id))
    conn.close()
    return redirect(url_for("teacher.groups"))


@teacher_bp.route("/practice/<int:exam_id>/results")
@login_required
def practice_exam_results(exam_id):
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("SELECT pe.*, sg.name as group_name FROM practice_exams pe JOIN student_groups sg ON pe.group_id=sg.id WHERE pe.id=%s AND pe.teacher_id=%s", (exam_id, current_user.id))
    exam = cur.fetchone()
    if not exam:
        conn.close(); return redirect(url_for("teacher.groups"))
    cur.execute("""
        SELECT pr.*, u.name, u.email FROM practice_results pr
        JOIN users u ON pr.student_id=u.id WHERE pr.exam_id=%s ORDER BY pr.score DESC
    """, (exam_id,))
    results = cur.fetchall()
    conn.close()
    return render_template("teacher/practice_results.html", exam=exam, results=results)
