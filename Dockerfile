# ============================================================
# Dockerfile — LMS Flask App (Production with RDS SSL)
# ============================================================

# ── Stage 1: Build (compile face_recognition / dlib) ─────────────────────────
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake \
    libopenblas-dev liblapack-dev \
    libx11-dev libgtk-3-dev \
    libboost-python-dev libboost-thread-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ── Stage 2: Final slim runtime image ────────────────────────────────────────
FROM python:3.11-slim

# Runtime libraries needed by dlib / face_recognition / numpy
RUN apt-get update && apt-get install -y --no-install-recommends \
    libopenblas0 libgomp1 libglib2.0-0 \
    libsm6 libxrender1 libxext6 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed Python packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages \
                    /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin/gunicorn /usr/local/bin/gunicorn

# ── Download AWS RDS CA certificate bundle ────────────────────────────────────
# This is the CA used to verify the RDS SSL certificate.
# It's public and safe to bake into the image.
RUN mkdir -p /app/certs && \
    curl -sSL \
      https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem \
      -o /app/certs/global-bundle.pem && \
    echo "RDS CA downloaded: $(wc -c < /app/certs/global-bundle.pem) bytes"

# Copy application code
COPY . .

# Non-root user for security
RUN useradd -m -u 1000 lmsuser && \
    chown -R lmsuser:lmsuser /app

USER lmsuser

EXPOSE 5000

CMD ["gunicorn", \
     "--bind",           "0.0.0.0:5000", \
     "--workers",        "4", \
     "--threads",        "2", \
     "--timeout",        "120", \
     "--access-logfile", "-", \
     "--error-logfile",  "-", \
     "run:app"]
