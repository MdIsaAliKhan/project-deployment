from flask import Blueprint, render_template, request, redirect, url_for, session
from flask_login import login_required, current_user
from app import get_db_connection

student_bp = Blueprint("student", __name__)


def is_blocked():
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("SELECT is_blocked FROM users WHERE id=%s", (current_user.id,))
    row = cur.fetchone()
    conn.close()
    return row and row["is_blocked"]


@student_bp.route("/dashboard")
@login_required
def dashboard():
    if is_blocked(): return render_template("student/blocked.html")
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("""
        SELECT e.*,
          (SELECT COUNT(*) FROM questions WHERE exam_id=e.id) as question_count,
          (SELECT id FROM results WHERE student_id=%s AND exam_id=e.id LIMIT 1) as attempt_id
        FROM exams e WHERE e.is_active=1 ORDER BY e.created_at DESC
    """, (current_user.id,))
    raw_exams = cur.fetchall()
    available_exams = []
    for e in raw_exams:
        e = dict(e); e["attempted"] = bool(e.get("attempt_id")); available_exams.append(e)
    cur.execute("SELECT COUNT(*) as cnt FROM results WHERE student_id=%s", (current_user.id,))
    completed_count = cur.fetchone()["cnt"]
    cur.execute("SELECT MAX(score) as best FROM results WHERE student_id=%s", (current_user.id,))
    best_row = cur.fetchone(); best_score = best_row["best"] if best_row else None
    # Practice exams count
    cur.execute("""
        SELECT COUNT(*) as cnt FROM practice_exams pe
        JOIN group_members gm ON gm.group_id=pe.group_id
        WHERE gm.student_id=%s AND pe.is_active=1
    """, (current_user.id,))
    practice_count = cur.fetchone()["cnt"]
    # Text exams count
    cur.execute("""
        SELECT COUNT(*) as cnt FROM text_exams te
        WHERE te.is_active=1
    """)
    text_exam_count = cur.fetchone()["cnt"]
    conn.close()
    return render_template("student/dashboard.html",
        available_exams=available_exams, completed_count=completed_count,
        best_score=best_score, practice_count=practice_count,
        text_exam_count=text_exam_count)


@student_bp.route("/exams")
@login_required
def exams():
    if is_blocked(): return render_template("student/blocked.html")
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("""
        SELECT e.*,
          (SELECT COUNT(*) FROM questions WHERE exam_id=e.id) as question_count,
          (SELECT id FROM results WHERE student_id=%s AND exam_id=e.id LIMIT 1) as attempt_id
        FROM exams e WHERE e.is_active=1 ORDER BY e.created_at DESC
    """, (current_user.id,))
    raw_exams = cur.fetchall()
    exams_list = []
    for e in raw_exams:
        e = dict(e); e["attempted"] = bool(e.get("attempt_id")); exams_list.append(e)
    conn.close()
    return render_template("student/exams.html", exams=exams_list)


@student_bp.route("/exam/<int:exam_id>", methods=["GET", "POST"])
@login_required
def exam(exam_id):
    if is_blocked(): return render_template("student/blocked.html")
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("SELECT * FROM exams WHERE id=%s AND is_active=1", (exam_id,))
    exam_obj = cur.fetchone()
    if not exam_obj: conn.close(); return redirect(url_for("student.exams"))
    cur.execute("SELECT id FROM results WHERE student_id=%s AND exam_id=%s", (current_user.id, exam_id))
    if cur.fetchone(): conn.close(); return redirect(url_for("student.result", exam_id=exam_id))
    if request.method == "POST":
        question_ids = session.get(f"exam_questions_{exam_id}", [])
        if not question_ids: conn.close(); return redirect(url_for("student.dashboard"))
        fmt = ",".join(["%s"] * len(question_ids))
        cur.execute(f"SELECT * FROM questions WHERE id IN ({fmt})", tuple(question_ids))
        questions = cur.fetchall()
        correct_count = wrong_count = skipped_count = score = 0
        detail_rows = []
        for q in questions:
            selected = request.form.get(str(q["id"]))
            if not selected:
                skipped_count += 1; detail_rows.append((q["id"], None, 0))
            elif selected == q["correct_option"]:
                correct_count += 1; score += q.get("marks", 1); detail_rows.append((q["id"], selected, 1))
            else:
                wrong_count += 1; detail_rows.append((q["id"], selected, 0))
        tab_switches = int(request.form.get("tab_switches", 0))
        cur.execute(
            "INSERT INTO results (student_id,exam_id,score,total_questions,correct_count,wrong_count,skipped_count,tab_switches) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (current_user.id, exam_id, score, len(questions), correct_count, wrong_count, skipped_count, tab_switches)
        )
        result_id = cur.lastrowid
        for q_id, sel, is_correct in detail_rows:
            cur.execute("INSERT INTO result_details (result_id,question_id,selected_option,is_correct) VALUES (%s,%s,%s,%s)", (result_id, q_id, sel, is_correct))
        conn.commit(); conn.close()
        session.pop(f"exam_questions_{exam_id}", None)
        return redirect(url_for("student.result", exam_id=exam_id))
    cur.execute("SELECT * FROM questions WHERE exam_id=%s ORDER BY RAND()", (exam_id,))
    questions = cur.fetchall()
    session[f"exam_questions_{exam_id}"] = [q["id"] for q in questions]
    conn.close()
    return render_template("student/exam.html", exam=exam_obj, questions=questions)


@student_bp.route("/exam/<int:exam_id>/preview")
@login_required
def exam_preview(exam_id):
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("SELECT * FROM exams WHERE id=%s AND is_active=1", (exam_id,))
    exam_obj = cur.fetchone()
    if not exam_obj: conn.close(); return redirect(url_for("student.exams"))
    cur.execute("SELECT * FROM questions WHERE exam_id=%s", (exam_id,))
    questions = cur.fetchall()
    cur.execute("SELECT id FROM results WHERE student_id=%s AND exam_id=%s", (current_user.id, exam_id))
    attempted = cur.fetchone() is not None
    conn.close()
    return render_template("student/exam_preview.html", exam=exam_obj, questions=questions, attempted=attempted)


@student_bp.route("/result/<int:exam_id>")
@login_required
def result(exam_id):
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("SELECT * FROM exams WHERE id=%s", (exam_id,))
    exam_obj = cur.fetchone()
    cur.execute("SELECT * FROM results WHERE student_id=%s AND exam_id=%s ORDER BY id DESC LIMIT 1", (current_user.id, exam_id))
    result_obj = cur.fetchone()
    details = []
    if result_obj:
        cur.execute("""
            SELECT rd.*, q.question, q.option_a, q.option_b, q.option_c, q.option_d, q.correct_option
            FROM result_details rd JOIN questions q ON rd.question_id=q.id WHERE rd.result_id=%s
        """, (result_obj["id"],))
        details = cur.fetchall()
    conn.close()
    return render_template("student/result.html", exam=exam_obj, result=result_obj, details=details)


@student_bp.route("/results")
@login_required
def results():
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("""
        SELECT r.*, e.title, e.total_marks FROM results r
        JOIN exams e ON r.exam_id=e.id WHERE r.student_id=%s ORDER BY r.submitted_at DESC
    """, (current_user.id,))
    all_results = cur.fetchall()
    conn.close()
    return render_template("student/results_list.html", results=all_results)


# ─── PRACTICE EXAMS (student side) ───────────────────────────────────────────
@student_bp.route("/practice")
@login_required
def practice():
    if is_blocked(): return render_template("student/blocked.html")
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("""
        SELECT pe.*, sg.name as group_name,
          (SELECT COUNT(*) FROM practice_questions WHERE exam_id=pe.id) as question_count,
          (SELECT id FROM practice_results WHERE student_id=%s AND exam_id=pe.id LIMIT 1) as attempt_id
        FROM practice_exams pe
        JOIN group_members gm ON gm.group_id=pe.group_id
        JOIN student_groups sg ON sg.id=pe.group_id
        WHERE gm.student_id=%s AND pe.is_active=1 ORDER BY pe.created_at DESC
    """, (current_user.id, current_user.id))
    raw = cur.fetchall()
    exams_list = []
    for e in raw:
        e = dict(e); e["attempted"] = bool(e.get("attempt_id")); exams_list.append(e)
    conn.close()
    return render_template("student/practice.html", exams=exams_list)


@student_bp.route("/practice/<int:exam_id>", methods=["GET", "POST"])
@login_required
def practice_exam(exam_id):
    if is_blocked(): return render_template("student/blocked.html")
    conn = get_db_connection()
    cur  = conn.cursor()
    # Verify student is in the group
    cur.execute("""
        SELECT pe.* FROM practice_exams pe
        JOIN group_members gm ON gm.group_id=pe.group_id
        WHERE pe.id=%s AND gm.student_id=%s AND pe.is_active=1
    """, (exam_id, current_user.id))
    exam_obj = cur.fetchone()
    if not exam_obj: conn.close(); return redirect(url_for("student.practice"))
    cur.execute("SELECT id FROM practice_results WHERE student_id=%s AND exam_id=%s", (current_user.id, exam_id))
    if cur.fetchone(): conn.close(); return redirect(url_for("student.practice_result", exam_id=exam_id))

    if request.method == "POST":
        question_ids = session.get(f"practice_questions_{exam_id}", [])
        if not question_ids: conn.close(); return redirect(url_for("student.practice"))
        fmt = ",".join(["%s"] * len(question_ids))
        cur.execute(f"SELECT * FROM practice_questions WHERE id IN ({fmt})", tuple(question_ids))
        questions = cur.fetchall()
        correct_count = wrong_count = skipped_count = score = 0
        detail_rows = []
        for q in questions:
            selected = request.form.get(str(q["id"]))
            if not selected:
                skipped_count += 1; detail_rows.append((q["id"], None, 0))
            elif selected == q["correct_option"]:
                correct_count += 1; score += q.get("marks", 1); detail_rows.append((q["id"], selected, 1))
            else:
                wrong_count += 1; detail_rows.append((q["id"], selected, 0))
        cur.execute(
            "INSERT INTO practice_results (student_id,exam_id,score,total_questions,correct_count,wrong_count,skipped_count) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (current_user.id, exam_id, score, len(questions), correct_count, wrong_count, skipped_count)
        )
        result_id = cur.lastrowid
        for q_id, sel, is_correct in detail_rows:
            cur.execute("INSERT INTO practice_result_details (result_id,question_id,selected_option,is_correct) VALUES (%s,%s,%s,%s)", (result_id, q_id, sel, is_correct))
        conn.commit(); conn.close()
        session.pop(f"practice_questions_{exam_id}", None)
        return redirect(url_for("student.practice_result", exam_id=exam_id))

    cur.execute("SELECT * FROM practice_questions WHERE exam_id=%s ORDER BY RAND()", (exam_id,))
    questions = cur.fetchall()
    session[f"practice_questions_{exam_id}"] = [q["id"] for q in questions]
    conn.close()
    return render_template("student/practice_exam.html", exam=exam_obj, questions=questions)


@student_bp.route("/practice/<int:exam_id>/result")
@login_required
def practice_result(exam_id):
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("SELECT pe.*, sg.name as group_name FROM practice_exams pe JOIN student_groups sg ON pe.group_id=sg.id WHERE pe.id=%s", (exam_id,))
    exam_obj = cur.fetchone()
    cur.execute("SELECT * FROM practice_results WHERE student_id=%s AND exam_id=%s ORDER BY id DESC LIMIT 1", (current_user.id, exam_id))
    result_obj = cur.fetchone()
    details = []
    if result_obj:
        cur.execute("""
            SELECT prd.*, pq.question, pq.option_a, pq.option_b, pq.option_c, pq.option_d, pq.correct_option
            FROM practice_result_details prd JOIN practice_questions pq ON prd.question_id=pq.id
            WHERE prd.result_id=%s
        """, (result_obj["id"],))
        details = cur.fetchall()
    conn.close()
    return render_template("student/practice_result.html", exam=exam_obj, result=result_obj, details=details)


# ─── TEXT EXAMS (student side) ────────────────────────────────────────────────
@student_bp.route("/text-exams")
@login_required
def text_exams():
    if is_blocked(): return render_template("student/blocked.html")
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("""
        SELECT te.*,
          (SELECT COUNT(*) FROM text_questions WHERE exam_id=te.id) as question_count,
          (SELECT id FROM text_submissions WHERE student_id=%s AND exam_id=te.id LIMIT 1) as submission_id
        FROM text_exams te WHERE te.is_active=1 ORDER BY te.created_at DESC
    """, (current_user.id,))
    raw = cur.fetchall()
    exams_list = []
    for e in raw:
        e = dict(e); e["attempted"] = bool(e.get("submission_id")); exams_list.append(e)
    conn.close()
    return render_template("student/text_exams.html", exams=exams_list)


@student_bp.route("/text-exam/<int:exam_id>", methods=["GET", "POST"])
@login_required
def text_exam(exam_id):
    if is_blocked(): return render_template("student/blocked.html")
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("SELECT * FROM text_exams WHERE id=%s AND is_active=1", (exam_id,))
    exam_obj = cur.fetchone()
    if not exam_obj: conn.close(); return redirect(url_for("student.text_exams"))
    cur.execute("SELECT id FROM text_submissions WHERE student_id=%s AND exam_id=%s", (current_user.id, exam_id))
    if cur.fetchone(): conn.close(); return redirect(url_for("student.text_result", exam_id=exam_id))
    cur.execute("SELECT * FROM text_questions WHERE exam_id=%s ORDER BY id", (exam_id,))
    questions = cur.fetchall()
    if request.method == "POST":
        cur.execute(
            "INSERT INTO text_submissions (student_id, exam_id) VALUES (%s,%s)",
            (current_user.id, exam_id)
        )
        sub_id = cur.lastrowid
        for q in questions:
            answer_text = request.form.get(f"answer_{q['id']}", "").strip()
            cur.execute(
                "INSERT INTO text_answers (submission_id, question_id, answer_text) VALUES (%s,%s,%s)",
                (sub_id, q["id"], answer_text)
            )
        conn.commit(); conn.close()
        return redirect(url_for("student.text_result", exam_id=exam_id))
    conn.close()
    return render_template("student/text_exam.html", exam=exam_obj, questions=questions)


@student_bp.route("/text-exam/<int:exam_id>/result")
@login_required
def text_result(exam_id):
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("SELECT * FROM text_exams WHERE id=%s", (exam_id,))
    exam_obj = cur.fetchone()
    cur.execute("SELECT * FROM text_submissions WHERE student_id=%s AND exam_id=%s ORDER BY id DESC LIMIT 1", (current_user.id, exam_id))
    submission = cur.fetchone()
    details = []
    if submission:
        cur.execute("""
            SELECT ta.*, tq.question, tq.marks as max_marks, tq.model_answer
            FROM text_answers ta JOIN text_questions tq ON ta.question_id=tq.id
            WHERE ta.submission_id=%s ORDER BY tq.id
        """, (submission["id"],))
        details = cur.fetchall()
    conn.close()
    # Check if result is published (admin control)
    result_visible = exam_obj and exam_obj["result_published"] == 1 and submission and submission["is_evaluated"]
    return render_template("student/text_result.html",
        exam=exam_obj, submission=submission, details=details,
        result_visible=result_visible)
