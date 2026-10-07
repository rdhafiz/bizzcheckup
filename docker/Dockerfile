# syntax=docker/dockerfile:1
# One image for both the web server and the Celery worker.
# Build:  docker build -f docker/Dockerfile -t bizzcheckup .

# --- Stage 1: build the CSS with the Tailwind standalone CLI ----------------
FROM debian:bookworm-slim AS css
ARG TAILWIND_VERSION=v4.3.3
ARG TARGETARCH
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*
RUN case "$TARGETARCH" in arm64) arch=arm64 ;; *) arch=x64 ;; esac \
    && curl -fsSL -o /usr/local/bin/tailwindcss \
       "https://github.com/tailwindlabs/tailwindcss/releases/download/${TAILWIND_VERSION}/tailwindcss-linux-${arch}" \
    && chmod +x /usr/local/bin/tailwindcss
WORKDIR /src
# Tailwind scans these folders for class names.
COPY frontend frontend
COPY templates templates
COPY bizzcheckup bizzcheckup
COPY static static
RUN tailwindcss -i frontend/tailwind.css -o static/css/app.css --minify

# --- Stage 2: the Python app -------------------------------------------------
FROM python:3.12-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Never run the app as root inside the container.
RUN useradd --create-home --uid 1000 app
WORKDIR /app

# Install libraries first: Docker caches this layer until requirements change.
COPY requirements/ requirements/
RUN pip install -r requirements/base.txt

COPY --chown=app:app . .
COPY --from=css --chown=app:app /src/static/css/app.css static/css/app.css

# Collect static files at build time. These values are only for this command.
RUN DJANGO_SECRET_KEY=build-only DATABASE_URL=sqlite:////tmp/build.db \
    python manage.py collectstatic --noinput --settings=config.settings.prod \
    && chown -R app:app staticfiles

USER app
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-"]
