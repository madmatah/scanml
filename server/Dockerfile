# ScanMyLib API image.
#
# Stages:
#   deps         virtualenv with the pinned runtime dependencies (hash-checked)
#   test         deps + pytest + the test suite:  docker build --target test ...
#   web-tools    Node and pnpm, which build the web UI
#   web-build    the web UI, type-checked and built into /out
#   api-sources  the api's Python package, without the web UI's sources
#   project      the repository's VERSION file (see below)
#   runtime      the production image (default, last stage): non-root, no build
#                tools, no pip and no Node, runs with a read-only root
#                filesystem and a tmpfs /tmp.
#
# Wheels only: building a package from its source would fetch its build
# dependencies without checking their hashes.
FROM python:3.12-slim-trixie AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH=/opt/venv/bin:$PATH
# The former time-zone names, such as US/Eastern, which SCANMYLIB_TZ may hold:
# without them, the C library falls back to UTC without a word.
RUN apt-get update \
 && apt-get install -y --no-install-recommends tzdata-legacy \
 && rm -rf /var/lib/apt/lists/*


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


# Node and pnpm, pinned as in scripts/lint/Dockerfile.web, the image of the
# gate's web tools (scripts/tests/test_web_toolchain_pins.py holds the two
# together): Node by digest, pnpm's standalone build by its SHA-256. No stage
# that holds them reaches the runtime image.
FROM node:26-trixie-slim@sha256:e6bedef217677b276c591795e169840edd9096dbf13f29df8ef8d1856b8820bc AS web-tools
ADD --checksum=sha256:2c58959fd5df5cb9f4e72784c08a60ffc7ee558fed9b04b22254e29112203a51 \
    https://github.com/pnpm/pnpm/releases/download/v12.17.0/pnpm-linux-x64.tar.gz /tmp/pnpm.tar.gz
RUN mkdir /opt/pnpm \
 && tar -xzf /tmp/pnpm.tar.gz -C /opt/pnpm --no-same-owner \
 && rm /tmp/pnpm.tar.gz \
 && ln -s /opt/pnpm/pnpm /usr/local/bin/pnpm


# The packages install from the frozen lockfile, under the guards of
# pnpm-workspace.yaml: no package's install script runs, so no package's code
# runs while the network is on. The type check and the build then run without
# it.
FROM web-tools AS web-build
WORKDIR /web
COPY scanmylib/web/package.json scanmylib/web/pnpm-lock.yaml scanmylib/web/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile --store-dir /tmp/pnpm-store \
 && rm -rf /tmp/pnpm-store /root/.cache /root/.local
COPY scanmylib/web ./
RUN --network=none node_modules/.bin/tsc --noEmit --project tsconfig.json \
 && node build.ts --outdir /out


# A stage of its own, since the built-in Dockerfile frontend has no
# COPY --exclude, and a .dockerignore entry would hide the sources from
# web-build too.
FROM base AS api-sources
COPY scanmylib /app/scanmylib
RUN rm -r /app/scanmylib/web


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
# Nothing runs pip once the packages are in: left in, it would only add its
# advisories to the vulnerability scan, and so would the wheel of pip that
# ensurepip keeps to install it again.
RUN python -m pip uninstall --yes pip \
 && /usr/local/bin/python3 -m pip uninstall --yes pip \
 && rm /usr/local/lib/python3.12/ensurepip/_bundled/pip-*.whl
COPY --from=api-sources /app/scanmylib /app/scanmylib
# Only the built files of the web UI: its entry page and static/.
COPY --from=web-build /out /app/scanmylib/web
RUN python -m compileall -q /app/scanmylib
COPY --from=project /VERSION /app/VERSION
ARG DEV_VERSION=
RUN if [ -n "$DEV_VERSION" ]; then printf '%s\n' "$DEV_VERSION" > /app/VERSION; fi
WORKDIR /app
USER ${UID}:${GID}
EXPOSE 8765
CMD ["python", "-m", "scanmylib"]
