import os
from flask import Flask
from flask_login import LoginManager

login_manager = LoginManager()

def create_app():
    app = Flask(__name__)

    # Reads from environment variables — works locally AND in Kubernetes
    app.config["SECRET_KEY"]     = os.environ.get("SECRET_KEY",     "change-me-in-production")
    app.config["MYSQL_HOST"]     = os.environ.get("MYSQL_HOST",     "localhost")
    app.config["MYSQL_USER"]     = os.environ.get("MYSQL_USER",     "root")
    app.config["MYSQL_PASSWORD"] = os.environ.get("MYSQL_PASSWORD", "@isa-1045")
    app.config["MYSQL_DB"]       = os.environ.get("MYSQL_DB",       "online_exam")

    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    from .auth.routes    import auth_bp
    from .admin.routes   import admin_bp
    from .teacher.routes import teacher_bp
    from .student.routes import student_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp,   url_prefix="/admin")
    app.register_blueprint(teacher_bp, url_prefix="/teacher")
    app.register_blueprint(student_bp, url_prefix="/student")

    return app


def get_db_connection():
    import pymysql
    from flask import current_app
    return pymysql.connect(
        host=current_app.config["MYSQL_HOST"],
        user=current_app.config["MYSQL_USER"],
        password=current_app.config["MYSQL_PASSWORD"],
        database=current_app.config["MYSQL_DB"],
        cursorclass=pymysql.cursors.DictCursor
    )
