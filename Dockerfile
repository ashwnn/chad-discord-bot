FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

# Install build deps and dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip \
    && pip install -r /app/requirements.txt

# Application files
COPY src/ /app/src/
COPY templates/ /app/templates/
COPY static/ /app/static/

# Create data dir for SQLite
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8000

CMD ["bash"]
