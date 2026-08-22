# ---------------------------------------------------------------------------
# AetherLab backend image
#
# Multi-stage: wheels are built in the builder stage and installed into a slim
# runtime stage, keeping the final image small and free of build tools.
# The same image serves the API, the Celery worker, Celery Beat and Flower --
# only the command differs (see docker-compose.yml).
# ---------------------------------------------------------------------------

FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Compiler + PostgreSQL headers for any source-only wheels.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Normalise the Windows-authored lockfile (UTF-16 -> UTF-8) and drop
# Windows-only packages, mirroring what CI does on Linux runners.
RUN python - <<'PY'
import pathlib

raw = pathlib.Path("requirements.txt").read_bytes()
text = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-8")
skip = ("win32_setctime", "colorama", "pywin32")
lines = [l for l in text.splitlines() if l.strip() and not l.lower().startswith(skip)]
pathlib.Path("requirements.linux.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

RUN pip wheel --wheel-dir /wheels -r requirements.linux.txt


# ------------------------------- runtime -----------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# libpq5 = psycopg runtime library; curl = container HEALTHCHECK.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash appuser

COPY --from=builder /wheels /wheels
COPY requirements.txt .

RUN python - <<'PY'
import pathlib

raw = pathlib.Path("requirements.txt").read_bytes()
text = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-8")
skip = ("win32_setctime", "colorama", "pywin32")
lines = [l for l in text.splitlines() if l.strip() and not l.lower().startswith(skip)]
pathlib.Path("requirements.linux.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

RUN pip install --no-cache-dir --find-links=/wheels -r requirements.linux.txt \
    && rm -rf /wheels

# Application code + Alembic migrations ship with the image.
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/v1/health/health || exit 1

# Default command: API server. worker / beat / flower override this in compose.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
