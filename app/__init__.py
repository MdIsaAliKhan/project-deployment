import os
import ssl
from flask import Flask
from flask_login import LoginManager

login_manager = LoginManager()


def create_app():
    app = Flask(__name__)

    # ── Config from environment variables ─────────────────────────────────────
    # Locally: set in .env file
    # Docker:  set via --env-file .env
    # EKS:     injected from ConfigMap + Secret
    app.config["SECRET_KEY"]     = os.environ.get("SECRET_KEY",     "change-me-in-production")
    app.config["MYSQL_HOST"]     = os.environ.get("MYSQL_HOST",     "localhost")
    app.config["MYSQL_USER"]     = os.environ.get("MYSQL_USER",     "root")
    app.config["MYSQL_PASSWORD"] = os.environ.get("MYSQL_PASSWORD", "@isa-1045")
    app.config["MYSQL_DB"]       = os.environ.get("MYSQL_DB",       "online_exam")

    # SSL is ON when connecting to RDS (RDS enforces it via parameter group)
    # Set MYSQL_SSL=false only for local development without SSL
    app.config["MYSQL_SSL"] = os.environ.get("MYSQL_SSL", "false").lower() == "true"

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
    """
    Returns a PyMySQL connection.

    - Locally (MYSQL_SSL=false): plain connection to localhost MySQL.
    - On EKS with RDS (MYSQL_SSL=true): SSL connection using the AWS
      RDS CA certificate bundle.

    RDS enforces SSL via the parameter group (require_secure_transport=ON),
    so any connection attempt without SSL will be rejected by RDS.
    """
    import pymysql
    from flask import current_app

    host     = current_app.config["MYSQL_HOST"]
    user     = current_app.config["MYSQL_USER"]
    password = current_app.config["MYSQL_PASSWORD"]
    database = current_app.config["MYSQL_DB"]
    use_ssl  = current_app.config["MYSQL_SSL"]

    connect_kwargs = dict(
        host=host,
        user=user,
        password=password,
        database=database,
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=10,        # fail fast if RDS is unreachable
        read_timeout=30,
        write_timeout=30,
        autocommit=False,
    )

    if use_ssl:
        # AWS RDS CA bundle — baked into the Docker image via Dockerfile
        # Download from: https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem
        rds_ca = os.environ.get(
            "MYSQL_SSL_CA",
            "/app/certs/global-bundle.pem"
        )
        ssl_ctx = ssl.create_default_context(cafile=rds_ca)
        ssl_ctx.verify_mode = ssl.CERT_REQUIRED
        connect_kwargs["ssl"] = {"ssl": ssl_ctx}

    return pymysql.connect(**connect_kwargs)
