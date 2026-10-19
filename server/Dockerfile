# ScanMyLib API image.
#
# Stages:
#   deps     virtualenv with the pinned runtime dependencies (hash-checked)
#   test     deps + pytest + the test suite:  docker build --target test ...
#   project  the repository's VERSION file (see below)
#   runtime  the production image (default, last stage): non-root, no build
#            tools, runs with a read-only root filesystem and a tmpfs /tmp.
#
# Wheels only: building a package from its source would fetch its build
# dependencies without checking their hashes.
FROM python:3.12-slim-bookworm AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH=/opt/venv/bin:$PATH


FROM base AS deps
COPY requirements.lock /tmp/requirements.lock
RUN python -m venv /opt/venv \
 && pip install --require-hashes --no-deps --only-binary :all: -r /tmp/requirements.lock \
 && rm /tmp/requirements.lock


FROM deps AS test
ARG UID=1000
ARG GID=1000
COPY requirements-test.lock /tmp/requirements-test.lock
RUN pip install --require-hashes --no-deps --only-binary :all: -r /tmp/requirements-test.lock \
 && rm /tmp/requirements-test.lock
WORKDIR /src
COPY pyproject.toml ./
COPY scanmylib ./scanmylib
COPY tests ./tests
ENV HOME=/tmp
USER ${UID}:${GID}
CMD ["python", "-m", "pytest"]


# The version the api reports is the repository's VERSION file, outside this
# build context: compose.yaml passes the repository root as the additional build
# context "project", which replaces this stage. A plain `docker build` of this
# directory falls back to this stage, and the api then reports "unknown". A
# development build reports the version that scripts/dev.sh derives from git
# instead (scripts/lib/version.py), given as the build argument DEV_VERSION.
FROM base AS project
RUN echo unknown > /VERSION


FROM base AS runtime
ARG UID=1000
ARG GID=1000
RUN groupadd --gid "${GID}" scanmylib \
 && useradd --uid "${UID}" --gid "${GID}" --no-create-home --home-dir /nonexistent \
      --shell /usr/sbin/nologin scanmylib \
 && mkdir -p /library /state /run/scanmylib /app-dist \
 && chown "${UID}:${GID}" /library /state /run/scanmylib
COPY --from=deps /opt/venv /opt/venv
COPY scanmylib /app/scanmylib
RUN python -m compileall -q /app/scanmylib
COPY --from=project /VERSION /app/VERSION
ARG DEV_VERSION=
RUN if [ -n "$DEV_VERSION" ]; then printf '%s\n' "$DEV_VERSION" > /app/VERSION; fi
WORKDIR /app
USER ${UID}:${GID}
EXPOSE 8765
CMD ["python", "-m", "scanmylib"]
