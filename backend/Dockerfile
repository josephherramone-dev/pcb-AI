# Backend API and EDA worker image.
# Based on the official KiCad image so kicad-cli and KiCad's Python (pcbnew)
# are available to the isolated EDA subprocesses.
FROM kicad/kicad:9.0

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3-venv python3-pip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
# --system-site-packages keeps KiCad's pcbnew module importable for diagnostics.
RUN python3 -m venv --system-site-packages /opt/venv
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .
COPY alembic.ini ./
COPY alembic ./alembic

RUN mkdir -p /data/storage && chown -R kicad:kicad /data /app
USER kicad

ENV KICAD_EXEC_MODE=local \
    KICAD_CLI=kicad-cli \
    KICAD_PYTHON=/usr/bin/python3 \
    STORAGE_ROOT=/data/storage

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
