# ThinkCode OJ -- production image
#
# Single image used for all 4 application processes (site/bridged/celery/
# wsevent); which one runs is selected at `docker run` time via the command
# (see docker-compose.production.yml / deploy.sh). This mirrors what
# thinkcode-docker (vnoj-docker fork) does with separate per-service
# Dockerfiles, but collapsed into one image to keep the CI build simple and
# the image cache shared across all 4 services.
#
# Build context: repo root. Built by GitHub Actions (.github/workflows/deploy.yml),
# NOT on the production server (2 vCPU / 2GB RAM is too small to build
# comfortably alongside the live site).

FROM python:3.11-slim-bookworm AS base

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git gcc g++ make curl gettext \
        libxml2-dev libxslt1-dev zlib1g-dev \
        default-libmysqlclient-dev pkg-config \
        libjpeg-dev libssl-dev && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /site

# ---- Python deps (cached separately from source so `pip install` only
#      re-runs when requirements actually change) ----
COPY requirements.txt additional_requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt -r additional_requirements.txt && \
    pip3 install --no-cache-dir django-environ gunicorn

# ---- Node deps (needed for make_style.sh + websocket/daemon.js) ----
COPY package.json package-lock.json ./
RUN npm ci

# ---- Application source ----
COPY . .

# Static assets (style.css, collectstatic) are built at image build time so
# STATIC_ROOT is baked into the image and doesn't need `manage.py
# collectstatic` to run against a live DB during deploy. `.ci.settings.py`
# (already shipped in the repo, used by build.yml's CI job) needs no real
# secrets -- it defaults to the sqlite3 DB from dmoj/settings.py, which is
# enough for collectstatic/compilemessages/compilejsi18n. At runtime the
# real dmoj/local_settings.py (baked in via `.dockerignore` NOT excluding it
# -- see docker-compose.production.yml env vars) takes over instead.
RUN cp .ci.settings.py dmoj/local_settings.py && \
    ./make_style.sh && \
    python3 manage.py collectstatic --noinput && \
    python3 manage.py compilemessages && \
    python3 manage.py compilejsi18n && \
    rm dmoj/local_settings.py

# websocket/config.js is gitignored (generated per-server in the native
# deployment) -- bake the checked-in Docker template in its place. These
# are internal container ports, not secrets, so they're fine to fix at
# build time rather than reading from the environment like
# dmoj/local_settings.py does.
COPY websocket/config.docker.js websocket/config.js

RUN useradd --create-home --shell /bin/bash dmoj && \
    chown -R dmoj:dmoj /site
USER dmoj

EXPOSE 8000 9998 9999 15100 15101 15102

# No default ENTRYPOINT/CMD -- each service overrides `command:` in
# docker-compose.production.yml (site/bridged/celery/wsevent all share this
# image, they just run different management commands).
