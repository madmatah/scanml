# ScanMyLib OCR sandbox image.
#
# The image is deliberately tiny: a Python interpreter, a C compiler (Triton,
# used by vLLM, compiles small launchers at runtime) and a few shared libs.
# The heavy, untrusted dependencies (PaddlePaddle, PaddleOCR, vLLM) and the
# model weights are NOT baked in: the one-shot `ocr-setup` service installs
# them into SANDBOX_DIR, which the `ocr` service then mounts read-only while
# running without any network interface (see compose.yaml).
#
# Two images share the base: `setup`, which `ocr-setup` runs, holds uv and the
# installer; `runtime`, which `ocr` runs, holds neither, so that what the
# sandbox runs carries no tool that only the installation needs.
FROM python:3.12-slim-trixie AS base

ARG UID=1000
ARG GID=1000

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      gcc libc6-dev libgomp1 libgl1 libglib2.0-0t64 \
 && rm -rf /var/lib/apt/lists/*

RUN groupadd -g "${GID}" ocr \
 && useradd -u "${UID}" -g "${GID}" -m -d /home/ocr -s /usr/sbin/nologin ocr \
 && mkdir -p /opt/sandbox /run/scanmylib /var/cache/ocr \
 && chown "${UID}:${GID}" /opt/sandbox /run/scanmylib /var/cache/ocr

ENV PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

FROM base AS setup

ARG UID=1000
ARG GID=1000

# uv installs the environments, so pip is not needed once it has installed uv.
RUN pip install --no-cache-dir uv==0.13.4 \
 && python3 -m pip uninstall --yes pip \
 && rm /usr/local/lib/python3.12/ensurepip/_bundled/pip-*.whl

COPY setup /app/setup

USER ${UID}:${GID}
CMD ["bash", "/app/setup/install.sh"]

FROM base AS runtime

ARG UID=1000
ARG GID=1000

# Nothing in the sandbox runs pip: left in, it would only add its advisories to
# the vulnerability scan, which reads this image, and so would the wheel of pip
# that ensurepip keeps to install it again.
RUN python3 -m pip uninstall --yes pip \
 && rm /usr/local/lib/python3.12/ensurepip/_bundled/pip-*.whl

COPY scanmylib_ocr /app/scanmylib_ocr

USER ${UID}:${GID}
CMD ["python3", "-m", "scanmylib_ocr.supervisor"]
