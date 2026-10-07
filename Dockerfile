# Production Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for psycopg2 and other packages
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev libfribidi0 \
    curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Match Railway's PostgreSQL 17 server for portable pg_dump backups.
# Repository setup: https://www.postgresql.org/download/linux/debian/
RUN install -d /usr/share/postgresql-common/pgdg \
    && curl --fail --silent --show-error https://www.postgresql.org/media/keys/ACCC4CF8.asc -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
    && . /etc/os-release \
    && printf 'deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt %s-pgdg main\n' "$VERSION_CODENAME" > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update && apt-get install -y --no-install-recommends postgresql-client-17 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Source text requires native bidi/shaping, including Qur'anic diacritics.
RUN python -c "from PIL import features; assert features.check_feature('raqm'), 'Arabic text shaping (RAQM) is required'"

# Copy application code
COPY . .

# Create uploads directory
RUN mkdir -p uploads

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

# Expose port
EXPOSE 8000

# Schema changes are a separate reviewed maintenance operation.
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
