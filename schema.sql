-- =========================================================
--  University LMS — Database Schema (Upgraded)
-- =========================================================

CREATE DATABASE IF NOT EXISTS online_exam CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE online_exam;

CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(120) NOT NULL,
    email VARCHAR(120) NOT NULL UNIQUE, password VARCHAR(255) NOT NULL,
    role ENUM('admin','teacher','student') NOT NULL DEFAULT 'student',
    face_descriptor LONGTEXT DEFAULT NULL, is_blocked TINYINT(1) NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;
-- Admin default password is 'admin123' (hashed with werkzeug scrypt)
INSERT IGNORE INTO users (name, email, password, role) VALUES ('Admin', 'admin@exam.com',
  'scrypt:32768:8:1$M1D70DPuCOkg0c8j$3268b47e721aad394d02950870cf1c8699fb398907b7488567407d54bc015d240d572a649bf22295755c81c8f9a6f1e7364a03d7079cd8e71cd309cd6c0e1b8e',
  'admin');

CREATE TABLE IF NOT EXISTS settings (
    id INT AUTO_INCREMENT PRIMARY KEY, setting_key VARCHAR(80) NOT NULL UNIQUE,
    setting_value VARCHAR(255) NOT NULL DEFAULT ''
) ENGINE=InnoDB;
INSERT IGNORE INTO settings (setting_key, setting_value) VALUES ('face_auth_enabled', '1');

CREATE TABLE IF NOT EXISTS exams (
    id INT AUTO_INCREMENT PRIMARY KEY, title VARCHAR(200) NOT NULL, description TEXT,
    teacher_id INT NOT NULL, duration_minutes INT NOT NULL DEFAULT 30,
    total_marks INT NOT NULL DEFAULT 0, is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (teacher_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS questions (
    id INT AUTO_INCREMENT PRIMARY KEY, exam_id INT NOT NULL, question TEXT NOT NULL,
    option_a VARCHAR(500) NOT NULL, option_b VARCHAR(500) NOT NULL,
    option_c VARCHAR(500) NOT NULL, option_d VARCHAR(500) NOT NULL,
    correct_option CHAR(1) NOT NULL, marks INT NOT NULL DEFAULT 1,
    FOREIGN KEY (exam_id) REFERENCES exams(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS results (
    id INT AUTO_INCREMENT PRIMARY KEY, student_id INT NOT NULL, exam_id INT NOT NULL,
    score INT NOT NULL DEFAULT 0, total_questions INT NOT NULL DEFAULT 0,
    correct_count INT NOT NULL DEFAULT 0, wrong_count INT NOT NULL DEFAULT 0,
    skipped_count INT NOT NULL DEFAULT 0, tab_switches INT NOT NULL DEFAULT 0,
    answers JSON DEFAULT NULL, submitted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (exam_id) REFERENCES exams(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS result_details (
    id INT AUTO_INCREMENT PRIMARY KEY, result_id INT NOT NULL, question_id INT NOT NULL,
    selected_option CHAR(1) DEFAULT NULL, is_correct TINYINT(1) NOT NULL DEFAULT 0,
    FOREIGN KEY (result_id) REFERENCES results(id) ON DELETE CASCADE,
    FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- TEXT / DESCRIPTIVE EXAMS
CREATE TABLE IF NOT EXISTS text_exams (
    id INT AUTO_INCREMENT PRIMARY KEY, title VARCHAR(200) NOT NULL, description TEXT,
    teacher_id INT NOT NULL, duration_minutes INT NOT NULL DEFAULT 60,
    total_marks INT NOT NULL DEFAULT 0, is_active TINYINT(1) NOT NULL DEFAULT 1,
    result_published TINYINT(1) NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (teacher_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS text_questions (
    id INT AUTO_INCREMENT PRIMARY KEY, exam_id INT NOT NULL, question TEXT NOT NULL,
    marks INT NOT NULL DEFAULT 5, model_answer TEXT DEFAULT NULL, key_points TEXT DEFAULT NULL,
    FOREIGN KEY (exam_id) REFERENCES text_exams(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS text_submissions (
    id INT AUTO_INCREMENT PRIMARY KEY, student_id INT NOT NULL, exam_id INT NOT NULL,
    submitted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    total_score INT DEFAULT NULL, is_evaluated TINYINT(1) NOT NULL DEFAULT 0,
    FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (exam_id) REFERENCES text_exams(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS text_answers (
    id INT AUTO_INCREMENT PRIMARY KEY, submission_id INT NOT NULL, question_id INT NOT NULL,
    answer_text LONGTEXT NOT NULL, awarded_marks INT DEFAULT NULL, teacher_comment TEXT DEFAULT NULL,
    FOREIGN KEY (submission_id) REFERENCES text_submissions(id) ON DELETE CASCADE,
    FOREIGN KEY (question_id) REFERENCES text_questions(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- GROUP PRACTICE SYSTEM
CREATE TABLE IF NOT EXISTS student_groups (
    id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(150) NOT NULL, description TEXT,
    teacher_id INT NOT NULL, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (teacher_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS group_members (
    id INT AUTO_INCREMENT PRIMARY KEY, group_id INT NOT NULL, student_id INT NOT NULL,
    UNIQUE KEY uq_group_student (group_id, student_id),
    FOREIGN KEY (group_id) REFERENCES student_groups(id) ON DELETE CASCADE,
    FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS practice_exams (
    id INT AUTO_INCREMENT PRIMARY KEY, title VARCHAR(200) NOT NULL, description TEXT,
    teacher_id INT NOT NULL, group_id INT NOT NULL,
    duration_minutes INT NOT NULL DEFAULT 30, total_marks INT NOT NULL DEFAULT 0,
    is_active TINYINT(1) NOT NULL DEFAULT 1, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (teacher_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (group_id) REFERENCES student_groups(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS practice_questions (
    id INT AUTO_INCREMENT PRIMARY KEY, exam_id INT NOT NULL, question TEXT NOT NULL,
    option_a VARCHAR(500) NOT NULL, option_b VARCHAR(500) NOT NULL,
    option_c VARCHAR(500) NOT NULL, option_d VARCHAR(500) NOT NULL,
    correct_option CHAR(1) NOT NULL, marks INT NOT NULL DEFAULT 1,
    FOREIGN KEY (exam_id) REFERENCES practice_exams(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS practice_results (
    id INT AUTO_INCREMENT PRIMARY KEY, student_id INT NOT NULL, exam_id INT NOT NULL,
    score INT NOT NULL DEFAULT 0, total_questions INT NOT NULL DEFAULT 0,
    correct_count INT NOT NULL DEFAULT 0, wrong_count INT NOT NULL DEFAULT 0,
    skipped_count INT NOT NULL DEFAULT 0, submitted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (exam_id) REFERENCES practice_exams(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS practice_result_details (
    id INT AUTO_INCREMENT PRIMARY KEY, result_id INT NOT NULL, question_id INT NOT NULL,
    selected_option CHAR(1) DEFAULT NULL, is_correct TINYINT(1) NOT NULL DEFAULT 0,
    FOREIGN KEY (result_id) REFERENCES practice_results(id) ON DELETE CASCADE,
    FOREIGN KEY (question_id) REFERENCES practice_questions(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- =========================================================
--  Performance Indexes (added to fix slow queries)
-- =========================================================

-- results table - most queried by student_id and exam_id
ALTER TABLE results ADD INDEX IF NOT EXISTS idx_results_student (student_id);
ALTER TABLE results ADD INDEX IF NOT EXISTS idx_results_exam    (exam_id);

-- text_submissions - queried heavily by teacher and admin
ALTER TABLE text_submissions ADD INDEX IF NOT EXISTS idx_textsub_student (student_id);
ALTER TABLE text_submissions ADD INDEX IF NOT EXISTS idx_textsub_exam    (exam_id);
ALTER TABLE text_submissions ADD INDEX IF NOT EXISTS idx_textsub_evaluated (is_evaluated);

-- practice_results - queried per group analytics
ALTER TABLE practice_results ADD INDEX IF NOT EXISTS idx_pracresult_student (student_id);
ALTER TABLE practice_results ADD INDEX IF NOT EXISTS idx_pracresult_exam    (exam_id);

-- group_members - queried on every student page load
ALTER TABLE group_members ADD INDEX IF NOT EXISTS idx_groupmember_student (student_id);

-- questions and practice_questions - queried per exam
ALTER TABLE questions          ADD INDEX IF NOT EXISTS idx_questions_exam (exam_id);
ALTER TABLE practice_questions ADD INDEX IF NOT EXISTS idx_pracq_exam     (exam_id);
ALTER TABLE text_questions     ADD INDEX IF NOT EXISTS idx_textq_exam     (exam_id);
