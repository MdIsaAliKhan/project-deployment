from app import create_app

# `app` must be at module level so gunicorn can find it via "run:app"
app = create_app()

if __name__ == "__main__":
    # Local development only — Docker/K8s use gunicorn instead
    app.run(debug=False, host="127.0.0.1", port=5000)
